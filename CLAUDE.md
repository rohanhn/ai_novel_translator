# Novel Translator

Dịch truyện Trung → Việt bằng LLM. Kiến trúc: xem [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quy trình làm việc
Mọi tính năng mới đi qua OpenSpec:
1. `/opsx:propose <mô tả yêu cầu>` → tạo proposal/design/specs/tasks trong `openspec/changes/`
2. Review, chỉnh nếu cần (`/opsx:update`)
3. `/opsx:apply` → tạo/chuyển sang nhánh local trùng tên change (từ `main`), hiện thực theo tasks, mỗi task một commit trên nhánh đó
4. `/opsx:archive` → gộp delta vào `openspec/specs/` (làm trên nhánh của change)
5. Đưa vào `main` bằng pull request từ nhánh của change. Không commit/merge thẳng vào `main`, không push khi chưa được yêu cầu.

Ràng buộc kiến trúc nằm trong `openspec/config.yaml` (context) — tuân thủ khi propose và apply.

### Kinh nghiệm OpenSpec
- **Đồng bộ `main` trước khi làm:** trước khi apply tiếp, archive hay mở PR, merge `main` vào nhánh change ở local (không push). Trước đó kiểm tra file hai bên cùng sửa (`git diff --name-only $(git merge-base main HEAD) main` so với `HEAD`). Có xung đột thì sửa trên nhánh change và chạy lại toàn bộ kiểm tra, không sửa trên `main`.
- **Merge PR:** dùng `gh pr merge` sau khi người dùng đồng ý, rồi `git fetch origin main:main` để cập nhật `main` local.
- **Thứ tự archive:** change sửa spec do change khác tạo phải archive sau change đó. Không propose change sửa một spec chưa có trong `openspec/specs/`; chờ change gốc archive xong. Tính năng thuộc capability đã có thì viết delta sửa spec đó, không tạo capability mới.
- **Không archive khi còn task chưa tick**, kể cả task chạy thử thủ công. Chạy thử dở thì để task mở.
- **Phát hiện vấn đề sau khi đã code:** sửa kế hoạch bằng `/opsx:update` trước, đồng bộ proposal/spec/design/tasks; task mới vào một mục mới (không sửa task đã tick), task chạy thử thủ công dời ra sau. Commit bản sửa kế hoạch lên nhánh change (`docs(openspec): ...`).
- **Chứng minh trước khi sửa spec:** gọi thẳng hàm domain với dữ liệu mẫu để tái hiện vấn đề.
- **Validate:** `openspec validate <change> --strict` sau mỗi lần sửa artifact. Requirement > 500 ký tự thì tách thành nhiều requirement, ví dụ và ca biên đưa vào scenario.
- **Hỏi người dùng** bằng tên trên giao diện (ví dụ "Thêm chương mới" / "Tải lại cả bộ"), không bằng tên nội bộ (`append`/`replace`); nêu rõ đánh đổi của từng lựa chọn.

### Chạy thử thủ công
- Build lại web, chạy với `NT_PROVIDER=echo`. `.env` chưa có `NT_PASSWORD_HASH` thì truyền hash tạm qua biến môi trường, không ghi vào `.env`.
- App ghi vào DB thật (`NT_DATABASE_URL`): không tự xóa hay sửa dữ liệu của người dùng.
- Gặp lỗi thì kiểm tra dữ liệu trước khi kết luận là bug: so thời điểm tạo dữ liệu với thời điểm commit tính năng (dữ liệu tạo trước tính năng có thể sai theo quy tắc mới).

## Lệnh
- Cài: `uv venv .venv && uv pip install -e ".[dev,all]"`; web: `cd web && npm ci`
- Env: chép `.env.example` → `.env`, điền `NT_DATABASE_URL`, `NT_TEST_DATABASE_URL` (Postgres local `shared-postgres`), `NT_PASSWORD_HASH` (tạo bằng `.venv/bin/novel hash-password`), `GEMINI_API_KEY`; chạy thử qua http thì đặt `NT_COOKIE_SECURE=false`
- Test: `.venv/bin/pytest -q` (cần Postgres local + `NT_TEST_DATABASE_URL`; không bao giờ gọi LLM thật trong test, dùng provider `echo`)
- Lint: `.venv/bin/ruff check src tests`
- Web: `cd web && npm run build` (ra `web/build`, FastAPI tự phục vụ); `npm run check`, `npm run check:contrast`, `npm run test:e2e` (Playwright, cần build trước)
- CLI: `.venv/bin/novel --help`; app: `.venv/bin/novel serve` → http://127.0.0.1:8000 (API docs `/docs`, cần đăng nhập)
- Dev UI không tốn quota: `NT_PROVIDER=echo NT_ECHO_DELAY=0.2 .venv/bin/novel serve`
- Docker/triển khai: xem [docs/DEPLOY.md](docs/DEPLOY.md)
