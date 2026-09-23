"""Unit tests for field_diff module — pure Python, no LLM, no network."""

import pytest
from driftmate.core.services.field_diff import (
    FieldDiff,
    diff_dicts,
    _flatten_keys,
)


class TestFlattenKeys:
    def test_flat_dict(self):
        d = {"a": 1, "b": 2}
        assert _flatten_keys(d) == {"a": 1, "b": 2}

    def test_nested_one_level(self):
        d = {"a": {"x": 1, "y": 2}, "b": 3}
        result = _flatten_keys(d)
        # Both parent dict key and child keys preserved
        assert result.get("a") == {"x": 1, "y": 2}
        assert result.get("a.x") == 1
        assert result.get("a.y") == 2
        assert result.get("b") == 3


class TestDiffDicts:
    def test_identical(self):
        d = {"a": 1, "b": {"x": 2}}
        diff = diff_dicts(d, d)
        assert diff.is_empty()
        assert diff.summary() == "-"

    def test_added_keys(self):
        old = {"a": 1}
        new = {"a": 1, "b": 2}
        diff = diff_dicts(old, new)
        assert diff.added == ["b"]
        assert diff.removed == []
        assert diff.type_changed == []
        assert diff.summary() == "1 added"

    def test_removed_keys(self):
        old = {"a": 1, "b": 2}
        new = {"a": 1}
        diff = diff_dicts(old, new)
        assert diff.added == []
        assert diff.removed == ["b"]
        assert diff.summary() == "1 removed"

    def test_type_changed(self):
        old = {"a": 1}
        new = {"a": "string"}
        diff = diff_dicts(old, new)
        assert diff.added == []
        assert diff.removed == []
        assert diff.type_changed == ["a"]
        assert diff.summary() == "1 type changed"

    def test_mixed(self):
        old = {"a": 1, "b": 2, "c": {"x": 1}}
        new = {"a": 1, "c": {"x": 1, "y": 2}, "d": 3}
        diff = diff_dicts(old, new)
        assert diff.added == ["c.y", "d"]
        assert diff.removed == ["b"]
        # "c" is type_changed because its sub-dict has changes
        assert "c" in diff.type_changed
        assert "1 type changed" in diff.summary()

    def test_none_inputs(self):
        diff = diff_dicts(None, None)
        assert diff.is_empty()

    def test_nested_dict_type_change(self):
        old = {"a": {"x": 1}}
        new = {"a": "not a dict"}
        diff = diff_dicts(old, new)
        assert diff.added == []
        assert diff.removed == ["a.x"]
        assert diff.type_changed == ["a"]


class TestFieldDiffSummary:
    def test_empty_summary(self):
        fd = FieldDiff()
        assert fd.summary() == "-"

    def test_mixed_summary(self):
        fd = FieldDiff(added=["a", "b"], removed=["c"], type_changed=["d"])
        summary = fd.summary()
        assert "2 added" in summary
        assert "1 removed" in summary
        assert "1 type changed" in summary