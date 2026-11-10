# Proposal: Triển khai lên VPS theo mô hình "CI build, VPS chỉ chạy"

## Why

Cách triển khai hiện tại (docs/DEPLOY.md) bắt VPS phải `git pull` và tự `docker build`. Nhược điểm:
- VPS cần Node, mã nguồn và tài nguyên build.
- Image không được quét lỗ hổng.
- Rollback cần khôi phục database, vì migration có thể đổi schema theo hướng image cũ không đọc được.
- App publish cổng ra host, đứng sau một Nginx/Caddy cấu hình tay.

Chuẩn hoá theo mô hình "CI build, VPS chỉ chạy" giải quyết các điểm trên:
- Image dựng và quét một lần trên GitHub Actions.
- VPS chỉ kéo một tag đã ghim.
- Cập nhật hay rollback chỉ cần đổi một biến.
- Hạ tầng dùng chung (Traefik, Postgres) được nhiều app trên cùng VPS dùng theo một khuôn.

## What Changes

**CI/CD (GitHub Actions)**
- Mọi PR, mọi push vào nhánh mặc định và mọi tag `vX.Y.Z` đều chạy kiểm tra: ruff, pytest (Postgres 16 service), svelte-check, contrast, web build, Playwright, shellcheck.
- Sau đó build image và quét bằng Trivy; có lỗ hổng HIGH hoặc CRITICAL đã có bản vá thì job fail.
- Chỉ push lên GHCR (`ghcr.io/<owner>/<repo>`) khi push vào nhánh mặc định hoặc push git tag `vX.Y.Z`. PR chỉ kiểm tra, không push.
- Tag image:
  - nhánh mặc định (repo dùng `main`, không phải `master`): `sha-<7 ký tự>` và `latest`;
  - git tag: chỉ `vX.Y.Z`. Không dời `latest` và không ghi đè tag `sha-` đã có.
- Image được push chính là image đã quét: build một lần, quét, rồi push đúng image đó.
- Chỉ phát hành tag nằm trên `main`: tag đặt trên commit chưa vào `main` thì CI fail và không push.
- Image ghi phiên bản (tag hoặc sha) vào biến môi trường và OCI label.

