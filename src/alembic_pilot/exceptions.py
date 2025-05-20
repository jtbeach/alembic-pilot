"""Custom exceptions for Alembic Pilot.

This module defines custom exceptions used throughout the Alembic Pilot package
for handling database ownership, role grants, and schema ownership errors.
"""


class DatabaseOwnershipError(Exception):
    """Raised when the current user is not the owner of the database or has not been granted the owner role."""

    pass


class AppSchemaOwnershipError(Exception):
    """Raised when the current user is not the owner of the app schema or has not been granted the owner role."""

    pass


class AlembicInitError(Exception):
    """Raised when there is an error initializing Alembic."""

    pass


class InvalidDatabaseURLError(Exception):
    """Raised when the database URL is invalid."""

    pass
