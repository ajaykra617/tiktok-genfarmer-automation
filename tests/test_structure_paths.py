from genfarmer_automation.structure_paths import find_key_paths, set_existing_path, structure_paths


def test_find_key_paths_recurses_without_alias_guessing():
    value = {"options": {"XPath": "", "nested": [{"other": 1}]}, "xpathLike": "no"}
    assert find_key_paths(value, "xpath") == [("options", "XPath")]


def test_set_existing_path_updates_only_existing_leaf():
    value = {"data": [{"XPath": "old"}]}
    set_existing_path(value, ("data", 0, "XPath"), "new")
    assert value == {"data": [{"XPath": "new"}]}


def test_set_existing_path_rejects_missing_schema():
    value = {"data": {}}
    try:
        set_existing_path(value, ("data", "XPath"), "new")
    except ValueError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("missing field should fail closed")


def test_structure_paths_hides_scalar_values():
    rows = structure_paths({"xpath": "secret-selector", "timeout": 30})
    text = "\n".join(rows)
    assert "secret-selector" not in text
    assert "$.xpath str" in text
    assert "$.timeout int" in text
