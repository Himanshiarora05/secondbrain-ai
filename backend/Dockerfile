# Backend image for Hugging Face Spaces (Docker SDK). Build context: backend/.
# All configuration comes from environment variables (Space "Variables and
# secrets"); no .env file is copied into the image. See docs/DEPLOY.md.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# CPU-only torch first: the default Linux wheel pulls several GB of CUDA
# libraries the free Space can't use. requirements.txt's pin is then satisfied.
COPY requirements.txt /tmp/requirements.txt
RUN TORCH_VERSION=$(grep -i '^torch==' /tmp/requirements.txt | cut -d= -f3) \
    && pip install --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}" \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    ANONYMIZED_TELEMETRY=False \
    PORT=7860 \
    CHROMA_DIR=/home/user/app/vector_db
WORKDIR /home/user/app

# Bake the embedding model into the image so startup doesn't download it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY --chown=user . .
RUN mkdir -p uploads vector_db

EXPOSE 7860
# The Chroma index lives on the container's disk, which a free Space loses on
# every restart; startup rebuilds it from the chunks in Postgres (main.py).
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
