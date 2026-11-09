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
- Cài: `uv venv .venv && uv pip install -e ".[dev,all]"`
- Test: `.venv/bin/pytest -q` (không bao giờ gọi LLM thật trong test; dùng provider `echo`)
- Lint: `.venv/bin/ruff check src tests`
- CLI: `.venv/bin/novel --help`; API: `.venv/bin/novel serve` → http://127.0.0.1:8000/docs
