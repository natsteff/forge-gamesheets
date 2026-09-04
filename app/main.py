"""HTTP application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.access import AccessControl, RedactSharingLinks
from app.build_info import BuildInfo
from app.config import Settings
from app.database import Database
from app.library.cache import cleanup_managed_files
from app.library.reconciliation import ReconciliationError, reconcile_scan
from app.library.scanner import scan_library
from app.security import (
    AllowedHosts,
    BrowserSecurityHeaders,
    LimitedRequestBodies,
    SameOriginMutations,
)
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
        scan_result = scan_library(validated.library_path)
        application.state.scan_issues = scan_result.issues
        try:
            application.state.last_reconciliation = reconcile_scan(
                database, scan_result
            )
            cleanup_managed_files(database, validated.data_path)
        except ReconciliationError:
            application.state.last_reconciliation = None
        application.state.settings = validated
        application.state.database = database
        yield

    identity = build_info or BuildInfo.from_environment()
    application = FastAPI(
        title="Forge GameSheets",
        description="Organize. Customize. Print. Play.",
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

    application.include_router(account_router)
    # Match the declared leaf routes, independent of FastAPI's lazy include
    # wrappers. Unknown/new app routes still default to Admin in AccessControl.
    application.state.access_routes = [*web_router.routes, *account_router.routes]
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
            "version": identity.version,
            "revision": identity.revision,
            "build_date": identity.build_date,
        }

    return application


app = create_app()
