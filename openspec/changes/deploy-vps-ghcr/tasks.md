# Tasks

## 1. App: version, health, IP client, migrate

- [x] 1.1 Thêm `Settings.version` (đọc `NT_VERSION`, mặc định `dev`), endpoint `GET /api/health` dùng chung handler với `/health`: chạy `SELECT 1` qua pool (timeout lấy connection 2 giây); trả 200 `{"status":"ok"}`, hoặc 503 `{"status":"unavailable"}` khi DB lỗi; chỉ thêm `version` khi có session hợp lệ; thêm `/api/health` vào `PUBLIC_PATHS`; log version lúc khởi động (D2, D4). Kiểm: test pytest gọi được cả hai đường dẫn khi chưa đăng nhập và không có `version`; đã đăng nhập thì có `version`; dùng pool giả lỗi thì nhận 503 và body không chứa chi tiết lỗi; log khởi động có version (caplog).
- [x] 1.2 `NT_TRUSTED_PROXY` nhận danh sách IP và CIDR (IPv4/IPv6): parse một lần bằng validator của Settings, mục sai thì báo lỗi nêu tên mục; `client_ip()` so khớp theo network, peer không phải IP thì không tin (D7). Kiểm: các test của 3 scenario trong spec access-control, cùng các test cũ của `test_auth.py`, đều pass.
- [x] 1.3 Lệnh CLI `novel migrate`: chỉ mở pool từ `NT_DATABASE_URL` rồi gọi `migrate()`, không qua `build_container`; in các version đã áp dụng hoặc "đã cập nhật"; lỗi thì thoát mã khác 0 kèm tên migration (D3). Kiểm: test CliRunner trên DB test (trống → áp dụng hết; chạy lần hai → "đã cập nhật"; không đặt `GEMINI_API_KEY` và `NT_PASSWORD_HASH` vẫn chạy).
- [x] 1.4 Test hành vi migrator: DB có `schema_migrations` version 999 thì `migrate()` trả `[]`, không lỗi; hai luồng gọi `migrate()` cùng lúc thì mỗi migration chỉ áp dụng một lần. Thêm `tests/test_migration_rules.py` quét `migrations/*.sql` theo luật D8 (bỏ comment trước). Kiểm: pytest pass với `001`, `002`; các file mẫu tạm có `DROP COLUMN`, `ADD COLUMN x INT NOT NULL`, `TRUNCATE`, `DELETE FROM` hoặc `ADD CONSTRAINT … UNIQUE` trên bảng cũ đều bị bắt kèm tên file; một `CREATE TABLE` mới có PK, FK và cột `NOT NULL` thì được chấp nhận (tham số hoá bằng `tmp_path`).

## 2. Image

- [x] 2.1 Thêm `docker/entrypoint.sh` (POSIX sh, `set -eu`; chỉ khi `$1` là `uvicorn` mới chạy `novel migrate`; rồi `exec "$@"`). Sửa `Dockerfile`: `ARG/ENV NT_VERSION`, label OCI `version`/`revision`, `ENTRYPOINT` gọi entrypoint, `HEALTHCHECK` dùng `/api/health` với `--start-period=60s --start-interval=2s`, giữ `CMD` uvicorn một worker và thêm `--timeout-graceful-shutdown 10`; bỏ `docker/` khỏi `.dockerignore` nếu bị loại (D2, D3, D4). Kiểm: `docker build --build-arg NT_VERSION=v0.0.0-test .` thành công; chạy với DB test thì log có bước migrate trước uvicorn, log khởi động ghi `v0.0.0-test`, `docker inspect` báo `healthy` và có label version; chạy với `NT_DATABASE_URL` sai thì container thoát với mã khác 0, không mở cổng 8000; `docker run --rm -i <image> novel hash-password` không có DB vẫn in ra hash.
- [x] 2.2 Cập nhật `docker-compose.yml` ở gốc thành bản chạy thử local: ghi rõ không dùng trên VPS, health mới, thêm `read_only`, `cap_drop`, `no-new-privileges` và `tmpfs /tmp` cho giống production. Kiểm: `docker compose config` hợp lệ; `docker compose up` với `.env` local thì container healthy.
- [x] 2.3 Cập nhật `docs/ARCHITECTURE.md` (sau khi entrypoint đã có): luồng khởi động container (entrypoint `novel migrate` → `exec` uvicorn; `build_container` migrate lại là no-op), `/api/health` (version chỉ khi đã đăng nhập, log version lúc khởi động), quy tắc migration chỉ thêm (kèm quy ước code phải chịu được `NULL` ở cột mới, vì có thể rollback rồi nâng cấp lại), `NT_TRUSTED_PROXY` dạng IP/CIDR. Kiểm: đọc lại, khớp code của nhóm 1–2; `.venv/bin/pytest -q` và `.venv/bin/ruff check src tests` pass.

