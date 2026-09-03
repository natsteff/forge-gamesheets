"""Server-rendered web interface for the indexed library."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.bgg.client import BggApiError, BggClient
from app.bgg.matching import enrich_game
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    delete_bgg_association,
    get_bgg_association,
    save_bgg_association,
)
from app.database import Database
from app.library.artwork import (
    MAX_ARTWORK_BYTES,
    cached_game_artwork,
    delete_uploaded_artwork,
    save_uploaded_artwork,
)
from app.library.cache import cleanup_managed_files
from app.library.filename_parser import ResourceCategory
from app.library.files import (
    ResourceFileMissing,
    UnsafeResourcePath,
    resolve_resource_pdf,
)
from app.library.previews import PreviewUnavailable, cached_resource_preview
from app.library.reconciliation import ReconciliationError, reconcile_scan
from app.library.repository import (
    GameDetail,
    IndexedResource,
    create_game_category,
    delete_game_category,
    get_game,
    get_game_artwork,
    get_game_category,
    get_resource,
    list_favorite_resources,
    list_game_categories,
    list_games,
    list_games_in_category,
    list_pinned_resources,
    list_recent_resources,
    list_resource_activity,
    record_resource_use,
    rename_game_category,
    reset_game_artwork_override,
    reset_game_title_override,
    reset_resource_override,
    save_game_artwork_override,
    save_game_categories,
    save_game_title_override,
    save_resource_override,
    set_resource_favorite,
    toggle_resource_pin,
)
from app.library.reprints import (
    ReprintGenerationError,
    existing_forge_reprint,
    generate_forge_reprint,
    resource_reprint_url,
)
from app.library.scanner import LibraryScanError, ScanIssue, scan_library
from app.preferences import (
    DEFAULT_FOOTER_TEXT,
    MAX_FOOTER_LENGTH,
    MAX_RECENT_LIMIT,
    ApplicationPreferences,
    get_preferences,
    save_preferences,
)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_CATEGORY_ORDER = (
    ResourceCategory.RULES,
    ResourceCategory.SCORE_SHEET,
    ResourceCategory.REFERENCE,
    ResourceCategory.ANSWER_SHEET,
    ResourceCategory.TOURNAMENT,
    ResourceCategory.SETUP,
    ResourceCategory.OTHER,
)

_CATEGORY_LABELS = {
    ResourceCategory.RULES: "Rules",
    ResourceCategory.SCORE_SHEET: "Score Sheets",
    ResourceCategory.REFERENCE: "Player References",
    ResourceCategory.ANSWER_SHEET: "Answer Sheets",
    ResourceCategory.TOURNAMENT: "Tournament Materials",
    ResourceCategory.SETUP: "Setup",
    ResourceCategory.OTHER: "Other",
}

MAX_GAME_CATEGORY_NAME_LENGTH = 60
RESERVED_GAME_CATEGORY_NAMES = frozenset({"all games", "uncategorized"})


def _template_preferences(request: Request) -> ApplicationPreferences:
    """Expose cached preferences to every base template."""
    if not hasattr(request.state, "application_preferences"):
        request.state.application_preferences = get_preferences(
            _database(request)
        )
    return request.state.application_preferences


templates.env.globals["application_preferences"] = _template_preferences


@router.get("/", response_class=HTMLResponse, name="library_home")
def library_home(request: Request) -> HTMLResponse:
    query = request.query_params.get("q", "").strip()[:200]
    games = list_games(_database(request), query or None)
    pinned = () if query else list_pinned_resources(_database(request))
    uncategorized_count = len(list_games_in_category(_database(request), None))
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={
            "games": games,
            "pinned": pinned,
            "game_categories": list_game_categories(_database(request)),
            "total_game_count": len(games),
            "uncategorized_count": uncategorized_count,
            "query": query,
            "scan_status": request.query_params.get("scan"),
            "scan_changes": request.query_params.get("changes"),
            "scan_issues": request.app.state.scan_issues,
        },
    )


@router.get("/categories", response_class=HTMLResponse, name="categories_home")
def categories_home(request: Request) -> HTMLResponse:
    """Show the complete game-category directory."""
    games = list_games(_database(request))
    return templates.TemplateResponse(
        request=request,
        name="categories.html",
        context={
            "game_categories": list_game_categories(_database(request)),
            "total_game_count": len(games),
            "uncategorized_count": len(
                list_games_in_category(_database(request), None)
            ),
        },
    )


@router.get("/games", response_class=HTMLResponse, name="all_games")
def all_games(request: Request) -> HTMLResponse:
    """Show every indexed game in one alphabetical list."""
    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": "All Games",
            "games": list_games(_database(request)),
            "page_descriptor": "Complete library",
        },
    )


@router.get(
    "/categories/{category_key}",
    response_class=HTMLResponse,
    name="category_detail",
)
def category_detail(request: Request, category_key: str) -> HTMLResponse:
    """List games assigned to a selected category."""
    if category_key == "uncategorized":
        category_name = "Uncategorized"
        games = list_games_in_category(_database(request), None)
    else:
        try:
            category_id = int(category_key)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="Category not found") from error
        category = get_game_category(_database(request), category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")
        category_name = category.name
        games = list_games_in_category(_database(request), category.id)
    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": category_name,
            "games": games,
            "page_descriptor": "Game category",
        },
    )


@router.get("/pinned", response_class=HTMLResponse, name="pinned_home")
def pinned_home(request: Request) -> HTMLResponse:
    """Show and manage the resources pinned to the Library homepage."""
    pinned = list_pinned_resources(_database(request))
    return templates.TemplateResponse(
        request=request,
        name="pinned.html",
        context={
            "pinned": pinned,
            "pin_status": request.query_params.get("pin"),
        },
    )


@router.get("/favorites", response_class=HTMLResponse, name="favorites_home")
def favorites_home(request: Request) -> HTMLResponse:
    """Show every resource the user has marked as a favorite."""
    return templates.TemplateResponse(
        request=request,
        name="favorites.html",
        context={
            "favorites": list_favorite_resources(_database(request)),
            "pin_status": request.query_params.get("pin"),
        },
    )


@router.get("/recent", response_class=HTMLResponse, name="recent_home")
def recent_home(request: Request) -> HTMLResponse:
    """Show the configured number of recently used resources."""
    preferences = get_preferences(_database(request))
    return templates.TemplateResponse(
        request=request,
        name="recent.html",
        context={
            "recent": list_recent_resources(
                _database(request), limit=preferences.recent_limit
            )
            if preferences.recent_limit
            else (),
            "recent_limit": preferences.recent_limit,
        },
    )


@router.get("/settings", response_class=HTMLResponse, name="settings_home")
def settings_home(request: Request) -> HTMLResponse:
    """Show the limited Phase 1 application settings."""
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "preferences": get_preferences(_database(request)),
            "game_categories": list_game_categories(_database(request)),
            "status": request.query_params.get("status"),
            "error": request.query_params.get("error"),
            "max_footer_length": MAX_FOOTER_LENGTH,
            "max_recent_limit": MAX_RECENT_LIMIT,
            "max_category_name_length": MAX_GAME_CATEGORY_NAME_LENGTH,
            "timezone_names": _timezone_names(),
            "build_info": request.app.state.build_info,
            "bgg_configured": bool(request.app.state.settings.bgg_api_token),
        },
    )


@router.post("/settings/preferences", response_class=RedirectResponse)
async def settings_preferences_save(request: Request) -> RedirectResponse:
    """Validate and save library-wide display preferences."""
    form = await request.form()
    current_preferences = get_preferences(_database(request))
    footer_text = str(form.get("footer_text", "")).strip()
    timezone_name = str(
        form.get("timezone_name", current_preferences.timezone_name)
    ).strip()
    try:
        recent_limit = int(str(form.get("recent_limit", "")))
    except ValueError:
        return _settings_redirect(error="invalid-preferences")
    if (
        len(footer_text) > MAX_FOOTER_LENGTH
        or not 0 <= recent_limit <= MAX_RECENT_LIMIT
        or not _valid_timezone(timezone_name)
    ):
        return _settings_redirect(error="invalid-preferences")
    save_preferences(
        _database(request),
        footer_text=footer_text,
        recent_limit=recent_limit,
        timezone_name=timezone_name,
    )
    return _settings_redirect(status="preferences-saved")


@router.post("/settings/footer/reset", response_class=RedirectResponse)
def settings_footer_reset(request: Request) -> RedirectResponse:
    """Restore the Forge GameSheets footer while preserving other settings."""
    preferences = get_preferences(_database(request))
    save_preferences(
        _database(request),
        footer_text=DEFAULT_FOOTER_TEXT,
        recent_limit=preferences.recent_limit,
        timezone_name=preferences.timezone_name,
    )
    return _settings_redirect(status="footer-restored")


@router.post("/settings/categories", response_class=RedirectResponse)
async def settings_category_create(request: Request) -> RedirectResponse:
    """Create a user-managed game category."""
    form = await request.form()
    name = _normalized_category_name(form.get("name"))
    if name is None:
        return _settings_redirect(error="invalid-category")
    if create_game_category(_database(request), name=name) is None:
        return _settings_redirect(error="duplicate-category")
    return _settings_redirect(status="category-created")


@router.post(
    "/settings/categories/{category_id}/rename",
    response_class=RedirectResponse,
)
async def settings_category_rename(
    request: Request, category_id: int
) -> RedirectResponse:
    """Rename a game category without changing its assignments."""
    form = await request.form()
    name = _normalized_category_name(form.get("name"))
    if name is None:
        return _settings_redirect(error="invalid-category")
    result = rename_game_category(_database(request), category_id, name=name)
    if result == "duplicate":
        return _settings_redirect(error="duplicate-category")
    if result == "missing":
        raise HTTPException(status_code=404, detail="Category not found")
    return _settings_redirect(status="category-renamed")


@router.post(
    "/settings/categories/{category_id}/delete",
    response_class=RedirectResponse,
)
def settings_category_delete(
    request: Request, category_id: int
) -> RedirectResponse:
    """Delete a category but never its games or files."""
    if not delete_game_category(_database(request), category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    return _settings_redirect(status="category-deleted")


@router.post("/rescan", response_class=RedirectResponse, name="library_rescan")
def library_rescan(request: Request) -> RedirectResponse:
    """Synchronize the SQLite index with the current filesystem library."""
    settings = request.app.state.settings
    try:
        scan_result = scan_library(settings.library_path)
        summary = reconcile_scan(_database(request), scan_result)
    except ReconciliationError:
        request.app.state.scan_issues = scan_result.issues
        query = urlencode({"scan": "partial", "issues": len(scan_result.issues)})
        return RedirectResponse(url=f"/?{query}", status_code=303)
    except LibraryScanError:
        request.app.state.scan_issues = (
            ScanIssue(Path("Library root"), "The library could not be read."),
        )
        return RedirectResponse(url="/?scan=failed&issues=1", status_code=303)

    request.app.state.scan_issues = ()
    request.app.state.last_reconciliation = summary
    cleanup_managed_files(_database(request), settings.data_path)
    change_count = sum(
        (
            summary.games_added,
            summary.games_updated,
            summary.games_removed,
            summary.resources_added,
            summary.resources_updated,
            summary.resources_removed,
        )
    )
    query = urlencode({"scan": "complete", "changes": change_count})
    return RedirectResponse(url=f"/?{query}", status_code=303)


@router.get("/history", response_class=HTMLResponse, name="activity_history")
def activity_history(request: Request) -> HTMLResponse:
    """Show recent successful PDF actions stored on this server."""
    preferences = get_preferences(_database(request))
    activity = tuple(
        (
            event,
            _format_local_timestamp(event.occurred_at, preferences.timezone_name),
        )
        for event in list_resource_activity(_database(request))
    )
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={"activity": activity, "timezone_name": preferences.timezone_name},
    )


@router.post(
    "/resources/{resource_id}/favorite",
    response_class=RedirectResponse,
    name="resource_favorite",
)
def resource_favorite(request: Request, resource_id: int) -> RedirectResponse:
    """Toggle a resource favorite and return to its game page."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    set_resource_favorite(
        _database(request), resource_id, favorite=not resource.is_favorite
    )
    return RedirectResponse(
        url=f"/games/{resource.game_id}#resource-{resource.id}", status_code=303
    )


