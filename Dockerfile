# syntax=docker/dockerfile:1
# Novel Translator: web app (SvelteKit static) + API (FastAPI) trong một image.
# Build: docker build -t novel-translator .   Xem docs/DEPLOY.md.

# --- 1. Build web app (chỉ cần ở bước build, không có Node trong image chạy) ---
FROM node:22-slim AS web
WORKDIR /web
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- 2. Image chạy: Python 3.14 slim, cùng phiên bản với môi trường dev ---
FROM python:3.14-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Provider tùy chọn: --build-arg EXTRAS=all để có thêm anthropic/openai.
ARG EXTRAS=""
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install ".${EXTRAS:+[$EXTRAS]}" \
    && useradd --system --uid 10001 --no-create-home app

COPY --from=web /web/build ./web/build

# Không cần volume: mọi dữ liệu nằm trong PostgreSQL. Migration tự chạy khi khởi động.
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# Đúng MỘT worker: job dịch, hàng đợi và luồng SSE nằm trong bộ nhớ của process (design D5).
CMD ["uvicorn", "novel_translator.interfaces.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
