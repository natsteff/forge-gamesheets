"""Safe validation and cached rendering of detected game artwork."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.library.files import ResourceFileMissing, UnsafeResourcePath
from app.library.repository import GameArtwork

MAX_ARTWORK_BYTES = 25 * 1024 * 1024
THUMBNAIL_SIZE = (512, 512)
UPLOAD_SIZE = (1024, 1024)


def cached_game_artwork(
    library_path: Path, data_path: Path, artwork: GameArtwork
) -> Path:
    """Return a validated square WebP cache for detected library artwork."""
    if artwork.source == "data":
        return _resolve_data_artwork(data_path, artwork)
    source = _resolve_artwork(library_path, artwork)
    cache_directory = data_path / "artwork-cache"
    cache_directory.mkdir(parents=True, exist_ok=True)
    cache_path = cache_directory / (
        f"game-{artwork.game_id}-{artwork.modified_ns}-{artwork.size_bytes}.webp"
    )
    if cache_path.is_file():
        return cache_path

    temporary_path = cache_directory / f".{uuid4().hex}.tmp"
    try:
        with Image.open(source) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise UnsafeResourcePath("Unsupported game artwork format.")
            image.load()
            thumbnail = ImageOps.fit(
                image.convert("RGBA"), THUMBNAIL_SIZE, method=Image.Resampling.LANCZOS
            )
            thumbnail.save(temporary_path, format="WEBP", quality=88, method=6)
        temporary_path.replace(cache_path)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        temporary_path.unlink(missing_ok=True)
        raise UnsafeResourcePath("Invalid game artwork image.") from error
    return cache_path


def save_uploaded_artwork(data_path: Path, game_id: int, content: bytes) -> GameArtwork:
    """Validate and normalize an uploaded image into app-managed storage."""
    if not content or len(content) > MAX_ARTWORK_BYTES:
        raise UnsafeResourcePath("Uploaded artwork is empty or exceeds 25 MB.")
    artwork_directory = data_path / "game-artwork"
    artwork_directory.mkdir(parents=True, exist_ok=True)
    relative_path = Path("game-artwork") / f"game-{game_id}.webp"
    destination = data_path / relative_path
    temporary_path = artwork_directory / f".{uuid4().hex}.tmp"
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise UnsafeResourcePath("Unsupported uploaded artwork format.")
            image.load()
            normalized = ImageOps.fit(
                image.convert("RGBA"), UPLOAD_SIZE, method=Image.Resampling.LANCZOS
            )
            normalized.save(temporary_path, format="WEBP", quality=90, method=6)
        temporary_path.replace(destination)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        temporary_path.unlink(missing_ok=True)
        raise UnsafeResourcePath("Invalid uploaded artwork image.") from error
    metadata = destination.stat()
    return GameArtwork(
        game_id=game_id,
        relative_path=relative_path.as_posix(),
        size_bytes=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
        source="data",
    )


def delete_uploaded_artwork(data_path: Path, artwork: GameArtwork) -> None:
    """Delete an app-managed artwork file after its database override is removed."""
    if artwork.source != "data":
        return
    try:
        path = _resolve_data_artwork(data_path, artwork)
    except ResourceFileMissing:
        return
    path.unlink(missing_ok=True)


def _resolve_artwork(library_path: Path, artwork: GameArtwork) -> Path:
    if artwork.size_bytes > MAX_ARTWORK_BYTES:
        raise UnsafeResourcePath("Game artwork exceeds the size limit.")
    root = library_path.resolve(strict=True)
    relative = PurePosixPath(artwork.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise UnsafeResourcePath("Game artwork is outside the library.")
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise UnsafeResourcePath("Symbolic links cannot be served as artwork.")
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ResourceFileMissing("Game artwork is no longer available.") from error
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise UnsafeResourcePath("Game artwork is outside the library.")
    return resolved


def _resolve_data_artwork(data_path: Path, artwork: GameArtwork) -> Path:
    root = data_path.resolve(strict=True)
    relative = PurePosixPath(artwork.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise UnsafeResourcePath("Uploaded artwork is outside application data.")
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ResourceFileMissing("Uploaded artwork is no longer available.") from error
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise UnsafeResourcePath("Uploaded artwork is outside application data.")
    return resolved
