import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.chroma import get_collection
from app.models.document import Document
from app.models.chunk import Chunk
from app.services.pdf.pdf_service import PDFService
from app.services.ppt.ppt_service import PPTService
from app.services.docx.docx_service import DOCXService
from app.services.youtube.youtube_service import YouTubeService, YouTubeCaptionError
from app.services.web.web_service import WebService, url_key
from app.services.web.errors import WebPageError
from app.services.rag.rag_service import RAGService
from app.services.embedding_service import get_embeddings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/upload", tags=["Upload"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# Old binary Office files (.ppt/.doc) are OLE compound files, which python-pptx and
# python-docx can't read. Password-protected .pptx/.docx files use the same container.
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

LEGACY_PPT_MESSAGE = (
    "Old PowerPoint files (.ppt) aren't supported. Open the file in PowerPoint "
    "(or Google Slides / LibreOffice), choose File → Save As → .pptx, and upload that."
)
LEGACY_DOC_MESSAGE = (
    "Old Word files (.doc) aren't supported. Open the file in Word "
    "(or Google Docs / LibreOffice), choose File → Save As → .docx, and upload that."
)
OLE_PPTX_MESSAGE = (
    "This file can't be read: it's either an old .ppt presentation renamed to .pptx, or it's "
    "password-protected. Remove any password and save it as .pptx, then upload it again."
)
OLE_DOCX_MESSAGE = (
    "This file can't be read: it's either an old .doc document renamed to .docx, or it's "
    "password-protected. Remove any password and save it as .docx, then upload it again."
)


class YouTubeUploadRequest(BaseModel):
    url: str


class WebsiteUploadRequest(BaseModel):
    url: str


def _store_document_and_chunks(
    db: Session,
    file_id: str,
    filename: str,
    content: str,
    chunks: List[str],
    source_type: str = "pdf",
    source_url: Optional[str] = None,
    metadata_json: Optional[str] = None,
    chunk_start_seconds: Optional[List[int]] = None,
) -> dict:
    """Shared helper to persist Document and Chunks to PostgreSQL and Chroma."""
    try:
        embeddings = get_embeddings(chunks)
    except Exception as e:
        logger.error(f"Embedding generation failed for document '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Could not generate document embeddings right now, please try again",
        )

    # 1. Prepare Document in PostgreSQL
    doc = Document(
        file_id=file_id,
        filename=filename,
        content=content,
        source_type=source_type,
        source_url=source_url,
        metadata_json=metadata_json,
    )
    db.add(doc)
    
    try:
        db.flush()  # Assigns doc.id without committing the transaction

        # 2. Prepare Chunks in PostgreSQL & Chroma
        collection = get_collection()
        chroma_ids = [f"{doc.id}-{i}" for i in range(len(chunks))]

        db_chunks = []
        chroma_metadatas = []

        for i, chunk_text in enumerate(chunks):
            start_sec = chunk_start_seconds[i] if chunk_start_seconds and i < len(chunk_start_seconds) else None
            db_chunks.append(
                Chunk(
                    document_id=doc.id,
                    content=chunk_text,
                    chroma_id=chroma_ids[i],
                    start_seconds=start_sec,
                )
            )
            meta = {
                "document_id": doc.id,
                "filename": filename,
                "chunk_index": i,
                "source_type": source_type,
            }
            if source_url:
                meta["source_url"] = source_url
            if start_sec is not None:
                meta["start_seconds"] = start_sec

            chroma_metadatas.append(meta)

        db.add_all(db_chunks)

        # 3. Add to Chroma FIRST
        collection.add(
            ids=chroma_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=chroma_metadatas,
        )

        # 4. Commit database transaction only when Chroma succeeded
        db.commit()
    except Exception as e:
        db.rollback()
        try:
            if "chroma_ids" in locals() and chroma_ids:
                collection.delete(ids=chroma_ids)
        except Exception:
            pass
        logger.error(f"Failed to persist document and chunks for '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Could not store document chunks: {e}",
        )

    return {
        "file_id": file_id,
        "document_id": doc.id,
        "text_length": len(content),
        "total_chunks": len(chunks),
        "source_type": source_type,
        "status": "stored",
    }


@router.post("/pdf")
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (maximum 20 MB)")

    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.pdf"

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        text = PDFService.extract_text(str(file_path))
    except Exception as e:
        logger.error(f"Failed to extract PDF text from '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Could not extract text from this PDF file, please try another file")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in this PDF file")

    chunks = RAGService.chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No usable text chunks after processing")

    return _store_document_and_chunks(
        db=db,
        file_id=file_id,
        filename=file.filename,
        content=text,
        chunks=chunks,
        source_type="pdf",
    )


