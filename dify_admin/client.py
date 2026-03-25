"""Dify Console API client.

Provides a unified interface for managing Dify apps, datasets,
and system configuration via the Console API.
"""

from __future__ import annotations

import json
import mimetypes
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from dify_admin.auth import DifySession, login
from dify_admin.exceptions import (
    DifyMethodNotAllowedError,
    DifyServerError,
    raise_for_dify_status,
)


class DifyClient:
    """Dify Console API client with automatic authentication.

    Usage:
        client = DifyClient("http://localhost:5001")
        client.login("ryu@test.com", "Admin123")

        # List apps
        apps = client.apps_list()

        # Upload documents to knowledge base
        client.kb_upload("dataset-id", Path("./docs/"))
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5001",
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._session: Optional[DifySession] = None
        self.max_retries = max_retries
        transport = httpx.HTTPTransport(retries=max_retries)
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    def __enter__(self) -> "DifyClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Authentication ──────────────────────────────────────

    def login(self, email: str, password: str) -> DifySession:
        """Login and store session."""
        self._session = login(self.base_url, email, password, self._http)
        return self._session

    @property
    def session(self) -> DifySession:
        """Get active session or raise."""
        if self._session is None:
            raise RuntimeError("Not logged in. Call client.login() first.")
        return self._session

    def _console_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make authenticated Console API request with retry on 5xx."""
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            response = self._http.request(
                method,
                url,
                cookies=self.session.cookies(),
                headers=self.session.headers(),
                **kwargs,
            )
            try:
                raise_for_dify_status(response)
                return response
            except DifyServerError as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(min(2**attempt, 10))
                    continue
                raise
        raise last_error  # type: ignore[misc]

    def _console_get(self, path: str, **params: Any) -> Any:
        """GET from Console API and return JSON."""
        return self._console_request("GET", path, params=params).json()

    def _console_post(self, path: str, **kwargs: Any) -> Any:
        """POST to Console API and return JSON (or success dict if empty)."""
        response = self._console_request("POST", path, **kwargs)
        if response.status_code == 204 or not response.content:
            return {"result": "success"}
        return response.json()

    def _console_put(self, path: str, **kwargs: Any) -> Any:
        """PUT to Console API and return JSON."""
        return self._console_request("PUT", path, **kwargs).json()

    def _console_delete(self, path: str) -> Any:
        """DELETE from Console API and return JSON (or None if empty response)."""
        response = self._console_request("DELETE", path)
        if response.status_code == 204 or not response.content:
            return {"result": "success"}
        return response.json()

    _MAX_PAGES = 1000

    def _paginate_all(self, path: str, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch all pages from a paginated Console API endpoint.

        Args:
            path: API path
            limit: Items per page
        """
        all_items: list[dict[str, Any]] = []
        for page in range(1, self._MAX_PAGES + 1):
            data = self._console_get(path, page=page, limit=limit)
            items = data.get("data", [])
            all_items.extend(items)
            if not data.get("has_more", False) or not items:
                break
        return all_items

    # ── Apps ────────────────────────────────────────────────

    def apps_list(
        self, page: int = 1, limit: int = 30, fetch_all: bool = False
    ) -> list[dict[str, Any]]:
        """List apps.

        Args:
            page: Page number (ignored when fetch_all=True)
            limit: Items per page
            fetch_all: If True, fetch all pages and return combined results
        """
        if fetch_all:
            return self._paginate_all("/console/api/apps", limit=limit)
        data = self._console_get("/console/api/apps", page=page, limit=limit)
        return data.get("data", [])

    def apps_get(self, app_id: str) -> dict[str, Any]:
        """Get app details."""
        return self._console_get(f"/console/api/apps/{app_id}")

    def apps_create(
        self,
        name: str,
        mode: str = "chat",
        icon_type: str = "emoji",
        icon: str = "🤖",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new app.

        Args:
            name: App name
            mode: App mode (chat, completion, advanced-chat, agent-chat, workflow)
            icon_type: Icon type (emoji or image)
            icon: Icon value
            description: App description
        """
        return self._console_post(
            "/console/api/apps",
            json={
                "name": name,
                "mode": mode,
                "icon_type": icon_type,
                "icon": icon,
                "description": description,
            },
        )

    def apps_rename(
        self,
        app_id: str,
        name: str,
        description: str | None = None,
        icon: str | None = None,
        icon_type: str | None = None,
    ) -> dict[str, Any]:
        """Rename an app and optionally update description/icon.

        Args:
            app_id: App ID
            name: New app name
            description: New description (None = keep current)
            icon: New icon (None = keep current)
            icon_type: New icon type (None = keep current)
        """
        payload: dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description
        if icon is not None:
            payload["icon"] = icon
        if icon_type is not None:
            payload["icon_type"] = icon_type
        return self._console_put(f"/console/api/apps/{app_id}", json=payload)

    def apps_search(self, query: str, mode: str | None = None) -> list[dict[str, Any]]:
        """Search apps by name (case-insensitive substring match).

        Args:
            query: Search string
            mode: Filter by app mode (chat, completion, advanced-chat, workflow)

        Returns:
            List of matching apps
        """
        all_apps = self.apps_list(fetch_all=True)
        query_lower = query.lower()
        results = [a for a in all_apps if query_lower in a.get("name", "").lower()]
        if mode:
            results = [a for a in results if a.get("mode") == mode]
        return results

    def apps_delete(self, app_id: str) -> dict[str, Any]:
        """Delete an app."""
        return self._console_delete(f"/console/api/apps/{app_id}")

    def apps_get_config(self, app_id: str) -> dict[str, Any]:
        """Get app model configuration.

        Tries /model-config endpoint first; falls back to model_config
        field from apps_get() if the endpoint returns 405 (common for
        advanced-chat/workflow apps or newer Dify versions).
        """
        try:
            return self._console_get(f"/console/api/apps/{app_id}/model-config")
        except DifyMethodNotAllowedError:
            app = self.apps_get(app_id)
            if "model_config" in app:
                return app["model_config"] or {}
            raise

    def apps_update_config(self, app_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update app model configuration."""
        return self._console_post(
            f"/console/api/apps/{app_id}/model-config",
            json=config,
        )

    # ── Datasets (Knowledge Bases) ──────────────────────────

    def kb_list(
        self, page: int = 1, limit: int = 30, fetch_all: bool = False
    ) -> list[dict[str, Any]]:
        """List knowledge bases.

        Args:
            page: Page number (ignored when fetch_all=True)
            limit: Items per page
            fetch_all: If True, fetch all pages and return combined results
        """
        if fetch_all:
            return self._paginate_all("/console/api/datasets", limit=limit)
        data = self._console_get("/console/api/datasets", page=page, limit=limit)
        return data.get("data", [])

    def kb_create(
        self,
        name: str,
        description: str = "",
        indexing_technique: str = "high_quality",
    ) -> dict[str, Any]:
        """Create a knowledge base."""
        return self._console_post(
            "/console/api/datasets",
            json={
                "name": name,
                "description": description,
                "indexing_technique": indexing_technique,
            },
        )

    def kb_delete(self, dataset_id: str) -> dict[str, Any]:
        """Delete a knowledge base."""
        return self._console_delete(f"/console/api/datasets/{dataset_id}")

    def kb_documents(
        self, dataset_id: str, page: int = 1, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List documents in a knowledge base."""
        data = self._console_get(
            f"/console/api/datasets/{dataset_id}/documents",
            page=page,
            limit=limit,
        )
        return data.get("data", [])

    def _upload_file_to_storage(self, file_path: Path) -> str:
        """Upload a file to Dify storage and return the file UUID.

        Step 1 of the 2-step upload process for Dify v1.13+.
        """
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            result = self._console_request(
                "POST",
                "/console/api/files/upload",
                files={"file": (file_path.name, f, mime_type)},
                data={"source": "datasets"},
            ).json()
        return result["id"]

    def kb_upload_file(
        self,
        dataset_id: str,
        file_path: Path,
        indexing_technique: str = "high_quality",
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        separator: str | None = None,
    ) -> dict[str, Any]:
        """Upload a single file to a knowledge base.

        Uses the Dify v1.13+ 2-step upload: file upload → document creation.

        Args:
            dataset_id: Dataset ID
            file_path: Path to file
            indexing_technique: Indexing technique (high_quality, economy)
            chunk_size: Max tokens per chunk (None = automatic)
            chunk_overlap: Overlap tokens between chunks (None = automatic)
            separator: Custom separator string (None = automatic)
        """
        # Step 1: upload file to storage
        file_id = self._upload_file_to_storage(file_path)

        # Step 2: build process_rule
        if chunk_size or chunk_overlap or separator:
            rules: dict[str, Any] = {"mode": "custom"}
            rules["rules"] = {}
            if chunk_size:
                rules["rules"]["segmentation"] = {
                    "max_tokens": chunk_size,
                    "chunk_overlap": chunk_overlap or 50,
                }
            if separator:
                rules["rules"]["segmentation"] = {
                    **rules["rules"].get("segmentation", {}),
                    "separator": separator,
                }
            process_rule = rules
        else:
            process_rule = {"mode": "automatic"}

        # Step 3: create document from uploaded file
        return self._console_post(
            f"/console/api/datasets/{dataset_id}/documents",
            json={
                "indexing_technique": indexing_technique,
                "data_source": {
                    "info_list": {
                        "data_source_type": "upload_file",
                        "file_info_list": {"file_ids": [file_id]},
                    }
                },
                "process_rule": process_rule,
            },
        )

    def kb_upload_dir(
        self,
        dataset_id: str,
        dir_path: Path,
        pattern: str = "*.md",
    ) -> dict[str, Any]:
        """Upload all matching files from a directory.

        Returns:
            Dict with 'uploaded', 'failed' counts, 'total', and 'failed_files' details
        """
        files = sorted(dir_path.glob(pattern))
        uploaded = 0
        failed = 0
        failed_files: list[dict[str, str]] = []
        for f in files:
            try:
                self.kb_upload_file(dataset_id, f)
                uploaded += 1
            except Exception as e:
                failed += 1
                failed_files.append({"name": f.name, "error": str(e)})
        return {
            "uploaded": uploaded,
            "failed": failed,
            "total": len(files),
            "failed_files": failed_files,
        }

    def kb_documents_all(self, dataset_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """List all documents in a knowledge base (all pages).

        Args:
            dataset_id: Dataset ID
            limit: Items per page
        """
        return self._paginate_all(f"/console/api/datasets/{dataset_id}/documents", limit=limit)

    def kb_document_status(self, dataset_id: str, document_id: str) -> dict[str, Any]:
        """Get indexing status of a document.

        Args:
            dataset_id: Dataset ID
            document_id: Document ID
        """
        return self._console_get(
            f"/console/api/datasets/{dataset_id}/documents/{document_id}/indexing-status"
        )

    def kb_document_reindex(self, dataset_id: str, document_id: str) -> dict[str, Any]:
        """Trigger re-indexing of a document.

        Uses the Dify v1.13+ retry endpoint.

        Args:
            dataset_id: Dataset ID
            document_id: Document ID
        """
        return self._console_post(
            f"/console/api/datasets/{dataset_id}/retry",
            json={"document_ids": [document_id]},
        )

    def kb_delete_document(self, dataset_id: str, document_id: str) -> dict[str, Any]:
        """Delete a single document from a knowledge base.

        Uses the Dify v1.13+ batch delete endpoint with document_id query param.

        Args:
            dataset_id: Dataset ID
            document_id: Document ID to delete
        """
        self._console_request(
            "DELETE",
            f"/console/api/datasets/{dataset_id}/documents",
            params={"document_id": document_id},
        )
        return {"result": "success"}

    def kb_delete_all_documents(self, dataset_id: str) -> int:
        """Delete all documents in a knowledge base.

        Deletes documents one-by-one using the single-document delete
        endpoint, which is compatible with Dify v1.13+.

        Returns:
            Number of documents deleted
        """
        deleted = 0
        while True:
            docs = self.kb_documents(dataset_id, page=1, limit=100)
            if not docs:
                break
            for doc in docs:
                doc_id = doc.get("id")
                if not doc_id:
                    continue
                self.kb_delete_document(dataset_id, doc_id)
                deleted += 1
            if len(docs) < 100:
                break
        return deleted

    def apps_export(self, app_id: str) -> dict[str, Any]:
        """Export app as DSL YAML.

        Args:
            app_id: App ID to export

        Returns:
            Dict with 'data' key containing YAML string
        """
        return self._console_get(f"/console/api/apps/{app_id}/export")

    def apps_import(self, data: str, name: str | None = None) -> dict[str, Any]:
        """Import app from DSL YAML string.

        Handles the Dify v1.13+ /apps/imports endpoint which returns an
        import job object. If the import requires confirmation (status=pending),
        automatically sends a confirm request.

        Args:
            data: YAML string of the app DSL
            name: Optional name override for the imported app

        Returns:
            Dict with at least 'id' (app ID) and 'name' keys
        """
        payload: dict[str, Any] = {
            "mode": "yaml-content",
            "yaml_content": data,
        }
        if name:
            payload["name"] = name
        result = self._console_post(
            "/console/api/apps/imports",
            json=payload,
        )

        # Handle pending imports that require confirmation
        import_id = result.get("id", "")
        if result.get("status") == "pending" and import_id:
            result = self._console_post(
                f"/console/api/apps/imports/{import_id}/confirm",
            )

        # Normalize: ensure 'id' points to the app, not the import job
        app_id = result.get("app_id") or result.get("id", "")
        if app_id and app_id != result.get("id"):
            result["id"] = app_id

        # Fetch app details to include name in response
        if app_id and "name" not in result:
            try:
                app = self.apps_get(app_id)
                result["name"] = app.get("name", name or "")
            except Exception:
                result["name"] = name or ""

        return result

    def apps_clone(self, app_id: str, name: str | None = None) -> dict[str, Any]:
        """Clone an app by exporting and re-importing its DSL.

        Args:
            app_id: Source app ID
            name: Name for the cloned app (default: "Copy of <original>")

        Returns:
            The newly created app dict

        Raises:
            yaml.YAMLError: If the exported DSL is malformed (unlikely)
        """
        export_data = self.apps_export(app_id)
        yaml_str = export_data.get("data", "")
        if not name:
            # Extract name from DSL YAML to avoid extra API call
            import yaml

            dsl = yaml.safe_load(yaml_str) or {}
            original_name = dsl.get("app", {}).get("name", app_id)
            name = f"Copy of {original_name}"
        return self.apps_import(yaml_str, name=name)

    # ── Dataset API (token-based, no login needed) ──────────

    def dataset_api_list(self, api_key: str) -> list[dict[str, Any]]:
        """List datasets via Dataset API (no console login needed)."""
        response = self._http.get(
            f"{self.base_url}/v1/datasets",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"page": 1, "limit": 100},
        )
        raise_for_dify_status(response)
        return response.json().get("data", [])

    def dataset_api_upload(
        self,
        api_key: str,
        dataset_id: str,
        file_path: Path,
    ) -> dict[str, Any]:
        """Upload file via Dataset API (no console login needed)."""
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            response = self._http.post(
                f"{self.base_url}/v1/datasets/{dataset_id}/document/create-by-file",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (file_path.name, f, mime_type)},
                data={
                    "data": json.dumps(
                        {
                            "indexing_technique": "high_quality",
                            "process_rule": {"mode": "automatic"},
                        }
                    )
                },
            )
        raise_for_dify_status(response)
        return response.json()

    # ── System ──────────────────────────────────────────────

    def system_features(self) -> dict[str, Any]:
        """Get system features (no auth needed)."""
        response = self._http.get(f"{self.base_url}/console/api/system-features")
        raise_for_dify_status(response)
        return response.json()

    def setup_status(self) -> dict[str, Any]:
        """Get setup status (no auth needed)."""
        response = self._http.get(f"{self.base_url}/console/api/setup")
        raise_for_dify_status(response)
        return response.json()
