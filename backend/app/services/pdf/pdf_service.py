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
    def has_images(source: PdfSource) -> bool:
        """Whether any page has an embedded image. A PDF with images but no
        text is almost always scanned pages without a text layer."""
        with _open(source) as document:
            return any(page.get_images() for page in document)

    @staticmethod
    def extract_text(source: PdfSource):
        return "".join(PDFService.extract_pages(source))
