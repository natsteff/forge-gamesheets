"""Server-rendered web interface for the indexed library."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from string import ascii_uppercase
from tempfile import TemporaryDirectory
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import accounts
from app.activity import (
    PAGE_SIZE,
    get_scan_detail,
    list_activity,
    record_activity,
    record_scan,
)
from app.bgg.categories import apply_bgg_categories
from app.bgg.client import (
    BggApiError,
    BggAuthenticationError,
    BggClient,
    BggRateLimitError,
    BggUnavailableError,
    resolve_game_slug,
    safe_bgg_image_url,
)
from app.bgg.edition import (
    BggEdition,
    get_bgg_edition,
    get_edition_sources,
    parse_edition_reference,
    save_bgg_edition,
)
from app.bgg.jobs import enqueue_batch, enqueue_initial, preview_batch, retry_failed
from app.bgg.matching import enrich_game, search_match
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    delete_bgg_association,
    get_bgg_association,
    save_bgg_association,
)
from app.bgg.version_enrichment import fill_blank_version_details
from app.database import Database
from app.library import processing_budget
from app.library.artwork import (
    MAX_ARTWORK_BYTES,
    cached_game_artwork,
    delete_uploaded_artwork,
    save_uploaded_artwork,
)
from app.library.box_dimensions import BoxDimensions
from app.library.cache import cleanup_managed_files
from app.library.filename_parser import ResourceCategory
from app.library.files import (
    ResourceFileMissing,
    UnsafeResourcePath,
    resolve_resource_file,
    resolve_resource_pdf,
)
from app.library.game_categories import add_missing_defaults, bulk_apply, folder_hint
from app.library.game_links import (
    GameLinkError,
    list_game_resource_links,
    save_game_resource_links,
)
from app.library.previews import (
    PreviewUnavailable,
    cached_image_preview,
    cached_resource_preview,
    render_pdf_preview,
)
from app.library.qr_access import requires_sign_in, set_requires_sign_in
from app.library.reconciliation import (
    DeletionReviewRequired,
    ReconciliationError,
    reconcile_scan,
)
from app.library.repository import (
    GameDetail,
    GameSummary,
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
    record_resource_use,
    rename_game_category,
    reset_game_artwork_override,
    reset_game_title_override,
    reset_resource_override,
    save_game_artwork_override,
    save_game_box_dimensions,
    save_game_categories,
    save_game_title_override,
    save_resource_override,
    set_resource_favorite,
    toggle_resource_pin,
)
from app.library.reprint_registry import record_validated_reprint
from app.library.reprint_targets import (
    preferred_reprint_target,
    readable_reprint_targets,
)
from app.library.reprints import (
    ReprintGenerationError,
    existing_forge_reprint,
    generate_forge_reprint,
)
from app.library.resource_types import (
    IMAGE_MIME_TYPES,
    is_artwork_named_file,
    is_reserved_game_artwork,
    resource_type_label,
)
from app.library.scanner import LibraryScanError, ScanIssue, scan_library
from app.preferences import (
    AUTO_RESCAN_MINUTES,
    DEFAULT_FOOTER_TEXT,
    MAX_FOOTER_LENGTH,
    MAX_RECENT_LIMIT,
    ApplicationPreferences,
    get_preferences,
    save_preferences,
)
from app.sheet_designer.model import (
    FORMAT_NAME,
    MAX_DOCUMENT_BYTES,
    SUPPORTED_VERSIONS,
    DocumentValidationError,
    normalize_document,
)
from app.sheet_designer.shared_rendering import (
    MAX_PDF_BYTES,
    PageOverflowError,
    RendererUnavailableError,
    render_pdf,
)
from app.sheet_game_associations import list_associated_sheets

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_CATEGORY_ORDER = (
    ResourceCategory.RULES,
    ResourceCategory.SCORE_SHEET,
    ResourceCategory.REFERENCE,
    ResourceCategory.ANSWER_SHEET,
    ResourceCategory.TOURNAMENT,
    ResourceCategory.SETUP,
    ResourceCategory.FGS_GAMESHEET,
    ResourceCategory.OTHER,
)

_CATEGORY_LABELS = {
    ResourceCategory.RULES: "Rules",
    ResourceCategory.SCORE_SHEET: "Score Sheets",
    ResourceCategory.REFERENCE: "Player References",
    ResourceCategory.ANSWER_SHEET: "Answer Sheets",
    ResourceCategory.TOURNAMENT: "Tournament Materials",
    ResourceCategory.SETUP: "Setup",
    ResourceCategory.FGS_GAMESHEET: "FGS GameSheets",
    ResourceCategory.OTHER: "Other",
}

MAX_GAME_CATEGORY_NAME_LENGTH = 60
RESERVED_GAME_CATEGORY_NAMES = frozenset({"all games", "uncategorized"})


def _template_preferences(request: Request) -> ApplicationPreferences:
    """Expose cached preferences to every base template."""
    if not hasattr(request.state, "application_preferences"):
        request.state.application_preferences = get_preferences(_database(request))
    return request.state.application_preferences


templates.env.globals["application_preferences"] = _template_preferences


def _has_ready_livesheets(request: Request) -> bool:
    """Keep navigation absent until the shared workspace has a ready sheet."""
    store = getattr(request.app.state, "sheet_designer_store", None)
    return bool(store and store.list_livesheet_documents())


templates.env.globals["has_ready_livesheets"] = _has_ready_livesheets


def _game_letter_navigation(
    games: tuple[GameSummary, ...],
) -> tuple[tuple[tuple[str, bool], ...], dict[int, str]]:
    """Index title initials only when the library is large enough to need jumps."""
    if len(games) < 50:
        return (), {}
    anchors: dict[int, str] = {}
    available: set[str] = set()
    for game in games:
        initial = game.title.strip()[:1].upper()
        letter = initial if len(initial) == 1 and initial in ascii_uppercase else "#"
        if letter not in available:
            available.add(letter)
            anchors[game.id] = letter
    links = tuple((letter, letter in available) for letter in ("#", *ascii_uppercase))
    return links, anchors


@router.get("/", response_class=HTMLResponse, name="library_home")
def library_home(request: Request) -> HTMLResponse:
    query = request.query_params.get("q", "").strip()[:200]
    games = list_games(_database(request), query or None)
    pinned = () if query else list_pinned_resources(_database(request))
    letter_links, letter_anchors = _game_letter_navigation(games if not query else ())
    scan_detail = None
    if request.query_params.get("scan") == "complete":
        try:
            scan_event_id = int(request.query_params.get("event", ""))
        except ValueError:
            scan_event_id = 0
        scan_detail = get_scan_detail(_database(request), scan_event_id)
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={
            "games": games,
            "pinned": pinned,
            "letter_links": letter_links,
            "letter_anchors": letter_anchors,
            "query": query,
            "scan_status": request.query_params.get("scan"),
            "scan_detail": scan_detail,
            "scan_issues": request.app.state.scan_issues,
            "auto_scan_notice": request.app.state.auto_scan_notice,
        },
    )


@router.get("/assign-categories", response_class=HTMLResponse, name="assign_categories")
def assign_categories(request: Request):
    query = request.query_params.get("q", "")[:200]
    category = request.query_params.get("category", "")
    sort = request.query_params.get("sort", "title")
    preview = request.query_params.get("preview") == "1"
    with _database(request).connect() as connection:
        rows = connection.execute(
            "SELECT g.id,g.relative_path,g.created_at,"
            "COALESCE(o.title,g.title) AS title "
            "FROM games g LEFT JOIN game_overrides o ON o.game_id=g.id"
        ).fetchall()
        assignments = defaultdict(list)
        for row in connection.execute(
            "SELECT a.game_id,c.id,c.name FROM game_category_assignments a "
            "JOIN game_categories c ON c.id=a.category_id ORDER BY c.name"
        ):
            assignments[row["game_id"]].append(dict(row))
        enabled = connection.execute(
            "SELECT folder_categories FROM application_preferences WHERE id=1"
        ).fetchone()[0]
    timezone_name = get_preferences(_database(request)).timezone_name
    games = []
    for row in rows:
        assigned = assignments[row["id"]]
        if query.casefold() not in row["title"].casefold():
            continue
        if category == "uncategorized" and assigned:
            continue
        if (
            category
            and category != "uncategorized"
            and not any(str(item["id"]) == category for item in assigned)
        ):
            continue
        games.append(
            {
                **dict(row),
                "categories": assigned,
                "hints": folder_hint(row["relative_path"])[1],
                "added_display": _format_local_timestamp(
                    row["created_at"], timezone_name
                ),
            }
        )
    games.sort(
        key=lambda game: (
            (game["created_at"], game["id"])
            if sort == "newest"
            else (game["title"].casefold(), game["id"])
        ),
        reverse=sort == "newest",
    )
    return templates.TemplateResponse(
        request=request,
        name="assign_categories.html",
        context={
            "games": games[:500],
            "total": len(games),
            "q": query,
            "category": category,
            "sort": sort,
            "preview": preview,
            "folder_enabled": enabled,
            "categories": list_game_categories(_database(request)),
            "message": request.query_params.get("message", "")[:300],
        },
    )


@router.post("/assign-categories", name="assign_categories_apply")
async def assign_categories_apply(request: Request):
    form = await request.form()
    operation = str(form.get("operation", ""))
    try:
        if form.get("confirm") != "yes":
            ids = set(int(value) for value in form.getlist("game_ids"))
            category_ids = set(int(value) for value in form.getlist("category_ids"))
            if not ids or len(ids) > 500:
                raise ValueError("Select between 1 and 500 games.")
            impacts = {
                "add": "Add the selected categories; keep other categories.",
                "remove": "Remove only the selected categories; keep other categories.",
                "replace": (
                    "Replace ALL existing categories with the selected categories."
                ),
                "clear": "Remove ALL categories. Category selections are ignored.",
                "folder": (
                    "Add each game's folder hints. Category selections are ignored."
                ),
            }
            if operation not in impacts:
                raise ValueError("Choose a valid operation.")
            if operation in {"add", "remove", "replace"} and not category_ids:
                raise ValueError("Select at least one category.")
            with _database(request).connect() as connection:
                selected = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT g.id,COALESCE(o.title,g.title) AS title,"
                        "g.relative_path "
                        "FROM games g LEFT JOIN game_overrides o ON o.game_id=g.id"
                    )
                    if row["id"] in ids
                ]
                categories = [
                    dict(row)
                    for row in connection.execute("SELECT id,name FROM game_categories")
                    if row["id"] in category_ids
                ]
            if len(selected) != len(ids) or len(categories) != len(category_ids):
                raise ValueError("A selected item no longer exists. Reload the page.")
            return templates.TemplateResponse(
                request=request,
                name="confirm_categories.html",
                context={
                    "selected": selected,
                    "categories": categories,
                    "impact": impacts[operation],
                    "operation": operation,
                    "fields": [
                        (key, str(value))
                        for key, value in form.multi_items()
                        if key
                        in {
                            "game_ids",
                            "category_ids",
                            "operation",
                            "q",
                            "category",
                            "sort",
                            "preview",
                        }
                    ],
                    "folder_hint": folder_hint,
                },
            )
        if operation == "folder" and form.get("preview") != "1":
            raise ValueError("Preview folder categories before applying them.")
        changed = bulk_apply(
            _database(request),
            [int(value) for value in form.getlist("game_ids")],
            [int(value) for value in form.getlist("category_ids")],
            operation,
        )
        message = f"Updated categories for {changed} games."
        record_activity(
            _database(request),
            "game_categories_updated",
            "Game categories updated",
            detail=message,
        )
    except ValueError as error:
        message = str(error)
    params = {
        key: str(form.get(key, ""))[:200]
        for key in ("q", "category", "sort", "preview")
    }
    params["message"] = message
    return RedirectResponse("/assign-categories?" + urlencode(params), 303)


@router.post("/settings/scanning", name="settings_scanning")
async def settings_scanning(request: Request):
    form = await request.form()
    mode = str(form.get("auto_rescan_mode", ""))
    if mode not in {"manual", "local", "15", "30", "60", "480", "1440"}:
        raise HTTPException(422, "Invalid auto rescan mode")
    frequency = int(mode) if mode not in {"manual", "local"} else 0
    if frequency not in AUTO_RESCAN_MINUTES:
        raise HTTPException(422, "Invalid auto rescan frequency")
    with _database(request).connect() as connection:
        connection.execute(
            "UPDATE application_preferences SET folder_categories=?, "
            "auto_rescan_minutes=?, local_event_scans=? WHERE id=1",
            (
                int(form.get("folder_categories") == "on"),
                frequency,
                int(mode != "manual"),
            ),
        )
    return RedirectResponse("/settings?status=scanning-saved", 303)


@router.get("/categories", response_class=HTMLResponse, name="categories_home")
def categories_home(request: Request) -> HTMLResponse:
    """Show the complete game-category directory."""
    games = list_games(_database(request))
    categories = list_game_categories(_database(request))
    uncategorized_count = len(list_games_in_category(_database(request), None))
    return templates.TemplateResponse(
        request=request,
        name="categories.html",
        context={
            "game_categories": categories,
            "total_game_count": len(games),
            "uncategorized_count": uncategorized_count,
            "show_empty": request.query_params.get("show_empty") == "1",
            "empty_category_count": sum(not item.game_count for item in categories)
            + (not uncategorized_count),
        },
    )


@router.get("/games", response_class=HTMLResponse, name="all_games")
def all_games(request: Request) -> HTMLResponse:
    """Show every indexed game in one alphabetical list."""
    games = list_games(_database(request))
    letter_links, letter_anchors = _game_letter_navigation(games)
    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": "All Games",
            "games": games,
            "page_descriptor": "Complete library",
            "letter_links": letter_links,
            "letter_anchors": letter_anchors,
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
    session_policy = None
    if request.state.auth_enabled:
        session_policy = accounts.session_policy(_database(request))
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
            "bgg_batch": preview_batch(_database(request)),
            "session_policy": session_policy,
            "session_duration_options": (
                (1800, "30 minutes"),
                (3600, "1 hour"),
                (14400, "4 hours"),
                (43200, "12 hours"),
                (86400, "1 day"),
                (604800, "7 days"),
                (1209600, "14 days"),
                (2592000, "30 days"),
                (7776000, "90 days"),
            ),
        },
    )


@router.post(
    "/settings/bgg/test",
    response_class=RedirectResponse,
    name="settings_bgg_test",
)
def settings_bgg_test(request: Request) -> RedirectResponse:
    """Verify the configured BGG token without exposing or persisting it."""
    client = _bgg_client(request)
    if client is None:
        return _settings_redirect(error="bgg-not-configured")
    try:
        game = client.get_game(13)
    except BggAuthenticationError:
        return _settings_redirect(error="bgg-authentication")
    except BggRateLimitError:
        return _settings_redirect(error="bgg-rate-limited")
    except BggUnavailableError:
        return _settings_redirect(error="bgg-unavailable")
    except BggApiError:
        return _settings_redirect(error="bgg-request")
    if game is None:
        return _settings_redirect(error="bgg-response")
    return _settings_redirect(status="bgg-connected")


@router.post(
    "/settings/bgg/refresh-all",
    response_class=RedirectResponse,
    name="settings_bgg_refresh_all",
)
def settings_bgg_refresh_all(request: Request) -> RedirectResponse:
    """Queue one paced enrichment pass after explicit Admin confirmation."""
    if not request.app.state.settings.bgg_api_token:
        return _settings_redirect(error="bgg-not-configured")
    count = enqueue_batch(_database(request))
    record_activity(
        _database(request),
        "bgg_refresh_started",
        "BoardGameGeek refresh started",
        detail=f"{count} games queued for background lookup.",
    )
    return _settings_redirect(status="bgg-batch-started", anchor="bgg-integration")


@router.post(
    "/settings/bgg/categories",
    response_class=RedirectResponse,
    name="settings_bgg_categories",
)
async def settings_bgg_categories(request: Request) -> RedirectResponse:
    """Control only BGG-driven category assignment, not manual categories."""
    form = await request.form()
    with _database(request).connect() as connection:
        connection.execute(
            "UPDATE application_preferences SET bgg_categories=?,"
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=1",
            (int(form.get("bgg_categories") == "on"),),
        )
    return _settings_redirect(status="bgg-categories-saved", anchor="bgg-integration")


@router.post(
    "/settings/bgg/retry-failed",
    response_class=RedirectResponse,
    name="settings_bgg_retry_failed",
)
def settings_bgg_retry_failed(request: Request) -> RedirectResponse:
    if not request.app.state.settings.bgg_api_token:
        return _settings_redirect(error="bgg-not-configured")
    count = retry_failed(_database(request))
    record_activity(
        _database(request),
        "bgg_refresh_retried",
        "Failed BoardGameGeek lookups retried",
        detail=f"{count} failed games queued again.",
    )
    return _settings_redirect(status="bgg-retry-started", anchor="bgg-integration")


@router.post(
    "/settings/categories/add-defaults",
    response_class=RedirectResponse,
    name="settings_categories_add_defaults",
)
def settings_categories_add_defaults(request: Request) -> RedirectResponse:
    added = add_missing_defaults(_database(request))
    return _settings_redirect(status=f"category-defaults-{added}")


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
    """Restore the FORGE GameSheets footer while preserving other settings."""
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
def settings_category_delete(request: Request, category_id: int) -> RedirectResponse:
    """Delete a category but never its games or files."""
    if not delete_game_category(_database(request), category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    return _settings_redirect(status="category-deleted")


@router.post("/rescan", response_class=RedirectResponse, name="library_rescan")
def library_rescan(
    request: Request, confirm_removals: str | None = Form(None)
) -> Response:
    """Synchronize the SQLite index with the current filesystem library."""
    settings = request.app.state.settings
    with request.app.state.scan_lock:
        with _database(request).connect() as connection:
            before_game_ids = {
                row[0] for row in connection.execute("SELECT id FROM games")
            }
        try:
            scan_result = scan_library(settings.library_path)
            summary = reconcile_scan(
                _database(request), scan_result, confirm_removals=confirm_removals
            )
        except DeletionReviewRequired as review:
            request.app.state.auto_scan_notice = True
            return templates.TemplateResponse(
                request=request,
                name="scan_removal_review.html",
                context={"review": review},
            )
        except ReconciliationError:
            request.app.state.scan_issues = scan_result.issues
            record_scan(_database(request), issue_count=len(scan_result.issues))
            query = urlencode({"scan": "partial", "issues": len(scan_result.issues)})
            return RedirectResponse(url=f"/?{query}", status_code=303)
        except LibraryScanError:
            request.app.state.scan_issues = (
                ScanIssue(Path("Library root"), "The library could not be read."),
            )
            record_scan(_database(request), failed=True)
            return RedirectResponse(url="/?scan=failed&issues=1", status_code=303)
        request.app.state.last_auto_scan_at = time.monotonic()

    request.app.state.scan_issues = ()
    request.app.state.auto_scan_notice = False
    request.app.state.auto_scan_review_fingerprint = None
    request.app.state.last_reconciliation = summary
    if settings.bgg_api_token:
        with _database(request).connect() as connection:
            after_game_ids = {
                row[0] for row in connection.execute("SELECT id FROM games")
            }
        enqueue_initial(_database(request), after_game_ids - before_game_ids)
    cleanup_managed_files(_database(request), settings.data_path)
    event_id = record_scan(_database(request), summary)
    query = urlencode({"scan": "complete", "event": event_id})
    return RedirectResponse(url=f"/?{query}", status_code=303)


@router.get("/history", response_class=HTMLResponse, name="activity_history")
def activity_history(request: Request) -> HTMLResponse:
    """Show one bounded page of application activity."""
    preferences = get_preferences(_database(request))
    raw_before = request.query_params.get("before")
    try:
        before = int(raw_before) if raw_before else None
        if before is not None and before < 1:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Invalid history cursor") from None
    events, older_cursor = list_activity(_database(request), before=before)
    activity = tuple(
        (
            event,
            _format_local_timestamp(event.occurred_at, preferences.timezone_name),
        )
        for event in events
    )
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "activity": activity,
            "timezone_name": preferences.timezone_name,
            "older_cursor": older_cursor,
            "has_newer": before is not None,
            "page_size": PAGE_SIZE,
            "accounts_enabled": accounts.auth_enabled(_database(request)),
        },
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
    if resource.provider == "other":
        raise HTTPException(status_code=404, detail="Resource not found")
    set_resource_favorite(
        _database(request), resource_id, favorite=not resource.is_favorite
    )
    game = get_game(_database(request), resource.game_id)
    record_activity(
        _database(request),
        "removed_from_favorites" if resource.is_favorite else "added_to_favorites",
        resource.title,
        detail=game.title,
        game_id=resource.game_id,
        resource_id=resource.id,
    )
    target = (
        "/favorites"
        if request.query_params.get("return_to") == "favorites"
        else f"/games/{resource.game_id}#resource-{resource.id}"
    )
    return RedirectResponse(url=target, status_code=303)


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
    if resource.provider == "other":
        raise HTTPException(status_code=404, detail="Resource not found")
    result = toggle_resource_pin(_database(request), resource_id)
    if result != "limit":
        game = get_game(_database(request), resource.game_id)
        record_activity(
            _database(request),
            (
                "pinned_for_quick_access"
                if result == "pinned"
                else "removed_from_quick_access"
            ),
            resource.title,
            detail=game.title,
            game_id=resource.game_id,
            resource_id=resource.id,
        )
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
            target = f"/games/{resource.game_id}?pin=limit#resource-{resource.id}"
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
    if resource is None or resource.provider == "other":
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
async def resource_edit_save(request: Request, resource_id: int) -> RedirectResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None or resource.provider == "other":
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
    record_activity(
        _database(request),
        "resource_edited",
        resource.title,
        detail="Resource entry edited.",
        game_id=resource.game_id,
        resource_id=resource.id,
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
    if resource is None or resource.provider == "other":
        raise HTTPException(status_code=404, detail="Resource not found")
    reset_resource_override(_database(request), resource_id)
    record_activity(
        _database(request),
        "resource_reset",
        resource.title,
        detail="Resource entry restored to scanned metadata.",
        game_id=resource.game_id,
        resource_id=resource.id,
    )
    return RedirectResponse(
        url=f"/games/{resource.game_id}#resource-{resource.id}", status_code=303
    )


def _fgs_source_data(library_path: Path, resource: IndexedResource) -> dict:
    """Read bounded library FGS JSON without saving a Designer draft."""
    path = resolve_resource_file(library_path, resource.relative_path, "fgs")
    with path.open("rb") as source:
        payload = source.read(MAX_DOCUMENT_BYTES + 1)
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise DocumentValidationError("FGS file exceeds the import limit")
    source = json.loads(payload.decode("utf-8"))
    if not isinstance(source, dict):
        raise DocumentValidationError("FGS document must be an object")
    return source


def _fgs_source_title(source: dict) -> str | None:
    """Use only a plausible top-level title for the cheap name-first pass."""
    title = source.get("title")
    if (
        source.get("format") != FORMAT_NAME
        or source.get("format_version") not in SUPPORTED_VERSIONS
        or not isinstance(title, str)
        or not 1 <= len(title.strip()) <= 160
    ):
        return None
    return title.strip()


def _fgs_resource_document(
    request: Request, resource_id: int
) -> tuple[IndexedResource, dict]:
    resource = get_resource(_database(request), resource_id)
    if resource is None or resource.provider != "fgs":
        raise HTTPException(404, "FGS file not found")
    try:
        document = normalize_document(
            _fgs_source_data(request.app.state.settings.library_path, resource)
        )
    except (ResourceFileMissing, UnsafeResourcePath, OSError) as error:
        raise HTTPException(410, "FGS file is unavailable") from error
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise HTTPException(422, "FGS file is invalid") from error
    return resource, document


@router.get("/games/{game_id}", response_class=HTMLResponse, name="game_detail")
def game_detail(request: Request, game_id: int) -> HTMLResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    grouped: defaultdict[ResourceCategory, list[IndexedResource]] = defaultdict(list)
    for resource in game.resources:
        if resource.provider != "other":
            grouped[resource.category].append(resource)
    sections = tuple(
        (_CATEGORY_LABELS[category], grouped[category])
        for category in _CATEGORY_ORDER
        if grouped[category]
    )
    unavailable_resource_ids: set[int] = set()
    for resource in game.resources:
        if resource.provider == "other":
            continue
        try:
            resolve_resource_file(
                request.app.state.settings.library_path,
                resource.relative_path,
                resource.provider,
            )
        except (ResourceFileMissing, UnsafeResourcePath):
            unavailable_resource_ids.add(resource.id)

    fgs_sheet_titles: dict[int, str] = {}
    fgs_matching_ids: dict[int, tuple[str, ...]] = {}
    for resource in game.resources:
        if resource.provider != "fgs" or resource.id in unavailable_resource_ids:
            continue
        try:
            source = _fgs_source_data(
                request.app.state.settings.library_path, resource
            )
        except (
            ResourceFileMissing,
            UnsafeResourcePath,
            OSError,
            UnicodeError,
            ValueError,
            TypeError,
            RecursionError,
        ):
            continue
        title = _fgs_source_title(source)
        if title is None:
            continue
        fgs_sheet_titles[resource.id] = title
        if request.state.can_contribute:
            matches = request.app.state.sheet_designer_store.matching_document_ids(
                source
            )
            if matches:
                fgs_matching_ids[resource.id] = matches

    return templates.TemplateResponse(
        request=request,
        name="game.html",
        context={
            "game": game,
            "sections": sections,
            "other_files": tuple(
                resource for resource in game.resources if resource.provider == "other"
            ),
            "reserved_artwork_paths": {
                resource.relative_path
                for resource in game.resources
                if is_reserved_game_artwork(resource.relative_path)
            },
            "artwork_named_paths": {
                resource.relative_path
                for resource in game.resources
                if is_artwork_named_file(resource.relative_path)
            },
            "resource_type_labels": {
                resource.id: resource_type_label(
                    resource.provider, resource.relative_path
                )
                for resource in game.resources
                if resource.provider in {"fgs", "image", "document"}
            },
            "fgs_sheet_titles": fgs_sheet_titles,
            "fgs_matching_ids": fgs_matching_ids,
            "bgg_association": get_bgg_association(_database(request), game.id),
            "bgg_image_url": safe_bgg_image_url(
                (association := get_bgg_association(_database(request), game.id))
                and (association.image_url or association.thumbnail_url)
            ),
            "bgg_edition": get_bgg_edition(_database(request), game.id),
            "bgg_edition_sources": get_edition_sources(_database(request), game.id),
            "game_resource_links": list_game_resource_links(
                _database(request), game.id
            ),
            "associated_sheets": list_associated_sheets(
                _database(request), request.app.state.sheet_designer_store, game.id
            ),
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
    dimension_fields = ("box_length", "box_width", "box_depth", "box_unit")
    update_dimensions = any(key in form for key in dimension_fields)
    dimensions = None
    if update_dimensions:
        raw = [str(form.get(key, "")).strip() for key in dimension_fields]
        if any(raw[:3]):
            try:
                dimensions = BoxDimensions(
                    float(raw[0]), float(raw[1]), float(raw[2]), raw[3]
                ).to_dict()
            except (TypeError, ValueError, OverflowError) as error:
                raise HTTPException(
                    422,
                    "Enter all three positive box measurements and choose in or cm.",
                ) from error
    save_game_title_override(_database(request), game_id, title=title)
    save_game_categories(_database(request), game_id, category_ids=category_ids)
    if update_dimensions:
        save_game_box_dimensions(_database(request), game_id, dimensions)
    record_activity(
        _database(request),
        "game_edited",
        title,
        detail="Game entry edited.",
        game_id=game_id,
    )
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)


@router.post(
    "/games/{game_id}/links",
    response_class=RedirectResponse,
    name="game_links_save",
)
async def game_links_save(request: Request, game_id: int) -> RedirectResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    form = await request.form()
    try:
        save_game_resource_links(
            _database(request),
            game_id,
            {
                "official": (
                    str(form.get("official_description", "")),
                    str(form.get("official_url", "")),
                ),
                "alternate": (
                    str(form.get("alternate_description", "")),
                    str(form.get("alternate_url", "")),
                ),
            },
        )
    except GameLinkError:
        return RedirectResponse(
            url=f"/games/{game_id}/edit?links_error=invalid", status_code=303
        )
    record_activity(
        _database(request),
        "game_links_edited",
        game.title,
        detail="Game resource links updated.",
        game_id=game_id,
    )
    return RedirectResponse(
        url=f"/games/{game_id}/edit?links_status=saved", status_code=303
    )


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
    record_activity(
        _database(request),
        "game_reset",
        game.title,
        detail="Game title restored to scanned metadata.",
        game_id=game_id,
    )
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
    game = get_game(_database(request), game_id)
    record_activity(
        _database(request),
        "artwork_updated",
        game.title,
        detail="Custom artwork uploaded.",
        game_id=game_id,
    )
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
    game = get_game(_database(request), game_id)
    record_activity(
        _database(request),
        "artwork_reset",
        game.title,
        detail="Custom artwork removed.",
        game_id=game_id,
    )
    return RedirectResponse(url=f"/games/{game_id}/edit", status_code=303)


@router.post(
    "/games/{game_id}/bgg/find",
    response_class=HTMLResponse,
    name="game_bgg_find",
)
async def game_bgg_find(request: Request, game_id: int) -> HTMLResponse:
    """Select one unique exact BGG match or show candidates for review."""
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
        exact_match, candidates = search_match(client, query)
    except BggApiError:
        return _game_edit_response(request, game, bgg_error="lookup-failed")
    existing = get_bgg_association(_database(request), game_id)
    if exact_match is not None and not (existing and existing.bgg_id):
        try:
            details = client.get_game(exact_match.id)
        except BggApiError:
            return _game_edit_response(request, game, bgg_error="lookup-failed")
        if details is None:
            return _game_edit_response(request, game, bgg_error="not-found")
        saved = save_bgg_association(
            _database(request),
            BggAssociation(
                game_id=game_id,
                lookup_enabled=True,
                match_state=BggMatchState.MATCHED,
                source_title=query,
                bgg_id=details.id,
                match_confidence=1.0,
                cached_name=details.name,
                year_published=details.year_published,
                image_url=details.image_url,
                thumbnail_url=details.thumbnail_url,
                last_lookup_at=_utc_timestamp(),
                description=(details.description or "")[:20000] or None,
            ),
            expected=existing,
        )
        if not saved:
            return _game_edit_response(request, game, bgg_error="association-changed")
        apply_bgg_categories(_database(request), game_id, details, mode="empty-only")
        record_activity(
            _database(request),
            "bgg_link_updated",
            game.title,
            detail="Unique exact BoardGameGeek match selected.",
            game_id=game_id,
        )
        return _game_edit_redirect(game_id, bgg_status="matched")
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
    existing = get_bgg_association(_database(request), game_id)
    try:
        details = client.get_game(bgg_id)
    except BggApiError:
        return _game_edit_redirect(game_id, bgg_error="lookup-failed")
    if details is None:
        return _game_edit_redirect(game_id, bgg_error="not-found")
    association = BggAssociation(
        game_id=game_id,
        lookup_enabled=True,
        match_state=BggMatchState.MANUAL,
        source_title=game.detected_title,
        bgg_id=details.id,
        match_confidence=1.0,
        cached_name=details.name,
        year_published=details.year_published,
        image_url=details.image_url,
        thumbnail_url=details.thumbnail_url,
        last_lookup_at=_utc_timestamp(),
        url_slug=details.url_slug,
        description=(details.description or "")[:20000] or None,
    )
    if not save_bgg_association(_database(request), association, expected=existing):
        return _game_edit_redirect(game_id, bgg_error="association-changed")
    apply_bgg_categories(_database(request), game_id, details, mode="empty-only")
    record_activity(
        _database(request),
        "bgg_link_updated",
        game.title,
        detail="BoardGameGeek link updated.",
        game_id=game_id,
    )
    return _game_edit_redirect(game_id, bgg_status="linked")


@router.post(
    "/games/{game_id}/bgg/refresh",
    response_class=RedirectResponse,
    name="game_bgg_refresh",
)
def game_bgg_refresh(request: Request, game_id: int) -> RedirectResponse:
    """Refresh metadata for the selected BGG ID without changing its match."""
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    existing = get_bgg_association(_database(request), game_id)
    if existing is None or existing.bgg_id is None:
        return _game_edit_redirect(game_id, bgg_error="not-linked")
    client = _bgg_client(request)
    if client is None:
        return _game_edit_redirect(game_id, bgg_error="not-configured")
    try:
        details = client.get_game(existing.bgg_id)
    except BggApiError:
        return _game_edit_redirect(game_id, bgg_error="lookup-failed")
    if details is None:
        return _game_edit_redirect(game_id, bgg_error="not-found")
    saved = save_bgg_association(
        _database(request),
        BggAssociation(
            game_id=game_id,
            lookup_enabled=True,
            match_state=existing.match_state,
            source_title=existing.source_title,
            bgg_id=details.id,
            match_confidence=existing.match_confidence,
            cached_name=details.name,
            year_published=details.year_published,
            image_url=details.image_url,
            thumbnail_url=details.thumbnail_url,
            last_lookup_at=_utc_timestamp(),
            url_slug=details.url_slug or existing.url_slug,
            description=(details.description or "")[:20000] or None,
        ),
        expected=existing,
    )
    if not saved:
        return _game_edit_redirect(game_id, bgg_error="association-changed")
    if request.state.can_admin:
        apply_bgg_categories(_database(request), game_id, details, mode="additive")
    record_activity(
        _database(request),
        "bgg_link_updated",
        game.title,
        detail="BoardGameGeek information refreshed.",
        game_id=game_id,
    )
    return _game_edit_redirect(game_id, bgg_status="refreshed")


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
    record_activity(
        _database(request),
        "bgg_link_updated",
        game.title,
        detail="BoardGameGeek lookup refreshed.",
        game_id=game_id,
    )
    return _game_edit_redirect(game_id, bgg_status=association.match_state.value)


@router.post("/games/{game_id}/bgg/manual", name="game_bgg_manual")
async def game_bgg_manual(request: Request, game_id: int):
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(404, "Game not found")
    form = await request.form()
    value = str(form.get("bgg_reference", "")).strip()
    slug = None
    try:
        if len(value) > 1000:
            raise ValueError
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or parsed.netloc.lower() not in {
            "boardgamegeek.com",
            "www.boardgamegeek.com",
        }:
            raise ValueError
        match = re.fullmatch(
            r"/boardgame/([0-9]{1,10})/([A-Za-z0-9_-]{1,200})(?:/files)?/?",
            parsed.path,
        )
        if not match:
            raise ValueError
        bgg_id = int(match[1])
        slug = match[2]
        if slug.lower() in {"files", "images", "forums", "videos", "ratings"}:
            raise ValueError
        if bgg_id <= 0:
            raise ValueError
    except ValueError:
        return _game_edit_redirect(game_id, bgg_error="invalid-reference")
    database = _database(request)
    existing = get_bgg_association(database, game_id)
    client = _bgg_client(request)
    if client is not None:
        try:
            details = client.get_game(bgg_id)
        except BggApiError:
            return _game_edit_redirect(game_id, bgg_error="manual-lookup-failed")
        if details is None or details.id != bgg_id:
            return _game_edit_redirect(game_id, bgg_error="manual-not-found")
        association = BggAssociation(
            game_id=game_id,
            lookup_enabled=True,
            match_state=BggMatchState.MANUAL,
            source_title=game.detected_title,
            bgg_id=details.id,
            match_confidence=1.0,
            cached_name=details.name,
            year_published=details.year_published,
            image_url=details.image_url,
            thumbnail_url=details.thumbnail_url,
            last_lookup_at=_utc_timestamp(),
            url_slug=slug,
            description=(details.description or "")[:20000] or None,
        )
        status = (
            "manual-replaced-verified"
            if existing and existing.bgg_id
            else "manual-verified"
        )
        detail = (
            "BoardGameGeek association replaced and verified from a supplied URL."
            if existing and existing.bgg_id
            else "BoardGameGeek association created and verified from a supplied URL."
        )
    else:
        # Preserve the supplied slug without fetching or guessing BGG metadata.
        association = BggAssociation(
            game_id=game_id,
            lookup_enabled=False,
            match_state=BggMatchState.MANUAL,
            source_title=game.detected_title,
            bgg_id=bgg_id,
            url_slug=slug,
        )
        status = "manual-replaced" if existing and existing.bgg_id else "manual-linked"
        detail = (
            "BoardGameGeek association replaced from an unverified supplied URL."
            if existing and existing.bgg_id
            else "BoardGameGeek association created from an unverified supplied URL."
        )
    saved = save_bgg_association(
        database,
        association,
        expected=existing,
    )
    if not saved:
        return _game_edit_redirect(game_id, bgg_error="association-changed")
    if client is not None:
        apply_bgg_categories(database, game_id, details, mode="empty-only")
    record_activity(
        _database(request),
        "bgg_link_updated",
        game.title,
        detail=detail,
        game_id=game_id,
    )
    return _game_edit_redirect(game_id, bgg_status=status)


@router.post("/games/{game_id}/bgg/edition", name="game_bgg_edition_save")
async def game_bgg_edition_save(request: Request, game_id: int):
    database = _database(request)
    game = get_game(database, game_id)
    if game is None:
        raise HTTPException(404, "Game not found")
    form = await request.form()
    association = get_bgg_association(database, game_id)
    try:
        edition = BggEdition(
            parse_edition_reference(str(form.get("edition_reference", ""))),
            str(form.get("edition_label", "")).strip(),
            association.bgg_id if association else None,
        )
    except ValueError:
        return _game_edit_redirect(game_id, bgg_error="invalid-edition")
    previous = get_bgg_edition(database, game_id)
    previous_values = previous is not None and previous.version_id != edition.version_id
    save_bgg_edition(database, game_id, edition)
    client = (
        _bgg_client(request) if association and association.last_lookup_at else None
    )
    if (
        client is not None
        and association is not None
        and association.bgg_id is not None
        and association.last_lookup_at is not None
        and (not edition.label or game.box_dimensions is None)
    ):
        try:
            found = fill_blank_version_details(
                database,
                client,
                game_id=game_id,
                parent_bgg_id=association.bgg_id,
                version_id=edition.version_id,
            )
        except BggApiError:
            return _game_edit_redirect(
                game_id, bgg_status="edition-saved-bgg-unavailable"
            )
        if not found:
            return _game_edit_redirect(game_id, bgg_status="edition-saved-no-details")
    return _game_edit_redirect(
        game_id,
        bgg_status="edition-saved-review-previous"
        if previous_values
        else "edition-saved",
    )


@router.post("/games/{game_id}/bgg/resolve-url", name="game_bgg_resolve_url")
def game_bgg_resolve_url(request: Request, game_id: int):
    database = _database(request)
    if get_game(database, game_id) is None:
        raise HTTPException(404, "Game not found")
    association = get_bgg_association(database, game_id)
    if association is None or association.bgg_id is None:
        return _game_edit_redirect(game_id, bgg_error="not-linked")
    slug = association.url_slug or resolve_game_slug(association.bgg_id)
    if slug is None:
        return _game_edit_redirect(game_id, bgg_status="page-link-unavailable")
    with database.connect() as connection:
        # Only repair the association we inspected; never overwrite a newer selection.
        connection.execute(
            "UPDATE game_bgg_associations SET url_slug=? "
            "WHERE game_id=? AND bgg_id=? AND url_slug IS NULL",
            (slug, game_id, association.bgg_id),
        )
    if request.query_params.get("open") == "versions":
        current = get_bgg_association(database, game_id)
        if (
            current is None
            or current.bgg_id != association.bgg_id
            or not current.versions_url
        ):
            return _game_edit_redirect(game_id, bgg_status="page-link-unavailable")
        return RedirectResponse(current.versions_url, status_code=303)
    return _game_edit_redirect(game_id, bgg_status="page-link-resolved")


@router.post("/games/{game_id}/bgg/edition/remove", name="game_bgg_edition_remove")
def game_bgg_edition_remove(request: Request, game_id: int):
    database = _database(request)
    if get_game(database, game_id) is None:
        raise HTTPException(404, "Game not found")
    save_bgg_edition(database, game_id, None)
    return _game_edit_redirect(game_id, bgg_status="edition-removed")


@router.post(
    "/games/{game_id}/bgg/unlink",
    response_class=RedirectResponse,
    name="game_bgg_unlink",
)
def game_bgg_unlink(request: Request, game_id: int) -> RedirectResponse:
    """Remove BGG state without changing the local game or its files."""
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    delete_bgg_association(_database(request), game_id)
    record_activity(
        _database(request),
        "bgg_link_removed",
        game.title,
        detail="BoardGameGeek link removed.",
        game_id=game_id,
    )
    return _game_edit_redirect(game_id, bgg_status="unlinked")


@router.post(
    "/games/{game_id}/bgg/lookup",
    response_class=RedirectResponse,
    name="game_bgg_lookup_toggle",
)
async def game_bgg_lookup_toggle(request: Request, game_id: int) -> RedirectResponse:
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
    record_activity(
        _database(request),
        "bgg_lookup_updated",
        game.title,
        detail=(
            "BoardGameGeek lookup enabled."
            if enabled
            else "BoardGameGeek lookup disabled."
        ),
        game_id=game_id,
    )
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

    qr_restricted = requires_sign_in(_database(request), resource_id)
    if qr_restricted and request.state.auth_enabled and not request.state.user:
        return RedirectResponse(
            "/login?" + urlencode({"next": request.url.path}), status_code=303
        )

    available = True
    generated_available = False
    try:
        source = resolve_resource_pdf(
            request.app.state.settings.library_path,
            resource.relative_path,
        )
        base_url = request.app.state.settings.base_url
        if base_url:
            generated_available = (
                _existing_reprint(request, source, resource_id) is not None
            )
    except (ResourceFileMissing, UnsafeResourcePath):
        available = False

    if request.state.auth_enabled and not request.state.user:
        return templates.TemplateResponse(
            request=request,
            name="qr_resource.html",
            context={
                "resource": resource,
                "game": game,
                "generated_available": generated_available,
            },
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

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
            "qr_requires_sign_in": qr_restricted,
        },
    )


def _qr_resource(request: Request, resource_id: int):
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if (
        requires_sign_in(_database(request), resource_id)
        and request.state.auth_enabled
        and not request.state.user
    ):
        return RedirectResponse(
            "/login?" + urlencode({"next": f"/r/{resource_id}"}), status_code=303
        )
    try:
        source = resolve_resource_pdf(
            request.app.state.settings.library_path, resource.relative_path
        )
    except (ResourceFileMissing, UnsafeResourcePath):
        raise HTTPException(status_code=404, detail="Resource unavailable") from None
    return resource, source


def _qr_file(request: Request, resource_id: int, *, generated: bool):
    result = _qr_resource(request, resource_id)
    if isinstance(result, RedirectResponse):
        return result
    resource, source = result
    path = _existing_reprint(request, source, resource_id) if generated else source
    if path is None:
        raise HTTPException(
            status_code=409, detail="FORGE GameSheets Reprint unavailable"
        )
    game = get_game(_database(request), resource.game_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=_pdf_filename(
            game, resource, prefix="FORGE GameSheets Reprint" if generated else None
        ),
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/r/{resource_id}/original", name="resource_qr_original")
def resource_qr_original(request: Request, resource_id: int):
    return _qr_file(request, resource_id, generated=False)


@router.get("/r/{resource_id}/reprint", name="resource_qr_reprint")
def resource_qr_reprint(request: Request, resource_id: int):
    return _qr_file(request, resource_id, generated=True)


@router.post("/resources/{resource_id}/qr-access", name="resource_qr_policy_save")
async def resource_qr_policy_save(request: Request, resource_id: int):
    resource = get_resource(_database(request), resource_id)
    form = await request.form()
    if not set_requires_sign_in(
        _database(request),
        resource_id,
        required=form.get("requires_sign_in") == "1",
    ):
        raise HTTPException(status_code=404, detail="Resource not found")
    record_activity(
        _database(request),
        "qr_access_updated",
        resource.title,
        detail="QR access restriction updated.",
        game_id=resource.game_id,
        resource_id=resource.id,
    )
    return _reprint_redirect(resource_id, status="qr-policy-saved")


@router.post(
    "/resources/{resource_id}/forge-reprint",
    response_class=RedirectResponse,
    name="resource_reprint_generate",
)
def resource_reprint_generate(request: Request, resource_id: int) -> RedirectResponse:
    """Generate a FORGE GameSheets-marked copy without changing the source PDF."""
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
def resource_reprint_regenerate(request: Request, resource_id: int) -> RedirectResponse:
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
    """Open the current FORGE GameSheets-marked copy for deliberate printing."""
    return _generated_reprint_response(request, resource_id, disposition="inline")


@router.get(
    "/resources/{resource_id}/forge-reprint/download",
    response_class=FileResponse,
    name="resource_reprint_download",
)
def resource_reprint_download(request: Request, resource_id: int) -> FileResponse:
    """Download the current FORGE GameSheets-marked copy."""
    return _generated_reprint_response(request, resource_id, disposition="attachment")


@router.get(
    "/resources/{resource_id}/preview",
    response_class=FileResponse,
    name="resource_preview",
)
def resource_preview(request: Request, resource_id: int) -> FileResponse:
    """Serve a PDF thumbnail or a scanned image for a resource preview."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.provider == "image":
        try:
            preview = cached_image_preview(
                request.app.state.settings.library_path,
                request.app.state.settings.data_path,
                resource,
            )
        except (ResourceFileMissing, UnsafeResourcePath, PreviewUnavailable) as error:
            raise HTTPException(404, "Preview unavailable") from error
        return FileResponse(
            preview,
            media_type="image/webp",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    if resource.provider != "pdf":
        raise HTTPException(404, "Preview unavailable")
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
    """Serve an indexed PDF or image inline for browser viewing."""
    return _resource_response(request, resource_id, disposition="inline", action="view")


@router.get(
    "/resources/{resource_id}/download",
    response_class=FileResponse,
    name="resource_download",
)
def resource_download(request: Request, resource_id: int) -> FileResponse:
    """Serve a supported indexed file as an explicit download."""
    return _resource_response(
        request, resource_id, disposition="attachment", action="download"
    )


@router.post(
    "/resources/{resource_id}/open-in-designer", name="resource_open_in_designer"
)
def resource_open_in_designer(request: Request, resource_id: int) -> RedirectResponse:
    """Import an editable copy without modifying the library FGS source."""
    resource = get_resource(_database(request), resource_id)
    if resource is None or resource.provider != "fgs":
        raise HTTPException(404, "FGS file not found")
    try:
        path = resolve_resource_file(
            request.app.state.settings.library_path, resource.relative_path, "fgs"
        )
        with path.open("rb") as source:
            payload = source.read(MAX_DOCUMENT_BYTES + 1)
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise HTTPException(422, "FGS file exceeds the import limit")
        request.app.state.sheet_designer_store.import_document(
            json.loads(payload.decode("utf-8"))
        )
    except (ResourceFileMissing, UnsafeResourcePath) as error:
        raise HTTPException(410, "FGS file is unavailable") from error
    except (
        UnicodeError,
        ValueError,
        TypeError,
        AttributeError,
        DocumentValidationError,
    ) as error:
        raise HTTPException(422, "FGS file could not be imported") from error
    return RedirectResponse("/sheet-designer?resume=1", status_code=303)


@router.get(
    "/resources/{resource_id}/fgs-preview",
    response_class=HTMLResponse,
    name="resource_fgs_preview",
)
def resource_fgs_preview(request: Request, resource_id: int) -> HTMLResponse:
    """Show a library FGS without importing it into Sheet Designer."""
    resource, document = _fgs_resource_document(request, resource_id)
    return templates.TemplateResponse(
        request=request,
        name="fgs_preview.html",
        context={"resource": resource, "sheet_title": document["title"]},
    )


@router.get(
    "/resources/{resource_id}/fgs-preview.webp",
    response_class=Response,
    name="resource_fgs_preview_image",
)
def resource_fgs_preview_image(request: Request, resource_id: int) -> Response:
    """Render a bounded, temporary image of the library FGS source."""
    _, document = _fgs_resource_document(request, resource_id)
    data_path = request.app.state.settings.data_path
    try:
        with processing_budget.rendering_slot(data_path):
            processing_budget.check_storage_budget(
                data_path, MAX_PDF_BYTES + processing_budget.MAX_PREVIEW_BYTES
            )
            with TemporaryDirectory(prefix=".fgs-preview-", dir=data_path) as work:
                pdf = Path(work) / "sheet.pdf"
                image = Path(work) / "sheet.webp"
                render_pdf(document, pdf)
                render_pdf_preview(pdf, image, preview_size=(850, 1100))
                payload = image.read_bytes()
    except PageOverflowError as error:
        raise HTTPException(422, "FGS sheet does not fit the preview page") from error
    except (
        RendererUnavailableError,
        PreviewUnavailable,
        processing_budget.ProcessingBudgetError,
        OSError,
        ValueError,
    ) as error:
        raise HTTPException(503, "FGS preview is unavailable") from error
    return Response(
        payload,
        media_type="image/webp",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/resources/{resource_id}/open-matching-fgs",
    response_class=HTMLResponse,
    name="resource_open_matching_fgs",
)
def resource_open_matching_fgs(
    request: Request, resource_id: int
) -> Response:
    """Open one identical sheet or ask which separate copy to open."""
    resource, document = _fgs_resource_document(request, resource_id)
    store = request.app.state.sheet_designer_store
    choices = store.matching_document_choices(document)
    if not choices:
        return RedirectResponse(
            url=f"/resources/{resource_id}/fgs-preview", status_code=303
        )
    if len(choices) > 1:
        return templates.TemplateResponse(
            request=request,
            name="fgs_match_choices.html",
            context={
                "resource": resource,
                "sheet_title": document["title"],
                "choices": choices,
            },
        )
    try:
        store.open(choices[0]["id"])
    except ValueError:
        return RedirectResponse(
            url=f"/resources/{resource_id}/fgs-preview", status_code=303
        )
    return RedirectResponse("/sheet-designer?resume=1", status_code=303)


@router.post(
    "/resources/{resource_id}/open-matching-fgs",
    response_class=RedirectResponse,
    name="resource_open_selected_fgs",
)
async def resource_open_selected_fgs(
    request: Request, resource_id: int
) -> RedirectResponse:
    """Recheck the chosen saved copy before changing the active Designer sheet."""
    form = await request.form()
    selected_id = str(form.get("workspace_id", ""))
    _, document = _fgs_resource_document(request, resource_id)
    store = request.app.state.sheet_designer_store
    if selected_id not in store.matching_document_ids(document):
        return RedirectResponse(
            url=f"/resources/{resource_id}/open-matching-fgs", status_code=303
        )
    try:
        store.open(selected_id)
    except ValueError:
        return RedirectResponse(
            url=f"/resources/{resource_id}/open-matching-fgs", status_code=303
        )
    return RedirectResponse("/sheet-designer?resume=1", status_code=303)


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
        target_url = preferred_reprint_target(
            _database(request),
            request.app.state.settings.base_url,
            resource_id,
        )
        output = generate_forge_reprint(
            source,
            request.app.state.settings.data_path,
            resource_id=resource_id,
            target_url=target_url,
            force=force,
        )
        record_validated_reprint(
            _database(request),
            source,
            output,
            resource_id=resource_id,
            target_url=target_url,
        )
        return output
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
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    game = get_game(_database(request), resource.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        source = resolve_resource_pdf(
            request.app.state.settings.library_path,
            resource.relative_path,
        )
        path = _existing_reprint(request, source, resource_id)
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410,
            detail="This PDF was removed after the last library scan.",
        ) from error
    except UnsafeResourcePath:
        raise HTTPException(status_code=404, detail="Resource not found")
    except ReprintGenerationError as error:
        raise HTTPException(
            status_code=422, detail="FORGE GameSheets Reprint unavailable."
        ) from error
    if path is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Generate the FORGE GameSheets Reprint before opening "
                "or downloading it."
            ),
        )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=_pdf_filename(game, resource, prefix="FORGE GameSheets Reprint"),
        content_disposition_type=disposition,
        headers={"Cache-Control": "no-store"},
    )