**Image và container**
- Khi chạy server, entrypoint chạy `novel migrate` (giữ advisory lock như hiện tại) rồi mới `exec` uvicorn. Migrate lỗi thì container thoát, không phục vụ request. Lệnh chạy một lần (ví dụ `novel hash-password`) thì không migrate.
- Thêm `GET /api/health`: công khai, kiểm tra kết nối database, trả `{"status"}`. Trường `version` chỉ có khi đã đăng nhập; version luôn được ghi vào log khởi động. `HEALTHCHECK` của image dùng endpoint này. `/health` cũ được giữ làm bí danh.
- Container không giữ trạng thái, cấu hình trong `compose.yaml`:
  - `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, user `10001` (không phải root);
  - không volume, chỉ có một `tmpfs` cho `/tmp` vì upload multipart lớn được đệm ra file tạm.

**Bố cục trên VPS (repo cung cấp mẫu trong `deploy/`)**
- Để chạy app, `/opt/novel-translator/` chỉ cần `compose.yaml` và `.env` (chmod 600); `backup.sh` được phép nằm cạnh. Không có mã nguồn trên VPS. Mọi bí mật nằm trong `.env`.
- Image ghim `${IMAGE_REPO}:${IMAGE_TAG}`. `IMAGE_TAG` bắt buộc, dạng `vX.Y.Z`. `IMAGE_REPO` mặc định là `ghcr.io/rohanhn/ai_novel_translator`, đổi được khi fork hoặc đổi tên repo. Cập nhật hay rollback đều là: sửa `IMAGE_TAG`, rồi `docker compose pull && docker compose up -d`.
- App nối vào hai network ngoài là `traefik` và `postgres`, và không publish cổng nào.
- Định tuyến bằng label Traefik theo `Host(${APP_HOST})`, entrypoint HTTPS, certresolver Let's Encrypt.
- Biến cấu hình dùng chung với runtime, gồm `NT_DATABASE_URL`, trỏ tới host Postgres trên network `postgres`.
- **BREAKING (vận hành)**: bỏ mô hình publish `127.0.0.1:8000` + Nginx/Caddy trên host. `docs/DEPLOY.md` được viết lại cho mô hình mới.

**Migration chỉ thêm**
- Từ nay migration chỉ được thêm: bảng mới (kèm mọi constraint), cột nullable hoặc có `DEFAULT`, index.
- Không được DROP, RENAME, TRUNCATE, xoá dòng, đổi kiểu cột, đặt `NOT NULL` cho cột đã có, hay thêm constraint (UNIQUE/CHECK/FK) vào bảng đã có.
- Một test quét các file migration để chặn những lệnh trên.
- Migrator hiện đã bỏ qua các version trong database mà nó không biết. Change này thêm test để khoá hành vi đó, nhờ vậy image cũ chạy được trên schema mới, và rollback không cần khôi phục database.

**Client IP sau Traefik**
- Việc chặn đăng nhập sai cần tính theo IP thật của client. Docs khuyên gán IP tĩnh cho Traefik, rồi tin đúng IP đó.
- `NT_TRUSTED_PROXY` nhận thêm dải CIDR làm phương án dự phòng (tin cả subnet của network `traefik`), dùng khi IP của Traefik có thể đổi. Docs ghi rõ rủi ro: các container khác trên network đó cũng được tin.

**CLI**
- Lệnh mới `novel migrate`: áp dụng migration còn thiếu, in các version vừa chạy, rồi thoát.

**Sao lưu database của app**
- `deploy/backup.sh` chạy bằng cron hằng ngày:
  - `pg_dump -Fc` database của app, dùng chính `NT_DATABASE_URL` trong `.env`;
  - chạy qua image `postgres:16` trên network `postgres`;
  - mã hoá trực tiếp bằng `age` với public key (private key giữ ngoài VPS), nên không có bản dump chưa mã hoá nào chạm đĩa;
  - giữ 14 bản mới nhất.
- Tài liệu hướng dẫn khôi phục.

### Ngoài phạm vi
- Dựng và vận hành hạ tầng dùng chung: Traefik v3 (entrypoint, certresolver, network `traefik`), Postgres 16 (container, network `postgres`), cài `age`/cron trên VPS. Docs chỉ nêu app cần hạ tầng cung cấp những gì.
- Tạo role và database cho app: admin làm thủ công như hiện tại.
- Chép bản sao lưu ra ngoài VPS (rclone/S3…) và giữ private key `age`: admin tự xử lý.
- Tự động deploy qua SSH từ CI. VPS chỉ đổi `IMAGE_TAG` bằng tay.
- Chạy nhiều worker hoặc nhiều bản sao: vẫn đúng MỘT container, MỘT worker (job dịch nằm trong bộ nhớ).
- Image đa kiến trúc: chỉ build `linux/amd64`.
- Đồng bộ version trong `pyproject.toml` với git tag.

## Capabilities

### New Capabilities
- `release-pipeline`: kiểm tra trên CI, build và quét image, quy tắc đẩy và đặt tag image trên GHCR.
- `deployment`: cách app chạy trong production: container không trạng thái và hạ quyền, entrypoint migrate rồi chạy server, health check, bố cục `compose.yaml` + `.env`, định tuyến qua Traefik, cập nhật và rollback bằng `IMAGE_TAG`, migration chỉ thêm.
- `database-backup`: sao lưu hằng ngày database của app, mã hoá bằng `age`, giữ 14 bản, khôi phục được.

### Modified Capabilities
- `interfaces`: requirement "CLI commands" thêm lệnh `migrate`.
- `access-control`: thêm requirement xác định IP client sau reverse proxy tin cậy (IP hoặc CIDR), dùng cho việc chặn đăng nhập sai.

## Impact

- **Mới**:
  - `.github/workflows/ci.yml`;
  - `deploy/compose.yaml`, `deploy/.env.example`, `deploy/backup.sh`;
  - `docker/entrypoint.sh` (hoặc tương đương);
  - test cho health, migrate CLI, quy tắc migration, CIDR proxy.
- **Sửa**:
  - `Dockerfile`: entrypoint, HEALTHCHECK, build arg version, OCI label;
  - `src/novel_translator/interfaces/api/app.py` (`/api/health`) và `auth.py` (CIDR, public path);
  - `interfaces/cli/main.py` (`migrate`);
  - `storage/db.py`: thêm hàm `ping` cho health. `storage/migrator.py` không đổi, vì hành vi với version lạ đã đúng, chỉ thêm test;
  - `config.py` (`NT_VERSION`);
  - `docker-compose.yml` ở gốc chỉ còn dùng để chạy thử local, cập nhật health;
  - `docs/DEPLOY.md` (viết lại), `docs/ARCHITECTURE.md`, `.env.example`.
- **API**: thêm `GET /api/health` (công khai). Các endpoint khác không đổi.
- **CLI**: thêm `novel migrate`.
- **Schema DB**: không đổi. Thêm quy ước "chỉ thêm" cho các migration sau này.
- **Chi phí LLM**: không ảnh hưởng. CI không gọi LLM thật (test dùng provider `echo`), và không cần `GEMINI_API_KEY` trong CI.
- **Phụ thuộc mới**: GitHub Actions (`docker/*`, `aquasecurity/trivy-action`), GHCR. Trên VPS cần `age` và image `postgres:16` cho bước sao lưu.
