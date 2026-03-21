"""バグ再現テスト: 堅牢性修正 第2弾.

参照: .kiro/specs/robustness-fixes-batch2/bugfix.md

これらのテストは、修正前は失敗し（バグ再現）、修正後にパスすることを期待する。
xfail マーカーにより現状はテストスイート全体がパスする。
"""

import re
import tempfile
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from dify_admin.cli import main
from dify_admin.client import DifyClient


class TestCliKeyError:
    """cli.py: APIレスポンスにキーが欠けている場合にKeyErrorにならないこと."""

    @pytest.mark.xfail(reason="KeyError未修正: cli.py で .get() が必要")
    def test_apps_list_with_missing_keys_completes_without_key_error(
        self,
        httpx_mock: object,
    ) -> None:
        """apps list で id/name/mode が欠けたレスポンスでも KeyError にならないこと."""
        def login_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        def apps_cb(request: httpx.Request) -> httpx.Response:
            # 意図的にキーを欠けたレスポンス
            return httpx.Response(
                status_code=200,
                json={
                    "data": [
                        {"id": "a1", "name": "App1", "mode": "chat"},
                        {"id": "a2"},  # name, mode 欠落
                        {"name": "App3"},  # id, mode 欠落
                    ]
                },
            )

        httpx_mock.add_callback(login_cb, url="http://localhost:5001/console/api/login")
        httpx_mock.add_callback(apps_cb, url=re.compile(r".*/console/api/apps"))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["apps", "list", "--email", "a@b.com", "--password", "pwd"],
        )
        assert result.exit_code == 0, f"KeyError or other: {result.output}"
        assert "KeyError" not in str(result.exc_info) if result.exc_info else True

    @pytest.mark.xfail(reason="KeyError未修正: cli.py で .get() が必要")
    def test_kb_list_with_missing_keys_completes_without_key_error(
        self,
        httpx_mock: object,
    ) -> None:
        """kb list で id/name 等が欠けたレスポンスでも KeyError にならないこと."""
        def login_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        def kb_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                json={
                    "data": [
                        {"id": "d1", "name": "KB1", "document_count": 0},
                        {"id": "d2"},  # name 等欠落
                    ]
                },
            )

        httpx_mock.add_callback(login_cb, url="http://localhost:5001/console/api/login")
        httpx_mock.add_callback(kb_cb, url=re.compile(r".*/console/api/datasets"))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["kb", "list", "--email", "a@b.com", "--password", "pwd"],
        )
        assert result.exit_code == 0, f"KeyError or other: {result.output}"


class TestClientKbUploadDirExceptionInfo:
    """client.py: kb_upload_dir の失敗時に例外情報が戻り値に含まれること."""

    @pytest.mark.xfail(reason="例外握りつぶし未修正: failed_files が必要")
    def test_kb_upload_dir_returns_exception_info_on_failure(
        self,
        httpx_mock: object,
    ) -> None:
        """アップロード失敗時に failed_files にファイル名と例外情報が含まれること."""
        call_count = 0

        def login_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        def upload_cb(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # 2件目で失敗
            if call_count == 2:
                return httpx.Response(status_code=500, text="Server Error")
            return httpx.Response(status_code=200, json={"document": {"id": "doc1"}})

        httpx_mock.add_callback(login_cb, url="http://localhost:5001/console/api/login")
        httpx_mock.add_callback(
            upload_cb,
            url=re.compile(r".*/document/create_by_file"),
        )

        client = DifyClient("http://localhost:5001")
        client.login("a@b.com", "pwd")

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("a")
            (Path(d) / "b.md").write_text("b")
            result = client.kb_upload_dir("ds1", Path(d), "*.md")

        client.close()

        assert "failed_files" in result
        assert len(result["failed_files"]) >= 1
        entry = result["failed_files"][0]
        assert "path" in entry or "file" in entry or "name" in entry
        assert "error" in entry or "exception" in entry or "message" in entry


class TestCliPathNotFileNorDir:
    """cli.py: ファイルでもディレクトリでもないパスでエラー終了すること."""

    @pytest.mark.xfail(reason="シンボリックリンク未対応: エラー終了が必要")
    def test_kb_upload_with_broken_symlink_exits_with_error(
        self,
        httpx_mock: object,
    ) -> None:
        """壊れたシンボリックリンク等でエラーメッセージを出し終了コード1で終了すること."""
        def login_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        httpx_mock.add_callback(login_cb, url="http://localhost:5001/console/api/login")

        with tempfile.TemporaryDirectory() as d:
            broken = Path(d) / "broken"
            broken.symlink_to("/nonexistent/path/12345")
            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    "kb", "upload",
                    "--email", "a@b.com", "--password", "pwd",
                    "ds1", str(broken),
                ],
            )

        assert result.exit_code == 1
        assert "file" in result.output.lower() or "path" in result.output.lower() or "error" in result.output.lower()


