"""Portable game-link exports and deliberate manifest imports."""

from __future__ import annotations

import hashlib
import io
import json
import plistlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from app.database import Database
from app.library.artwork import save_uploaded_artwork
from app.library.game_links import _validate_link
from app.library.processing_limits import validate_image_pixels
from app.library.repository import save_game_artwork_override

FORMAT = "forge-gamesheets-metadata"
VERSION = "1.0"
KINDS = {"official", "alternate", "bgg"}
LABELS = {
    "official": "Official resource",
    "alternate": "Alternate resource",
    "bgg": "BoardGameGeek",
}
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_EXPORT_BYTES = 24 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LinkImportPreview:
    entries: tuple[dict, ...]
    add: int
    replace: int
    unchanged: int
    skipped: int


@dataclass(frozen=True, slots=True)
class ArtworkImport:
    game_directory: str
    filename: str
    content: bytes


@dataclass(frozen=True, slots=True)
class MetadataImport:
    entries: tuple[dict, ...]
    artwork: tuple[ArtworkImport, ...] = ()


def export_links(database: Database, data_path: Path | None = None) -> bytes:
    with database.connect() as connection:
        rows = connection.execute("""
            SELECT g.relative_path AS game_directory, l.kind, l.description, l.url
            FROM games g JOIN game_resource_links l ON l.game_id=g.id
            UNION ALL
            SELECT g.relative_path, 'bgg', 'BoardGameGeek',
                   'https://boardgamegeek.com/boardgame/' || b.bgg_id ||
                   CASE WHEN b.url_slug IS NULL THEN '' ELSE '/' || b.url_slug END
            FROM games g JOIN game_bgg_associations b ON b.game_id=g.id
            WHERE b.bgg_id IS NOT NULL
            ORDER BY game_directory, kind
        """).fetchall()
        artwork_rows = connection.execute("""
            SELECT g.relative_path AS game_directory, a.relative_path
            FROM games g JOIN game_artwork_overrides a ON a.game_id=g.id
            ORDER BY g.relative_path
        """).fetchall()
    entries = [dict(row) for row in rows]
    artwork_records = []
    artwork_files = []
    if data_path is not None:
        root = data_path.resolve(strict=True)
        for row in artwork_rows:
            candidate = root.joinpath(*Path(row["relative_path"]).parts)
            try:
                resolved = candidate.resolve(strict=True)
            except (FileNotFoundError, OSError):
                continue
            if not resolved.is_file() or not resolved.is_relative_to(root):
                continue
            suffix = hashlib.sha256(row["game_directory"].encode()).hexdigest()[:12]
            archive_name = f"artwork/{_filename(row['game_directory'])}-{suffix}.webp"
            artwork_records.append(
                {"game_directory": row["game_directory"], "file": archive_name}
            )
            artwork_files.append((archive_name, resolved.read_bytes()))
    manifest = {
        "format": FORMAT,
        "format_version": VERSION,
        "entries": entries,
        "artwork": artwork_records,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "forge-metadata-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        for entry in entries:
            stem = f"{_filename(entry['game_directory'])} - {LABELS[entry['kind']]}"
            archive.writestr(
                stem + ".url", f"[InternetShortcut]\r\nURL={entry['url']}\r\n"
            )
            archive.writestr(stem + ".webloc", plistlib.dumps({"URL": entry["url"]}))
        for archive_name, content in artwork_files:
            archive.writestr(archive_name, content)
    return output.getvalue()


def parse_export(payload: bytes) -> MetadataImport:
    """Validate a Forge ZIP export, or accept a manifest-only JSON fallback."""
    if len(payload) > MAX_EXPORT_BYTES:
        raise ValueError("The metadata export is too large.")
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        return MetadataImport(parse_manifest(payload))
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            value = _manifest_value(archive.read("forge-metadata-manifest.json"))
            entries = _manifest_entries(value)
            artwork = []
            total_artwork_bytes = 0
            for item in value.get("artwork", []):
                if (
                    not isinstance(item, dict)
                    or set(item) != {"game_directory", "file"}
                    or not _valid_game_directory(item["game_directory"])
                    or not isinstance(item["file"], str)
                    or not re.fullmatch(r"artwork/[^/]+\.webp", item["file"])
                ):
                    raise ValueError("An artwork manifest entry is invalid.")
                info = archive.getinfo(item["file"])
                if info.file_size > 25 * 1024 * 1024:
                    raise ValueError("Exported artwork exceeds the size limit.")
                total_artwork_bytes += info.file_size
                if total_artwork_bytes > MAX_EXPORT_BYTES:
                    raise ValueError("The metadata export is too large.")
                content = archive.read(info)
                _validate_artwork(content)
                artwork.append(
                    ArtworkImport(item["game_directory"], item["file"], content)
                )
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        raise ValueError("The metadata export is incomplete or invalid.") from error
    identities = [item.game_directory for item in artwork]
    if len(identities) != len(set(identities)):
        raise ValueError("The metadata export contains duplicate artwork entries.")
    return MetadataImport(entries, tuple(artwork))


def parse_manifest(payload: bytes) -> tuple[dict, ...]:
    return _manifest_entries(_manifest_value(payload))


def _manifest_value(payload: bytes) -> dict:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("The link manifest is too large.")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The link manifest is not valid JSON.") from error
    if (
        not isinstance(value, dict)
        or value.get("format") != FORMAT
        or value.get("format_version") != VERSION
        or set(value)
        not in (
            {"format", "format_version", "entries"},
            {"format", "format_version", "entries", "artwork"},
        )
    ):
        raise ValueError("The link manifest format or version is unsupported.")
    if not isinstance(value.get("artwork", []), list):
        raise ValueError("The artwork manifest entries are invalid.")
    return value


def _manifest_entries(value: dict) -> tuple[dict, ...]:
    entries = value["entries"]
    if not isinstance(entries, list) or len(entries) > 10000:
        raise ValueError("The link manifest entries are invalid.")
    normalized = tuple(_entry(item) for item in entries)
    identities = [(item["game_directory"], item["kind"]) for item in normalized]
    if len(identities) != len(set(identities)):
        raise ValueError("The link manifest contains duplicate game link types.")
    return normalized


def preview_import(
    database: Database,
    entries: tuple[dict, ...],
    policy: str,
    artwork: tuple[ArtworkImport, ...] = (),
) -> LinkImportPreview:
    if policy not in {"empty", "replace"}:
        raise ValueError("Invalid import policy.")
    with database.connect() as connection:
        games = {
            row["relative_path"]: row
            for row in connection.execute("SELECT id, relative_path FROM games")
        }
        current = {
            (row["relative_path"], row["kind"]): row["url"]
            for row in connection.execute(
                "SELECT g.relative_path, l.kind, l.url FROM games g "
                "JOIN game_resource_links l ON l.game_id=g.id"
            )
        }
        current.update(
            {
                (row["relative_path"], "bgg"): str(row["bgg_id"])
                for row in connection.execute(
                    "SELECT g.relative_path, b.bgg_id FROM games g "
                    "JOIN game_bgg_associations b ON b.game_id=g.id "
                    "WHERE b.bgg_id IS NOT NULL"
                )
            }
        )
        current_artwork = {
            row["relative_path"]
            for row in connection.execute(
                "SELECT g.relative_path FROM games g JOIN game_artwork_overrides a "
                "ON a.game_id=g.id"
            )
        }
    add = replace = unchanged = skipped = 0
    for item in entries:
        if item["game_directory"] not in games:
            skipped += 1
            continue
        existing = current.get((item["game_directory"], item["kind"]))
        comparable = str(_bgg_id(item["url"])) if item["kind"] == "bgg" else item["url"]
        if existing == comparable:
            unchanged += 1
        elif existing is None:
            add += 1
        elif policy == "replace":
            replace += 1
        else:
            skipped += 1
    for item in artwork:
        if item.game_directory not in games:
            skipped += 1
        elif item.game_directory not in current_artwork:
            add += 1
        elif policy == "replace":
            replace += 1
        else:
            skipped += 1
    return LinkImportPreview(entries, add, replace, unchanged, skipped)


def apply_import(
    database: Database,
    entries: tuple[dict, ...],
    policy: str,
    artwork: tuple[ArtworkImport, ...] = (),
    data_path: Path | None = None,
) -> LinkImportPreview:
    preview = preview_import(database, entries, policy, artwork)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            games = {
                r["relative_path"]: r
                for r in connection.execute(
                    "SELECT id, relative_path, title FROM games"
                )
            }
            for item in entries:
                game = games.get(item["game_directory"])
                if not game:
                    continue
                if item["kind"] == "bgg":
                    bgg_id = _bgg_id(item["url"])
                    exists = connection.execute(
                        "SELECT bgg_id FROM game_bgg_associations WHERE game_id=?",
                        (game["id"],),
                    ).fetchone()
                    if exists and exists["bgg_id"] is not None and policy == "empty":
                        continue
                    connection.execute(
                        """INSERT INTO game_bgg_associations
                        (game_id,lookup_enabled,match_state,bgg_id,source_title,url_slug)
                        VALUES (?,1,'manual',?,?,?) ON CONFLICT(game_id) DO UPDATE SET
                        match_state='manual', bgg_id=excluded.bgg_id,
                        source_title=excluded.source_title,
                        url_slug=excluded.url_slug, match_confidence=NULL,
                        cached_name=NULL, year_published=NULL, image_url=NULL,
                        thumbnail_url=NULL, failure_code=NULL, last_lookup_at=NULL""",
                        (game["id"], bgg_id, game["title"], _bgg_slug(item["url"])),
                    )
                else:
                    exists = connection.execute(
                        "SELECT 1 FROM game_resource_links WHERE game_id=? AND kind=?",
                        (game["id"], item["kind"]),
                    ).fetchone()
                    if exists and policy == "empty":
                        continue
                    connection.execute(
                        """INSERT INTO game_resource_links
                        (game_id,kind,description,url,display_order) VALUES (?,?,?,?,?)
                        ON CONFLICT(game_id,kind) DO UPDATE SET
                        description=excluded.description, url=excluded.url""",
                        (
                            game["id"],
                            item["kind"],
                            item["description"],
                            item["url"],
                            0 if item["kind"] == "official" else 1,
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    if artwork:
        if data_path is None:
            raise ValueError("Application data storage is required for artwork import.")
        with database.connect() as connection:
            games = {
                row["relative_path"]: row["id"]
                for row in connection.execute("SELECT id, relative_path FROM games")
            }
            existing = {
                row["game_id"]
                for row in connection.execute(
                    "SELECT game_id FROM game_artwork_overrides"
                )
            }
        for item in artwork:
            game_id = games.get(item.game_directory)
            if game_id is None or (game_id in existing and policy == "empty"):
                continue
            saved = save_uploaded_artwork(data_path, game_id, item.content)
            save_game_artwork_override(database, saved)
    return preview


def scan_shortcuts(library: Path) -> tuple[dict, ...]:
    entries = []
    root = library.resolve(strict=True)
    for path in root.rglob("*"):
        if (
            path.suffix.lower() not in {".url", ".webloc"}
            or not path.is_file()
            or path.is_symlink()
        ):
            continue
        relative = path.resolve().relative_to(root)
        if len(relative.parts) < 2:
            continue
        kind = _kind(path.stem)
        if not kind:
            continue
        try:
            url = _shortcut_url(path)
            entry = _entry(
                {
                    "game_directory": relative.parts[0],
                    "kind": kind,
                    "description": LABELS[kind],
                    "url": url,
                }
            )
        except (KeyError, OSError, TypeError, ValueError):
            continue
        entries.append(entry)
    unique = {(x["game_directory"], x["kind"], x["url"]): x for x in entries}
    return tuple(unique.values())


def _entry(value):
    if not isinstance(value, dict) or set(value) != {
        "game_directory",
        "kind",
        "description",
        "url",
    }:
        raise ValueError("A link manifest entry is invalid.")
    game = value["game_directory"]
    if not _valid_game_directory(game):
        raise ValueError("A game directory is invalid.")
    kind = value["kind"]
    if kind not in KINDS:
        raise ValueError("A link type is invalid.")
    description = value["description"]
    url = value["url"]
    if not isinstance(description, str) or len(description) > 120:
        raise ValueError("A link description is invalid.")
    if kind == "bgg":
        _bgg_id(url)
    else:
        _validate_link(kind, description, url)
    return {
        "game_directory": game,
        "kind": kind,
        "description": description,
        "url": url,
    }


def _valid_game_directory(game):
    return (
        isinstance(game, str)
        and bool(game)
        and "/" not in game
        and "\\" not in game
        and game not in {".", ".."}
    )


def _filename(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:120] or "Game"


def _validate_artwork(content):
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Unsupported artwork format.")
            validate_image_pixels(*image.size)
            image.load()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise ValueError("Exported artwork is invalid.") from error


def _kind(stem):
    lower = stem.lower()
    return next(
        (
            k
            for k, label in LABELS.items()
            if lower == label.lower() or lower.endswith(" - " + label.lower())
        ),
        None,
    )


def _bgg_id(url):
    parsed = urlsplit(url)
    match = re.fullmatch(r"/boardgame/(\d+)(?:/([A-Za-z0-9_-]{1,200}))?/?", parsed.path)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"boardgamegeek.com", "www.boardgamegeek.com"}
        or not match
    ):
        raise ValueError("A BoardGameGeek URL is invalid.")
    return int(match.group(1))


def _bgg_slug(url):
    parts = urlsplit(url).path.strip("/").split("/")
    return parts[2] if len(parts) > 2 else None


def _shortcut_url(path):
    if path.stat().st_size > 16 * 1024:
        raise ValueError("Shortcut too large")
    if path.suffix.lower() == ".webloc":
        return plistlib.loads(path.read_bytes())["URL"]
    match = re.search(r"(?im)^URL=(.+)$", path.read_text(encoding="utf-8-sig"))
    if not match:
        raise ValueError("Missing URL")
    return match.group(1).strip()
