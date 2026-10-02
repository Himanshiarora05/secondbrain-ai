from typing import Union

import fitz

# A file path, or the PDF's bytes. The upload endpoint passes bytes: when
# PyMuPDF fails to parse a file it keeps it open for as long as the error is
# alive, and on Windows that stops the failed upload from being deleted.
PdfSource = Union[str, bytes]


def _open(source: PdfSource) -> fitz.Document:
    if isinstance(source, (bytes, bytearray)):
        return fitz.open(stream=source, filetype="pdf")
    return fitz.open(source)


class PDFService:

    @staticmethod
    def extract_pages(source: PdfSource) -> list[str]:
        """Text of each page in order (index 0 = page 1).

        Page numbers are the PDF's physical pages, which can differ from the
        numbers printed on the pages (e.g. roman-numbered front matter).
        """
        with _open(source) as document:
            return [page.get_text() for page in document]

    @staticmethod
    def scanned_pages(source: PdfSource) -> list[int]:
        """Page numbers (1-based) with no text but at least one image: scanned
        pages without a text layer, which need OCR. Blank pages aren't listed."""
        with _open(source) as document:
            return [
                number for number, page in enumerate(document, start=1)
                if not page.get_text().strip() and page.get_images()
            ]

    @staticmethod
    def render_pages(source: PdfSource, page_numbers: list[int], dpi: int = 150) -> list[bytes]:
        """JPEG pictures of the given pages (1-based), in the same order, for OCR."""
        with _open(source) as document:
            return [
                document[number - 1].get_pixmap(dpi=dpi).tobytes("jpeg", jpg_quality=85)
                for number in page_numbers
            ]

    @staticmethod
    def extract_text(source: PdfSource):
        return "".join(PDFService.extract_pages(source))