def _existing_reprint(request: Request, source: Path, resource_id: int) -> Path | None:
    for target in readable_reprint_targets(
        _database(request), request.app.state.settings.base_url, resource_id
    ):
        path = existing_forge_reprint(
            source,
            request.app.state.settings.data_path,
            resource_id=resource_id,
            target_url=target,
        )
        if path:
            return path
    return None


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
    *, status: str | None = None, error: str | None = None, anchor: str | None = None
) -> RedirectResponse:
    query = urlencode(
        {key: value for key, value in (("status", status), ("error", error)) if value}
    )
    return RedirectResponse(
        url=(f"/settings?{query}" if query else "/settings")
        + (f"#{anchor}" if anchor else ""),
        status_code=303,
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
            "selected_category_ids": {category.id for category in game.categories},
            "bgg_association": get_bgg_association(_database(request), game.id),
            "game_resource_links": {
                link.kind: link
                for link in list_game_resource_links(_database(request), game.id)
            },
            "links_status": request.query_params.get("links_status"),
            "links_error": request.query_params.get("links_error"),
            "bgg_configured": bool(request.app.state.settings.bgg_api_token),
            "bgg_candidates": bgg_candidates,
            "bgg_query": bgg_query or game.detected_title,
            "bgg_edition": get_bgg_edition(_database(request), game.id),
            "bgg_edition_sources": get_edition_sources(_database(request), game.id),
            "bgg_status": request.query_params.get("bgg_status"),
            "bgg_error": bgg_error or request.query_params.get("bgg_error"),
        },
    )


