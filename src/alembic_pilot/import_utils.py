"""Utility functions for getting import paths of Python objects."""

import inspect
from collections.abc import Callable
from types import ModuleType
from typing import Any


def get_import_path_for_class(class_type: type) -> tuple[str, str] | None:
    """
    Gets the import path components for a Python class type.

    Args:
        class_type: The Python class type object.

    Returns:
        A tuple of (module_name, qual_name) if the class can be reliably imported,
        or None if the class cannot be reliably imported by string path
        (e.g., classes in __main__, builtins, or dynamically defined classes).
    """
    if not isinstance(class_type, type):
        # Ensure the input is actually a class type
        return None

    if hasattr(class_type, "__module__") and hasattr(class_type, "__qualname__"):
        module_name: str | None = class_type.__module__
        qual_name: str = class_type.__qualname__

        # Classes defined in __main__ or dynamically (<locals>) are not standardly importable
        if module_name is None or module_name == "__main__" or "<locals>" in qual_name:
            return None

        # You might choose to exclude builtins here if you don't need their paths
        if module_name == "builtins":
            return None  # Or return f"{module_name}.{qual_name}" if desired

        return module_name, qual_name

    return None  # Cannot determine import path


def get_import_path_for_callable(
    callable_obj: Callable[..., Any],
) -> tuple[str, str] | None:
    """
    Gets the import path components for a callable object.

    This function handles functions, classes, methods, and instances
    of callable classes.

    Args:
        callable_obj: The Python callable (function, class, method,
                      or instance of a callable class) instance.

    Returns:
        A tuple of (module_name, qual_name) if the object can be reliably imported,
        or None if the object cannot be reliably imported by string path
        (e.g., lambdas, objects in __main__, or dynamically defined objects).
    """
    # Handle functions, methods, and other callables directly
    # Use inspect to be robust across different callable types (functions, methods, etc.)
    if inspect.isroutine(callable_obj):
        try:
            # Get the module and qualified name using inspect
            module: ModuleType | None = inspect.getmodule(callable_obj)
            module_name = module.__name__ if module else None
            qual_name = (
                inspect.getmembers(module)[0][0] if module else None
            )  # Fallback to __qualname__

            # For methods, __qualname__ is usually sufficient
            if inspect.ismethod(callable_obj) or inspect.isfunction(callable_obj):
                qual_name = callable_obj.__qualname__

            # Objects defined interactively in the main script (__main__)
            # or lambdas (<lambda>) typically cannot be imported by string path.
            if (
                module_name is None
                or module_name == "__main__"
                or qual_name is None
                or qual_name == "<lambda>"
                or "<locals>" in qual_name
            ):
                return None

            # Exclude builtins unless specifically desired
            if module_name == "builtins":
                return (
                    None  # Or return f"{module_name}.{qual_name}" if you want builtins
                )

            return module_name, qual_name
        except Exception:
            # Handle cases where inspect might fail for unusual callables
            return None

    return None  # Object is not a recognized callable type
