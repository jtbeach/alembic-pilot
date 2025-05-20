"""Database management and schema upgrade functionality for Alembic Pilot.

This module provides the ManagedDatabase class which handles database creation,
ownership verification, and schema management operations.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TypeAlias

from psycopg import AsyncConnection
from psycopg.rows import TupleRow
from psycopg.sql import SQL, Identifier
from psycopg_toolbox import (
    autocommit,
    create_database,
    create_schema,
    obtain_advisory_lock,
)
from sqlalchemy import URL
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import SchemaItem

from .alembic import (
    apply_migrations,
    compare_schema,
    copy_script_mako,
    create_versions_directory,
    generate_alembic_ini,
    generate_env_py,
)
from .db_connection import connect
from .exceptions import AlembicInitError, InvalidDatabaseURLError
from .sanity_checks import (
    verify_app_schema_ownership,
    verify_database_ownership,
)

# Type definitions for callables
DbUrlCallable: TypeAlias = Callable[[], URL]
IncludeObjectCallable: TypeAlias = Callable[
    [SchemaItem, str | None, str | None, bool, SchemaItem | None], bool
]


logger = logging.getLogger(__name__)


class ManagedDatabase:
    """Manages database creation, ownership verification, and schema migrations.

    This class provides a high-level interface for managing PostgreSQL databases,
    including creating new databases, verifying ownership permissions, and handling
    schema migrations through Alembic. It ensures proper database setup and maintains
    schema consistency across deployments.
    """

    def __init__(
        self,
        *,
        db_url: DbUrlCallable | str,
        declarative_base: type[DeclarativeBase] | None,
        models_module: ModuleType | None,
        mgmt_database: str = "postgres",
        app_schema_name: str = "public",
        include_object_callable: IncludeObjectCallable | None = None,
        verbose: bool = False,
        alembic_ini_path: Path | None = None,
    ):
        """
        Initialize a ManagedDatabase instance.

        Args:
            db_url: Either a function that returns the database URL or a string containing the database URL.
            declarative_base: SQLAlchemy declarative base class for autogenerate. If None, autogeneration will not work.
            models_module: Module containing all SQLAlchemy model imports. If None, autogeneration of revisions and comparison of schema will not work.
            mgmt_database: The name of the management database to connect to when creating a new database.
            app_schema_name: The name of the PostgreSQL schema to use for the application. The database owner is required to have ownership of the schema either directly or via a role grant.
            include_object_callable: Optional function to filter objects for autogenerate.
            verbose: Whether to print verbose output.
            alembic_ini_path: Path to the Alembic ini file. If not provided, assumes the file is in the current working directory. Default make sense, this is only useful for testing.
        """
        self._db_url = db_url
        self.declarative_base = declarative_base
        self.models_module = models_module
        self.mgmt_database = mgmt_database
        self.app_schema_name = app_schema_name
        self.include_object_callable = include_object_callable
        self.verbose = verbose
        self.lock_name = f"alembic-pilot-{self.db_url.database}"
        if alembic_ini_path is None:
            self.alembic_ini_path = Path.cwd() / "alembic.ini"
        else:
            self.alembic_ini_path = alembic_ini_path

    @property
    def db_url(self) -> URL:
        """Get the database URL.

        If the db_url is a string, it is assumed to be a database URL and is returned as is.
        If the db_url is a function, it is called to get the database URL.
        """
        if isinstance(self._db_url, str):
            return make_url(self._db_url)
        return self._db_url()

    def init_alembic(
        self,
        *,
        migrations_dir: Path,
    ) -> None:
        """Initialize Alembic configuration for database migrations.

        Creates and configures all necessary Alembic files:
        - alembic.ini
        - <migrations_dir>/env.py
        - <migrations_dir>/script.py.mako
        - <migrations_dir>/versions/

        This method provides a streamlined alternative to running `alembic init` and
        manually editing the configuration files. It automatically sets up the env.py
        file with your application's models and database URL.

        This should be called once after database creation (when create_database() returns True).

        Args:
            migrations_dir: Root directory for Alembic migrations.
        """
        if self.alembic_ini_path.exists():
            raise AlembicInitError(
                "alembic.ini file already exists. Please remove it before running this function."
            ) from None

        # Check that the migrations directory is a subdirectory of the alembic.ini file's parent directory
        try:
            migrations_dir.relative_to(self.alembic_ini_path.parent)
        except ValueError:
            raise AlembicInitError(
                "Migrations directory is not a subdirectory of the directory containing alembic.ini."
            ) from None

        # Allow both migrations dir and relative paths
        migrations_root = migrations_dir.resolve()

        if migrations_root.exists():
            raise AlembicInitError(
                "Alembic migrations directory already exists. Please remove it before running this function."
            ) from None

        # Create the alembic root directory
        migrations_root.mkdir(parents=True, exist_ok=False)

        # Create and configure all necessary files
        create_versions_directory(migrations_root)
        generate_alembic_ini(migrations_root, self.alembic_ini_path)
        generate_env_py(
            migrations_root=migrations_root,
            models_module=self.models_module,
            db_url_callable=self._db_url if not isinstance(self._db_url, str) else None,
            include_object_callable=self.include_object_callable,
            declarative_base=self.declarative_base,
            app_schema_name=self.app_schema_name,
        )
        copy_script_mako(migrations_root)
        logger.info("Alembic configuration files created successfully")

    async def create_database(
        self,
        error_if_exists: bool = True,
    ) -> bool:
        """
        Create a new database with the given name.

        Args:
            error_if_exists (bool, optional): If True, raise an error if the database already exists. If False, will just skip the database creation if it already exists.

        Returns:
            bool: True if the database was created, False if it already exists.
        """
        async with (
            await self.connect(self.mgmt_database) as mgmt_db_conn,
            autocommit(mgmt_db_conn),
            obtain_advisory_lock(mgmt_db_conn, self.lock_name),
        ):
            # Create the database
            db_url = self.db_url
            if db_url.database is None:
                raise InvalidDatabaseURLError(
                    "Database name is required in the database URL"
                )
            created_database = await create_database(
                mgmt_db_conn,
                db_url.database,
                ignore_exists=not error_if_exists,
            )

            if created_database:
                logger.info("Managed database created successfully")
            else:
                logger.info("Existing database found")

            # Creates the application schema if it missing.
            await self.create_app_schema()

            return created_database

    async def create_app_schema(
        self,
        error_if_exists: bool = False,
    ) -> bool:
        """
        Create the application schema if it missing.

        Args:
            error_if_exists (bool, optional): If True, raise an error if the schema already exists. If False, will just verify the schema ownership if it already exists.

        Returns:
            bool: True if the database was created, False if it already exists.
        """
        async with await self.connect() as conn:
            created_schema = await create_schema(
                conn,
                self.app_schema_name,
                owner=self.db_url.username,
                ignore_exists=not error_if_exists,
            )

            if created_schema:
                logger.info("Application schema created successfully")
            else:
                # verify that we are the owner of the schema (ie. that our role has been granted ownership of the schema)
                await verify_app_schema_ownership(conn, self.app_schema_name)
                logger.info("Application schema already exists and ownership is valid")

            # We set the search path to the app schema so that Alembic auto-generated
            # migrations work as expected. See https://alembic.sqlalchemy.org/en/latest/api/autogenerate.html#remote-schema-table-introspection-and-postgresql-search-path
            await conn.execute(
                SQL("ALTER DATABASE {} SET search_path TO {}").format(
                    Identifier(conn.info.dbname), Identifier(self.app_schema_name)
                )
            )
            return created_schema

    async def upgrade_schema_to_latest(self) -> None:
        """
        Apply database migrations (via Alembic) to bring the database up to the current state defined in code.

        This method will:
        1. Verify that the current user owns the database or has been granted the owner role
        2. Verify that the current user owns the app schema or has been granted the owner role
        3. Apply any pending migrations to bring the database up to date

        Raises:
            DatabaseOwnershipError: If the current user is not the owner of the database or has not been granted the owner role.
            AppSchemaOwnershipError: If the current user is not the owner of the app schema or has not been granted the owner role.
        """
        async with (
            await self.connect() as conn,
            obtain_advisory_lock(conn, self.lock_name),
        ):
            # Verify database ownership
            await verify_database_ownership(conn)

            # Verify app schema ownership
            await verify_app_schema_ownership(conn, self.app_schema_name)

            # Call alembic CLI to apply migrations. If we don't have a callable in our
            # alembic config, make sure we pass the db_url as an argument to the alembic CLI.
            apply_migrations(
                self.alembic_ini_path,
                self.db_url if isinstance(self._db_url, str) else None,
            )

            logger.info("Database schema upgraded to latest")

    async def compare_schema_to_latest(self) -> list[tuple | list]:
        """Compares the deployed database schema against the current state defined in code.

        This method connects to the database and compares its current schema against
        the SQLAlchemy models defined in your application. It returns a list of
        differences that would need to be applied to bring the database up to date.

        The returned differences follow Alembic's autogenerate format, which includes
        tuples and lists describing schema changes. See the Alembic documentation for
        details on the format: https://alembic.sqlalchemy.org/en/latest/api/autogenerate.html#getting-diffs

        Returns:
            A list of schema differences that would need to be applied.
        """
        if self.declarative_base is None:
            raise ValueError(
                "Declarative base is not set. Schema comparison will not work."
            )

        async with (
            await self.connect() as conn,
            obtain_advisory_lock(conn, self.lock_name),
        ):
            diffs = compare_schema(
                self.db_url,
                self.declarative_base,
                include_object_callable=self.include_object_callable,
            )

            if diffs:
                logger.info("Database schema is out of date")
                logger.info(f"Differences: {diffs}")
            else:
                logger.info("Database schema is in sync")

            return diffs

    async def connect(self, dbname: str | None = None) -> AsyncConnection[TupleRow]:
        """Establishes a connection to the specified database.

        Args:
            dbname: Name of the database to connect to. If None, will use the database name from the db_url_callable.

        Returns:
            An active database connection.
        """
        db_url = self.db_url
        if db_url.host is None:
            raise InvalidDatabaseURLError("Host is required in the database URL")
        if db_url.database is None:
            raise InvalidDatabaseURLError(
                "Database name is required in the database URL"
            )
        if db_url.username is None:
            raise InvalidDatabaseURLError("Username is required in the database URL")

        return await connect(
            host=db_url.host,
            port=db_url.port if db_url.port is not None else 5432,
            username=db_url.username,
            password=db_url.password,
            dbname=dbname if dbname is not None else db_url.database,
            verbose=self.verbose,
        )
