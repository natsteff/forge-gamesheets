"""Injected, filesystem-backed workspace for portable Sheet Designer drafts."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.sheet_designer.model import (
    FORMAT_NAME,
    FORMAT_VERSION,
    MAX_DOCUMENT_BYTES,
    migrate_document,
    normalize_document,
)
from app.sheet_designer.sample import expedition_document


class FileDraftStore:
    """Persist independent FGS sheets atomically beneath an injected root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.drafts = root / "drafts"
        self.current_pointer = root / "current"
        self.legacy_path = root / "current.fgs"

    @property
    def path(self) -> Path:
        """Return the active draft path for compatibility with early callers."""
        return self._document_path(self._ensure_current())

    def load(self) -> dict:
        return self.load_document(self._ensure_current())

    def current_id(self) -> str:
        return self._ensure_current()

    def load_document(self, workspace_id: str) -> dict:
        path = self._document_path(workspace_id)
        try:
            payload = path.read_bytes()
        except FileNotFoundError as error:
            raise ValueError("Sheet not found.") from error
        if path.is_symlink() or len(payload) > MAX_DOCUMENT_BYTES:
            raise ValueError("Saved FGS draft is unavailable or exceeds its limit.")
        source = json.loads(payload)
        document = migrate_document(source)
        if document != source:
            backup = path.with_suffix(".fgs.v0.1-prototype.bak")
            if source.get("format_version") == "0.1-prototype" and not backup.exists():
                self._atomic_write(backup, payload)
            self._write_document(document, workspace_id=workspace_id)
        return document

    def save(self, document: dict) -> dict:
        normalized = migrate_document(document)
        workspace_id = self._ensure_current()
        self._write_document(normalized, workspace_id=workspace_id)
        self._write_pointer(workspace_id)
        return normalized

    def create(
        self, title: str, page_size: str = "letter", orientation: str = "portrait"
    ) -> dict:
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
            raise ValueError("Enter a sheet title between 1 and 160 characters.")
        title = title.strip()
        document_id = self._unique_id(title)
        document = normalize_document(
            {
                "format": FORMAT_NAME,
                "format_version": FORMAT_VERSION,
                "id": document_id,
                "title": title,
                "page": {"size": page_size, "orientation": orientation},
                "theme": {"accent": "#c84b24"},
                "rows": [
                    {
                        "id": "row-header",
                        "blocks": [
                            {
                                "id": "header-main",
                                "type": "header",
                                "title": title,
                                "subtitle": "",
                            }
                        ],
                    },
                    {
                        "id": "row-score",
                        "blocks": [
                            {
                                "id": "score-main",
                                "type": "score_table",
                                "title": "Score table",
                                "players": ["Player 1", "Player 2"],
                                "score_rows": ["Round 1", "Total"],
                                "show_total": False,
                                "total_label": "Total",
                            }
                        ],
                    },
                ],
            }
        )
        self._write_document(document, workspace_id=document_id)
        self._write_pointer(document_id)
        return document

    def import_document(self, source: dict) -> dict:
        """Add a portable FGS document without replacing the active draft."""
        document = migrate_document(source)
        workspace_id = self._unique_id(document["title"])
        self._write_document(document, workspace_id=workspace_id)
        self._write_pointer(workspace_id)
        return document

    def list_documents(self) -> dict:
        current_id = self._ensure_current()
        documents = []
        for path in self.drafts.glob("*.fgs"):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                document = self.load_document(path.stem)
            except (ValueError, json.JSONDecodeError):
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
            documents.append(
                {
                    "id": path.stem,
                    "title": document["title"],
                    "modified": modified,
                }
            )
        documents.sort(key=lambda item: (item["title"].casefold(), item["id"]))
        return {"current_id": current_id, "documents": documents}

    def list_livesheet_documents(self) -> list[dict]:
        """Return saved sheets explicitly enabled for interactive scoring."""
        ready = []
        for item in self.list_documents()["documents"]:
            try:
                document = self.load_document(item["id"])
            except (ValueError, json.JSONDecodeError):
                continue
            setting = document.get("extensions", {}).get(
                "io.github.natsteff.livesheet", {}
            )
            if setting.get("enabled") is True:
                ready.append({**item, "document": document})
        return ready

    def open(self, document_id: str) -> dict:
        document = self.load_document(document_id)
        self._write_pointer(document_id)
        return document

    def duplicate(self, document_id: str) -> dict:
        document = self.load_document(document_id)
        document["id"] = self._unique_id(f"{document['title']}-copy")
        document["title"] = f"{document['title']} copy"
        workspace_id = document["id"]
        self._write_document(document, workspace_id=workspace_id)
        self._write_pointer(workspace_id)
        return document

    def delete(self, document_id: str) -> dict:
        current_id = self._ensure_current()
        path = self._document_path(document_id)
        if not path.is_file() or path.is_symlink():
            raise ValueError("Sheet not found.")
        path.unlink()
        if document_id != current_id:
            return self.load_document(current_id)
        remaining = sorted(self.drafts.glob("*.fgs"))
        if remaining:
            return self.open(remaining[0].stem)
        return self.create("Untitled Game Sheet")

    def _ensure_current(self) -> str:
        try:
            document_id = self.current_pointer.read_text(encoding="utf-8").strip()
            if self._document_path(document_id).is_file():
                return document_id
        except (FileNotFoundError, ValueError):
            pass
        if self.legacy_path.is_file() and not self.legacy_path.is_symlink():
            payload = self.legacy_path.read_bytes()
            if len(payload) <= MAX_DOCUMENT_BYTES:
                document = migrate_document(json.loads(payload))
                workspace_id = document["id"]
                if self._document_path(workspace_id).exists():
                    workspace_id = self._unique_id(document["title"])
                self._write_document(document, workspace_id=workspace_id)
                self._write_pointer(workspace_id)
                return workspace_id
        document = expedition_document()
        workspace_id = document["id"]
        if self._document_path(workspace_id).exists():
            workspace_id = self._unique_id(document["title"])
        self._write_document(document, workspace_id=workspace_id)
        self._write_pointer(workspace_id)
        return workspace_id

    def _unique_id(self, title: str) -> str:
        stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
        while True:
            candidate = f"{stem or 'game-sheet'}-{uuid4().hex[:8]}"
            if not self._document_path(candidate).exists():
                return candidate

    def _document_path(self, document_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", document_id):
            raise ValueError("Invalid sheet ID.")
        return self.drafts / f"{document_id}.fgs"

    def _write_document(
        self, document: dict, *, workspace_id: str | None = None
    ) -> None:
        normalized = normalize_document(document)
        payload = (
            json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            )
            + b"\n"
        )
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise ValueError("FGS draft exceeds the format size limit.")
        self._atomic_write(
            self._document_path(workspace_id or normalized["id"]), payload
        )

    def _write_pointer(self, document_id: str) -> None:
        self._atomic_write(self.current_pointer, f"{document_id}\n".encode())

    @staticmethod
    def _atomic_write(destination: Path, payload: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
