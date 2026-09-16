"""Server-rendered launch and scoring workflow for temporary LiveSheets."""

from __future__ import annotations

import time
from io import BytesIO
from urllib.parse import quote

import qrcode
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.livesheet import (
    LiveSheetError,
    SessionMode,
    claim_player,
    create_session,
    end_session,
    session_state,
    update_checklist,
    update_notes,
    update_player_name,
    update_score,
)
from app.web import templates

router = APIRouter()


def _now() -> int:
    return int(time.time())


def _ready(request: Request) -> list[dict]:
    return request.app.state.sheet_designer_store.list_livesheet_documents()


def _document(request: Request, document_id: str) -> dict:
    for item in _ready(request):
        if item["id"] == document_id:
            return item["document"]
    raise HTTPException(404, "LiveSheet-ready GameSheet not found.")


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _state(request: Request, session_id: str, token: str) -> dict:
    try:
        state = session_state(request.app.state.database, session_id, token, now=_now())
    except LiveSheetError as error:
        raise HTTPException(404, str(error)) from error
    state["score_tables"] = [
        {
            **block,
            "labels": list(block["score_rows"])
            + ([block["total_label"]] if block["show_total"] else []),
        }
        for row in state["document"]["rows"]
        for block in row["blocks"]
        if block["type"] == "score_table"
    ]
    state["token"] = token
    return state


@router.get("/livesheets", response_class=HTMLResponse, name="livesheets_home")
def livesheets_home(request: Request):
    return templates.TemplateResponse(
        request=request, name="livesheets.html", context={"sheets": _ready(request)}
    )


@router.get(
    "/livesheets/{document_id}/setup",
    response_class=HTMLResponse,
    name="livesheet_setup",
)
def livesheet_setup(request: Request, document_id: str):
    return templates.TemplateResponse(
        request=request,
        name="livesheet_setup.html",
        context={"sheet": _document(request, document_id), "workspace_id": document_id},
    )


