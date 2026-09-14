"""Select the supported Forge runtime without changing existing defaults."""

import os

from app.main import app as full_app
from app.sheet_designer.standalone import create_standalone_app

mode = os.environ.get("FORGE_GAMESHEETS_MODE", "full").strip().lower()
if mode == "full":
    app = full_app
elif mode == "designer":
    app = create_standalone_app()
else:
    raise RuntimeError("FORGE_GAMESHEETS_MODE must be 'full' or 'designer'.")
