from logging.config import fileConfig

from psycopg.sql import Identifier, SQL
from sqlalchemy import pool, create_engine, event, Connection

from alembic import context

% if models_import_module:
# Import the SQLAlchemy models (so that Alembic can introspect them)
import ${models_import_module}  # noqa: F401
% endif
% if db_url_callable_module and db_url_callable_name:
# Import the database URL callable
from ${db_url_callable_module} import ${db_url_callable_name}
% endif
% if declarative_base_module and declarative_base_name:
# Import the SQLAlchemy declarative base class for autogeneration/introspection
from ${declarative_base_module} import ${declarative_base_name}
% endif
% if autogenerate_include_object_callable_module and autogenerate_include_object_callable_name:
# Import an include_object callable so that we can filter objects for autogeneration
from ${autogenerate_include_object_callable_module} import ${autogenerate_include_object_callable_name}
% endif

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

args = context.get_x_argument(as_dictionary=True)

# When invoking from code, we don't want to re-init logging so
# we allow an argument to be passed which avoid this.
skip_logging_init = args.get("SKIP_LOGGING_INIT", False)
if not skip_logging_init and config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
% if declarative_base_module:
target_metadata = ${declarative_base_module}.metadata
% else:
target_metadata = None
% endif

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

% if db_url_callable_module and db_url_callable_name:
url = ${db_url_callable_name}()
% else:
url = args.get("ENGINE_URL")
% endif

# Store the app schema name so we can make sure the search path is set to this schema
# for all alembic migrations.
app_schema_name = "${app_schema_name}"

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    @event.listens_for(connectable, "connect")
    def set_search_path(dbapi_conn: Connection, *args):
        """Set search path connect to reflect the default schema.

        This schema is where we expect tables to be created if they don't explicitly
        specify a schema. This includes the alembic_version table.

        We choose to do this here to avoid some issues with how search_path affects
        database reflection (see https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#remote-schema-table-introspection-and-postgresql-search-path)
        """
        old_autocommit = dbapi_conn.autocommit
        try:
            dbapi_conn.autocommit = True
            dbapi_conn.execute(
                SQL("SET SEARCH_PATH TO {schema_name}").format(
                    schema_name=Identifier(app_schema_name)
                )
            )
        finally:
            dbapi_conn.autocommit = old_autocommit

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
    % if autogenerate_include_object_callable_module and autogenerate_include_object_callable_name:
            include_object=${autogenerate_include_object_callable_name},
    % endif
            compare_server_default=True,
            compare_type=True,
            transaction_per_migration=True,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()