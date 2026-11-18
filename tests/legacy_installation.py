"""Explicit pre-owner-setup fixtures for existing trusted-mode regressions."""

from app.database import MIGRATIONS, Database, _apply_migration
from app.main import create_app as create_current_app


def create_app(settings=None, build_info=None):
    # Existing workflow suites exercise upgraded open installations. Seed the
    # real pre-38 migration history; do not bypass production authorization.
    if settings is not None:
        database = Database.in_data_directory(settings.data_path)
        if not database.path.exists():
            with database.connect() as connection:
                connection.execute(
                    "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
                    "name TEXT NOT NULL)"
                )
                for migration in MIGRATIONS:
                    if migration.version < 38:
                        _apply_migration(connection, migration)
    return create_current_app(settings, build_info)
