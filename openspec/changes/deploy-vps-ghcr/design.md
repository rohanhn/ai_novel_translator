# Design: deploy-vps-ghcr

## Context

Hiện trạng liên quan:
- **`Dockerfile`**: build hai bước, Node 22 build `web/`, rồi chạy trên Python 3.14 slim với user `app` (uid 10001). `HEALTHCHECK` gọi `/health`. `CMD` chạy uvicorn với `--workers 1`. Chưa có entrypoint riêng.
- **Migration**: chạy trong `build_container()` (`storage/migrator.py`), giữ `pg_advisory_lock(LOCK_KEY)`, mỗi file một transaction, ghi vào `schema_migrations`. Migrator chỉ áp dụng những version còn thiếu, nên đã bỏ qua các version lạ trong DB. Chưa có test nào khoá hành vi này. Hai migration hiện có (`001`, `002`) đều chỉ thêm.
- **`GET /health`**: công khai, nằm trong `PUBLIC_PATHS`, trả `{"status":"ok"}` mà không kiểm tra DB. Playwright (`webServer.url`) và hai test pytest gọi endpoint này.
- **`client_ip()`** (`interfaces/api/auth.py`): chỉ so khớp đúng IP với `NT_TRUSTED_PROXY`, lấy hop cuối của `X-Forwarded-For`.
- **`docker-compose.yml` ở gốc**: `build: .`, publish `127.0.0.1:8000`, một network ngoài cho `shared-postgres`. `docs/DEPLOY.md` mô tả mô hình build trên VPS + Nginx/Caddy.
- **Chưa có `.github/`.** Pytest và e2e cần Postgres, và e2e xoá schema của DB test nên không chạy song song với pytest trên cùng một DB.
- **Upload**: Starlette đệm phần multipart lớn hơn 1 MB ra file tạm trong `tempfile.gettempdir()` (mặc định `/tmp`). Giới hạn upload TXT là 50 MB, ảnh bìa 10 MB.

Lớp bị thay đổi:
- **interfaces**: API thêm `/api/health` và parse CIDR trong `auth.py`; CLI thêm `migrate`.
- **storage**: `db.py` thêm hàm `ping` (gọi qua `Container.database_ok()`, nên interface không chạm thẳng vào storage); quy tắc "chỉ thêm" chỉ kiểm ở mức test.
- **config**: thêm `version`, kiểm tra hợp lệ của `trusted_proxy`.
- **domain, application, pipeline, providers**: không đổi.

Phần còn lại là hạ tầng: Dockerfile, entrypoint, `deploy/`, CI.

## Goals / Non-Goals

**Goals:**
- Một image duy nhất, dựng trên CI, chạy trên VPS chỉ với `compose.yaml` và `.env`.
- Rollback image chạy được mà không phải đụng tới database.
- Mọi bước kiểm tra local hiện có (theo CLAUDE.md) đều chạy được trên CI.

**Non-Goals:**
- Dựng Traefik/Postgres, tự động deploy, nhiều bản sao: xem proposal "Ngoài phạm vi".
- Zero-downtime khi cập nhật. Mô hình một container, một worker chấp nhận gián đoạn ngắn (mục tiêu dưới 20 giây, xem D4 và D5) khi `up -d` tạo lại container.

## Decisions

### D1. Một workflow `ci.yml`, ba job nối tiếp
- **`checks`**:
  - Service `postgres:16` tạo hai database: `nt_test` cho pytest và `nt_e2e_test` cho Playwright (tên đều kết thúc `_test`, đúng yêu cầu của `conftest.py` và `e2e/server.py`).
  - Chạy `uv venv .venv && uv pip install -e ".[dev,all]"` ở gốc repo, giống CLAUDE.md. Venv phải nằm đúng `.venv` vì `web/playwright.config.ts` gọi `.venv/bin/python web/e2e/server.py`. Sau đó chạy `.venv/bin/ruff check src tests` và `.venv/bin/pytest -q`.
  - Chạy `npm ci`, `npm run check`, `npm run check:contrast`, `npm run build`, rồi Playwright (chromium, `npx playwright install --with-deps chromium`) với `NT_TEST_DATABASE_URL` trỏ tới `nt_e2e_test`.
  - Chạy `shellcheck` cho `deploy/*.sh` và `docker/*.sh`.
