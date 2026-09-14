"""Narrow prototype coverage for the portable sheet designer module."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sheet_designer.commands import delete_block, move_row
from app.sheet_designer.model import DocumentValidationError, normalize_document
from app.sheet_designer.rendering import PAGE_SIZES, PageOverflowError, render_pdf
from app.sheet_designer.sample import expedition_document
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
    legacy["title"] = "Recovered draft"
    (root / "current.fgs").write_text(json.dumps(legacy))

    store = FileDraftStore(root)
    assert store.load()["title"] == "Recovered draft"
    assert store.path.parent == root / "drafts"


def test_untrusted_fgs_requires_prototype_version_and_unique_ids():
    document = expedition_document()
    document["format_version"] = "1"
    with pytest.raises(DocumentValidationError, match="0.1-prototype"):
        normalize_document(document)

    document = expedition_document()
    document["rows"][1]["blocks"][0]["id"] = "header-main"
    with pytest.raises(DocumentValidationError, match="Duplicate"):
        normalize_document(document)


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


def test_score_table_summary_row_is_optional_and_renameable(tmp_path: Path):
    document = expedition_document()
    score_table = document["rows"][1]["blocks"][0]
    score_table["total_label"] = "Final score"
    renamed = render_pdf(document, tmp_path / "renamed.pdf")
    with pymupdf.open(renamed) as pdf:
        assert "Final score" in pdf[0].get_text()

    score_table["show_total"] = False
    hidden = render_pdf(document, tmp_path / "hidden.pdf")
    with pymupdf.open(hidden) as pdf:
        assert "Final score" not in pdf[0].get_text()


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
    with TestClient(app) as client:
        page = client.get("/sheet-designer")
        assert page.status_code == 200
        assert "Sheet structure" in page.text
        assert "sheet-designer.js" in page.text
        assert "/static/brand/forge-wordmark.png" in page.text

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


def test_designer_appears_as_native_forge_admin_feature(tmp_path: Path):
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
    assert "Press Return to add a row. Delete a line to remove that row." in script
    assert "Summary row label" in script
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