@router.post("/livesheets/{document_id}/start", name="livesheet_start")
def livesheet_start(
    request: Request,
    document_id: str,
    mode: str = Form(...),
    player_count: int = Form(...),
    host_position: int | None = Form(None),
    host_name: str = Form(""),
):
    try:
        credentials = create_session(
            request.app.state.database,
            _document(request, document_id),
            mode=mode,
            player_count=player_count,
            host_position=host_position if mode == SessionMode.INDIVIDUAL else None,
            now=_now(),
        )
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    if host_name.strip():
        player_position = host_position or 1
        name_token = (
            credentials.host_player_token
            if mode == SessionMode.INDIVIDUAL
            else credentials.host_token
        )
        try:
            update_player_name(
                request.app.state.database,
                credentials.session_id,
                name_token or "",
                player_position=player_position,
                name=host_name.strip(),
                now=_now(),
            )
        except LiveSheetError as error:
            end_session(
                request.app.state.database,
                credentials.session_id,
                credentials.host_token,
                now=_now(),
            )
            raise HTTPException(422, str(error)) from error
    target = (
        f"/livesheets/{credentials.session_id}/host?t={quote(credentials.host_token)}"
    )
    if credentials.host_player_token:
        target += f"&p={quote(credentials.host_player_token)}"
    response = _redirect(target)
    response.set_cookie(
        f"livesheet_invite_{credentials.session_id}",
        credentials.invite_token,
        max_age=24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@router.get(
    "/livesheets/{session_id}/host",
    response_class=HTMLResponse,
    name="livesheet_host",
)
def livesheet_host(request: Request, session_id: str, t: str, p: str | None = None):
    state = _state(request, session_id, t)
    if p:
        player_state = _state(request, session_id, p)
        state["player_position"] = player_state["player_position"]
    invite = request.cookies.get(f"livesheet_invite_{session_id}")
    if not invite:
        raise HTTPException(404, "This host link is incomplete.")
    join_url = (
        str(request.base_url).rstrip("/")
        + f"/livesheets/{session_id}/join?t={quote(invite)}"
    )
    return templates.TemplateResponse(
        request=request,
        name="livesheet_play.html",
        context={"session": state, "join_url": join_url, "player_token": p},
    )


@router.post("/livesheets/{session_id}/host/score", name="livesheet_host_score")
def livesheet_host_score(
    request: Request,
    session_id: str,
    token: str = Form(...),
    player_token: str = Form(""),
    block_id: str = Form(...),
    row_index: int = Form(...),
    player_position: int = Form(...),
    value: int = Form(...),
):
    scoring_token = player_token or token
    try:
        update_score(
            request.app.state.database,
            session_id,
            scoring_token,
            block_id=block_id,
            row_index=row_index,
            player_position=player_position,
            value=value,
            now=_now(),
        )
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    suffix = f"&p={quote(player_token)}" if player_token else ""
    return _redirect(f"/livesheets/{session_id}/host?t={quote(token)}{suffix}")


@router.post("/livesheets/{session_id}/end", name="livesheet_end")
def livesheet_end(session_id: str, request: Request, token: str = Form(...)):
    try:
        end_session(request.app.state.database, session_id, token, now=_now())
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    return _redirect("/livesheets")


@router.get(
    "/livesheets/{session_id}/join",
    response_class=HTMLResponse,
    name="livesheet_join",
)
def livesheet_join(request: Request, session_id: str, t: str):
    state = _state(request, session_id, t)
    return templates.TemplateResponse(
        request=request,
        name="livesheet_join.html",
        context={"session": state},
    )


@router.post("/livesheets/{session_id}/claim", name="livesheet_claim")
def livesheet_claim(
    request: Request,
    session_id: str,
    invite_token: str = Form(...),
    position: int = Form(...),
    name: str = Form(...),
):
    try:
        token = claim_player(
            request.app.state.database,
            session_id,
            invite_token,
            position=position,
            name=name,
            now=_now(),
        )
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    return _redirect(f"/livesheets/{session_id}/play?t={quote(token)}")


@router.get(
    "/livesheets/{session_id}/play",
    response_class=HTMLResponse,
    name="livesheet_player",
)
def livesheet_player(request: Request, session_id: str, t: str):
    state = _state(request, session_id, t)
    return templates.TemplateResponse(
        request=request,
        name="livesheet_play.html",
        context={"session": state, "join_url": None, "player_token": t},
    )


@router.post("/livesheets/{session_id}/play/score", name="livesheet_player_score")
def livesheet_player_score(
    request: Request,
    session_id: str,
    token: str = Form(...),
    block_id: str = Form(...),
    row_index: int = Form(...),
    player_position: int = Form(...),
    value: int = Form(...),
):
    try:
        update_score(
            request.app.state.database,
            session_id,
            token,
            block_id=block_id,
            row_index=row_index,
            player_position=player_position,
            value=value,
            now=_now(),
        )
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    return _redirect(f"/livesheets/{session_id}/play?t={quote(token)}")


@router.post("/livesheets/{session_id}/name", name="livesheet_name")
def livesheet_name(
    request: Request,
    session_id: str,
    token: str = Form(...),
    host_token: str = Form(""),
    player_position: int = Form(...),
    name: str = Form(...),
):
    try:
        update_player_name(
            request.app.state.database,
            session_id,
            token,
            player_position=player_position,
            name=name,
            now=_now(),
        )
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    if host_token:
        return _redirect(
            f"/livesheets/{session_id}/host?t={quote(host_token)}&p={quote(token)}"
        )
    return _redirect(f"/livesheets/{session_id}/play?t={quote(token)}")


@router.post("/livesheets/{session_id}/checklist", name="livesheet_checklist")
def livesheet_checklist(
    request: Request,
    session_id: str,
    token: str = Form(...),
    player_token: str = Form(""),
    block_id: str = Form(...),
    item_index: int = Form(...),
    checked: bool = Form(False),
):
    try:
        update_checklist(
            request.app.state.database,
            session_id,
            token,
            block_id=block_id,
            item_index=item_index,
            checked=checked,
            now=_now(),
        )
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    suffix = f"&p={quote(player_token)}" if player_token else ""
    return _redirect(f"/livesheets/{session_id}/host?t={quote(token)}{suffix}")


@router.post("/livesheets/{session_id}/notes", name="livesheet_notes")
def livesheet_notes(
    request: Request,
    session_id: str,
    token: str = Form(...),
    player_token: str = Form(""),
    block_id: str = Form(...),
    value: str = Form(""),
):
    try:
        update_notes(
            request.app.state.database,
            session_id,
            token,
            block_id=block_id,
            value=value,
            now=_now(),
        )
    except LiveSheetError as error:
        raise HTTPException(422, str(error)) from error
    suffix = f"&p={quote(player_token)}" if player_token else ""
    return _redirect(f"/livesheets/{session_id}/host?t={quote(token)}{suffix}")


@router.get("/livesheets/{session_id}/qr", name="livesheet_qr")
def livesheet_qr(request: Request, session_id: str, t: str):
    _state(request, session_id, t)
    target = str(request.url_for("livesheet_join", session_id=session_id)) + (
        f"?t={quote(t)}"
    )
    image = qrcode.make(target)
    output = BytesIO()
    image.save(output, format="PNG")
    return Response(output.getvalue(), media_type="image/png")
