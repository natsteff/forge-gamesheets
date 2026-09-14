"""HTTP adapter for the experimental sheet designer module."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app.sheet_designer.model import DocumentValidationError, normalize_document
from app.sheet_designer.rendering import PageOverflowError, render_pdf
from app.sheet_designer.storage import FileDraftStore

router = APIRouter()


def _store(request: Request) -> FileDraftStore:
    return request.app.state.sheet_designer_store


def _templates(request: Request):
    return request.app.state.sheet_designer_templates


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
        return JSONResponse(_store(request).delete(document_id))
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


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
    return FileResponse(
        Path(output),
        media_type="application/pdf",
        filename=_filename(current["title"], ".pdf"),
    )
