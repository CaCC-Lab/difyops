"""Tests for resolve.py — name resolution."""

from unittest.mock import MagicMock

import pytest

from dify_admin.resolve import (
    AmbiguousNameError,
    NameNotFoundError,
    resolve_app_by_name,
    resolve_kb_by_name,
)


def _mock_client(apps: list | None = None, datasets: list | None = None) -> MagicMock:
    """Create a mock DifyClient with preset data."""
    client = MagicMock()
    if apps is not None:
        client.apps_list.return_value = apps
    if datasets is not None:
        client.kb_list.return_value = datasets
    return client


class TestResolveAppByName:
    def test_single_match(self) -> None:
        client = _mock_client(apps=[{"id": "a1", "name": "Bot"}])
        result = resolve_app_by_name(client, "Bot")
        assert result["id"] == "a1"
        client.apps_list.assert_called_once_with(fetch_all=True)

    def test_no_match_raises(self) -> None:
        client = _mock_client(apps=[{"id": "a1", "name": "Bot"}])
        with pytest.raises(NameNotFoundError, match="No app found"):
            resolve_app_by_name(client, "Missing")

    def test_multiple_matches_raises(self) -> None:
        client = _mock_client(
            apps=[
                {"id": "a1", "name": "Bot"},
                {"id": "a2", "name": "Bot"},
            ]
        )
        with pytest.raises(AmbiguousNameError, match="Multiple apps"):
            resolve_app_by_name(client, "Bot")

    def test_case_sensitive(self) -> None:
        client = _mock_client(apps=[{"id": "a1", "name": "Bot"}])
        with pytest.raises(NameNotFoundError):
            resolve_app_by_name(client, "bot")

    def test_empty_list(self) -> None:
        client = _mock_client(apps=[])
        with pytest.raises(NameNotFoundError):
            resolve_app_by_name(client, "Bot")


class TestResolveKbByName:
    def test_single_match(self) -> None:
        client = _mock_client(datasets=[{"id": "d1", "name": "FAQ"}])
        result = resolve_kb_by_name(client, "FAQ")
        assert result["id"] == "d1"
        client.kb_list.assert_called_once_with(fetch_all=True)

    def test_no_match_raises(self) -> None:
        client = _mock_client(datasets=[{"id": "d1", "name": "FAQ"}])
        with pytest.raises(NameNotFoundError, match="No knowledge base"):
            resolve_kb_by_name(client, "Missing")

    def test_multiple_matches_raises(self) -> None:
        client = _mock_client(
            datasets=[
                {"id": "d1", "name": "FAQ"},
                {"id": "d2", "name": "FAQ"},
            ]
        )
        with pytest.raises(AmbiguousNameError, match="Multiple knowledge bases"):
            resolve_kb_by_name(client, "FAQ")
