"""バグ再現テスト: セキュリティ修正 第1弾.

参照: .kiro/specs/security-fixes-batch1/bugfix.md

これらのテストは、修正前は失敗し（バグ再現）、修正後にパスすることを期待する。
現状は3件とも失敗する（バグが存在するため）。
"""

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from dify_admin.auth import AuthenticationError, login
from dify_admin.client import DifyClient
from dify_admin.password import reset_via_docker


class TestPasswordSqlInjection:
    """password.py: SQLインジェクション文字列を含むemailでSQL文が安全に構築されるか."""

    @pytest.mark.xfail(reason="SQLi未修正: password.py のパラメータ化が必要")
    def test_sql_injection_email_produces_safe_sql(self) -> None:
        """email='admin' OR '1'='1' のとき、SQLがインジェクションにならないこと."""
        sql_cmd: str = ""

        def capture_run(*args: object, **kwargs: object) -> MagicMock:
            nonlocal sql_cmd
            # psql -c "UPDATE ..." の -c 引数を取得
            args_list = list(args[0]) if args else kwargs.get("args", [])
            for i, arg in enumerate(args_list):
                if arg == "-c" and i + 1 < len(args_list):
                    sql_cmd = args_list[i + 1]
                    break
            return MagicMock(stdout="UPDATE 1", returncode=0)

        with patch("dify_admin.password.subprocess.run", side_effect=capture_run):
            reset_via_docker(
                email="admin' OR '1'='1",
                new_password="newpass",
                container_name="dify-db",
            )

        # インジェクションの場合: WHERE email = 'admin' OR '1'='1' となり
        # " OR '1'='1" がSQLとして解釈される。安全な構築ではそのような文字列が
        # 論理演算子として出現しないこと
        assert " OR '1'='1" not in sql_cmd, (
            "SQLにインジェクション文字列がそのまま含まれており、"
            "複数行の更新や不正な条件が実行される可能性があります"
        )


class TestClientJsonConstruction:
    """client.py: indexing_techniqueが特殊文字を含む場合のJSON構築."""

    def _extract_data_from_multipart(self, content: bytes) -> str:
        """multipart/form-data から data フィールドを抽出."""
        data_match = re.search(
            rb'name="data"\r\n\r\n(.*?)(?=\r\n--|\Z)',
            content,
            re.DOTALL,
        )
        if data_match:
            return data_match.group(1).decode("utf-8")
        raise ValueError("data field not found in multipart body")

    @pytest.mark.xfail(reason="JSON構築未修正: client.py で json.dumps が必要")
    def test_indexing_technique_with_special_chars_produces_valid_json(
        self,
        httpx_mock: object,
    ) -> None:
        """indexing_technique にダブルクォート等を含む場合のJSONが有効であること."""
        data_field_value: str = ""

        def login_callback(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        def upload_callback(request: httpx.Request) -> httpx.Response:
            nonlocal data_field_value
            data_field_value = self._extract_data_from_multipart(request.content)
            return httpx.Response(status_code=200, json={"document": {"id": "doc1"}})

        httpx_mock.add_callback(login_callback, url="http://localhost:5001/console/api/login")
        httpx_mock.add_callback(
            upload_callback,
            url=re.compile(r".*/document/create_by_file"),
        )

        client = DifyClient("http://localhost:5001")
        client.login("admin@test.com", "password")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# Sample\n\nContent.")
            tmp = Path(f.name)
        try:
            client.kb_upload_file(
                "dataset-123",
                tmp,
                indexing_technique='high_quality"}; "malicious": "true',
            )
        finally:
            tmp.unlink(missing_ok=True)
        client.close()

        # data フィールドが有効なJSONとしてパースできること
        parsed = json.loads(data_field_value)
        assert "indexing_technique" in parsed
        assert parsed["indexing_technique"] == 'high_quality"}; "malicious": "true'


class TestAuthNonJsonResponse:
    """auth.py: 非JSONレスポンス（HTML等）でのログイン失敗時にAuthenticationErrorが発生するか."""

    @pytest.mark.xfail(reason="auth.py: 非JSONレスポンス時に AuthenticationError が必要")
    def test_html_error_response_raises_authentication_error(
        self,
        httpx_mock: object,
    ) -> None:
        """HTMLエラーページが返された場合、JSONDecodeErrorではなくAuthenticationError."""
        httpx_mock.add_response(
            url="http://localhost:5001/console/api/login",
            method="POST",
            status_code=401,
            html="<html><body>Internal Server Error</body></html>",
        )

        with pytest.raises(AuthenticationError) as exc_info:
            login("http://localhost:5001", "admin@test.com", "wrongpass")

        assert "Login failed" in str(exc_info.value) or "401" in str(exc_info.value)