## 3. Mẫu triển khai `deploy/`

- [x] 3.1 Viết `deploy/compose.yaml`: image `${IMAGE_REPO:-ghcr.io/rohanhn/ai_novel_translator}:${IMAGE_TAG:?…}`, `APP_HOST:?`, label Traefik (D6), hai network ngoài `traefik`/`postgres` (tên đổi được qua biến), không có `ports`/`volumes`, hardening và `tmpfs` (D5), `env_file: .env`. Viết `deploy/.env.example` liệt kê mọi biến kèm chú thích. Kiểm: `docker compose -f deploy/compose.yaml --env-file deploy/.env.example config` báo thiếu `IMAGE_TAG` khi để trống, hợp lệ khi đã đặt; kết quả không có `ports`, có đủ label, và đặt `TRAEFIK_NETWORK=edge` thì cả network ngoài lẫn label `traefik.docker.network` đều thành `edge`.
- [ ] 3.2 Viết `deploy/backup.sh` theo D9: chỉ đọc các khoá cần từ `.env`, không `source`, bỏ cặp nháy bao ngoài; nhiều recipient tách bằng dấu phẩy, mỗi key một `-r`; tên file `<prefix>-YYYYMMDD-HHMMSS.dump.age` (UTC), không ghi đè; `umask 077`; pipe `pg_dump -Fc | age` vào file `.tmp`, `trap` dọn file tạm khi lỗi; `mv` sang tên có ngày giờ; giữ 14 bản; kiểm tra cấu hình và lệnh trước khi dump. Kiểm: `shellcheck deploy/backup.sh docker/entrypoint.sh` sạch.
- [ ] 3.3 Viết `tests/test_backup_script.py`: chạy `backup.sh` với `docker` và `age` giả trong `PATH` tạm, gồm các trường hợp:
  - thiếu recipient → thoát mã khác 0, không gọi docker;
  - dump lỗi → không còn `.tmp`, 14 bản cũ còn nguyên;
  - thành công khi đã có 14 bản → còn 14 bản, bản cũ nhất bị xoá, tên file đúng mẫu;
  - URL database không xuất hiện trong tham số dòng lệnh của `docker`;
  - giá trị trong `.env` có nháy đơn hoặc nháy kép được đọc đúng;
  - hai recipient → `age` nhận hai cờ `-r`.

  Kiểm: pytest pass (bỏ qua có lý do nếu máy không có `bash`).
- [ ] 3.4 Kiểm tra image thật trong điều kiện production: `docker run --read-only --tmpfs /tmp:size=128m --cap-drop ALL --security-opt no-new-privileges --user 10001:10001` với DB test và `NT_PROVIDER=echo`. Thử đăng nhập, upload TXT khoảng 50 MB, upload bìa PNG, mở chương và xem SSE chạy dần. Gặp lỗi ghi file thì sửa image (ví dụ `HOME=/tmp`) và ghi lại trong design. Đo gián đoạn khi tạo lại container trong lúc đang mở SSE: từ `docker stop` tới khi `healthy` dưới 20 giây (không tính pull), trang đọc báo mất kết nối, và mở lại chương thì dịch lại được. Kiểm: các bước trên thành công; log không có lỗi `Read-only file system`.

## 4. CI/CD

