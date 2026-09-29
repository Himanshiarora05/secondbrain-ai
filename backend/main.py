from dotenv import load_dotenv
import os

load_dotenv()

from fastapi import FastAPI
from app.database.db import init_db
from app.api.upload import router as upload_router
from app.routes.search import router as search_router
from app.routes.documents import router as documents_router
from app.routes.study import router as study_router
from app.routes.merged_sets import router as merged_sets_router

app = FastAPI(
    title="SecondBrain AI",
    description="AI-powered Study Intelligence Platform",
    version="1.0.0",
)

app.include_router(upload_router)
app.include_router(search_router)
app.include_router(documents_router)
app.include_router(study_router)
app.include_router(merged_sets_router)


@app.on_event("startup")
def on_startup():
    # Creates the documents/chunks tables if they don't exist yet.
    # Previously nothing called Base.metadata.create_all() anywhere in the
    # app - it only worked if the tables had been created some other way.
    init_db()


@app.get("/")
def root():
    return {"message": "Welcome to SecondBrain AI!"}


@app.get("/api/v1/health")
def health():
    return {
        "status": "healthy",
        "service": "SecondBrain AI",
        "version": "1.0.0"
    }