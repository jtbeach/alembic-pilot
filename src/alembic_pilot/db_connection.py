"""Database connection utilities for Alembic Pilot.

This module provides functions for establishing database connections with proper configuration.
"""

from psycopg import AsyncConnection
from psycopg.rows import TupleRow
from psycopg_toolbox import LoggingConnection


async def connect(
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,
    dbname: str,
    verbose: bool = False,
) -> AsyncConnection[TupleRow]:
    """Establishes a connection to the specified database.

    Creates either a regular or logging connection based on the verbose setting.
    The connection is configured with the provided host, port, and credentials.

    Args:
        host: The hostname of the PostgreSQL server.
        port: The port number of the PostgreSQL server.
        username: The username for the connection.
        password: The password for the connection. Can be None (will read from env var, .pgpass, etc.)
        dbname: Name of the database to connect to.
        verbose: Whether to use a logging connection that prints SQL queries.

    Returns:
        An active database connection.
    """
    if verbose:
        return await LoggingConnection.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            dbname=dbname,
        )
    else:
        return await AsyncConnection.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            dbname=dbname,
        )