- [ ] 4.1 Viết `.github/workflows/ci.yml`, job `checks` (D1):
  - Postgres 16 service, tạo database `nt_test` và `nt_e2e_test`;
  - `uv venv .venv && uv pip install -e ".[dev,all]"` ở gốc repo (Playwright gọi `.venv/bin/python`), rồi ruff, pytest;
  - npm ci, check, check:contrast, build, Playwright chromium dùng DB e2e;
  - shellcheck;
  - cache uv, npm, Playwright;
  - `permissions: contents: read`; không dùng bí mật nào ngoài `GITHUB_TOKEN`.

  Kiểm: `actionlint` sạch; chạy thử các bước bằng lệnh local tương ứng.
- [ ] 4.2 Thêm job `image` (`needs: checks`):
  - metadata-action: nhánh mặc định → `sha-<short>` + `latest`; tag semver → chỉ `v{{version}}`; `flavor: latest=false`; PR → tag tạm không push;
  - build đúng một lần: `linux/amd64`, `load: true`, `push: false`, `--build-arg NT_VERSION`;
  - Trivy quét image đã load: `HIGH,CRITICAL`, `ignore-unfixed`, `exit-code 1`; DB lấy từ mirror `public.ecr.aws` trước, GHCR làm dự phòng; cache DB theo ngày;
  - login GHCR rồi `docker push --all-tags` chính image đó, chỉ khi push vào nhánh mặc định hoặc tag `v*.*.*`; `permissions: packages: write` chỉ cho job này;
  - trigger: `pull_request`, push `main`, tag `v*.*.*`;
  - với tag: kiểm tra `git merge-base --is-ancestor "$GITHUB_SHA" origin/main` (checkout `fetch-depth: 0`), fail trước khi build nếu commit không nằm trên `main`.

  Kiểm: `actionlint` sạch; chạy Trivy local trên image vừa build (`docker run aquasec/trivy image …` với cùng tham số) để biết trước kết quả.
- [ ] 4.3 Chạy thử CI trên GitHub (cần người dùng cho phép push nhánh): mở PR thì job `checks` và `image` chạy, image không được push; sau khi merge thì GHCR có `sha-<short>` + `latest`; gắn tag thì chỉ thêm `vX.Y.Z`, và `latest` không đổi digest. Kiểm: link run thành công; `docker pull ghcr.io/rohanhn/ai_novel_translator:sha-<short>` được, và log khởi động của image ghi đúng version.

## 5. Tài liệu

- [ ] 5.1 Viết lại `docs/DEPLOY.md` cho mô hình mới (D10):
  - yêu cầu đối với hạ tầng: Traefik v3 (entrypoint, certresolver, timeout, không buffer), Postgres 16, hai network;
  - tạo role và DB;
  - `/opt/novel-translator` với `chmod 600 .env`; `docker login ghcr.io` nếu package private;
  - `NT_TRUSTED_PROXY`: khuyến nghị gán IP tĩnh cho Traefik rồi tin đúng IP đó; phương án dự phòng là tin subnet của network traefik, kèm cảnh báo rủi ro (D7);
  - phát hành bằng git tag; cập nhật và rollback bằng `IMAGE_TAG`;
  - quy tắc migration chỉ thêm, và quy ước code phải chịu được `NULL` ở cột mới;
  - cài cron backup (user chạy cron, quyền của `.env` và `BACKUP_DIR`, cảnh báo nhóm `docker`); giải mã và khôi phục (single transaction); tập khôi phục;
  - bảng ánh xạ biến từ mô hình cũ, và các bước chuyển đổi (Migration Plan).

  Cập nhật `.env.example` ở gốc (trỏ sang `deploy/.env.example` cho VPS) và `CLAUDE.md` (lệnh `novel migrate`). Kiểm: mọi lệnh trong docs khớp tên file và biến thật (`grep` các biến trong `deploy/.env.example`).

## 6. Kiểm tra tổng

- [ ] 6.1 Chạy toàn bộ: `.venv/bin/pytest -q`, `.venv/bin/ruff check src tests`, `cd web && npm run check && npm run check:contrast && npm run build && npm run test:e2e`, `shellcheck`, `actionlint`, `openspec validate deploy-vps-ghcr --strict`. Kiểm: tất cả pass, ghi số liệu vào commit.

## Workflow follow-up

- Sau khi archive và merge: gắn tag `v0.2.0` và làm theo "Migration Plan" trong design.md trên VPS (việc của admin).
