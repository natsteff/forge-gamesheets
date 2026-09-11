"""Persist validation facts for app-managed generated reprints."""

import sqlite3
from pathlib import Path

from app.database import Database
from app.library.reprints import GENERATOR_VERSION


def record_validated_reprint(
    database: Database,
    source_path: Path,
    output_path: Path,
    *,
    resource_id: int,
    target_url: str,
) -> bool:
    """Record a reprint only after the generator has validated its PDF output."""
    try:
        source = source_path.stat()
        output = output_path.stat()
        with database.connect() as connection:
            connection.execute(
                """INSERT INTO generated_reprints (
                   resource_id, source_size_bytes, source_modified_ns,
                   generator_version, target_url, filename,
                   output_size_bytes, output_modified_ns
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(resource_id) DO UPDATE SET
                   source_size_bytes=excluded.source_size_bytes,
                   source_modified_ns=excluded.source_modified_ns,
                   generator_version=excluded.generator_version,
                   target_url=excluded.target_url,
                   filename=excluded.filename,
                   output_size_bytes=excluded.output_size_bytes,
                   output_modified_ns=excluded.output_modified_ns,
                   validated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (
                    resource_id,
                    source.st_size,
                    source.st_mtime_ns,
                    GENERATOR_VERSION,
                    target_url,
                    output_path.name,
                    output.st_size,
                    output.st_mtime_ns,
                ),
            )
    except (OSError, sqlite3.Error):
        return False
    return True
