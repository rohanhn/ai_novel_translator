# Proposal: MVP web reader

## Why

Kiến trúc v0.1 là công cụ CLI/API dịch bằng LLM, chưa phục vụ đúng mục tiêu trong `docs/raw/base-idea.md`: một không gian riêng trên web để đọc truyện Trung đã dịch sang Việt mượt mà trên điện thoại, tên riêng nhất quán, biên tập được, và chi phí $0 (dùng Gemini API free tier của chính người dùng). MVP này biến lõi dịch hiện có thành một web reader cá nhân chạy trên VPS.

## What Changes

**Triển khai và truy cập**
- Web app chạy trên VPS tại subdomain riêng (`<app>.mydomain.com`), app ở gốc `/`, một container: FastAPI phục vụ Svelte SPA (file tĩnh) và JSON/SSE API.
- **BREAKING:** lưu trữ chuyển từ SQLite sang **PostgreSQL** có sẵn (instance Docker dùng chung trên local và VPS), dùng database và role riêng của app. Bỏ hẳn SQLite; dữ liệu thử của v0.1 không được chuyển.
- Một người dùng duy nhất, đăng nhập bằng một mật khẩu cấu hình qua biến môi trường, dùng session cookie, giới hạn số lần đăng nhập sai. Toàn bộ trang là `noindex` và không có URL công khai.

**Dịch**
- **BREAKING:** provider mặc định chuyển từ Anthropic sang **Gemini** (BYOK, API key của user qua env). Thêm provider Gemini vào registry.
- Chuỗi fallback provider/model có thứ tự: Gemini model chính → Gemini model nhẹ (cùng key). Lỗi 429 phân biệt hai loại: hết quota theo phút thì chờ và thử lại; hết quota theo ngày thì chuyển bước trong chuỗi hoặc dừng và báo giờ reset.
- **BREAKING:** mỗi chương dịch bằng **một request** (tiêu đề + nội dung + đề xuất tên mới), thay cho mô hình nhiều đoạn 3.000 ký tự cộng một request riêng cho tiêu đề. Chỉ cắt đoạn khi chương vượt ngưỡng lớn.
- Kết quả dịch được stream về reader. Bản dịch được lưu và dùng lại, kèm phiên bản bộ tên dùng lúc dịch.
- **Buffer N+1:** khi có tín hiệu đọc thật (đọc ≥30s, cuộn ≥60%, hoặc bắt đầu dịch N), hệ thống tải raw và dịch trước chương N+1. Buffer chỉ dùng bước đầu của chuỗi fallback; khi bước đầu hết quota ngày thì buffer dừng, phần quota còn lại dành cho chương user chủ động mở. Mỗi lần chỉ buffer tối đa một chương.

**Bộ tên**
- LLM đề xuất tên riêng mới trong cùng response; user duyệt (đồng ý / sửa / bỏ qua).
- Đổi bản dịch của một tên: thay thế trong các chương đã dịch có raw chứa tên đó, rồi gắn nhãn "bộ tên đã đổi" kèm nút dịch lại. Chương đã biên tập tay không bị thay tự động, chỉ được gắn nhãn.

**Đọc và biên tập**
- Reader cuộn dọc, responsive mobile, đổi màu nền và cỡ chữ, lưu tiến độ đọc (chương + vị trí).
- Sửa tay bản dịch. Chương đã sửa được đánh dấu "đã biên tập".
- Màn hình cài đặt hiển thị số lượt đã dùng hôm nay theo từng bước của chuỗi fallback.

**Thư viện**
- Upload `.txt` từ web. Xóa truyện xóa sạch raw, bản dịch, bộ tên và tiến độ liên quan.

**Giao diện và quy ước**
- **BREAKING:** Web SPA + HTTP API là giao diện chính. CLI chỉ còn là công cụ quản trị/dev, không bắt buộc ngang tính năng.
- Cập nhật `openspec/config.yaml`:
  - Bỏ ràng buộc "CLI và API phải ngang tính năng".
  - Đổi provider mặc định sang Gemini và áp dụng mô hình một request mỗi chương.
  - Thêm ràng buộc tuân thủ pháp lý: chỉ dùng API chính thức; không xoay vòng nhiều tài khoản, không lách rate limit, không tự động hóa giao diện chat của gói tiêu dùng; thư viện riêng tư.
- Cập nhật `docs/raw/base-idea.md` mục 4.2: thay quy tắc "không tự dịch chương kế" bằng quy tắc buffer N+1 có kiểm soát quota như trên.

