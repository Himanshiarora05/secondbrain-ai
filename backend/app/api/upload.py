from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import uuid

from app.services.pdf.pdf_service import PDFService
from app.services.rag.rag_service import RAGService

router = APIRouter(
    prefix="/api/v1/upload",
    tags=["Upload"]
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

rag_service = RAGService()


@router.post("/pdf")
async def upload_pdf(file: UploadFile = File(...)):

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed."
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds 20 MB."
        )

    file_id = str(uuid.uuid4())

    extension = Path(file.filename).suffix
    stored_filename = f"{file_id}{extension}"

    file_path = UPLOAD_DIR / stored_filename

    with open(file_path, "wb") as f:
        f.write(content)

    # Extract text
    text = PDFService.extract_text(str(file_path))

    # Split into chunks
    chunks = rag_service.chunk_text(text)

    # Create embeddings
    embeddings = rag_service.create_embeddings(chunks)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "stored_filename": stored_filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "text_length": len(text),
        "total_chunks": len(chunks),
        "embedding_dimension": embeddings.shape[1] if len(embeddings) > 0 else 0,
        "status": "processed"
    }