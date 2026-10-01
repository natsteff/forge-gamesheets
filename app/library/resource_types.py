"""Explicit file types supported by the library browser."""

from pathlib import Path

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
DOCUMENT_EXTENSIONS = frozenset(
    {
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".rtf",
        ".txt",
        ".md",
        ".csv",
        ".tsv",
    }
)
GAME_ARTWORK_FILENAMES = frozenset(
    f"{name}{extension}"
    for name in ("icon", "cover")
    for extension in (".png", ".webp", ".jpg", ".jpeg")
)


def is_reserved_game_artwork(path: str | Path) -> bool:
    """Only recognized artwork names at a game folder's top level are reserved."""
    parts = Path(path).parts
    return len(parts) == 2 and parts[1].casefold() in GAME_ARTWORK_FILENAMES


def is_artwork_named_file(path: str | Path) -> bool:
    """Identify top-level icon/cover stems, including unsupported formats."""
    parts = Path(path).parts
    return len(parts) == 2 and Path(parts[1]).stem.casefold() in {"icon", "cover"}


def resource_type_label(provider: str, relative_path: str) -> str:
    """Expose the file format for categorized non-PDF resources."""
    if provider == "fgs":
        return "FGS source"
    if provider in {"image", "document"}:
        kind = "Image" if provider == "image" else "Document"
        return f"{kind} ({Path(relative_path).suffix[1:].casefold()})"
    raise ValueError(f"Unsupported resource label provider: {provider}")


def resource_type(path: str | Path) -> str:
    suffix = Path(path).suffix.casefold()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".fgs":
        return "fgs"
    if suffix in IMAGE_MIME_TYPES:
        return "image"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    return "other"
