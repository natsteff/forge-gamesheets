"""Tests for Forge-marked derived PDF generation."""

from pathlib import Path

import fitz
import pytest

from app.library.reprints import (
    FOOTER_HEIGHT_POINTS,
    GENERATOR_VERSION,
    NARROW_FOOTER_HEIGHT_POINTS,
    ReprintGenerationError,
    existing_forge_reprint,
    generate_forge_reprint,
    resource_reprint_url,
)


def _source_pdf(path: Path) -> None:
    document = fitz.open()
    portrait = document.new_page(width=612, height=792)
    portrait.insert_text((72, 72), "Portrait source page")
    landscape = document.new_page(width=792, height=612)
    landscape.insert_text((72, 72), "Landscape source page")
    document.save(path)
    document.close()


def test_resource_reprint_url_requires_configured_base_url() -> None:
    assert (
        resource_reprint_url("https://forge.example.test", 12)
        == "https://forge.example.test/r/12"
    )
    with pytest.raises(ReprintGenerationError, match="BASE_URL"):
        resource_reprint_url(None, 12)


def test_generate_reprint_preserves_source_and_marks_every_page(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    data = tmp_path / "data"
    data.mkdir()
    _source_pdf(source)
    original = source.read_bytes()
    target_url = "https://forge.example.test/r/12"

    generated = generate_forge_reprint(
        source,
        data,
        resource_id=12,
        target_url=target_url,
    )

    assert source.read_bytes() == original
    assert generated.parent == data / "generated"
    with fitz.open(source) as source_document, fitz.open(generated) as output:
        assert output.page_count == source_document.page_count == 2
        for source_page, output_page in zip(source_document, output, strict=True):
            assert output_page.rect.width == pytest.approx(source_page.rect.width)
            assert output_page.rect.height == pytest.approx(
                source_page.rect.height + FOOTER_HEIGHT_POINTS
            )
            text = output_page.get_text()
            assert "Scan QR code or access URL to reprint:" in text
            assert "No ownership of or affiliation with source content" in text
            assert "Library operator is responsible for authorization" in text
            assert target_url in text
            assert len(output_page.get_images(full=True)) >= 2
            fonts = {
                span["font"]
                for block in output_page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
            }
            assert "Helvetica-Oblique" in fonts
            spans = [
                span
                for block in output_page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
            ]
            instruction_span = next(
                span
                for span in spans
                if span["text"].startswith("Scan QR code")
            )
            ownership_span = next(
                span
                for span in spans
                if span["text"].startswith("No ownership")
            )
            operator_span = next(
                span
                for span in spans
                if span["text"].startswith("Library operator")
            )
            instruction_y = instruction_span["origin"][1]
            ownership_y = ownership_span["origin"][1]
            operator_y = operator_span["origin"][1]
            assert instruction_span["color"] == 0
            assert ownership_span["size"] == pytest.approx(6.0)
            assert operator_span["size"] == pytest.approx(6.0)
            assert operator_y - ownership_y == pytest.approx(7)
            assert ownership_y - instruction_y > operator_y - ownership_y
        assert output.metadata["keywords"] == (
            f"forge-reprint-v{GENERATOR_VERSION}"
        )


def test_generate_reprint_uses_readable_stacked_footer_on_narrow_page(
    tmp_path: Path,
) -> None:
    source = tmp_path / "narrow.pdf"
    data = tmp_path / "data"
    data.mkdir()
    document = fitz.open()
    document.new_page(width=216, height=288)
    document.save(source)
    document.close()

    generated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="https://forge.example.test/r/1",
    )

    with fitz.open(generated) as output:
        page = output[0]
        assert page.rect.height == pytest.approx(
            288 + NARROW_FOOTER_HEIGHT_POINTS
        )
        text = " ".join(page.get_text().split())
        assert "Scan QR code or access URL to reprint:" in text
        assert "No ownership of or affiliation with source content" in text
        assert "Library operator is responsible for authorization" in text
        assert len(page.get_images(full=True)) >= 2