### Out of scope (sau MVP)
- URL import, connector, chapter manifest, prefetch raw từ web; quy trình takedown.
- Provider fallback ngoài Gemini (OpenRouter, Groq...).
- Chế độ copy-paste bán tự động qua clipboard.
- Bộ tên chung cấp user (lớp trên bộ tên của truyện); style profile theo truyện.
- Reader lật trang kiểu ebook; đọc offline/PWA.
- Nhiều tài khoản người dùng; BYOK qua giao diện (MVP đọc key từ env). Chia sẻ bản dịch giữa user thuộc backlog dài hạn.
- Xoay vòng nhiều tài khoản để lách quota: bị loại hẳn, không phải "để sau".

## Capabilities

### New Capabilities
- `access-control`: đăng nhập một user bằng mật khẩu, session, chống brute-force, `noindex`.
- `web-reader`: trải nghiệm đọc trên web: hiển thị chương có streaming, chuyển chương, đổi nền/cỡ chữ, lưu tiến độ đọc.
- `translation-prefetch`: buffer N+1: tín hiệu kích hoạt, điều kiện chặn, giới hạn một chương, chính sách ưu tiên quota giữa foreground và background.
- `translation-editing`: sửa tay bản dịch, trạng thái "đã biên tập", bảo vệ chương đã biên tập khỏi thay đổi tự động.

### Modified Capabilities
- `llm-providers`: thêm Gemini làm mặc định; chuỗi fallback có thứ tự; phân loại và xử lý lỗi quota (phút / ngày); đếm lượt dùng theo ngày.
- `translation-pipeline`: một request mỗi chương có đề xuất tên; streaming; lưu phiên bản bộ tên trên bản dịch; bỏ request dịch tiêu đề riêng.
- `glossary`: hàng chờ duyệt tên do LLM đề xuất; lan truyền thay đổi tên (thay thế có phạm vi + gắn nhãn dịch lại).
- `novel-library`: upload qua web; xóa truyện kèm toàn bộ dữ liệu liên quan.
- `interfaces`: web SPA + API là giao diện chính, có endpoint SSE; bỏ yêu cầu ngang tính năng với CLI; CLI là công cụ quản trị.

## Impact

- **Code:**
  - `providers/`: thêm provider Gemini; thêm lớp fallback chain + quota tracker được nối trong `container.py` để pipeline/application không rẽ nhánh theo tên provider.
  - `pipeline/`: prompt mới có định dạng 3 phần (TITLE/BODY/NAMES) và parser streaming.
  - `application/`: thêm service cho prefetch, editing, glossary suggestions, rename propagation, reading progress.
  - `interfaces/api`: auth, SSE, các endpoint mới.
  - Thêm `web/` (Svelte + Vite).
- **Schema DB:** schema được viết lại cho PostgreSQL, thêm bảng/cột cho tiến độ đọc, đề xuất tên, phiên bản bộ tên, cờ đã biên tập/stale, đếm lượt dùng theo ngày, session. Có cơ chế migration bằng file SQL. Dữ liệu SQLite v0.1 bị bỏ (chỉ là dữ liệu thử).
- **API:** thêm endpoint auth, streaming dịch, tiến độ, bộ tên đề xuất, sửa bản dịch, xóa truyện, trạng thái quota. Mọi endpoint (trừ login, health) yêu cầu session.
- **CLI:** giữ lại cho import/quản trị/debug, không mở rộng thêm.
- **Chi phí LLM:** $0 với Gemini free tier. Số request mỗi chương giảm từ khoảng 4 xuống 1. Buffer N+1 tiêu tối đa thêm một chương mỗi lần bỏ ngang và không bao giờ dùng quota dự phòng. Đánh đổi đã chấp nhận: ở free tier, Google có thể dùng dữ liệu gửi lên.
- **Dependencies:** Python: SDK Gemini (`google-genai`), thư viện hash mật khẩu, driver PostgreSQL (`psycopg` 3 kèm pool). Frontend: Node (chỉ lúc build), Svelte, Vite. Docker image multi-stage.
- **Vận hành:** một container app trên VPS sau reverse proxy HTTPS có sẵn, nối vào Docker network của container PostgreSQL dùng chung. Database và role của app được tạo thủ công một lần. Sao lưu bằng `pg_dump`.
- **Phát triển:** test cần PostgreSQL local đang chạy, dùng một database test riêng.
