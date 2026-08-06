from fastapi import FastAPI
from app.api.upload import router as upload_router

app = FastAPI(
    title="SecondBrain AI",
    description="AI-powered Study Intelligence Platform",
    version="1.0.0",
)

app.include_router(upload_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to SecondBrain AI!"
    }


@app.get("/api/v1/health")
def health():
    return {
        "status": "healthy",
        "service": "SecondBrain AI",
        "version": "1.0.0"
    }