"""Folder hints and transactional bulk categorization; never write library files."""

import re


def folder_hint(name):
    match = re.fullmatch(r"([^\[\]]+?)\s*\[([^\[\]]+)\]", name)
    if not match:
        return name, ()
    title = match[1].strip()
    names = [part.strip() for part in match[2].split(",")]
    if not title or any(
        not value
        or len(value) > 60
        or value.casefold() in {"all games", "uncategorized"}
        or any(ord(char) < 32 for char in value)
        for value in names
    ):
        return name, ()
    unique = {}
    for value in names:
        unique.setdefault(value.casefold(), value)
    return title, tuple(unique.values())


def import_hint(connection, game_id, folder, *, title=False):
    display, names = folder_hint(folder)
    existing = {
        row["name"].casefold(): row["id"]
        for row in connection.execute("SELECT id,name FROM game_categories")
    }
    for name in names:
        category_id = existing.get(name.casefold())
        if category_id is None:
            category_id = connection.execute(
                "INSERT INTO game_categories(name) VALUES (?)", (name,)
            ).lastrowid
            existing[name.casefold()] = category_id
        connection.execute(
            "INSERT OR IGNORE INTO game_category_assignments VALUES (?,?)",
            (game_id, category_id),
        )
    if names and title:
        connection.execute(
            "INSERT OR IGNORE INTO game_overrides(game_id,title) VALUES (?,?)",
            (game_id, display),
        )


def bulk_apply(database, game_ids, category_ids, operation):
    if operation not in {"add", "remove", "replace", "clear", "folder"}:
        raise ValueError("Choose a valid operation.")
    games, categories = set(game_ids), set(category_ids)
    if not games or len(games) > 500:
        raise ValueError("Select between 1 and 500 games.")
    if operation in {"add", "remove", "replace"} and not categories:
        raise ValueError("Select at least one category.")
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            rows = {row["id"]: row for row in connection.execute("SELECT * FROM games")}
            valid = {
                row[0] for row in connection.execute("SELECT id FROM game_categories")
            }
            if not games <= rows.keys() or not categories <= valid:
                raise ValueError(
                    "A selected game or category no longer exists. Reload the page."
                )
            changed = 0
            for game_id in games:
                before = {
                    row[0]
                    for row in connection.execute(
                        "SELECT category_id FROM game_category_assignments "
                        "WHERE game_id=?",
                        (game_id,),
                    )
                }
                if operation == "folder":
                    import_hint(connection, game_id, rows[game_id]["relative_path"])
                else:
                    after = (
                        before | categories
                        if operation == "add"
                        else before - categories
                        if operation == "remove"
                        else categories
                        if operation == "replace"
                        else set()
                    )
                    connection.execute(
                        "DELETE FROM game_category_assignments WHERE game_id=?",
                        (game_id,),
                    )
                    connection.executemany(
                        "INSERT INTO game_category_assignments VALUES (?,?)",
                        ((game_id, category) for category in after),
                    )
                after = {
                    row[0]
                    for row in connection.execute(
                        "SELECT category_id FROM game_category_assignments "
                        "WHERE game_id=?",
                        (game_id,),
                    )
                }
                changed += before != after
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return changed