- **`image`** (`needs: checks`):
  - `docker/metadata-action` sinh tag theo luật của spec. Mỗi lần chạy chỉ một nhóm tag được bật:
    - nhánh mặc định: `type=sha,prefix=sha-,format=short,enable={{is_default_branch}}` và `type=raw,value=latest,enable={{is_default_branch}}`;
    - tag phát hành: `type=semver,pattern=v{{version}}`;
    - `flavor: latest=false`, để metadata-action không tự gắn `latest` cho tag semver (mặc định `latest=auto` sẽ làm việc đó);
    - PR: tag tạm `pr-<số>`, chỉ dùng trong job và không bao giờ push.

    Nhờ vậy tag `v1.4.0` không push lại `sha-…` (image `sha-…` đã có từ lần merge, và báo version `sha-…`), và cũng không dời `latest`.
  - **Build đúng một lần.** `docker/build-push-action` build `linux/amd64` với `load: true`, `push: false`, cache `type=gha`, gắn đủ tag từ metadata, và truyền `--build-arg NT_VERSION=<tag hoặc sha-xxx>`.
  - `aquasecurity/trivy-action` quét đúng image đã load, với `severity: HIGH,CRITICAL`, `ignore-unfixed: true`, `exit-code: 1`.
  - **Push đúng image đã quét.** Lệnh `docker push --all-tags ghcr.io/<owner>/<repo>` chỉ chạy khi `github.event_name == 'push'` và (`ref` là nhánh mặc định hoặc khớp `refs/tags/v*.*.*`). Không gọi `build-push-action` lần thứ hai, vì build lại có thể cho ra digest khác với image vừa quét.
  - Đăng nhập GHCR bằng `GITHUB_TOKEN` với `permissions: packages: write`. Các job còn lại chỉ có `contents: read`.
- **Trigger**:
  - `pull_request`;
  - `push` vào `main`;
  - `push` tag `v*.*.*`. Tag dạng khác không kích hoạt workflow, nên không push gì.
- **Tag phải nằm trên `main`.** Với sự kiện tag, job `image` có một bước kiểm tra: checkout với `fetch-depth: 0`, rồi `git merge-base --is-ancestor "$GITHUB_SHA" origin/main`. Nếu commit không nằm trong lịch sử `main` thì job fail trước khi build, và không push gì. Như vậy chỉ code đã qua PR và review mới phát hành được.

*Phương án đã cân nhắc:*
- Tách workflow PR và release: phải lặp lại cấu hình, dễ lệch nhau.
- Quét sau khi push: vi phạm yêu cầu "quét trước khi đẩy".
- Build lần hai với `push: true` (dựa vào cache): digest có thể khác image đã quét, vì metadata và timestamp của image config có thể đổi.
- Tag phát hành vẫn push thêm `sha-…`: cùng một tag sha sẽ trỏ tới hai image báo hai version khác nhau.

Tên nhánh mặc định của repo là `main`. Yêu cầu ban đầu ghi `master`, nhưng điều kiện `{{is_default_branch}}` nên đúng với cả hai.

### D2. Phiên bản trong image
- `ARG NT_VERSION=dev`, sau đó `ENV NT_VERSION=$NT_VERSION`, cùng label `org.opencontainers.image.version` và `.revision`.
- `Settings.version: str = "dev"` đọc từ `NT_VERSION`.
- Không sửa `pyproject.toml`, vì đồng bộ version nằm ngoài phạm vi.

### D3. Entrypoint: `novel migrate` rồi `exec` server
- `docker/entrypoint.sh` (POSIX sh, `set -eu`):
  ```
  if [ "${1:-}" = "uvicorn" ]; then
      novel migrate
  fi
  exec "$@"
  ```
- Chỉ migrate khi lệnh là server mặc định (`uvicorn`, tức `CMD` của image). Các lệnh chạy một lần như `docker run --rm -it <image> novel hash-password` chạy thẳng, không cần DB. Lệnh nào cần DB (`novel list`, `novel migrate`…) thì tự mở DB như khi chạy ngoài container. `docker compose exec` không đi qua entrypoint nên không bị ảnh hưởng.
- Dockerfile:
  ```
  ENTRYPOINT ["/app/docker/entrypoint.sh"]
  CMD ["uvicorn", ..., "--workers", "1"]
  ```