class TestCliStatusExitCode:
    """cli.py: status 接続失敗時に非ゼロ終了コードを返すこと."""

    @pytest.mark.xfail(reason="status 終了コード未修正: SystemExit(1) が必要")
    def test_status_connection_failure_returns_nonzero_exit_code(
        self,
        httpx_mock: object,
    ) -> None:
        """Dify 接続失敗時に終了コードが 0 以外であること."""
        httpx_mock.add_response(
            url="http://localhost:5001/console/api/setup",
            status_code=500,
            text="Internal Server Error",
        )

        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        assert result.exit_code != 0


class TestClientPagination:
    """client.py: apps_list / kb_list の全ページ取得."""

    @pytest.mark.xfail(reason="ページネーション未対応: 全ページ取得オプションが必要")
    def test_apps_list_fetches_all_pages(
        self,
        httpx_mock: object,
    ) -> None:
        """apps_list で全ページ取得時に全件返ること."""
        def login_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        def apps_cb(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 1))
            limit = int(request.url.params.get("limit", 30))
            if page == 1:
                items = [{"id": f"a{i}", "name": f"App{i}", "mode": "chat"} for i in range(limit)]
                return httpx.Response(
                    status_code=200,
                    json={"data": items, "has_more": True, "total": 35},
                )
            items = [{"id": f"a{i}", "name": f"App{i}", "mode": "chat"} for i in range(30, 35)]
            return httpx.Response(
                status_code=200,
                json={"data": items, "has_more": False, "total": 35},
            )

        httpx_mock.add_callback(login_cb, url="http://localhost:5001/console/api/login")
        httpx_mock.add_callback(apps_cb, url=re.compile(r".*/console/api/apps"))

        client = DifyClient("http://localhost:5001")
        client.login("a@b.com", "pwd")

        # fetch_all 等のパラメータで全ページ取得（仕様に応じて調整）
        try:
            apps = client.apps_list(fetch_all=True)
        except TypeError:
            apps = getattr(client, "apps_list_all", lambda: client.apps_list())()

        client.close()

        assert len(apps) == 35

    @pytest.mark.xfail(reason="ページネーション未対応: 全ページ取得オプションが必要")
    def test_kb_list_fetches_all_pages(
        self,
        httpx_mock: object,
    ) -> None:
        """kb_list で全ページ取得時に全件返ること."""
        def login_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        def kb_cb(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 1))
            if page == 1:
                items = [{"id": f"d{i}", "name": f"KB{i}"} for i in range(30)]
                return httpx.Response(
                    status_code=200,
                    json={"data": items, "has_more": True, "total": 35},
                )
            items = [{"id": f"d{i}", "name": f"KB{i}"} for i in range(30, 35)]
            return httpx.Response(
                status_code=200,
                json={"data": items, "has_more": False, "total": 35},
            )

        httpx_mock.add_callback(login_cb, url="http://localhost:5001/console/api/login")
        httpx_mock.add_callback(kb_cb, url=re.compile(r".*/console/api/datasets"))

        client = DifyClient("http://localhost:5001")
        client.login("a@b.com", "pwd")

        try:
            datasets = client.kb_list(fetch_all=True)
        except TypeError:
            datasets = getattr(client, "kb_list_all", lambda: client.kb_list())()

        client.close()

        assert len(datasets) == 35


class TestClientMimeType:
    """client.py: kb_upload_file がファイル拡張子に基づくMIMEタイプを送信すること."""

    def _extract_mime_from_multipart(self, content: bytes, filename: str) -> str:
        """multipart から file パートの Content-Type を抽出."""
        # name="file" の直後の Content-Type を探す（filename は様々な形式になりうる）
        idx = content.find(b'name="file"')
        if idx >= 0:
            ct_idx = content.find(b"Content-Type:", idx)
            if ct_idx >= 0:
                start = ct_idx + len(b"Content-Type:")
                end = content.find(b"\r\n", start)
                return content[start:end].decode().strip()
        return ""

    @pytest.mark.xfail(reason="MIMEタイプハードコード未修正: mimetypes が必要")
    def test_kb_upload_file_sends_extension_based_mime_type(
        self,
        httpx_mock: object,
    ) -> None:
        """PDF ファイルで application/pdf が送信されること（text/markdown ではない）."""
        captured_content: bytes = b""

        def login_cb(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                headers=[
                    ("set-cookie", "access_token=at; Path=/"),
                    ("set-cookie", "csrf_token=csrf; Path=/"),
                ],
            )

        def upload_cb(request: httpx.Request) -> httpx.Response:
            nonlocal captured_content
            captured_content = request.content
            return httpx.Response(status_code=200, json={"document": {"id": "doc1"}})

        httpx_mock.add_callback(login_cb, url="http://localhost:5001/console/api/login")
        httpx_mock.add_callback(
            upload_cb,
            url=re.compile(r".*/document/create_by_file"),
        )

        client = DifyClient("http://localhost:5001")
        client.login("a@b.com", "pwd")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 dummy")
            tmp = Path(f.name)
        try:
            client.kb_upload_file("ds1", tmp)
        finally:
            tmp.unlink(missing_ok=True)
        client.close()

        mime = self._extract_mime_from_multipart(captured_content, tmp.name)
        assert "application/pdf" in mime or mime == "application/pdf"
        assert "text/markdown" not in mime or "application/pdf" in mime
