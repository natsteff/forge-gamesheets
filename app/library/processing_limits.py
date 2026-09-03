"""Conservative workload limits for untrusted document and image parsing."""

MAX_PDF_PROCESSING_BYTES = 250 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_PDF_PAGE_DIMENSION_POINTS = 14_400  # 200 inches at 72 points per inch.
MAX_PREVIEW_RENDER_PIXELS = 25_000_000
MAX_ARTWORK_PIXELS = 40_000_000


def validate_pdf_file_size(size_bytes: int) -> None:
    if size_bytes > MAX_PDF_PROCESSING_BYTES:
        raise ValueError("PDF exceeds the 250 MB processing limit.")


def validate_pdf_document(document) -> None:
    if document.page_count > MAX_PDF_PAGES:
        raise ValueError("PDF exceeds the 500-page processing limit.")
    for page in document:
        if (
            page.rect.width > MAX_PDF_PAGE_DIMENSION_POINTS
            or page.rect.height > MAX_PDF_PAGE_DIMENSION_POINTS
        ):
            raise ValueError("PDF page dimensions exceed the processing limit.")


def validate_image_pixels(width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width * height > MAX_ARTWORK_PIXELS:
        raise ValueError("Image dimensions exceed the 40-megapixel processing limit.")
