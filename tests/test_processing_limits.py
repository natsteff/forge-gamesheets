"""Untrusted image and document workloads have explicit upper bounds."""

from io import BytesIO

import pytest
from PIL import Image

from app.library.artwork import save_uploaded_artwork
from app.library.files import UnsafeResourcePath
from app.library.processing_limits import validate_image_pixels


def test_image_pixel_limit_has_an_inclusive_boundary():
    validate_image_pixels(8_000, 5_000)
    with pytest.raises(ValueError, match="40-megapixel"):
        validate_image_pixels(8_001, 5_000)


def test_artwork_rejects_dimensions_before_decoding_pixels(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    stream = BytesIO()
    Image.new("RGB", (20, 20), "white").save(stream, format="PNG")
    monkeypatch.setattr("app.library.processing_limits.MAX_ARTWORK_PIXELS", 1)
    with pytest.raises(UnsafeResourcePath, match="Invalid uploaded artwork"):
        save_uploaded_artwork(data, 1, stream.getvalue())
    assert not (data / "game-artwork" / "game-1.webp").exists()
