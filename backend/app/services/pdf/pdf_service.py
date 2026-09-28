import fitz


class PDFService:

    @staticmethod
    def extract_pages(pdf_path: str) -> list[str]:
        """Text of each page in order (index 0 = page 1).

        Page numbers are the PDF's physical pages, which can differ from the
        numbers printed on the pages (e.g. roman-numbered front matter).
        """
        with fitz.open(pdf_path) as document:
            return [page.get_text() for page in document]

    @staticmethod
    def extract_text(pdf_path: str):
        return "".join(PDFService.extract_pages(pdf_path))
