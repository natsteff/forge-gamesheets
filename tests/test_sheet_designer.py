"""Narrow prototype coverage for the portable sheet designer module."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sheet_designer.commands import delete_block, move_row
from app.sheet_designer.model import (
    FORMAT_VERSION,
    PROTOTYPE_VERSION,
    DocumentValidationError,
    migrate_document,
    normalize_document,
)
from app.sheet_designer.sample import expedition_document
from app.sheet_designer.shared_rendering import (
    PAGE_SIZES,
    PageOverflowError,
    render_pdf,
)
from app.sheet_designer.standalone import create_standalone_app
from app.sheet_designer.storage import FileDraftStore


def test_expedition_fixture_round_trips_through_portable_store(tmp_path: Path):
    store = FileDraftStore(tmp_path / "drafts")
    expected = expedition_document()

    assert store.load() == expected
    assert store.save(expected) == expected
    assert json.loads(store.path.read_text()) == expected
    assert not tuple(store.root.glob("*.tmp"))


def test_workspace_creates_opens_duplicates_and_deletes_sheets(tmp_path: Path):
    store = FileDraftStore(tmp_path / "drafts")
    first = store.load()
    second = store.create("Round Tracker", "a4", "landscape")

    workspace = store.list_documents()
    assert workspace["current_id"] == second["id"]
    assert [item["title"] for item in workspace["documents"]] == [
        "Expedition Score Sheet",
        "Round Tracker",
    ]
    assert store.open(first["id"])["title"] == "Expedition Score Sheet"

    assert store.delete(second["id"])["id"] == first["id"]
    second = store.create("Round Tracker", "a4", "landscape")

    duplicate = store.duplicate(second["id"])
    assert duplicate["title"] == "Round Tracker copy"
    assert duplicate["id"] != second["id"]
    assert store.delete(duplicate["id"])["id"] in {first["id"], second["id"]}
    assert not (store.drafts / f"{duplicate['id']}.fgs").exists()


def test_workspace_migrates_the_original_single_draft(tmp_path: Path):
    root = tmp_path / "designer"
    root.mkdir()
    legacy = expedition_document()
    legacy["format_version"] = PROTOTYPE_VERSION
    legacy["title"] = "Recovered draft"
    (root / "current.fgs").write_text(json.dumps(legacy))

    store = FileDraftStore(root)
    assert store.load()["title"] == "Recovered draft"
    assert store.load()["format_version"] == FORMAT_VERSION
    assert store.path.parent == root / "drafts"


def test_workspace_backs_up_prototype_before_in_place_migration(tmp_path: Path):
    root = tmp_path / "designer"
    drafts = root / "drafts"
    drafts.mkdir(parents=True)
    prototype = json.loads(
        (Path(__file__).parent / "fixtures/fgs/prototype-valid.fgs").read_text()
    )
    path = drafts / "prototype-sheet.fgs"
    path.write_text(json.dumps(prototype))
    (root / "current").write_text("prototype-sheet\n")
    store = FileDraftStore(root)
    assert store.load()["format_version"] == FORMAT_VERSION
    assert path.with_suffix(".fgs.v0.1-prototype.bak").is_file()


def test_untrusted_fgs_requires_supported_version_and_unique_ids():
    document = expedition_document()
    document["format_version"] = "2.0"
    with pytest.raises(DocumentValidationError, match="1.0"):
        normalize_document(document)

    document = expedition_document()
    document["rows"][1]["blocks"][0]["id"] = "header-main"
    with pytest.raises(DocumentValidationError, match="Duplicate"):
        normalize_document(document)


def test_prototype_migrates_and_v1_preserves_extensions():
    prototype = expedition_document()
    prototype["format_version"] = PROTOTYPE_VERSION
    migrated = migrate_document(prototype)
    assert migrated["format_version"] == FORMAT_VERSION
    migrated["extensions"] = {"com.example.editor": {"grid": True}}
    migrated["rows"][0]["extensions"] = {"com.example.layout": "locked"}
    assert normalize_document(migrated)["extensions"] == migrated["extensions"]
    assert normalize_document(migrated)["rows"][0]["extensions"] == {
        "com.example.layout": "locked"
    }


def test_v1_rejects_unknown_properties_instead_of_discarding_them():
    document = expedition_document()
    document["web_app_only"] = True
    with pytest.raises(DocumentValidationError, match="Unknown document property"):
        normalize_document(document)


def test_workspace_identity_is_separate_from_document_id(tmp_path: Path):
    store = FileDraftStore(tmp_path / "designer")
    workspace_id = store.list_documents()["current_id"]
    imported = expedition_document()
    imported["id"] = "portable-shared-id"
    assert store.save(imported)["id"] == "portable-shared-id"
    assert store.list_documents()["current_id"] == workspace_id
    assert store.path.stem == workspace_id


def test_import_creates_a_new_workspace_without_overwriting_current(tmp_path: Path):
    store = FileDraftStore(tmp_path / "designer")
    original = store.load()
    original_workspace = store.list_documents()["current_id"]
    imported = expedition_document()
    imported["id"] = "portable-id-different-from-workspace"
    imported["title"] = "Imported Score Sheet"

    result = store.import_document(imported)
    workspace = store.list_documents()
    imported_item = next(
        item for item in workspace["documents"] if item["title"] == result["title"]
    )

    assert store.load_document(original_workspace) == original
    assert imported_item["id"] != imported["id"]
    assert workspace["current_id"] == imported_item["id"]
    assert store.load_document(imported_item["id"])["id"] == imported["id"]


def test_fgs_conformance_fixtures():
    fixtures = Path(__file__).parent / "fixtures" / "fgs"
    valid = json.loads((fixtures / "v1-valid-minimal.fgs").read_text())
    prototype = json.loads((fixtures / "prototype-valid.fgs").read_text())
    invalid = json.loads((fixtures / "v1-invalid-unknown-property.fgs").read_text())
    assert normalize_document(valid) == valid
    assert migrate_document(prototype)["format_version"] == FORMAT_VERSION
    with pytest.raises(DocumentValidationError, match="Unknown document property"):
        normalize_document(invalid)


def test_keyboard_equivalent_commands_move_and_delete_sections():
    document = expedition_document()
    moved = move_row(document, "row-score", -1)
    assert [row["id"] for row in moved["rows"]][:2] == [
        "row-score",
        "row-header",
    ]

    deleted = delete_block(document, "checklist-main")
    guidance = next(row for row in deleted["rows"] if row["id"] == "row-guidance")
    assert [block["id"] for block in guidance["blocks"]] == ["reference-main"]


def test_pdf_is_single_page_correct_size_and_deterministic(tmp_path: Path):
    first = render_pdf(expedition_document(), tmp_path / "first.pdf")
    second = render_pdf(expedition_document(), tmp_path / "second.pdf")
    assert first.read_bytes() == second.read_bytes()

    with pymupdf.open(first) as pdf:
        assert pdf.page_count == 1
        assert pdf[0].rect.width == pytest.approx(PAGE_SIZES["letter"][0])
        assert pdf[0].rect.height == pytest.approx(PAGE_SIZES["letter"][1])
        text = "".join(page.get_text() for page in pdf)
    assert "Expedition Score Sheet" in text
    assert "Routes" in text
    assert "Milestones" in text


def test_pdf_category_labels_use_the_shared_bold_font(tmp_path: Path):
    output = render_pdf(expedition_document(), tmp_path / "font-check.pdf")
    with pymupdf.open(output) as pdf:
        spans = [
            span
            for block in pdf[0].get_text("dict")["blocks"]
            if "lines" in block
            for line in block["lines"]
            for span in line["spans"]
        ]
    assert any(
        span["text"] == "Routes" and "NotoSans-Bold" in span["font"] for span in spans
    )


def test_pdf_titles_use_accent_but_table_labels_remain_neutral(tmp_path: Path):
    document = expedition_document()
    document["theme"]["accent"] = "#a52f23"
    output = render_pdf(document, tmp_path / "accent-check.pdf")
    with pymupdf.open(output) as pdf:
        spans = [
            span
            for block in pdf[0].get_text("dict")["blocks"]
            if "lines" in block
            for line in block["lines"]
            for span in line["spans"]
        ]
        assert "fgs-page-1.0" in pdf.metadata["creator"]
    assert any(
        span["text"] == "Expedition Score Sheet" and span["color"] == 0xA52F23
        for span in spans
    )
    assert any(
        span["text"] == "Score table" and span["color"] == 0xA52F23
        for span in spans
    )
    assert any(span["text"] == "Routes" and span["color"] != 0xA52F23 for span in spans)


def test_pinned_renderer_files_match_the_build_manifest():
    root = Path(__file__).resolve().parents[1] / "app" / "static" / "fgs-renderer"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "fgs-page-1.0"
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected


def test_score_table_summary_row_is_optional_and_renameable(tmp_path: Path):
    document = expedition_document()
    score_table = document["rows"][1]["blocks"][0]
    score_table["score_rows"].remove("Total")
    score_table["show_total"] = True
    score_table["total_label"] = "Final score"
    renamed = render_pdf(document, tmp_path / "renamed.pdf")
    with pymupdf.open(renamed) as pdf:
        assert "Final score" in pdf[0].get_text()

    score_table["show_total"] = False
    hidden = render_pdf(document, tmp_path / "hidden.pdf")
    with pymupdf.open(hidden) as pdf:
        assert "Final score" not in pdf[0].get_text()


def test_multiple_compact_score_tables_fit_when_the_rendered_rows_fit(tmp_path: Path):
    document = expedition_document()
    document["rows"] = [document["rows"][0]]
    players = ["Known", "P1", "P2", "P3", "P4", "P5", "P6"]
    for index, (title, row_count) in enumerate(
        (("Suspects", 6), ("Weapons", 6), ("Rooms", 9))
    ):
        document["rows"].append(
            {
                "id": f"row-{index}",
                "blocks": [
                    {
                        "id": f"table-{index}",
                        "type": "score_table",
                        "title": title,
                        "players": players,
                        "score_rows": [f"Entry {row}" for row in range(row_count)],
                        "show_total": False,
                        "total_label": "Total",
                    }
                ],
            }
        )
    document["rows"].append(
        {
            "id": "row-reference",
            "blocks": [
                {
                    "id": "reference",
                    "type": "reference",
                    "title": "Detective Notes",
                    "items": ["Reminder one", "Reminder two", "Reminder three"],
                }
            ],
        }
    )

    output = render_pdf(document, tmp_path / "compact-tables.pdf")

    with pymupdf.open(output) as pdf:
        assert pdf.page_count == 1
        text = "".join(page.get_text() for page in pdf)
        assert "Rooms" in text
        assert "Entry 0" in text


def test_pdf_rejects_overflow_instead_of_clipping(tmp_path: Path):
    document = expedition_document()
    document["rows"].extend(
        {
            "id": f"row-notes-{index}",
            "blocks": [
                {
                    "id": f"notes-{index}",
                    "type": "notes",
                    "title": f"Notes {index}",
                    "lines": 20,
                }
            ],
        }
        for index in range(4)
    )
    output = tmp_path / "overflow.pdf"
    with pytest.raises(PageOverflowError):
        render_pdf(document, output)
    assert not output.exists()


def test_standalone_shell_saves_and_exports_without_forge_database(tmp_path: Path):
    app = create_standalone_app(tmp_path / "standalone")
    with TestClient(
        app,
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        page = client.get("/sheet-designer")
        assert page.status_code == 200
        assert "Sheet structure" in page.text
        assert "What would you like to work on?" in page.text
        assert "New sheet" in page.text
        assert "Open sheets" in page.text
        assert "Resume last sheet" in page.text
        assert "sheet-designer.js" in page.text
        renderer = client.get("/static/fgs-renderer/browser.mjs")
        assert renderer.status_code == 200
        assert "javascript" in renderer.headers["content-type"]
        assert "/static/brand/forge-wordmark.png" in page.text
        assert "Forge GameSheets on GitHub" in page.text
        assert "https://github.com/natsteff/forge-gamesheets" in page.text
        assert client.get("/").url.path == "/sheet-designer"
        assert client.get("/health").json()["mode"] == "designer"

        document = client.get("/sheet-designer/document").json()
        document["title"] = "Standalone Test"
        assert client.post("/sheet-designer/document", json=document).status_code == 200
        fgs = client.get("/sheet-designer/export.fgs")
        pdf = client.get("/sheet-designer/export.pdf")
        assert fgs.status_code == 200
        assert fgs.headers["content-disposition"].endswith(
            'filename="standalone-test.fgs"'
        )
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")

        prototype = expedition_document()
        prototype["format_version"] = PROTOTYPE_VERSION
        migrated = client.post("/sheet-designer/document", json=prototype)
        assert migrated.status_code == 200
        assert migrated.json()["format_version"] == FORMAT_VERSION

        created = client.post(
            "/sheet-designer/documents",
            json={
                "title": "New Scores",
                "page_size": "a4",
                "orientation": "landscape",
            },
        )
        assert created.status_code == 201
        created_document = created.json()
        assert created_document["title"] == "New Scores"
        assert created_document["page"] == {
            "size": "a4",
            "orientation": "landscape",
        }
        workspace = client.get("/sheet-designer/documents").json()
        assert len(workspace["documents"]) == 2
        assert workspace["current_id"] == created_document["id"]

        duplicated = client.post(
            f"/sheet-designer/documents/{created_document['id']}/duplicate"
        )
        assert duplicated.status_code == 201
        assert duplicated.json()["title"] == "New Scores copy"
        deleted = client.delete(f"/sheet-designer/documents/{duplicated.json()['id']}")
        assert deleted.status_code == 200


def test_designer_appears_as_native_forge_contributor_feature(tmp_path: Path):
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        home = client.get("/")
        page = client.get("/sheet-designer")
        saved = client.post("/sheet-designer/document", json=expedition_document())

    assert ">Sheet Designer</a>" in home.text
    assert home.text.index(">Sheet Designer</a>") < home.text.index(">History</a>")
    admin_links = home.text.split('id="nav-admin"', 1)[1].split("</div>", 1)[0]
    assert "Sheet Designer" not in admin_links
    assert page.status_code == 200
    assert "site-header" in page.text
    assert saved.status_code == 200
    workspace = data / "sheet-designer"
    assert (workspace / "current").is_file()
    assert tuple((workspace / "drafts").glob("*.fgs"))


def test_score_row_editor_explains_dynamic_line_behavior():
    script = (Path(__file__).parents[1] / "app/static/sheet-designer.js").read_text()
    assert "Score rows (one per line)" in script
    assert "Press Return to add or remove rows." in script
    assert "Summary row label" not in script
    assert "Include a summary row" not in script
    assert "Add Total row" in script
    assert "Add Grand Total row" in script
    assert 'normalized === "total"' in script
    assert 'normalized === "grand total"' in script
    assert "Generate numbered rows" in script
    assert "Array.from({length: count}" in script
    assert "Math.min(12, Math.max(4, items.length))" in script
    assert "Checklist items" in script
    assert "Reminders" in script
    assert "block.items = items" in script


def test_section_picker_lists_supported_blocks_without_a_text_prompt():
    root = Path(__file__).parents[1]
    template = (root / "app/templates/_sheet_designer_workspace.html").read_text()
    script = (root / "app/static/sheet-designer.js").read_text()
    for value in ("header", "score_table", "reference", "checklist", "notes"):
        assert f'value="{value}"' in template
    assert 'const type = $("section-type").value;' in script
    assert "prompt(" not in script
    assert "New sheet" in template
    assert "Open sheets" in template
    assert "data-new-dialog" in template
    assert "data-startup" in template
    assert "data-start-new" in template
    assert "data-start-open" in template
    assert "data-start-resume" in template
    assert "Resume last sheet" in template
    assert "Experimental prototype" not in template
    assert ">New</button>" in template
    assert ">Open</button>" in template
    assert 'class="designer-export-menu"' in template
    assert template.index("data-open-dialog") < template.index("data-import-file")
    assert 'requestDocument("/sheet-designer/documents")' in script
    assert 'requestDocument("/sheet-designer/document")' in script
    assert 'fetch("/sheet-designer/document").then' not in script


def test_designer_explains_its_scope_from_startup_and_editor():
    root = Path(__file__).parents[1]
    template = (root / "app/templates/_sheet_designer_workspace.html").read_text()
    script = (root / "app/static/sheet-designer.js").read_text()
    assert template.count("data-about-designer") == 2
    assert "About Sheet Designer" in template
    assert "structured, single-page layouts" in template
    assert "not a general page-layout or spreadsheet tool" in template
    assert "temporary interactive LiveSheets" in template
    assert "An LLM can draft an FGS file" in template
    assert "only share source documents you are permitted to upload" in template
    assert "FGS_V1_SPECIFICATION.md" in template
    assert '$("about-dialog").showModal()' in script


def test_integrated_designer_can_mark_a_sheet_livesheet_ready():
    root = Path(__file__).parents[1]
    template = (root / "app/templates/_sheet_designer_workspace.html").read_text()
    script = (root / "app/static/sheet-designer.js").read_text()
    assert "Configure LiveSheet" in template
    assert "Make this GameSheet available for LiveSheet" in template
    assert "does not create or freeze a separate copy" in template
    assert "Scores and player names are never saved in the FGS source" in template
    assert "io.github.natsteff.livesheet" in script
    assert 'if ($("livesheet"))' in script
    assert 'requestDocument("/sheet-designer/documents/import"' in script
    assert "{% if not standalone %}" in template


def test_integrated_designer_can_associate_current_sheet_with_a_game(tmp_path: Path):
    library = tmp_path / "library"
    data = tmp_path / "data"
    (library / "Farkle").mkdir(parents=True)
    data.mkdir()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        document = client.app.state.sheet_designer_store.load()
        document["title"] = "Farkle Score Sheet"
        client.app.state.sheet_designer_store.save(document)
        with client.app.state.database.connect() as connection:
            game_id = connection.execute(
                "SELECT id FROM games WHERE relative_path='Farkle'"
            ).fetchone()["id"]
        initial = client.get("/sheet-designer/game-association")
        saved = client.post(
            "/sheet-designer/game-association", json={"game_id": game_id}
        )
        associated = client.get("/sheet-designer/game-association")
        removed = client.delete("/sheet-designer/game-association")

    assert initial.status_code == 200
    assert initial.json()["association"] is None
    assert initial.json()["query"] == "Farkle"
    assert initial.json()["suggested_game_id"] == game_id
    assert initial.json()["games"] == [{"id": game_id, "title": "Farkle"}]
    assert saved.status_code == 200
    assert associated.json()["association"] == {
        "game_id": game_id,
        "game_title": "Farkle",
        "available": True,
    }
    assert removed.status_code == 200


def test_deleting_a_sheet_removes_its_local_game_association(tmp_path: Path):
    library = tmp_path / "library"
    data = tmp_path / "data"
    (library / "Farkle").mkdir(parents=True)
    data.mkdir()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        store = client.app.state.sheet_designer_store
        workspace_id = store.current_id()
        with client.app.state.database.connect() as connection:
            game_id = connection.execute("SELECT id FROM games").fetchone()["id"]
        client.post("/sheet-designer/game-association", json={"game_id": game_id})

        response = client.delete(f"/sheet-designer/documents/{workspace_id}")
        with client.app.state.database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM gamesheet_game_associations WHERE workspace_id=?",
                (workspace_id,),
            ).fetchone()[0]

    assert response.status_code == 200
    assert count == 0


def test_game_association_controls_are_integrated_only():
    template = (
        Path(__file__).parents[1] / "app/templates/_sheet_designer_workspace.html"
    ).read_text()
    script = (Path(__file__).parents[1] / "app/static/sheet-designer.js").read_text()
    assert "Associate with a game" in template
    assert "not added to exported FGS files" in template
    assert "data-game-link" in template
    assert 'requestDocument("/sheet-designer/game-association"' in script
    assert "encodeURIComponent(query)" in script
    assert 'query === null' in script


def test_designer_controls_reuse_forge_form_tokens():
    styles = (Path(__file__).parents[1] / "app/static/styles.css").read_text()
    assert '.designer-app input:not([type="checkbox"]):not([type="file"])' in styles
    assert "border-radius: 0.65rem" in styles
    assert "background: var(--surface)" in styles
    assert "font-weight: 400" in styles
    assert 'textarea[data-list="score_rows"] { min-height: 10rem; }' in styles
    assert ".page-shell:has(.designer-app) { width: 100%" in styles
    assert "z-index: 100" in styles


def test_designer_uses_one_collapsible_scrolling_tool_sidebar():
    root = Path(__file__).parents[1]
    template = (root / "app/templates/_sheet_designer_workspace.html").read_text()
    styles = (root / "app/static/styles.css").read_text()
    script = (root / "app/static/sheet-designer.js").read_text()
    assert '<aside class="designer-tools"' in template
    assert '<details class="designer-structure" open>' in template
    assert "data-section-count" in template
    structure_position = template.index('class="designer-structure"')
    properties_position = template.index('class="designer-properties"')
    preview_position = template.index('class="designer-canvas-shell"')
    assert structure_position < properties_position < preview_position
    assert "grid-template-columns: minmax(20rem, 23rem) minmax(32rem, 1fr)" in styles
    assert "overflow-y: auto" in styles
    assert '$("section-count").textContent' in script
    assert "summary::after" in styles


def test_fit_warning_is_independent_of_autosave_messages():
    root = Path(__file__).parents[1]
    template = (root / "app/templates/_sheet_designer_workspace.html").read_text()
    script = (root / "app/static/sheet-designer.js").read_text()

    assert 'data-fit-message role="status" hidden' in template
    assert 'const fitMessage = $("fit-message")' in script
    assert "fitMessage.hidden = result.fits" in script
    assert (
        'message(`Section "${result.overflow}" does not fit on one page.' not in script
    )


def test_designer_edits_the_portable_accent_color():
    root = Path(__file__).parents[1]
    template = (root / "app/templates/_sheet_designer_workspace.html").read_text()
    script = (root / "app/static/sheet-designer.js").read_text()

    assert 'data-accent type="color"' in template
    assert '$("accent").value = model.theme.accent' in script
    assert 'draft.theme.accent = event.target.value' in script