@router.post(
    "/resources/{resource_id}/pin",
    response_class=RedirectResponse,
    name="resource_pin",
)
async def resource_pin(request: Request, resource_id: int) -> RedirectResponse:
    """Toggle homepage pinning while enforcing the ten-resource limit."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    result = toggle_resource_pin(_database(request), resource_id)
    form = await request.form()
    destination = str(form.get("return_to", "game"))
    destinations = {
        "favorites": "/favorites",
        "pinned": "/pinned",
        "game": f"/games/{resource.game_id}#resource-{resource.id}",
    }
    if destination not in destinations:
        destination = "game"
    target = destinations[destination]
    if result == "limit":
        if destination == "game":
            target = (
                f"/games/{resource.game_id}?pin=limit#resource-{resource.id}"
            )
        else:
            target = f"{target}?pin=limit"
    return RedirectResponse(url=target, status_code=303)


@router.get(
    "/resources/{resource_id}/edit",
    response_class=HTMLResponse,
    name="resource_edit",
)
def resource_edit(request: Request, resource_id: int) -> HTMLResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return templates.TemplateResponse(
        request=request,
        name="resource_edit.html",
        context={
            "resource": resource,
            "categories": tuple(
                (category.value, _CATEGORY_LABELS[category])
                for category in _CATEGORY_ORDER
            ),
        },
    )


@router.post(
    "/resources/{resource_id}/edit",
    response_class=RedirectResponse,
)
async def resource_edit_save(
    request: Request, resource_id: int
) -> RedirectResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    form = await request.form()
    title = str(form.get("title", "")).strip()
    variant = str(form.get("variant", "")).strip() or None
    try:
        category = ResourceCategory(str(form.get("category", "")))
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="Invalid resource category"
        ) from error
    if not title or len(title) > 200 or (variant and len(variant) > 200):
        raise HTTPException(status_code=422, detail="Invalid resource metadata")
    save_resource_override(
        _database(request),
        resource_id,
        title=title,
        category=category,
        variant=variant,
    )
    return RedirectResponse(
        url=f"/games/{resource.game_id}#resource-{resource.id}", status_code=303
    )


@router.post(
    "/resources/{resource_id}/reset",
    response_class=RedirectResponse,
    name="resource_reset",
)
def resource_reset(request: Request, resource_id: int) -> RedirectResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    reset_resource_override(_database(request), resource_id)
    return RedirectResponse(
        url=f"/games/{resource.game_id}#resource-{resource.id}", status_code=303
    )


@router.get("/games/{game_id}", response_class=HTMLResponse, name="game_detail")
def game_detail(request: Request, game_id: int) -> HTMLResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    grouped: defaultdict[ResourceCategory, list[IndexedResource]] = defaultdict(list)
    for resource in game.resources:
        grouped[resource.category].append(resource)
    sections = tuple(
        (_CATEGORY_LABELS[category], grouped[category])
        for category in _CATEGORY_ORDER
        if grouped[category]
    )
    unavailable_resource_ids: set[int] = set()
    for resource in game.resources:
        try:
            resolve_resource_pdf(
                request.app.state.settings.library_path, resource.relative_path
            )
        except (ResourceFileMissing, UnsafeResourcePath):
            unavailable_resource_ids.add(resource.id)

    return templates.TemplateResponse(
        request=request,
        name="game.html",
        context={
            "game": game,
            "sections": sections,
            "unavailable_resource_ids": unavailable_resource_ids,
            "pin_status": request.query_params.get("pin"),
        },
    )


@router.get(
    "/games/{game_id}/edit",
    response_class=HTMLResponse,
    name="game_edit",
)
def game_edit(request: Request, game_id: int) -> HTMLResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return _game_edit_response(request, game)


@router.post("/games/{game_id}/edit", response_class=RedirectResponse)
async def game_edit_save(request: Request, game_id: int) -> RedirectResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    form = await request.form()
    title = str(form.get("title", "")).strip()
    raw_category_ids = form.getlist("category_ids")
    if not title or len(title) > 200:
        raise HTTPException(status_code=422, detail="Invalid game title")
    try:
        category_ids = tuple(int(value) for value in raw_category_ids)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid game category") from error
    available_ids = {
        category.id for category in list_game_categories(_database(request))
    }
    if any(category_id not in available_ids for category_id in category_ids):
        raise HTTPException(status_code=422, detail="Invalid game category")
    save_game_title_override(_database(request), game_id, title=title)
    save_game_categories(_database(request), game_id, category_ids=category_ids)
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)


@router.post(
    "/games/{game_id}/reset",
    response_class=RedirectResponse,
    name="game_reset",
)
def game_reset(request: Request, game_id: int) -> RedirectResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    reset_game_title_override(_database(request), game_id)
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)


@router.get(
    "/games/{game_id}/artwork",
    response_class=FileResponse,
    name="game_artwork",
)
def game_artwork(request: Request, game_id: int) -> FileResponse:
    artwork = get_game_artwork(_database(request), game_id)
    if artwork is None:
        raise HTTPException(status_code=404, detail="Game artwork not found")
    settings = request.app.state.settings
    try:
        cache_path = cached_game_artwork(
            settings.library_path, settings.data_path, artwork
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410, detail="Game artwork was removed"
        ) from error
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=404, detail="Game artwork not found") from error
    return FileResponse(
        cache_path,
        media_type="image/webp",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/games/{game_id}/artwork",
    response_class=RedirectResponse,
    name="game_artwork_upload",
)
async def game_artwork_upload(
    request: Request,
    game_id: int,
    artwork_file: UploadFile = File(...),
) -> RedirectResponse:
    if get_game(_database(request), game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    content = await artwork_file.read(MAX_ARTWORK_BYTES + 1)
    try:
        artwork = save_uploaded_artwork(
            request.app.state.settings.data_path, game_id, content
        )
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    save_game_artwork_override(_database(request), artwork)
    return RedirectResponse(url=f"/games/{game_id}/edit", status_code=303)


@router.post(
    "/games/{game_id}/artwork/reset",
    response_class=RedirectResponse,
    name="game_artwork_reset",
)
def game_artwork_reset(request: Request, game_id: int) -> RedirectResponse:
    artwork = get_game_artwork(_database(request), game_id)
    if artwork is None or artwork.source != "data":
        raise HTTPException(status_code=404, detail="Uploaded artwork not found")
    reset_game_artwork_override(_database(request), game_id)
    delete_uploaded_artwork(request.app.state.settings.data_path, artwork)
    return RedirectResponse(url=f"/games/{game_id}/edit", status_code=303)


@router.post(
    "/games/{game_id}/bgg/find",
    response_class=HTMLResponse,
    name="game_bgg_find",
)
async def game_bgg_find(request: Request, game_id: int) -> HTMLResponse:
    """Search BGG only after an explicit user action and show candidates."""
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    client = _bgg_client(request)
    if client is None:
        return _game_edit_response(request, game, bgg_error="not-configured")
    form = await request.form()
    query = " ".join(str(form.get("query", "")).split())
    if not query or len(query) > 200:
        return _game_edit_response(request, game, bgg_error="invalid-query")
    try:
        candidates = client.search_games(query)
    except BggApiError:
        return _game_edit_response(request, game, bgg_error="lookup-failed")
    return _game_edit_response(
        request,
        game,
        bgg_candidates=candidates,
        bgg_query=query,
        bgg_error="no-results" if not candidates else None,
    )


@router.post(
    "/games/{game_id}/bgg/select",
    response_class=RedirectResponse,
    name="game_bgg_select",
)
async def game_bgg_select(request: Request, game_id: int) -> RedirectResponse:
    """Persist a BGG item explicitly selected by the library operator."""
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    client = _bgg_client(request)
    if client is None:
        return _game_edit_redirect(game_id, bgg_error="not-configured")
    form = await request.form()
    try:
        bgg_id = int(str(form.get("bgg_id", "")))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid BGG ID") from None
    if bgg_id <= 0:
        raise HTTPException(status_code=422, detail="Invalid BGG ID")
    try:
        details = client.get_game(bgg_id)
    except BggApiError:
        return _game_edit_redirect(game_id, bgg_error="lookup-failed")
    if details is None:
        return _game_edit_redirect(game_id, bgg_error="not-found")
    existing = get_bgg_association(_database(request), game_id)
    association = BggAssociation(
        game_id=game_id,
        lookup_enabled=existing.lookup_enabled if existing else True,
        match_state=BggMatchState.MANUAL,
        source_title=game.detected_title,
        bgg_id=details.id,
        match_confidence=1.0,
        cached_name=details.name,
        year_published=details.year_published,
        image_url=details.image_url,
        thumbnail_url=details.thumbnail_url,
        last_lookup_at=_utc_timestamp(),
    )
    save_bgg_association(_database(request), association)
    return _game_edit_redirect(game_id, bgg_status="linked")


@router.post(
    "/games/{game_id}/bgg/retry",
    response_class=RedirectResponse,
    name="game_bgg_retry",
)
def game_bgg_retry(request: Request, game_id: int) -> RedirectResponse:
    """Retry conservative automatic matching after an explicit request."""
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    client = _bgg_client(request)
    if client is None:
        return _game_edit_redirect(game_id, bgg_error="not-configured")
    association = enrich_game(
        _database(request),
        client,
        game_id=game_id,
        source_title=game.detected_title,
        force=True,
    )
    return _game_edit_redirect(game_id, bgg_status=association.match_state.value)


@router.post(
    "/games/{game_id}/bgg/unlink",
    response_class=RedirectResponse,
    name="game_bgg_unlink",
)
def game_bgg_unlink(request: Request, game_id: int) -> RedirectResponse:
    """Remove BGG state without changing the local game or its files."""
    if get_game(_database(request), game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if not request.app.state.settings.bgg_api_token:
        return _game_edit_redirect(game_id, bgg_error="not-configured")
    delete_bgg_association(_database(request), game_id)
    return _game_edit_redirect(game_id, bgg_status="unlinked")


@router.post(
    "/games/{game_id}/bgg/lookup",
    response_class=RedirectResponse,
    name="game_bgg_lookup_toggle",
)
async def game_bgg_lookup_toggle(
    request: Request, game_id: int
) -> RedirectResponse:
    """Enable or disable future BGG lookup while preserving cached state."""
    if not request.app.state.settings.bgg_api_token:
        return _game_edit_redirect(game_id, bgg_error="not-configured")
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    form = await request.form()
    enabled = str(form.get("enabled", "")) == "1"
    existing = get_bgg_association(_database(request), game_id)
    association = BggAssociation(
        game_id=game_id,
        lookup_enabled=enabled,
        match_state=existing.match_state if existing else BggMatchState.PENDING,
        source_title=existing.source_title if existing else game.detected_title,
        bgg_id=existing.bgg_id if existing else None,
        match_confidence=existing.match_confidence if existing else None,
        cached_name=existing.cached_name if existing else None,
        year_published=existing.year_published if existing else None,
        image_url=existing.image_url if existing else None,
        thumbnail_url=existing.thumbnail_url if existing else None,
        failure_code=existing.failure_code if existing else None,
        last_lookup_at=existing.last_lookup_at if existing else None,
    )
    save_bgg_association(_database(request), association)
    status = "lookup-enabled" if enabled else "lookup-disabled"
    return _game_edit_redirect(game_id, bgg_status=status)


@router.get(
    "/r/{resource_id}",
    response_class=HTMLResponse,
    name="resource_reprint",
)
def resource_reprint(request: Request, resource_id: int) -> HTMLResponse:
    """Show a stable, deliberate landing page for QR reprint links."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    game = get_game(_database(request), resource.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    available = True
    generated_available = False
    try:
        source = resolve_resource_pdf(
            request.app.state.settings.library_path,
            resource.relative_path,
        )
        base_url = request.app.state.settings.base_url
        if base_url:
            target_url = resource_reprint_url(base_url, resource_id)
            generated_available = existing_forge_reprint(
                source,
                request.app.state.settings.data_path,
                resource_id=resource_id,
                target_url=target_url,
            ) is not None
    except (ResourceFileMissing, UnsafeResourcePath):
        available = False

    return templates.TemplateResponse(
        request=request,
        name="resource_reprint.html",
        context={
            "game": game,
            "resource": resource,
            "available": available,
            "generation_enabled": bool(request.app.state.settings.base_url),
            "generated_available": generated_available,
            "generation_status": request.query_params.get("status"),
            "generation_error": request.query_params.get("error"),
        },
    )


