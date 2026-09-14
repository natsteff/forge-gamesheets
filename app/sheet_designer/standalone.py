"""Standalone development shell for the sheet designer module."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from app.config import normalize_host
from app.security import (
    AllowedHosts,
    BrowserSecurityHeaders,
    LimitedRequestBodies,
    SameOriginMutations,
)
from app.sheet_designer.storage import FileDraftStore
from app.sheet_designer.web import router


def create_standalone_app(data_root: Path | None = None) -> FastAPI:
    package_root = Path(__file__).resolve().parents[1]
    application = FastAPI(title="Forge GameSheets Sheet Designer")
    application.add_middleware(LimitedRequestBodies)
    application.add_middleware(SameOriginMutations)
    application.add_middleware(AllowedHosts)
    application.add_middleware(BrowserSecurityHeaders)
    application.mount(
        "/static", StaticFiles(directory=package_root / "static"), name="static"
    )
    root = data_root or Path(
        os.environ.get("FORGE_SHEET_DESIGNER_DATA", "/tmp/forge-sheet-designer")
    )
    application.state.sheet_designer_store = FileDraftStore(root)
    application.state.sheet_designer_templates = Jinja2Templates(
        directory=package_root / "templates"
    )
    application.state.sheet_designer_template = "sheet_designer_standalone.html"
    application.state.sheet_designer_standalone = True
    hosts = ["localhost", "127.0.0.1", "::1"]
    hosts.extend(
        item.strip()
        for item in os.environ.get("FORGE_GAMESHEETS_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    )
    application.state.settings = SimpleNamespace(
        allowed_hosts=tuple(dict.fromkeys(normalize_host(item) for item in hosts))
    )
    application.include_router(router)

    @application.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/sheet-designer")

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "forge-gamesheets",
            "mode": "designer",
        }

    return application


app = create_standalone_app()
