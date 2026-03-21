"""Tests for patch.py — dot-notation config patching."""

import pytest

from dify_admin.patch import (
    apply_patches,
    delete_nested,
    get_nested,
    parse_value,
    set_nested,
)


class TestGetNested:
    def test_simple_key(self) -> None:
        assert get_nested({"name": "foo"}, "name") == "foo"

    def test_nested_key(self) -> None:
        data = {"model": {"name": "gpt-4o", "params": {"temperature": 0.7}}}
        assert get_nested(data, "model.name") == "gpt-4o"
        assert get_nested(data, "model.params.temperature") == 0.7

    def test_missing_key_raises(self) -> None:
        with pytest.raises(KeyError):
            get_nested({"a": 1}, "b")

    def test_missing_nested_key_raises(self) -> None:
        with pytest.raises(KeyError):
            get_nested({"a": {"b": 1}}, "a.c")

    def test_traverse_non_dict_raises(self) -> None:
        with pytest.raises(KeyError):
            get_nested({"a": "string"}, "a.b")


class TestSetNested:
    def test_simple_set(self) -> None:
        data: dict = {}
        set_nested(data, "name", "foo")
        assert data == {"name": "foo"}

    def test_nested_set(self) -> None:
        data: dict = {"model": {"name": "old"}}
        set_nested(data, "model.name", "new")
        assert data["model"]["name"] == "new"

    def test_creates_intermediate_dicts(self) -> None:
        data: dict = {}
        set_nested(data, "a.b.c", 42)
        assert data == {"a": {"b": {"c": 42}}}

    def test_overwrites_non_dict_intermediate(self) -> None:
        data: dict = {"a": "string"}
        set_nested(data, "a.b", 1)
        assert data == {"a": {"b": 1}}

    def test_returns_modified_dict(self) -> None:
        data: dict = {}
        result = set_nested(data, "x", 1)
        assert result is data


class TestDeleteNested:
    def test_simple_delete(self) -> None:
        data = {"a": 1, "b": 2}
        delete_nested(data, "a")
        assert data == {"b": 2}

    def test_nested_delete(self) -> None:
        data = {"model": {"name": "gpt", "stop": ["\n"]}}
        delete_nested(data, "model.stop")
        assert data == {"model": {"name": "gpt"}}

    def test_missing_key_raises(self) -> None:
        with pytest.raises(KeyError):
            delete_nested({"a": 1}, "b")

    def test_missing_nested_key_raises(self) -> None:
        with pytest.raises(KeyError):
            delete_nested({"a": {"b": 1}}, "a.c")


class TestParseValue:
    def test_integer(self) -> None:
        assert parse_value("42") == 42

    def test_float(self) -> None:
        assert parse_value("0.7") == 0.7

    def test_bool_true(self) -> None:
        assert parse_value("true") is True

    def test_bool_false(self) -> None:
        assert parse_value("false") is False

    def test_null(self) -> None:
        assert parse_value("null") is None

    def test_json_string(self) -> None:
        assert parse_value('"hello"') == "hello"

    def test_plain_string(self) -> None:
        assert parse_value("hello") == "hello"

    def test_json_array(self) -> None:
        assert parse_value('["a","b"]') == ["a", "b"]

    def test_json_object(self) -> None:
        assert parse_value('{"key": "val"}') == {"key": "val"}


class TestApplyPatches:
    def test_set_operations(self) -> None:
        config: dict = {"model": {"name": "old"}}
        apply_patches(config, set_ops=[("model.name", "new"), ("model.temp", "0.5")])
        assert config["model"]["name"] == "new"
        assert config["model"]["temp"] == 0.5

    def test_unset_operations(self) -> None:
        config: dict = {"a": 1, "b": 2}
        apply_patches(config, unset_ops=["b"])
        assert config == {"a": 1}

    def test_combined_set_and_unset(self) -> None:
        config: dict = {"keep": 1, "remove": 2}
        apply_patches(config, set_ops=[("add", "3")], unset_ops=["remove"])
        assert config == {"keep": 1, "add": 3}

    def test_no_ops_is_noop(self) -> None:
        config: dict = {"a": 1}
        apply_patches(config)
        assert config == {"a": 1}