@router.post(
    "/resources/{resource_id}/forge-reprint",
    response_class=RedirectResponse,
    name="resource_reprint_generate",
)
def resource_reprint_generate(
    request: Request, resource_id: int
) -> RedirectResponse:
    """Generate a derived Forge-marked copy without changing its source PDF."""
    try:
        _generated_reprint(request, resource_id)
    except ReprintGenerationError:
        return _reprint_redirect(resource_id, error="generation-failed")
    return _reprint_redirect(resource_id)


@router.post(
    "/resources/{resource_id}/forge-reprint/regenerate",
    response_class=RedirectResponse,
    name="resource_reprint_regenerate",
)
def resource_reprint_regenerate(
    request: Request, resource_id: int
) -> RedirectResponse:
    """Replace a current derived copy and confirm the refresh to the user."""
    try:
        _generated_reprint(request, resource_id, force=True)
    except ReprintGenerationError:
        return _reprint_redirect(resource_id, error="generation-failed")
    return _reprint_redirect(resource_id, status="regenerated")


@router.get(
    "/resources/{resource_id}/forge-reprint/open",
    response_class=FileResponse,
    name="resource_reprint_view",
)
def resource_reprint_view(request: Request, resource_id: int) -> FileResponse:
    """Open the current Forge-marked derived copy for deliberate printing."""
    return _generated_reprint_response(request, resource_id, disposition="inline")


