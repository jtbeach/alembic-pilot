"""Database sanity check utilities for Alembic Pilot.

This module provides functions for verifying database and schema ownership permissions.
"""

from psycopg import AsyncConnection
from psycopg.rows import TupleRow

from .exceptions import (
    AppSchemaOwnershipError,
    DatabaseOwnershipError,
)


async def verify_database_ownership(conn: AsyncConnection[TupleRow]) -> None:
    """Verify database ownership permissions.

    Checks if the current user has ownership rights over the database,
    either directly or through role membership.

    Args:
        conn: Active database connection.

    Raises:
        DatabaseOwnershipError: If the user lacks required permissions.
    """
    query = """
    SELECT
        pg_catalog.pg_has_role(
            current_user, -- The role to check membership for (the current user)
            d.datdba,       -- The role to check membership against (the database owner's OID)
            'member'        -- The type of membership to check for (any membership)
        ) AS is_database_owner_or_member
    FROM
        pg_catalog.pg_database d
    WHERE
        d.datname = current_database(); -- Filter for the current database
    """
    result = await conn.execute(query)
    row = await result.fetchone()
    if not row or not row[0]:
        raise DatabaseOwnershipError(
            "Current user is not the owner of the database or has not been granted the owner role."
        )


async def verify_app_schema_ownership(
    conn: AsyncConnection[TupleRow],
    app_schema_name: str,
) -> None:
    """Verify application schema ownership permissions.

    Checks if the current user has ownership rights over the application
    schema, either directly or through role membership.

    Args:
        conn: Active database connection.
        app_schema_name: Name of the application schema to verify ownership for.

    Raises:
        AppSchemaOwnershipError: If the user lacks required permissions.
    """
    query = """
    SELECT
        pg_catalog.pg_has_role(current_user, n.nspowner, 'member')
    FROM
        pg_catalog.pg_namespace n
    WHERE
        n.nspname = %s;
    """
    result = await conn.execute(query, [app_schema_name])
    row = await result.fetchone()
    if not row or not row[0]:
        raise AppSchemaOwnershipError(
            f"Current user is not the owner of the schema '{app_schema_name}' or has not been granted the owner role."
        )
