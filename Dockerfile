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
# Phiên bản (tag vX.Y.Z hoặc sha-xxxxxxx) do CI truyền vào; app log ra lúc khởi động và báo
# trong /api/health cho người đã đăng nhập (design D2).
ARG NT_VERSION=dev
ARG NT_REVISION=unknown
LABEL org.opencontainers.image.title="novel-translator" \
      org.opencontainers.image.version="${NT_VERSION}" \
      org.opencontainers.image.revision="${NT_REVISION}"
ENV NT_VERSION=${NT_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Vá gói hệ thống của base image ngay khi build (Trivy chặn release nếu còn CVE HIGH/CRITICAL
# đã có bản vá, xem design D1); dọn danh sách apt để không phình image.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Provider tùy chọn: --build-arg EXTRAS=all để có thêm anthropic/openai.
ARG EXTRAS=""
COPY pyproject.toml ./
COPY src/ ./src/
# Cài xong thì gỡ pip: lúc chạy không cần, và pip mang theo bản riêng của msgpack/setuptools/
# urllib3 mà Trivy báo lỗ hổng.
RUN pip install ".${EXTRAS:+[$EXTRAS]}" \
    && pip uninstall -y pip \
    && useradd --system --uid 10001 --no-create-home app

COPY --from=web /web/build ./web/build
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

# Không cần volume: mọi dữ liệu nằm trong PostgreSQL. Container chạy được với rootfs read-only
# (chỉ /tmp là tmpfs, xem deploy/compose.yaml).
USER app
EXPOSE 8000
# --start-interval: kiểm tra mỗi 2 giây trong lúc khởi động để Traefik nhận container mới ngay
# khi sẵn sàng thay vì chờ 30 giây (Docker Engine 25+; bản cũ bỏ qua).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

# Server: migrate trước (entrypoint) rồi chạy. Đúng MỘT worker: job dịch, hàng đợi và luồng SSE
# nằm trong bộ nhớ của process. Graceful shutdown tối đa 10 giây: SSE không tự đóng, không giới
# hạn thì `docker stop` luôn phải chờ hết stop_grace_period.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "novel_translator.interfaces.api.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--timeout-graceful-shutdown", "10"]