@router.post("/pptx")
async def upload_pptx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = file.filename or ""
    if filename.lower().endswith(".ppt"):
        raise HTTPException(status_code=400, detail=LEGACY_PPT_MESSAGE)
    if not filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only PowerPoint (.pptx) files are allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (maximum 20 MB)")
    if content.startswith(OLE_SIGNATURE):
        raise HTTPException(status_code=400, detail=OLE_PPTX_MESSAGE)

    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.pptx"

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        text = PPTService.extract_text(str(file_path))
    except ValueError as e:
        logger.error(f"Corrupt or unreadable PPTX '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Could not process this PowerPoint file. Please ensure it is a valid .pptx presentation",
        )
    except Exception as e:
        logger.error(f"Unexpected error extracting PPTX '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Could not process this PowerPoint presentation right now, please try again",
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in this PowerPoint presentation")

    chunks = RAGService.chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No usable text chunks after processing")

    return _store_document_and_chunks(
        db=db,
        file_id=file_id,
        filename=filename,
        content=text,
        chunks=chunks,
        source_type="pptx",
    )


@router.post("/docx")
async def upload_docx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = file.filename or ""
    if filename.lower().endswith(".doc"):
        raise HTTPException(status_code=400, detail=LEGACY_DOC_MESSAGE)
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only Word (.docx) files are allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (maximum 20 MB)")
    if content.startswith(OLE_SIGNATURE):
        raise HTTPException(status_code=400, detail=OLE_DOCX_MESSAGE)

    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.docx"

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        text = DOCXService.extract_text(str(file_path))
    except ValueError as e:
        logger.error(f"Corrupt or unreadable DOCX '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Could not process this Word document. Please ensure it is a valid .docx file",
        )
    except Exception as e:
        logger.error(f"Unexpected error extracting DOCX '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Could not process this Word document right now, please try again",
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in this Word document")

    chunks = RAGService.chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No usable text chunks after processing")

    return _store_document_and_chunks(
        db=db,
        file_id=file_id,
        filename=filename,
        content=text,
        chunks=chunks,
        source_type="docx",
    )


@router.post("/youtube")
async def upload_youtube(payload: YouTubeUploadRequest, db: Session = Depends(get_db)):
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please provide a valid YouTube URL")

    try:
        video_id, segments = YouTubeService.fetch_transcript(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YouTubeCaptionError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not retrieve video transcript: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching YouTube transcript for '{url}': {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Could not process this YouTube video right now, please try again",
        )

    packed_chunks = YouTubeService.pack_transcript_chunks(segments)
    if not packed_chunks:
        raise HTTPException(status_code=400, detail="No usable transcript chunks found in this video")

    chunk_texts = [c["text"] for c in packed_chunks]
    chunk_start_seconds = [c["start_seconds"] for c in packed_chunks]

    full_text = " ".join([s["text"] for s in segments])
    file_id = str(uuid.uuid4())
    display_title = f"YouTube: {video_id}"

    return _store_document_and_chunks(
        db=db,
        file_id=file_id,
        filename=display_title,
        content=full_text,
        chunks=chunk_texts,
        source_type="youtube",
        source_url=url,
        metadata_json=json.dumps(segments[:100]),  # Sample segments for reference
        chunk_start_seconds=chunk_start_seconds,
    )


def _find_existing_website(db: Session, url: str) -> Optional[Document]:
    """The saved website document for the same page as `url` (see url_key), if any.

    Compares against each document's final URL and the link originally entered.
    """
    key = url_key(url)
    if not key:
        return None
    rows = (
        db.query(Document.id, Document.filename, Document.source_url, Document.metadata_json)
        .filter(Document.source_type == "website")
        .all()
    )
    for row in rows:
        saved = [row.source_url]
        try:
            saved.append(json.loads(row.metadata_json or "{}").get("original_url"))
        except (ValueError, AttributeError):
            pass
        if key in {url_key(u) for u in saved if u}:
            return row
    return None


def _already_imported(row) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": f'This page is already in your library as "{row.filename}". '
                       "To import it again, delete that document first.",
            "document_id": row.id,
        },
    )


# Plain def (not async): fetching and extraction block, so FastAPI runs this in a worker thread.
@router.post("/website")
def upload_website(payload: WebsiteUploadRequest, db: Session = Depends(get_db)):
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please provide a web page link")

    # Checked before fetching (saves the download) and again after redirects,
    # so a short or http:// link to a page that's already saved is caught too.
    existing = _find_existing_website(db, url)
    if existing:
        raise _already_imported(existing)

    try:
        page = WebService.fetch_page(url)
        existing = _find_existing_website(db, page.url)
        if existing:
            raise _already_imported(existing)
        article = WebService.extract_article(page.html, page.url)
    except HTTPException:
        raise
    except WebPageError as e:
        logger.info(f"Website import refused for '{url}': {e.code}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected error importing web page '{url}': {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Could not import this web page right now, please try again",
        )

    chunks = RAGService.chunk_text(article.text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No usable text chunks after processing")

    return _store_document_and_chunks(
        db=db,
        file_id=str(uuid.uuid4()),
        filename=article.title,
        content=article.text,
        chunks=chunks,
        source_type="website",
        source_url=page.url,
        metadata_json=json.dumps({
            "title": article.title,
            "site_name": article.site_name,
            "original_url": url,
            "final_url": page.url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }),
    )
