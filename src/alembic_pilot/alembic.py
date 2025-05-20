"""Alembic initialization and configuration utilities.

This module provides functions for initializing and configuring Alembic migrations,
including creating necessary directories and generating configuration files.
"""

import logging
import os
import shutil
import warnings
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, TypeAlias

import alembic.config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from mako.template import Template
from sqlalchemy import URL, Engine, NullPool, create_engine
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import SchemaItem

from .exceptions import AlembicInitError
from .import_utils import (
    get_import_path_for_callable,
    get_import_path_for_class,
)

# Type definitions for callables
DbUrlCallable: TypeAlias = Callable[[], URL]
IncludeObjectCallable: TypeAlias = Callable[
    [SchemaItem, str | None, str | None, bool, SchemaItem | None], bool
]

logger = logging.getLogger(__name__)


def create_versions_directory(migrations_root: Path) -> None:
    """Create the versions directory for Alembic migrations.

    Args:
        migrations_root: Root directory for Alembic migrations.

    Raises:
        AlembicInitError: If the migrations directory already exists.
    """
    versions_dir = migrations_root / "versions"
    try:
        versions_dir.mkdir(exist_ok=False)
        # Create .gitkeep file to ensure the directory is tracked by git
        (versions_dir / ".gitkeep").touch()
    except OSError:
        raise AlembicInitError(
            "Alembic migrations directory already exists. Please remove it before running this function."
        ) from None


def generate_alembic_ini(migrations_root: Path, alembic_ini_path: Path) -> None:
    """Generate the alembic.ini file.

    Args:
        relative_migrations_root: Relative path to the migrations directory.
    """

    migrations_root_relative_to_alembic_ini = migrations_root.relative_to(
        alembic_ini_path.parent
    )
    template_path = Path(__file__).parent / "data" / "alembic.ini.mako"
    template = Template(filename=str(template_path), strict_undefined=True)  # nosec  # Used for code generation, not HTML/JS
    rendered = template.render(
        migrations_root_relative_to_alembic_ini=str(
            migrations_root_relative_to_alembic_ini
        )
    )
    alembic_ini_path.write_text(rendered)


def generate_env_py(
    *,
    migrations_root: Path,
    db_url_callable: DbUrlCallable | None,
    models_module: ModuleType | None,
    include_object_callable: IncludeObjectCallable | None,
    declarative_base: type[DeclarativeBase] | None,
    app_schema_name: str,
) -> None:
    """Generate the env.py file for Alembic.

    Args:
        migrations_root: Root directory for Alembic migrations.
        db_url_callable: Optional function that returns the database URL.
            Not provided in tests -- if not provided, `alembic` will not be functional from the
            command line, only when called from ManagedDatabase.
        models_module: Optional module containing all SQLAlchemy model imports for autogenerate.
        include_object_callable: Optional function to filter objects for autogenerate.
        declarative_base: Optional SQLAlchemy declarative base class for autogenerate.

    Raises:
        ValueError: If import paths cannot be determined for any of the callables.
    """
    env_template_path = Path(__file__).parent / "data" / "env.py.mako"
    env_template = Template(filename=str(env_template_path), strict_undefined=True)  # nosec  # Used for code generation, not HTML/JS

    db_url_callable_module = None
    db_url_callable_name = None
    if db_url_callable is not None:
        db_url_import_path = get_import_path_for_callable(db_url_callable)
        if db_url_import_path is None:
            raise ValueError("Could not determine import statement for db_url_callable")
        db_url_callable_module, db_url_callable_name = db_url_import_path

    autogenerate_include_object_callable_module = None
    autogenerate_include_object_callable_name = None
    if include_object_callable is not None:
        autogenerate_include_object_callable_import_path = get_import_path_for_callable(
            include_object_callable
        )
        if autogenerate_include_object_callable_import_path is None:
            raise ValueError(
                "Could not determine import statement for autogenerate_include_object_callable"
            )
        (
            autogenerate_include_object_callable_module,
            autogenerate_include_object_callable_name,
        ) = autogenerate_include_object_callable_import_path

    declarative_base_import_module = None
    declarative_base_import_name = None
    if declarative_base is not None:
        declarative_base_import_path = get_import_path_for_class(declarative_base)
        if declarative_base_import_path is None:
            logger.warning(
                "Could not determine import statement for declarative_base_import_path. Auto-generation will not work in generate Alembic config."
            )
        else:
            (
                declarative_base_import_module,
                declarative_base_import_name,
            ) = declarative_base_import_path

    env_rendered = env_template.render(
        models_import_module=(
            models_module.__name__ if models_module is not None else None
        ),
        db_url_callable_module=db_url_callable_module,
        db_url_callable_name=db_url_callable_name,
        autogenerate_include_object_callable_module=autogenerate_include_object_callable_module,
        autogenerate_include_object_callable_name=autogenerate_include_object_callable_name,
        declarative_base_module=declarative_base_import_module,
        declarative_base_name=declarative_base_import_name,
        app_schema_name=app_schema_name,
    )
    (migrations_root / "env.py").write_text(env_rendered)


def copy_script_mako(migrations_root: Path) -> None:
    """Copy the script.py.mako template file.

    Args:
        migrations_root: Root directory for Alembic migrations.
    """
    script_template_path = Path(__file__).parent / "data" / "script.mako"
    shutil.copy2(script_template_path, migrations_root / "script.py.mako")


def apply_migrations(
    alembic_ini_path: Path,
    url_to_pass_as_argument: URL | None = None,
) -> None:
    """Function to implement schema upgrade via the alembic CLI."""
    alembic_base_dir = alembic_ini_path.parent.absolute()
    # We have to chdir to the folder containing the alembic.ini folder
    # or it won't resolve the relative path to the migrations
    os.chdir(alembic_base_dir)
    args = [
        "--raiseerr",
        "-c",
        str(alembic_ini_path),
        "-x",
        "SKIP_LOGGING_INIT=1",
    ]
    if url_to_pass_as_argument:
        args.extend(
            [
                "-x",
                f"ENGINE_URL={url_to_pass_as_argument.render_as_string()}",
            ]
        )

    args.extend(["upgrade", "head"])
    return alembic.config.main(argv=args)


def compare_schema(
    engine_url: URL,
    declarative_base: type[DeclarativeBase],
    include_object_callable: IncludeObjectCallable | None = None,
) -> list[tuple | list]:
    """Function to implement schema comparison via alembic."""
    engine: Engine | None = None
    try:
        engine = create_engine(engine_url, poolclass=NullPool)
        with engine.connect() as conn:
            with warnings.catch_warnings():
                # Don't print out some harmless sqlalchemy warnings about index reflection --  see
                # https://stackoverflow.com/questions/5225780/turn-off-a-warning-in-sqlalchemy
                warnings.simplefilter("ignore", category=SAWarning)

            opts: dict[str, Any] = {
                "include_schemas": True,
                "compare_server_default": True,
                "compare_type": True,
            }
            if include_object_callable is not None:
                opts["include_object"] = include_object_callable

            mc = MigrationContext.configure(conn, opts=opts)
            return compare_metadata(mc, declarative_base.metadata)
    finally:
        if engine is not None:
            engine.dispose()
