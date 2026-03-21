"""Tests for DifyClient."""

import pytest

from dify_admin.client import DifyClient


class TestDifyClientInit:
    def test_default_url(self) -> None:
        client = DifyClient()
        assert client.base_url == "http://localhost:5001"
        client.close()

    def test_custom_url(self) -> None:
        client = DifyClient("http://dify.example.com:8080")
        assert client.base_url == "http://dify.example.com:8080"
        client.close()

    def test_trailing_slash_stripped(self) -> None:
        client = DifyClient("http://localhost:5001/")
        assert client.base_url == "http://localhost:5001"
        client.close()

    def test_not_logged_in_raises(self) -> None:
        client = DifyClient()
        with pytest.raises(RuntimeError, match="Not logged in"):
            _ = client.session
        client.close()

    def test_context_manager(self) -> None:
        with DifyClient() as client:
            assert client.base_url == "http://localhost:5001"
