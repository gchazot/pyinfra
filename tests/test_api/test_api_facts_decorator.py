from unittest import mock
import unittest
from pyinfra.api.facts import fact


class TestFactDecorator(unittest.TestCase):
    def test_fact_metadata(self):
        @fact()
        def basic_fact() -> str:
            return "hello"

        assert basic_fact.abstract is False
        assert basic_fact.name == "basic_fact"

    def test_default_default_is_None(self):
        @fact()
        def fact_without_default() -> str:
            return "hello"

        assert fact_without_default.default() is None

    def test_default_value(self):
        @fact(default_value="world")
        def fact_with_default() -> str:
            return "hello"

        assert fact_with_default.default() == "world"
