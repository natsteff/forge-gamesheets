"""Admin web workflow for portable game links."""

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.activity import record_activity
from app.library.link_portability import (
    FORMAT,
    VERSION,
    MetadataImport,
    apply_import,
    export_links,
    parse_export,
    parse_manifest,
    preview_import,
    scan_shortcuts,
)
from app.web import templates

router = APIRouter()


@router.get(
    "/settings/metadata-portability",
    response_class=HTMLResponse,
    name="link_portability",
)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="link_portability.html",
        context={"preview": None, "token": None, "source": None, "error": None},
    )


@router.get("/settings/metadata-portability/export", name="link_portability_export")
def export(request: Request):
    return Response(
        export_links(request.app.state.database, request.app.state.settings.data_path),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="forge-metadata-export.zip"'
        },
    )


@router.post(
    "/settings/metadata-portability/import/preview",
    response_class=HTMLResponse,
    name="link_manifest_preview",
)
async def manifest_preview(
    request: Request, export_file: UploadFile = File(...), policy: str = Form(...)
):
    try:
        payload = await export_file.read()
        package = parse_export(payload)
        return _preview(
            request,
            package.entries,
            policy,
            "Forge metadata export",
            artwork=package.artwork,
            upload=payload,
        )
    except ValueError as error:
        return _error(request, str(error))


@router.post(
    "/settings/metadata-portability/scan/preview",
    response_class=HTMLResponse,
    name="link_scan_preview",
)
def scan_preview(request: Request, policy: str = Form(...)):
    try:
        return _preview(
            request,
            scan_shortcuts(request.app.state.settings.library_path),
            policy,
            "Library shortcut scan",
        )
    except ValueError as error:
        return _error(request, str(error))


@router.post("/settings/metadata-portability/import/apply", name="link_import_apply")
def apply(request: Request, token: str = Form(...)):
    if not token.isalnum() or len(token) != 32:
        raise HTTPException(400, "Invalid import preview.")
    path = _pending_root(request) / f"{token}.json"
    try:
        if path.is_symlink():
            raise OSError("Unsafe preview path")
        pending = json.loads(path.read_text())
        policy = pending["policy"]
        upload_path = path.with_suffix(".upload")
        if pending.get("upload"):
            if upload_path.is_symlink():
                raise OSError("Unsafe preview upload path")
            package = parse_export(upload_path.read_bytes())
        else:
            entries = parse_manifest(
                json.dumps(
                    {
                        "format": FORMAT,
                        "format_version": VERSION,
                        "entries": pending["entries"],
                    }
                ).encode()
            )
            package = MetadataImport(entries)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(410, "Import preview expired.") from error
    path.unlink(missing_ok=True)
    upload_path.unlink(missing_ok=True)
    result = apply_import(
        request.app.state.database,
        package.entries,
        policy,
        package.artwork,
        request.app.state.settings.data_path,
    )
    record_activity(
        request.app.state.database,
        "game_links_imported",
        "Game links imported",
        detail=(
            f"{result.add} added, {result.replace} replaced, "
            f"{result.unchanged} unchanged, {result.skipped} skipped."
        ),
    )
    return RedirectResponse(
        f"/settings/metadata-portability?imported={result.add + result.replace}", 303
    )


def _preview(request, entries, policy, source, *, artwork=(), upload=None):
    result = preview_import(request.app.state.database, entries, policy, artwork)
    token = uuid4().hex
    root = _pending_root(request)
    root.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 3600
    for old in root.glob("*.json"):
        if not old.is_symlink() and old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
            old.with_suffix(".upload").unlink(missing_ok=True)
    pending = root / f"{token}.json"
    pending.write_text(
        json.dumps(
            {"policy": policy, "entries": entries, "upload": upload is not None}
        ),
        encoding="utf-8",
    )
    pending.chmod(0o600)
    if upload is not None:
        upload_path = pending.with_suffix(".upload")
        upload_path.write_bytes(upload)
        upload_path.chmod(0o600)
    return templates.TemplateResponse(
        request=request,
        name="link_portability.html",
        context={
            "preview": result,
            "token": token,
            "source": source,
            "policy": policy,
            "error": None,
        },
    )


def _error(request, error):
    return templates.TemplateResponse(
        request=request,
        name="link_portability.html",
        status_code=422,
        context={"preview": None, "token": None, "source": None, "error": error},
    )


def _pending_root(request) -> Path:
    return request.app.state.settings.data_path / "link-imports"
