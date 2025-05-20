"""Tests for import utility functions.

These tests verify the functionality of the import path resolution utilities.
"""

from alembic_pilot.import_utils import (
    get_import_path_for_callable,
    get_import_path_for_class,
)


class TestClass:
    """Test class for import path testing."""

    pass


def test_function():
    """Test function for import path testing."""
    pass


class TestGetClassImportPath:
    """Tests for get_class_import_path function."""

    def test_valid_class(self):
        """Test getting import path for a valid class."""
        result = get_import_path_for_class(TestClass)
        assert result == ("test_import_utils", "TestClass")

    def test_builtin_class(self):
        """Test getting import path for a builtin class."""
        result = get_import_path_for_class(str)
        assert result is None

    def test_dynamic_class(self):
        """Test getting import path for a dynamically created class."""
        dynamic_class = type("DynamicClass", (), {})
        result = get_import_path_for_class(dynamic_class)
        assert result == ("test_import_utils", "DynamicClass")


class TestGetImportPath:
    """Tests for get_import_path function."""

    def test_valid_function(self):
        """Test getting import path for a valid function."""
        result = get_import_path_for_callable(test_function)
        assert result == ("test_import_utils", "test_function")

    def test_valid_class(self):
        """Test getting import path for a valid class."""
        result = get_import_path_for_callable(TestClass)
        assert result is None

    def test_lambda_function(self):
        """Test getting import path for a lambda function."""

        def identity(x):
            return x

        result = get_import_path_for_callable(identity)
        assert result is None

    def test_builtin_function(self):
        """Test getting import path for a builtin function."""
        result = get_import_path_for_callable(len)
        assert result is None

    def test_method(self):
        """Test getting import path for a method."""

        class TestClassWithMethod:
            def test_method(self):
                pass

        result = get_import_path_for_callable(TestClassWithMethod.test_method)
        assert result is None

    def test_instance_method(self):
        """Test getting import path for an instance method."""

        class TestClassWithMethod:
            def test_method(self):
                pass

        instance = TestClassWithMethod()
        result = get_import_path_for_callable(instance.test_method)
        assert result is None
