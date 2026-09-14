"""Standalone development shell for the sheet designer module."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from app.sheet_designer.storage import FileDraftStore
from app.sheet_designer.web import router


def create_standalone_app(data_root: Path | None = None) -> FastAPI:
    package_root = Path(__file__).resolve().parents[1]
    application = FastAPI(title="Forge GameSheets Sheet Designer")
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
    application.include_router(router)
    return application


app = create_standalone_app()