- `exec` giúp uvicorn nhận SIGTERM trực tiếp.
- Migrate lỗi thì `set -e` làm container thoát, và `restart: unless-stopped` sẽ thử lại. Log ghi tên migration lỗi.
- `novel migrate` (CLI) chỉ mở pool và gọi `migrate()`. Lệnh này **không** dùng `build_container()`, vì hàm đó kéo theo provider và auth, trong khi spec yêu cầu `migrate` không cần LLM key hay mật khẩu.
- `build_container()` vẫn gọi `migrate()` khi khởi động (lúc đó là no-op, chỉ tốn một vòng lock và select). Nhờ vậy dev chạy `novel serve` và pytest không đổi gì.

*Phương án đã cân nhắc:*
- Bỏ migrate khỏi `build_container`: phá luồng dev và test, mà không được thêm gì.
- Luôn migrate với mọi lệnh: `docker run <image> novel hash-password` (bước tạo mật khẩu trong docs) sẽ đòi DB và hỏng.
- Service `migrate` riêng trong compose (one-shot với `depends_on: service_completed_successfully`): thêm thành phần, và yêu cầu nói rõ "entrypoint chạy migration".

### D4. Health: `/api/health` kiểm tra DB, `/health` là bí danh
- Một hàm xử lý gắn vào hai đường dẫn. Hàm chạy `SELECT 1` qua pool với timeout ngắn (lấy connection tối đa 2 giây).
- Thành công trả 200 `{"status":"ok"}`. Có exception thì trả 503 `{"status":"unavailable"}`, không lộ chi tiết lỗi.
- Chỉ thêm trường `version` khi request có session hợp lệ. Handler tự kiểm tra cookie (endpoint là public nên middleware không chặn) bằng chính hàm xác thực session của `auth`. Người lạ không biết app đang chạy bản nào, nên khó dò lỗ hổng theo phiên bản.
- Lúc khởi động (lifespan), app ghi một dòng log `Novel Translator <version>`. Admin kiểm tra bản đang chạy bằng `docker compose logs app`, hoặc `docker inspect` xem label `org.opencontainers.image.version`, mà không cần đăng nhập.
- Thêm `/api/health` vào `PUBLIC_PATHS`.
- `HEALTHCHECK` gọi `http://127.0.0.1:8000/api/health` bằng Python stdlib như hiện tại (image không có curl). Tham số: `--interval=30s --timeout=5s --start-period=60s --start-interval=2s --retries=3`.
  - Traefik (Docker provider) bỏ qua container chưa `healthy`.
  - Không có `--start-interval`, Docker chỉ kiểm tra lần đầu sau `interval` (30 giây), nên site trả 404 ít nhất chừng đó sau mỗi lần `up -d`.
  - Với `--start-interval=2s`, container được đánh dấu healthy khoảng 2 giây sau khi uvicorn sẵn sàng.
  - Cần Docker Engine 25+ (Compose 2.20+ nếu khai báo trong compose). Docs ghi yêu cầu này; bản Docker cũ bỏ qua tham số và quay về chờ 30 giây.
- Nếu container đã chết vì cấu hình sai thì không có health để gọi; trường hợp này để Docker xử lý.

*Phương án đã cân nhắc:* đổi hẳn `/health` thành `/api/health`. Cách đó phải sửa Playwright, test và docs, mà bí danh thì rẻ.

