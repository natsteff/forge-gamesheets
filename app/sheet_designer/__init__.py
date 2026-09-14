"""Portable FGS structured GameSheet support.

The public surface intentionally avoids importing Forge's library, account, or
database modules so the designer can run in its standalone shell.
"""

from app.sheet_designer.model import (
    FORMAT_NAME,
    FORMAT_VERSION,
    DocumentValidationError,
    migrate_document,
    normalize_document,
)
from app.sheet_designer.rendering import PageOverflowError, render_pdf
from app.sheet_designer.storage import FileDraftStore

__all__ = [
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "DocumentValidationError",
    "FileDraftStore",
    "PageOverflowError",
    "migrate_document",
    "normalize_document",
    "render_pdf",
]
