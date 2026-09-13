import pytest

from genfarmer_automation.elementexists_schema import (
    ElementExistsSchemaError,
    resolve_xpath_path,
)


SENTINEL = "//*[@resource-id='__GF_SCHEMA_PROBE__']"


def test_existing_xpath_key_wins_without_sentinel():
    path, basis = resolve_xpath_path({"options": {"XPath": "old"}}, SENTINEL)
    assert path == ("options", "XPath")
    assert basis == "verified XPath key"


def test_exact_sentinel_learns_nonstandard_serialized_field():
    data = {"options": {"selectorValue": SENTINEL, "nodeTimeout": "30"}}
    path, basis = resolve_xpath_path(data, SENTINEL)
    assert path == ("options", "selectorValue")
    assert basis == "exact schema-probe sentinel"


def test_missing_xpath_and_missing_sentinel_fails_closed():
    with pytest.raises(ElementExistsSchemaError):
        resolve_xpath_path({"options": {"nodeTimeout": "30"}}, SENTINEL)


def test_duplicate_sentinel_fails_closed():
    data = {"a": SENTINEL, "b": {"c": SENTINEL}}
    with pytest.raises(ElementExistsSchemaError):
        resolve_xpath_path(data, SENTINEL)