### D5. Container cứng hoá: khai báo trong compose, image hỗ trợ
`deploy/compose.yaml`:
- `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `user: "10001:10001"`;
- `tmpfs: ["/tmp:size=128m,mode=1777"]`, `restart: unless-stopped`, `stop_grace_period: 15s`;
- `CMD` của uvicorn thêm `--timeout-graceful-shutdown 10`. Kết nối SSE không bao giờ tự đóng, nên nếu không giới hạn, uvicorn sẽ chờ chúng cho tới khi hết `stop_grace_period` rồi mới bị kill. Với 10 giây, request thường kịp xong, còn SSE bị cắt. Trang đọc báo "Mất kết nối tới máy chủ." (`web/src/lib/reader/stream.ts`): EventSource gặp phản hồi 404/502 trong lúc restart thì đóng hẳn, và job dịch trong bộ nhớ cũng đã mất. Người đọc mở lại chương thì app dịch lại. Change này không thêm cơ chế tự kết nối lại. Tổng gián đoạn khi cập nhật: dừng tối đa khoảng 10 giây, cộng migrate, uvicorn khởi động và lần kiểm tra health đầu (khoảng 2 giây).
- không có `ports`, không có `volumes`.

Lý do và ràng buộc:
- `tmpfs` không phải volume (nằm trong RAM, mất khi dừng container). Nó cần cho file đệm multipart. 128 MB đủ cho một upload 50 MB cộng ảnh bìa.
- Python trong image không ghi `.pyc` vì đã có `PYTHONDONTWRITEBYTECODE=1`. Cần xác minh rằng uvicorn, Pillow và psycopg không ghi vào `$HOME` hay thư mục cài đặt khi rootfs là read-only. Task 3.4 kiểm tra việc này bằng `docker run --read-only`.

*Phương án đã cân nhắc:*
- Ép Starlette giữ file trong RAM: phải sửa sâu vào framework.
- Giảm giới hạn upload: đổi hành vi người dùng.

### D6. Định tuyến Traefik bằng label
```
traefik.enable=true
traefik.docker.network=${TRAEFIK_NETWORK:-traefik}   # app có 2 network, phải chỉ rõ; trùng tên network ngoài
traefik.http.routers.${APP_NAME}.rule=Host(`${APP_HOST}`)
traefik.http.routers.${APP_NAME}.entrypoints=${TRAEFIK_ENTRYPOINT:-websecure}
traefik.http.routers.${APP_NAME}.tls.certresolver=${TRAEFIK_CERTRESOLVER:-letsencrypt}
traefik.http.services.${APP_NAME}.loadbalancer.server.port=8000
```
- `APP_NAME` mặc định `novel-translator`, đổi được khi cùng VPS chạy hai bản.
- Trong `compose.yaml`, label phải viết dạng danh sách `- key=value`: compose không thay biến trong khoá của mapping, nên dạng `key: value` sẽ để nguyên chuỗi `${APP_NAME…}` trong tên router.
- Network `traefik` và `postgres` được khai báo `external: true`. Tên thật đọc từ `TRAEFIK_NETWORK` và `POSTGRES_NETWORK`, mặc định đúng như tên trong yêu cầu. Label `traefik.docker.network` dùng cùng biến `TRAEFIK_NETWORK`. Nếu ghi cứng `traefik` thì khi đổi tên network, Traefik sẽ chọn sai IP của container và trả 502.
- **SSE**: Traefik v3 không buffer response theo mặc định, và tự flush với `text/event-stream`. App đã gửi keep-alive mỗi 15 giây, nên không vướng `idleTimeout` mặc định (180 giây). Docs ghi phần cấu hình mà hạ tầng cần có: entrypoint HTTPS, certresolver, không bật middleware buffering, và không đặt `respondingTimeouts.writeTimeout` ngắn trên entrypoint.
- **Upload 50 MB**: Traefik không giới hạn body theo mặc định. Docs nhắc rằng `respondingTimeouts.readTimeout` (mặc định 60 giây ở v3) phải đủ cho upload trên mạng chậm.

### D7. IP client: `NT_TRUSTED_PROXY` nhận CIDR
- Parse một lần thành `list[ip_network]` (`strict=False`). IP đơn được coi là `/32` hoặc `/128`.
- Có mục sai thì báo lỗi khi tạo Settings: dùng validator của pydantic, nêu rõ mục sai. App không khởi động.
- So khớp bằng `ip_address(peer) in net`. Peer không parse được (ví dụ `unknown`) thì không tin.
- **Khuyến nghị trong docs: tin đúng một IP.** Admin gán IP tĩnh cho Traefik trên network `traefik` (`ipv4_address` trong compose của Traefik, network có `ipam.config.subnet` cố định), rồi đặt `NT_TRUSTED_PROXY` bằng IP đó.
- Nếu không gán được IP tĩnh thì dùng phương án dự phòng: tin cả subnet của network `traefik` (docs có lệnh `docker network inspect` để lấy). Docs ghi rõ cái giá phải trả: mọi container khác trên network `traefik` (các app khác) cũng được tin, và có thể giả `X-Forwarded-For` để né việc chặn đăng nhập sai khi gọi thẳng vào app.
- Traefik mặc định ghi đè `X-Forwarded-For` từ client không tin cậy và nối IP client vào cuối, nên quy tắc "lấy hop cuối" vẫn đúng.

### D8. Kiểm tra "migration chỉ thêm" bằng test tĩnh
- `tests/test_migration_rules.py` duyệt mọi `migrations/*.sql`. Trước tiên bỏ comment `--` và `/* */`, rồi tìm (không phân biệt hoa thường):
  - `DROP TABLE|COLUMN|INDEX|CONSTRAINT|TYPE|SCHEMA|VIEW`;
  - `RENAME`, `ALTER COLUMN … TYPE`, `ALTER COLUMN … SET NOT NULL`, `TRUNCATE`, `DELETE FROM`;
  - `ADD COLUMN … NOT NULL` mà không có `DEFAULT` trong cùng mệnh đề;
  - `ALTER TABLE … ADD CONSTRAINT`, `ADD COLUMN … UNIQUE|CHECK|REFERENCES`, `CREATE UNIQUE INDEX` (thực chất là một ràng buộc unique) và `ALTER COLUMN … DROP DEFAULT`, trên bảng không được tạo trong cùng file. Constraint mới trên bảng đã có có thể làm bản cũ ghi lỗi, mà test tĩnh không biết dữ liệu hay code cũ có thỏa constraint đó hay không, nên cấm hẳn. Bảng mới thì bản cũ không dùng tới, nên được phép có mọi constraint. Test lấy danh sách bảng do file tạo bằng `CREATE TABLE`.
- Test báo tên file và câu vi phạm.
- `001` và `002` phải qua test (đã kiểm: cả hai chỉ thêm).
- **Quy ước cho code (không kiểm bằng test tĩnh):** code đọc cột do migration mới thêm phải chịu được `NULL`, kể cả cột có `DEFAULT`. Lý do: khi rollback, bản cũ vẫn ghi dòng mới vào bảng; cột nullable sẽ mang `NULL`, còn cột có `DEFAULT` mang giá trị mặc định chứ không phải giá trị mà logic bản mới sẽ tính. Khi nâng cấp lại, bản mới gặp các dòng đó. Muốn backfill thì làm trong code lúc đọc, hoặc bằng một migration `UPDATE … WHERE col IS NULL` (được phép vì chỉ điền giá trị, không xoá).
- Không có cơ chế "cho phép ngoại lệ". Khi thật sự cần, đó là một change riêng phải bàn trong design, kèm kế hoạch hai bước (expand, rồi contract sau khi không còn image cũ cần rollback).
- **Test khoá hành vi của migrator**: chèn `schema_migrations(version=999)` rồi gọi `migrate()`. Kết quả phải không lỗi, trả `[]`, và `current_version` bằng 999.

*Phương án đã cân nhắc:* parser SQL thật (sqlglot). Thêm phụ thuộc mà không đáng, vì file migration do chính repo viết và ngắn.

Schema DB của change này không đổi, nên không có dữ liệu cũ cần migrate.

### D9. Sao lưu: `deploy/backup.sh` chạy trên host
- **Gọi:** `backup.sh [/opt/novel-translator]`. Script đọc `.env` của thư mục app, chỉ lấy các khoá cần bằng `grep`/`sed` và không `source` cả file (tránh chạy nội dung `.env` như shell). Khi đọc, script lấy dòng cuối cùng của khoá, bỏ khoảng trắng hai đầu và bỏ một cặp nháy đơn hoặc nháy kép bao ngoài (giống cách compose đọc `.env`). Các khoá cần:
  - `NT_DATABASE_URL`;
  - `BACKUP_AGE_RECIPIENT`: một hoặc nhiều public key `age1…`, cách nhau bằng dấu phẩy. Mỗi key thành một cờ `-r` (ví dụ key của admin và key dự phòng cất offline);
  - `BACKUP_DIR` (mặc định `/var/backups/novel-translator`);
  - `POSTGRES_NETWORK`;
  - `BACKUP_PG_IMAGE` (mặc định `postgres:16`).
- **Dump:**
  ```
  docker run --rm --network "$POSTGRES_NETWORK" -e PGURL "$BACKUP_PG_IMAGE" sh -c 'pg_dump -Fc "$PGURL"' \
    | age "${recipient_args[@]}" > "$BACKUP_DIR/.<name>.tmp"   # mỗi key một -r
  ```
  - URL truyền qua biến môi trường, không đặt trên dòng lệnh, nên không lộ qua `ps` trên host.
  - Chỉ cần quyền của role app, không cần superuser hay tên container Postgres.
- **An toàn khi lỗi:** `set -euo pipefail`. Dump hoặc mã hoá lỗi thì xoá file `.tmp` (`trap`) và thoát với mã khác 0, không xoá bản cũ. Thành công thì `mv` sang `<prefix>-YYYYMMDD-HHMMSS.dump.age` (tính đến giây, theo UTC). Nếu tên đã tồn tại thì thoát lỗi chứ không ghi đè. Sau đó xoá các bản cũ hơn 14 bản mới nhất (`ls -1t` theo pattern của prefix). Như vậy không bao giờ có bản dump rõ trên đĩa.
- **Quyền:** `umask 077`, nên file chỉ chủ sở hữu đọc được.
- **Kiểm tra trước khi chạy:** thiếu `.env`, URL, recipient, hoặc không có lệnh `age`/`docker` thì báo lỗi và thoát trước khi dump.
- **Cron mẫu trong docs:** `15 3 * * * /opt/novel-translator/backup.sh /opt/novel-translator >> /var/log/novel-translator-backup.log 2>&1`. Script được chép vào thư mục app cạnh compose, coi là công cụ vận hành chứ không phải cấu hình app.
- **User chạy cron:** đặt trong crontab của chính user sở hữu `/opt/novel-translator/.env` (mode 600) và đọc được socket Docker. Thường là `root` (`/etc/cron.d/novel-translator` với cột user `root`), hoặc user deploy thuộc nhóm `docker`. Docs ghi rõ: nhóm `docker` tương đương quyền root, và `BACKUP_DIR` phải thuộc cùng user đó với mode 700.
- **Test:** `tests/test_backup_script.py` chạy script với `docker` và `age` giả (stub trong `PATH` tạm) để kiểm tra:
  - lỗi cấu hình;
  - không xoá bản cũ khi dump lỗi;
  - giữ đúng 14 bản;
  - không còn file `.tmp`.

  Không cần Docker thật. Thêm `shellcheck` trên CI.

*Phương án đã cân nhắc:*
- `docker exec <postgres-container> pg_dump`: phụ thuộc tên container của admin.
- Cài `postgresql-client-16` trên host: thêm việc cài đặt, và phiên bản dễ lệch so với server.

### D10. Mẫu `deploy/` và docs
- `deploy/compose.yaml` và `deploy/.env.example` liệt kê đủ biến:
  - `IMAGE_REPO`, `IMAGE_TAG` (bắt buộc), `APP_HOST` (bắt buộc), `APP_NAME`;
  - `TRAEFIK_*`, `*_NETWORK`;
  - `NT_DATABASE_URL`, `NT_PASSWORD_HASH`, `GEMINI_API_KEY`, `NT_TRUSTED_PROXY`, `NT_CHAIN`…;
  - `BACKUP_*`.
- Image là `${IMAGE_REPO:-ghcr.io/rohanhn/ai_novel_translator}:${IMAGE_TAG:?…}`, nên fork hoặc đổi tên repo không phải sửa compose. Tên GHCR phải viết thường; CI tự hạ chữ bằng metadata-action, còn `.env.example` ghi chú điều này cho `IMAGE_REPO`.
- Nếu package GHCR để private, VPS cần `docker login ghcr.io` bằng PAT `read:packages`. Docs ghi cả hai trường hợp.
- Viết lại `docs/DEPLOY.md`:
  - yêu cầu đối với hạ tầng;
  - tạo role và DB;
  - chuẩn bị `/opt/novel-translator` với chmod 600;
  - cách lấy subnet của network traefik;
  - cập nhật và rollback;
  - sao lưu, khôi phục, phát hành bằng git tag;
  - quy tắc migration chỉ thêm.
- `docker-compose.yml` ở gốc giữ lại để build và chạy thử local: đổi health, thêm `read_only` và `tmpfs` để môi trường local giống production. Đầu file ghi rõ: không dùng trên VPS.

## Risks / Trade-offs

- **[Read-only rootfs làm vỡ thư viện ghi file ngầm]** (cache của Pillow, `$HOME` của psycopg/pgpass…) → Task 3.4 chạy image với `--read-only --tmpfs /tmp --cap-drop ALL`, rồi thử login, upload TXT 50 MB, upload bìa và dịch qua `echo`. Gặp lỗi thì đặt `HOME=/tmp` trong image.
- **[Tin cả subnet `traefik` cho phép container khác giả IP client]** → Docs khuyên gán IP tĩnh cho Traefik và chỉ tin IP đó; CIDR chỉ là phương án dự phòng, có ghi rõ rủi ro. Để giả được IP, kẻ tấn công phải chiếm được một container khác trên cùng VPS, và mật khẩu argon2 vẫn là lớp bảo vệ chính.
- **[Trivy chặn release vì CVE của base image vừa công bố]** → Chỉ chặn khi đã có bản vá (`ignore-unfixed`), nên build lại thường là đủ. Có thể thêm `.trivyignore` kèm lý do và ngày hết hạn, qua review PR.
- **[Trivy lỗi `TOOMANYREQUESTS` khi tải DB lỗ hổng từ GHCR]** (lỗi hay gặp trên runner dùng chung) → Đặt `TRIVY_DB_REPOSITORY=public.ecr.aws/aquasecurity/trivy-db` và `TRIVY_JAVA_DB_REPOSITORY=public.ecr.aws/aquasecurity/trivy-java-db` làm nguồn chính, giữ GHCR làm dự phòng; cache thư mục DB của Trivy (`actions/cache`, khoá theo ngày) để mỗi ngày chỉ tải một lần.
- **[Quy tắc "chỉ thêm" làm schema phình dần]** → Chấp nhận. Muốn dọn thì làm change riêng theo kiểu expand/contract, sau khi chắc chắn không còn rollback về bản cũ.
- **[Rollback rồi nâng cấp lại: bản mới gặp dòng do bản cũ ghi, có `NULL` hoặc giá trị mặc định ở cột mới]** → Quy ước trong D8: code phải chịu được `NULL` ở cột mới; ghi vào docs/DEPLOY.md (phần quy tắc migration) và ARCHITECTURE.md. Review PR có migration phải kiểm điểm này.
- **[Image cũ chạy trên schema mới vẫn có thể lỗi về logic]** (ví dụ bản mới ghi dữ liệu theo cách bản cũ không hiểu) → Quy tắc chỉ thêm bảo vệ phần schema. Docs vẫn khuyên chạy backup thủ công trước mỗi lần cập nhật, để còn đường lui cho trường hợp hiếm.
- **[Gián đoạn khi `up -d` (dưới 20 giây), SSE đang mở bị cắt, và chương đang dịch trở về "Chưa dịch"]** → Chấp nhận (mô hình một worker). `--start-interval` và `--timeout-graceful-shutdown` giữ gián đoạn ngắn. Docs ghi rõ, và khuyên cập nhật vào giờ ít đọc.
- **[CI chậm vì Playwright + build image]** → Dùng cache cho `uv`, npm, Playwright browser và GHA Docker cache. Chỉ cài chromium.
- **[Rò rỉ bí mật qua log CI]** → CI không cần bí mật nào ngoài `GITHUB_TOKEN`. Mật khẩu Postgres của service CI chỉ dùng trong job.
- **[`age` recipient sai làm mọi bản sao lưu không giải mã được]** → Docs có bước tập khôi phục ngay sau khi cài: giải mã trên máy giữ private key, rồi `pg_restore --list`.

## Migration Plan

1. Merge change, rồi gắn tag `v0.2.0` (hoặc số tiếp theo). CI đẩy image lên GHCR.
2. Trên VPS, bảo đảm hạ tầng có network `traefik` và `postgres`, Postgres 16 với role và DB của app (đã có sẵn từ trước).
3. Chạy backup thủ công từ mô hình cũ (lệnh `pg_dump` trong DEPLOY.md cũ).
4. Tạo `/opt/novel-translator/` với `compose.yaml` và `.env` (chép giá trị từ `.env` cũ, đổi tên biến theo bảng ánh xạ trong docs), `chmod 600 .env`. Nếu cần thì `docker login ghcr.io`.
5. Dừng container cũ (`docker compose down` ở thư mục cũ), bỏ cấu hình Nginx/Caddy của subdomain, rồi `docker compose pull && docker compose up -d` ở thư mục mới. Kiểm tra `docker compose ps` báo healthy, `https://<APP_HOST>/api/health` trả `ok`, và `docker compose logs app` ghi đúng version.
6. Cài cron backup, chạy thử một lần, tập khôi phục.

**Rollback của chính việc chuyển đổi:** dừng compose mới, bật lại compose cũ và proxy cũ. DB không đổi schema nên không cần khôi phục.