@router.get(
    "/resources/{resource_id}/forge-reprint/download",
    response_class=FileResponse,
    name="resource_reprint_download",
)
def resource_reprint_download(request: Request, resource_id: int) -> FileResponse:
    """Download the current Forge-marked derived copy."""
    return _generated_reprint_response(request, resource_id, disposition="attachment")


@router.get(
    "/resources/{resource_id}/preview",
    response_class=FileResponse,
    name="resource_preview",
)
def resource_preview(request: Request, resource_id: int) -> FileResponse:
    """Render and serve a cached first-page preview for an indexed PDF."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        preview = cached_resource_preview(
            request.app.state.settings.library_path,
            request.app.state.settings.data_path,
            resource,
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410, detail="Resource file is missing"
        ) from error
    except (PreviewUnavailable, UnsafeResourcePath) as error:
        raise HTTPException(status_code=404, detail="Preview unavailable") from error
    return FileResponse(
        preview,
        media_type="image/webp",
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/resources/{resource_id}/open",
    response_class=FileResponse,
    name="resource_view",
)
def resource_view(request: Request, resource_id: int) -> FileResponse:
    """Serve an indexed PDF inline for browser viewing and printing."""
    return _resource_response(
        request, resource_id, disposition="inline", action="view"
    )


@router.get(
    "/resources/{resource_id}/download",
    response_class=FileResponse,
    name="resource_download",
)
def resource_download(request: Request, resource_id: int) -> FileResponse:
    """Serve an indexed PDF as an explicit download."""
    return _resource_response(
        request, resource_id, disposition="attachment", action="download"
    )


def _database(request: Request) -> Database:
    return request.app.state.database


def _generated_reprint(
    request: Request, resource_id: int, *, force: bool = False
) -> Path:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        source = resolve_resource_pdf(
            request.app.state.settings.library_path,
            resource.relative_path,
        )
        target_url = resource_reprint_url(
            request.app.state.settings.base_url,
            resource_id,
        )
        return generate_forge_reprint(
            source,
            request.app.state.settings.data_path,
            resource_id=resource_id,
            target_url=target_url,
            force=force,
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410,
            detail="This PDF was removed after the last library scan.",
        ) from error
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=404, detail="Resource not found") from error


def _generated_reprint_response(
    request: Request, resource_id: int, *, disposition: str
) -> FileResponse:
    try:
        path = _generated_reprint(request, resource_id)
    except ReprintGenerationError as error:
        raise HTTPException(
            status_code=422,
            detail="FORGE Reprint generation failed.",
        ) from error
    resource = get_resource(_database(request), resource_id)
    game = get_game(_database(request), resource.game_id) if resource else None
    if resource is None or game is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=_pdf_filename(game, resource, prefix="FORGE Reprint"),
        content_disposition_type=disposition,
        headers={"Cache-Control": "no-store"},
    )


def _reprint_redirect(
    resource_id: int,
    *,
    status: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    query = urlencode(
        {key: value for key, value in (("status", status), ("error", error)) if value}
    )
    suffix = f"?{query}" if query else ""
    return RedirectResponse(url=f"/r/{resource_id}{suffix}", status_code=303)


def _settings_redirect(
    *, status: str | None = None, error: str | None = None
) -> RedirectResponse:
    query = urlencode(
        {key: value for key, value in (("status", status), ("error", error)) if value}
    )
    return RedirectResponse(
        url=f"/settings?{query}" if query else "/settings", status_code=303
    )


def _game_edit_response(
    request: Request,
    game: GameDetail,
    *,
    bgg_candidates: tuple[object, ...] = (),
    bgg_query: str | None = None,
    bgg_error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="game_edit.html",
        context={
            "game": game,
            "game_categories": list_game_categories(_database(request)),
            "selected_category_ids": {
                category.id for category in game.categories
            },
            "bgg_association": get_bgg_association(
                _database(request), game.id
            ),
            "bgg_configured": bool(request.app.state.settings.bgg_api_token),
            "bgg_candidates": bgg_candidates,
            "bgg_query": bgg_query or game.detected_title,
            "bgg_status": request.query_params.get("bgg_status"),
            "bgg_error": bgg_error or request.query_params.get("bgg_error"),
        },
    )


def _bgg_client(request: Request) -> BggClient | None:
    token = request.app.state.settings.bgg_api_token
    if token is None:
        return None
    factory = getattr(request.app.state, "bgg_client_factory", BggClient)
    return factory(token)


def _game_edit_redirect(
    game_id: int,
    *,
    bgg_status: str | None = None,
    bgg_error: str | None = None,
) -> RedirectResponse:
    query = urlencode(
        {
            key: value
            for key, value in (
                ("bgg_status", bgg_status),
                ("bgg_error", bgg_error),
            )
            if value
        }
    )
    suffix = f"?{query}" if query else ""
    return RedirectResponse(url=f"/games/{game_id}/edit{suffix}", status_code=303)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _timezone_names() -> tuple[str, ...]:
    regions = (
        "Africa/",
        "America/",
        "Antarctica/",
        "Arctic/",
        "Asia/",
        "Atlantic/",
        "Australia/",
        "Europe/",
        "Indian/",
        "Pacific/",
    )
    names = sorted(
        name for name in available_timezones() if name.startswith(regions)
    )
    return ("UTC", *names)


def _format_local_timestamp(value: str, timezone_name: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    local = parsed.astimezone(ZoneInfo(timezone_name))
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local:%b} {local.day}, {local.year} · {hour}:{local:%M %p %Z}"


def _normalized_category_name(value: object) -> str | None:
    name = " ".join(str(value or "").split())
    if (
        not name
        or len(name) > MAX_GAME_CATEGORY_NAME_LENGTH
        or name.casefold() in RESERVED_GAME_CATEGORY_NAMES
    ):
        return None
    return name


def _resource_response(
    request: Request, resource_id: int, *, disposition: str, action: str
) -> FileResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    game = get_game(_database(request), resource.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        path = resolve_resource_pdf(
            request.app.state.settings.library_path,
            resource.relative_path,
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410,
            detail="This PDF was removed after the last library scan.",
        ) from error
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=404, detail="Resource not found") from error

    record_resource_use(_database(request), resource_id, action=action)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=_pdf_filename(game, resource),
        content_disposition_type=disposition,
        headers={"Cache-Control": "no-store"},
    )


def _pdf_filename(
    game: GameDetail, resource: IndexedResource, *, prefix: str | None = None
) -> str:
    """Build a portable filename from trusted display metadata."""
    parts = [prefix, game.title, resource.title, resource.variant]
    readable = " - ".join(part for part in parts if part)
    portable = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]+', " ", readable)
    portable = " ".join(portable.split()).strip(" .-")[:180].rstrip(" .-")
    return f"{portable or 'Forge GameSheets resource'}.pdf"