def test_generate_reprint_preserves_long_url_on_a4_landscape(
    tmp_path: Path,
) -> None:
    source = tmp_path / "a4-landscape.pdf"
    data = tmp_path / "data"
    data.mkdir()
    document = fitz.open()
    document.new_page(width=841.89, height=595.28)
    document.save(source)
    document.close()
    target_url = (
        "https://forge-gamesheets.internal.example.net:8443/"
        "tabletop-library/r/987654"
    )

    generated = generate_forge_reprint(
        source,
        data,
        resource_id=987654,
        target_url=target_url,
    )

    with fitz.open(generated) as output:
        page = output[0]
        assert page.rect.width == pytest.approx(841.89)
        assert page.rect.height == pytest.approx(595.28 + FOOTER_HEIGHT_POINTS)
        assert target_url in page.get_text()
        assert len(page.get_images(full=True)) >= 2


def test_generate_reprint_reuses_source_specific_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    data = tmp_path / "data"
    data.mkdir()
    _source_pdf(source)

    first = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://forge.local/r/1",
    )
    first_bytes = first.read_bytes()
    second = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://forge.local/r/1",
    )

    assert second == first
    assert second.read_bytes() == first_bytes
    assert existing_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://forge.local/r/1",
    ) == first


def test_generate_reprint_force_replaces_current_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    data = tmp_path / "data"
    data.mkdir()
    _source_pdf(source)

    generated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://forge.local/r/1",
    )
    current_with_marker = generated.read_bytes() + b"\n% current-cache-marker\n"
    generated.write_bytes(current_with_marker)

    regenerated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://forge.local/r/1",
        force=True,
    )

    assert regenerated == generated
    assert regenerated.read_bytes() != current_with_marker
    with fitz.open(regenerated) as document:
        assert document.metadata["keywords"] == (
            f"forge-reprint-v{GENERATOR_VERSION}"
        )


def test_existing_reprint_rejects_stale_target_without_writing(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    data = tmp_path / "data"
    data.mkdir()
    _source_pdf(source)
    generated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://old-forge.local/r/1",
    )
    original_bytes = generated.read_bytes()

    assert existing_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="https://new-forge.example/r/1",
    ) is None
    assert generated.read_bytes() == original_bytes


def test_generate_reprint_replaces_stale_target_url(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    data = tmp_path / "data"
    data.mkdir()
    _source_pdf(source)

    generated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://old-forge.local/r/1",
    )
    original_bytes = generated.read_bytes()
    regenerated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="https://new-forge.example/r/1",
    )

    assert regenerated == generated
    assert regenerated.read_bytes() != original_bytes
    with fitz.open(regenerated) as document:
        assert document.metadata["subject"] == "https://new-forge.example/r/1"
        assert "https://new-forge.example/r/1" in document[0].get_text()


def test_generate_reprint_replaces_invalid_cached_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    data = tmp_path / "data"
    data.mkdir()
    _source_pdf(source)

    generated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://forge.local/r/1",
    )
    generated.write_bytes(b"damaged cache")

    regenerated = generate_forge_reprint(
        source,
        data,
        resource_id=1,
        target_url="http://forge.local/r/1",
    )

    with fitz.open(regenerated) as document:
        assert document.page_count == 2


def test_generation_failure_leaves_no_partial_output(tmp_path: Path) -> None:
    source = tmp_path / "invalid.pdf"
    data = tmp_path / "data"
    data.mkdir()
    source.write_bytes(b"not a PDF")

    with pytest.raises(ReprintGenerationError, match="invalid|unsupported"):
        generate_forge_reprint(
            source,
            data,
            resource_id=1,
            target_url="http://forge.local/r/1",
        )

    generated = data / "generated"
    assert not tuple(generated.glob("*.pdf"))
    assert not tuple(generated.glob("*.tmp"))


def test_generation_rejects_pages_too_small_for_mark(tmp_path: Path) -> None:
    source = tmp_path / "tiny.pdf"
    data = tmp_path / "data"
    data.mkdir()
    document = fitz.open()
    document.new_page(width=100, height=100)
    document.save(source)
    document.close()

    with pytest.raises(ReprintGenerationError, match="too small"):
        generate_forge_reprint(
            source,
            data,
            resource_id=1,
            target_url="http://forge.local/r/1",
        )
