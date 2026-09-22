"""HTTP adapter for the experimental sheet designer module."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)

from app.library.previews import PreviewUnavailable
from app.library.repository import list_games
from app.sheet_designer.model import DocumentValidationError, normalize_document
from app.sheet_designer.previews import cached_sheet_preview
from app.sheet_designer.shared_rendering import (
    PageOverflowError,
    RendererUnavailableError,
    render_pdf,
)
from app.sheet_designer.storage import FileDraftStore
from app.sheet_game_associations import (
    get_association,
    remove_association,
    save_association,
)

router = APIRouter()


def _store(request: Request) -> FileDraftStore:
    return request.app.state.sheet_designer_store


def _templates(request: Request):
    return request.app.state.sheet_designer_templates


def _database(request: Request):
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(404, "Game associations require the full application.")
    return database


def _filename(title: str, suffix: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{stem or 'game-sheet'}{suffix}"


@router.get("/sheet-designer", response_class=HTMLResponse, name="sheet_designer")
def designer(request: Request):
    return _templates(request).TemplateResponse(
        request=request,
        name=request.app.state.sheet_designer_template,
        context={"standalone": request.app.state.sheet_designer_standalone},
    )


@router.get("/sheet-designer/document", name="sheet_designer_document")
def document(request: Request):
    try:
        return JSONResponse(_store(request).load())
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(
            500, "The saved sheet draft could not be loaded."
        ) from error


@router.post("/sheet-designer/document", name="sheet_designer_save")
async def save_document(request: Request):
    try:
        return JSONResponse(_store(request).save(await request.json()))
    except (DocumentValidationError, json.JSONDecodeError) as error:
        raise HTTPException(422, str(error)) from error


@router.get("/sheet-designer/documents", name="sheet_designer_documents")
def documents(request: Request):
    return JSONResponse(_store(request).list_documents())


@router.post("/sheet-designer/documents", name="sheet_designer_create")
async def create_document(request: Request):
    try:
        payload = await request.json()
        document = _store(request).create(
            payload.get("title", ""),
            payload.get("page_size", "letter"),
            payload.get("orientation", "portrait"),
        )
        return JSONResponse(document, status_code=201)
    except (AttributeError, DocumentValidationError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/sheet-designer/documents/import", name="sheet_designer_import")
async def import_document(request: Request):
    try:
        return JSONResponse(
            _store(request).import_document(await request.json()), status_code=201
        )
    except (DocumentValidationError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/sheet-designer/documents/{document_id}/open", name="sheet_designer_open")
def open_document(request: Request, document_id: str):
    try:
        return JSONResponse(_store(request).open(document_id))
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.post(
    "/sheet-designer/documents/{document_id}/duplicate",
    name="sheet_designer_duplicate",
)
def duplicate_document(request: Request, document_id: str):
    try:
        return JSONResponse(_store(request).duplicate(document_id), status_code=201)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.delete("/sheet-designer/documents/{document_id}", name="sheet_designer_delete")
def delete_document(request: Request, document_id: str):
    try:
        document = _store(request).delete(document_id)
        database = getattr(request.app.state, "database", None)
        if database is not None:
            remove_association(database, document_id)
        return JSONResponse(document)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.get(
    "/sheet-designer/documents/{document_id}/edit",
    response_class=RedirectResponse,
    name="sheet_designer_edit_document",
)
def edit_document(request: Request, document_id: str):
    try:
        _store(request).open(document_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    return RedirectResponse("/sheet-designer?resume=1", status_code=303)


def _suggested_game_query(title: str) -> str:
    query = re.sub(
        r"\s+(?:game\s*sheet|score\s*sheet|scores?)\s*$", "", title, flags=re.I
    ).strip()
    return query or title.strip()


@router.get("/sheet-designer/game-association", name="sheet_game_association")
def game_association(request: Request, q: str | None = None):
    workspace_id = _store(request).current_id()
    association = get_association(_database(request), workspace_id)
    suggested_query = (
        q.strip()[:200]
        if q is not None
        else (
            association.game_title
            if association
            else _suggested_game_query(_store(request).load()["title"])
        )
    )
    games = list_games(_database(request), suggested_query or None)
    normalized_query = " ".join(suggested_query.casefold().split())
    exact = [
        game
        for game in games
        if " ".join(game.title.casefold().split()) == normalized_query
    ]
    return JSONResponse(
        {
            "workspace_id": workspace_id,
            "query": suggested_query,
            "suggested_game_id": exact[0].id if len(exact) == 1 else None,
            "association": (
                {
                    "game_id": association.game_id,
                    "game_title": association.game_title,
                    "available": association.game_id is not None,
                }
                if association
                else None
            ),
            "games": [{"id": game.id, "title": game.title} for game in games],
        }
    )


@router.get(
    "/sheet-designer/documents/{document_id}/preview.webp",
    response_class=FileResponse,
    name="sheet_designer_preview",
)
def sheet_designer_preview(request: Request, document_id: str):
    try:
        preview = cached_sheet_preview(
            request.app.state.settings.data_path, _store(request), document_id
        )
    except (PreviewUnavailable, ValueError):
        raise HTTPException(404, "GameSheet preview unavailable.") from None
    return FileResponse(preview, media_type="image/webp")


@router.post("/sheet-designer/game-association", name="sheet_game_association_save")
async def game_association_save(request: Request):
    payload = await request.json()
    try:
        game_id = int(payload.get("game_id"))
        save_association(_database(request), _store(request).current_id(), game_id)
    except (AttributeError, TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return JSONResponse({"saved": True})


@router.delete(
    "/sheet-designer/game-association", name="sheet_game_association_remove"
)
def game_association_remove(request: Request):
    remove_association(_database(request), _store(request).current_id())
    return JSONResponse({"removed": True})


@router.get("/sheet-designer/export.fgs", name="sheet_designer_fgs")
def export_fgs(request: Request):
    current = _store(request).load()
    body = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    disposition = f'attachment; filename="{_filename(current["title"], ".fgs")}"'
    return Response(
        body,
        media_type="application/vnd.forge-gamesheets+json",
        headers={"Content-Disposition": disposition},
    )


@router.get("/sheet-designer/export.pdf", name="sheet_designer_pdf")
def export_pdf(request: Request):
    current = normalize_document(_store(request).load())
    output = _store(request).root / "current.pdf"
    try:
        render_pdf(current, output)
    except PageOverflowError as error:
        raise HTTPException(409, str(error)) from error
    except RendererUnavailableError as error:
        raise HTTPException(503, str(error)) from error
    return FileResponse(
        Path(output),
        media_type="application/pdf",
        filename=_filename(current["title"], ".pdf"),
    )