def _bgg_client(request: Request) -> BggClient | None:
    token = request.app.state.settings.bgg_api_token
    if token is None:
        return None
    factory = getattr(request.app.state, "bgg_client_factory", BggClient)
    if factory is BggClient:
        return BggClient(
            token,
            request_pacer=request.app.state.bgg_request_pacer,
            category_enabled=lambda: get_preferences(_database(request)).bgg_categories,
        )
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
    return RedirectResponse(
        url=f"/games/{game_id}/edit{suffix}#bgg-integration", status_code=303
    )


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
    names = sorted(name for name in available_timezones() if name.startswith(regions))
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

    if resource.provider == "other" or (
        disposition == "inline" and resource.provider not in {"pdf", "image"}
    ):
        raise HTTPException(404, "Resource cannot be opened this way")
    try:
        path = resolve_resource_file(
            request.app.state.settings.library_path,
            resource.relative_path,
            resource.provider,
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410,
            detail="This file was removed after the last library scan.",
        ) from error
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=404, detail="Resource not found") from error

    record_resource_use(_database(request), resource_id, action=action)
    media_type = "application/octet-stream"
    if resource.provider == "pdf":
        media_type = "application/pdf"
    elif resource.provider == "image":
        media_type = IMAGE_MIME_TYPES[path.suffix.casefold()]
    filename = (
        _pdf_filename(game, resource) if resource.provider == "pdf" else path.name
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type=disposition,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _pdf_filename(
    game: GameDetail, resource: IndexedResource, *, prefix: str | None = None
) -> str:
    """Build a portable filename from trusted display metadata."""
    parts = [prefix, game.title, resource.title, resource.variant]
    readable = " - ".join(part for part in parts if part)
    portable = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]+', " ", readable)
    portable = " ".join(portable.split()).strip(" .-")[:180].rstrip(" .-")
    return f"{portable or 'FORGE GameSheets resource'}.pdf"
