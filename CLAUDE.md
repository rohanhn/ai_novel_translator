# Novel Translator

Dịch truyện Trung → Việt bằng LLM. Kiến trúc: xem [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quy trình làm việc
Mọi tính năng mới đi qua OpenSpec:
1. `/opsx:propose <mô tả yêu cầu>` → tạo proposal/design/specs/tasks trong `openspec/changes/`
2. Review, chỉnh nếu cần (`/opsx:update`)
3. `/opsx:apply` → hiện thực theo tasks
4. `/opsx:archive` → gộp delta vào `openspec/specs/`

Ràng buộc kiến trúc nằm trong `openspec/config.yaml` (context) — tuân thủ khi propose và apply.

## Lệnh
- Cài: `uv venv .venv && uv pip install -e ".[dev,all]"`; web: `cd web && npm ci`
- Env: chép `.env.example` → `.env`, điền `NT_DATABASE_URL`, `NT_TEST_DATABASE_URL` (Postgres local `shared-postgres`), `NT_PASSWORD_HASH` (tạo bằng `.venv/bin/novel hash-password`), `GEMINI_API_KEY`; chạy thử qua http thì đặt `NT_COOKIE_SECURE=false`
- Test: `.venv/bin/pytest -q` (cần Postgres local + `NT_TEST_DATABASE_URL`; không bao giờ gọi LLM thật trong test, dùng provider `echo`)
- Lint: `.venv/bin/ruff check src tests`
- Web: `cd web && npm run build` (ra `web/build`, FastAPI tự phục vụ); `npm run check`, `npm run check:contrast`, `npm run test:e2e` (Playwright, cần build trước)
- CLI: `.venv/bin/novel --help`; app: `.venv/bin/novel serve` → http://127.0.0.1:8000 (API docs `/docs`, cần đăng nhập)
- Dev UI không tốn quota: `NT_PROVIDER=echo NT_ECHO_DELAY=0.2 .venv/bin/novel serve`
- Docker/triển khai: xem [docs/DEPLOY.md](docs/DEPLOY.md)
