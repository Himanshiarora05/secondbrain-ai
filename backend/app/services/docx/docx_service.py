"""
Word (.docx) Document Text Extraction Service.

Extracts paragraphs, headings (with Markdown structure), and tables.
"""

from pathlib import Path
from docx import Document


class DOCXService:

    @staticmethod
    def extract_text(file_path: str) -> str:
        """Extract formatted text from a Word (.docx) document.

        Preserves headings (# Heading 1, ## Heading 2, etc.), regular paragraph text,
        and table cell contents.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"DOCX file not found: {file_path}")

        try:
            doc = Document(file_path)
        except Exception as e:
            raise ValueError(f"Failed to parse Word document: {e}") from e

        text_blocks = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            style_name = p.style.name if p.style else ""
            # Preserve headings using Markdown format
            if style_name.startswith("Heading 1"):
                text_blocks.append(f"# {text}")
            elif style_name.startswith("Heading 2"):
                text_blocks.append(f"## {text}")
            elif style_name.startswith("Heading 3"):
                text_blocks.append(f"### {text}")
            elif style_name.startswith("Heading"):
                text_blocks.append(f"#### {text}")
            elif style_name.startswith("List"):
                text_blocks.append(f"- {text}")
            else:
                text_blocks.append(text)

        # Also extract table text
        for table in doc.tables:
            table_rows = []
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_cells:
                    table_rows.append(" | ".join(row_cells))
            if table_rows:
                text_blocks.append("\n".join(table_rows))

        return "\n\n".join(text_blocks)
