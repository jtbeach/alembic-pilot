"""Tests for the ManagedDatabase class.

These tests use live database interactions through psycopg_toolbox.testfixtures.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from psycopg import AsyncConnection
from psycopg.rows import TupleRow
from psycopg_toolbox import (
    AlreadyExistsError,
    autocommit,
    database_exists,
    drop_database,
    drop_schema,
)
from psycopg_toolbox.testfixtures import DBConfig
from sqlalchemy import URL
from sqlalchemy.orm import DeclarativeBase

from alembic_pilot import AlembicInitError, ManagedDatabase


@pytest.fixture
def declarative_base() -> type[DeclarativeBase]:
    """Create a declarative base for testing.

    This fixture creates a fresh DeclarativeBase class for each test,
    ensuring that model metadata is isolated between tests.
    """

    class TestBase(DeclarativeBase):
        """Base class for test models."""

        pass

    return TestBase


@pytest.fixture
async def db_url(
    db_config: DBConfig, psycopg_toolbox_empty_db: AsyncConnection[TupleRow]
) -> URL:
    """Create a database URL for testing."""
    db_name = f"managed_db_test-{db_config.dbname}"
    # Delete the database if it exists due to a crash in a previous test

    async with autocommit(psycopg_toolbox_empty_db):
        if await database_exists(psycopg_toolbox_empty_db, db_name):
            await drop_database(psycopg_toolbox_empty_db, db_name, ignore_missing=True)

    return URL.create(
        drivername="postgresql+psycopg",
        username=db_config.user,
        password=db_config.password,
        host=db_config.host,
        port=db_config.port,
        database=f"managed_db_test-{db_config.dbname}",
    )


@pytest.fixture
async def managed_db(
    tmp_path: Path,
    db_url: URL,
    declarative_base: type[DeclarativeBase],
    psycopg_toolbox_empty_db: AsyncConnection[TupleRow],
) -> AsyncGenerator[ManagedDatabase, None]:
    """Create a ManagedDatabase instance for testing."""
    yield ManagedDatabase(
        db_url=db_url.render_as_string(),
        declarative_base=declarative_base,
        models_module=None,
        app_schema_name="public",
        verbose=True,
        alembic_ini_path=tmp_path / "alembic.ini",
    )

    # Drop the database after the test if it was created
    async with autocommit(psycopg_toolbox_empty_db):
        assert db_url.database is not None
        await drop_database(
            psycopg_toolbox_empty_db, db_url.database, ignore_missing=True
        )


async def test_create_database(managed_db: ManagedDatabase) -> None:
    """Test database creation."""
    # First creation should succeed
    created = await managed_db.create_database(error_if_exists=True)
    assert created is True

    # Second creation should fail with error_if_exists=True
    with pytest.raises(AlreadyExistsError, match="Database .* already exists"):
        await managed_db.create_database(error_if_exists=True)

    # Second creation should return False with error_if_exists=False
    created = await managed_db.create_database(error_if_exists=False)
    assert created is False


async def test_create_app_schema(managed_db: ManagedDatabase) -> None:
    """Test application schema creation."""
    # Create database first
    await managed_db.create_database()

    # Since database creation also creates the app schema, we need to drop it
    async with await managed_db.connect() as conn:
        await drop_schema(conn, managed_db.app_schema_name)

    # Schema creation should succeed
    created = await managed_db.create_app_schema(error_if_exists=True)
    assert created is True

    # Second creation should fail with error_if_exists=True
    with pytest.raises(AlreadyExistsError, match="Schema .* already exists"):
        await managed_db.create_app_schema(error_if_exists=True)

    # Second creation should return False with error_if_exists=False
    created = await managed_db.create_app_schema(error_if_exists=False)
    assert created is False


async def test_init_alembic(managed_db: ManagedDatabase, tmp_path: Path) -> None:
    """Test Alembic initialization."""
    # Create database and schema first
    await managed_db.create_database()
    await managed_db.create_app_schema()

    # Initialize Alembic
    migrations_dir = tmp_path / "migrations"
    managed_db.init_alembic(migrations_dir=migrations_dir)

    # Verify files were created
    assert (migrations_dir / "env.py").exists()
    assert (migrations_dir / "script.py.mako").exists()
    assert (migrations_dir / "versions").exists()
    assert (migrations_dir / "versions").is_dir()

    # Second initialization should fail
    with pytest.raises(AlembicInitError, match="alembic.ini file already exists"):
        managed_db.init_alembic(migrations_dir=migrations_dir)


async def test_compare_schema_to_latest(
    managed_db: ManagedDatabase, tmp_path: Path
) -> None:
    """Test schema comparison."""
    await managed_db.create_database()
    await managed_db.create_app_schema()

    # Initialize Alembic
    migrations_dir = tmp_path / "migrations"
    managed_db.init_alembic(migrations_dir=migrations_dir)

    # We don't have any migrations yet, so the diff should be empty
    diffs = await managed_db.compare_schema_to_latest()
    assert len(diffs) == 0


async def test_upgrade_schema_to_latest(
    managed_db: ManagedDatabase,
    tmp_path: Path,
) -> None:
    """Test schema upgrade."""
    # Create database and schema first
    await managed_db.create_database()
    await managed_db.create_app_schema()

    # Initialize Alembic
    migrations_dir = tmp_path / "migrations"
    managed_db.init_alembic(migrations_dir=migrations_dir)

    # Upgrade schema
    await managed_db.upgrade_schema_to_latest()
