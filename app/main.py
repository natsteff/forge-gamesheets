"""HTTP application entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import anyio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.access import AccessControl, RedactSharingLinks
from app.activity import record_scan
from app.bgg.client import BggClient
from app.bgg.jobs import RequestPacer, enqueue_initial, process_next, resume_interrupted
from app.build_info import BuildInfo
from app.config import Settings
from app.database import Database
from app.library.cache import cleanup_managed_files
from app.library.reconciliation import ReconciliationError, reconcile_scan
from app.library.reprint_maintenance import interrupt_active_jobs
from app.library.scanner import scan_library
from app.security import (
    AllowedHosts,
    BrowserSecurityHeaders,
    LimitedRequestBodies,
    SameOriginMutations,
)
from app.sheet_designer.storage import FileDraftStore
from app.sheet_designer.web import router as sheet_designer_router
from app.web import router as web_router


def create_app(
    settings: Settings | None = None, build_info: BuildInfo | None = None
) -> FastAPI:
    """Create an application whose filesystem settings validate at startup."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configured = settings or Settings.from_environment()
        validated = configured.validated()
        database = Database.in_data_directory(validated.data_path)
        database.initialize()
        with database.connect() as connection:
            before_game_ids = {
                row[0] for row in connection.execute("SELECT id FROM games")
            }
        interrupt_active_jobs(database)
        scan_result = scan_library(validated.library_path)
        application.state.scan_issues = scan_result.issues
        try:
            application.state.last_reconciliation = reconcile_scan(
                database, scan_result
            )
            if validated.bgg_api_token:
                with database.connect() as connection:
                    after_game_ids = {
                        row[0] for row in connection.execute("SELECT id FROM games")
                    }
                enqueue_initial(database, after_game_ids - before_game_ids)
            record_scan(database, application.state.last_reconciliation)
            cleanup_managed_files(database, validated.data_path)
        except ReconciliationError:
            application.state.last_reconciliation = None
            record_scan(database, issue_count=len(scan_result.issues))
        application.state.settings = validated
        application.state.database = database
        application.state.bgg_request_pacer = (
            RequestPacer() if validated.bgg_api_token else None
        )
        application.state.sheet_designer_store = FileDraftStore(
            validated.data_path / "sheet-designer"
        )
        worker = None
        if validated.bgg_api_token:
            resume_interrupted(database)
            worker = asyncio.create_task(
                _run_bgg_queue(
                    database,
                    validated.bgg_api_token,
                    application.state.bgg_request_pacer,
                )
            )
        try:
            yield
        finally:
            if worker is not None:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker

    identity = build_info or BuildInfo.from_environment()
    application = FastAPI(
        title="FORGE GameSheets",
        description="Collect. Create. Print. Play. Or Go Live with LiveSheets.",
        version=identity.version,
        lifespan=lifespan,
    )
    application.add_middleware(LimitedRequestBodies)
    application.add_middleware(AccessControl)
    application.add_middleware(SameOriginMutations)
    application.add_middleware(AllowedHosts)
    application.add_middleware(BrowserSecurityHeaders)
    application.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )
    application.include_router(web_router)
    from app.account_web import router as account_router
    from app.link_portability_web import router as link_portability_router
    from app.links_web import router as links_router
    from app.livesheet_web import router as livesheet_router
    from app.reprint_web import router as reprint_router

    application.include_router(account_router)
    application.include_router(reprint_router)
    application.include_router(link_portability_router)
    application.include_router(sheet_designer_router)
    application.include_router(livesheet_router)
    application.include_router(links_router)
    from app.web import templates

    application.state.sheet_designer_templates = templates
    application.state.sheet_designer_template = "sheet_designer.html"
    application.state.sheet_designer_standalone = False
    # Match the declared leaf routes, independent of FastAPI's lazy include
    # wrappers. Unknown/new app routes still default to Admin in AccessControl.
    application.state.access_routes = [
        *web_router.routes,
        *account_router.routes,
        *reprint_router.routes,
        *link_portability_router.routes,
        *sheet_designer_router.routes,
        *livesheet_router.routes,
        *links_router.routes,
    ]
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, RedactSharingLinks) for item in logger.filters):
        logger.addFilter(RedactSharingLinks())
    application.state.build_info = identity

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str | None]:
        """Report whether the HTTP service is available."""
        return {
            "status": "ok",
            "service": "forge-gamesheets",
            "mode": "full",
            "version": identity.version,
            "revision": identity.revision,
            "build_date": identity.build_date,
        }

    return application


app = create_app()


async def _run_bgg_queue(database: Database, token: str, pacer: RequestPacer) -> None:
    client = BggClient(token, request_pacer=pacer)
    while True:
        worked = await anyio.to_thread.run_sync(process_next, database, client)
        await asyncio.sleep(
            60.0 if worked == "rate-limited" else 0.5 if worked else 2.0
        )
