# Alembic Pilot

A powerful and flexible database migration management tool built on top of Alembic, designed to simplify database operations across various cloud platforms including AWS, Azure, Google Cloud, and Heroku.

## Features

- 🚀 **Simple Database Management**: Create and manage PostgreSQL databases with ease
- 🔄 **Schema Management**: Create and upgrade application schemas
- 🌐 **Cloud Platform Support**: Works seamlessly with AWS, Azure, Google Cloud, and Heroku
- 🔍 **Schema Comparison**: Compare your models with the current database state
- 🛠️ **CLI Integration**: Easy-to-use command-line interface for database operations
- 🔐 **Concurrency Safety**: Built-in mutex for safe concurrent operations, perfect for Kubernetes initContainers

## Installation

```bash
pip install alembic-pilot
```

## Quick Start

1. Initialize your database manager:

```python
from alembic_pilot import ManagedDatabase
from sqlalchemy import URL

db_manager = ManagedDatabase(
    db_url=URL.create(
        "postgresql+psycopg",
        username="your_username",
        host="your_host",
        database="your_database",
        password="your_password",
    ).render_as_string(),
    declarative_base=MyAppBase,  # Your SQLAlchemy declarative base for auto-generated migrations and schema introspection
    models_module=myapp.models,  # Module containing your models for auto-generated migrations and schema introspection
    app_schema_name="public",  # change this if you want your app to live in a different PostgreSQL schema
)
```

Note: above is just sample code -- you wouldn't ever put your password like this in production
code. Instead, you would likely be reading this from an environment variable or even better,
defined in a `.pgpass` file.

1. Initialize Alembic:

This is an alternative to `alembic init` that automatically gives you a working config
that will handle auto-generation and schema comparison.

```python
from pathlib import Path

db_manager.init_alembic(migrations_dir=Path("db_migrations"))
```

3. Create your database (for non-Heroku deployments):

The following command will automate the creation of the database and also the
creation of the PostgreSQL schema inside the database that you have nominated to use
for you app. Can be configured to ignore errors so you can put this in a k8s initContainer
and have it work create it automatically on the very first deploy and then have it act
as a no-op for future deploys.

```python
await db_manager.create_database(error_if_exists=False)
```

4. Create your application schema:

(Only useful if using Heroku)

In Heroku, you can't create new databases, so the `create_database` call above won't
work. Therefore, this package provides the functionality of creating the schema as
a separate method so you can still call it.

If you're not on Heroku, this will be taken care of by the `create_database` call and
you don't need to call it.

```python
await db_manager.create_app_schema(error_if_exists=False)
```

5. Upgrade your schema to the latest version:

Will apply any Alembic migrations that are defined in the codebase but have not
yet been applied to the database. Similar to `alembic upgrade head` but with a mutex
around it to serialize multiple concurrent callers. Also sanity checks that the current
user has appropriate permissions.

```python
await db_manager.upgrade_schema_to_latest()
```

## CLI Usage

Alembic Pilot an API, but consumers of this package would normally implement a CLI
that calls the Alembic Pilot functions described above.

A full implementation might look something like this in your app

```
import asyncio
import functools
import logging
import logging.config
from pathlib import Path

import click
from alembic_pilot import ManagedDatabase
from sqlalchemy import URL

from myapp.models import Base
import myapp.models


def get_db_url():
    return URL.create(
        "postgresql+psycopg",
        username="postgres",
        host="XXX.rds.amazonaws.com",
        database="apptest",
    )


def include_object(obj, name, type_, reflected, compare_to):
    return True


def async_cli_cmd(func):
    """Decorator for async click commands."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))

    return wrapper


db_manager = ManagedDatabase(
    db_url=get_db_url,
    declarative_base=Base,
    models_module=test.models,
    app_schema_name="test",
)


logger = logging.getLogger(__name__)


@click.group()
def db():
    """CLI command to manage database."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Initialized app logging")


@db.command()
def init_alembic():
    """Initialize the database."""
    db_manager.init_alembic(migrations_dir=(Path.cwd() / Path("db_migrations")))


@db.command()
@async_cli_cmd
@click.option(
    "--error-if-exists/--no-error-if-exists",
    default=False,
    help="Throw an error if DB already exists.",
)
async def create_database(error_if_exists: bool):
    """Create the PostgreSQL database for the application."""
    await db_manager.create_database(error_if_exists=error_if_exists)


@db.command()
@async_cli_cmd
@click.option(
    "--error-if-exists/--no-error-if-exists",
    default=False,
    help="Throw an error if schema already exists.",
)
async def create_app_schema(error_if_exists: bool):
    """Create the PostgreSQL database for the application."""
    await db_manager.create_app_schema(error_if_exists=error_if_exists)


@db.command()
@async_cli_cmd
async def upgrade_app_schema():
    """Upgrade the database to the latest version."""
    await db_manager.upgrade_schema_to_latest()


@db.command()
@async_cli_cmd
async def compare_app_schema():
    """Compare the database to the latest version."""
    await db_manager.compare_schema_to_latest()
```

If you're using `uv` as your package managers, you would then add something like
this to your `pyproject.toml` (assuming code is in `myapp/cli/db.py`):

```
[project.scripts]
db = "myapp.cli.db:db"
```

If you're using `poetry`, it would be;

```
[tool.poetry.scripts]
db = 'myapp.cli.db:cli'
```

The you would be able to run the commands from the command line or from within a shell
script (if using `uv`, you would prefix these with `uv run` and with `poetry run` if using Poetry).

```bash
# Initialize Alembic
db init-alembic

# Create database (non-Heroku)
db create-database

# Create application schema
db create-app-schema

# Upgrade schema to latest version
db upgrade-app-schema

# Compare current schema with models
db compare-app-schema
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

