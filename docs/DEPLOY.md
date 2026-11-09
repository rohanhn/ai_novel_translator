# Triển khai Novel Translator

App chạy trong **một container** (web app + API) và dùng PostgreSQL 16 có sẵn trong container
`shared-postgres`. Postgres này dùng chung với các app khác, trên cả máy dev lẫn VPS. Mọi dữ liệu
nằm trong database của app nên container không cần volume.

```
Trình duyệt ──HTTPS──▶ Nginx/Caddy (subdomain) ──▶ 127.0.0.1:8000 ──▶ container app
                                                                       │ (Docker network của shared-postgres)
                                                                       ▼
                                                              shared-postgres:5432 / ai_novel_translator
```

> **Chỉ chạy MỘT worker.** Job dịch, hàng đợi và luồng SSE nằm trong bộ nhớ của process.
> Image đã cố định `uvicorn --workers 1`; đừng tăng số worker hay chạy nhiều bản sao container.

## 1. Tạo role và database (thủ công, một lần)

App không tự tạo role hay database. Mở `psql` bằng tài khoản quản trị của `shared-postgres`
(thay `postgres` bằng superuser thật của instance):

```bash
docker exec -it shared-postgres psql -U postgres
```

```sql
-- Mật khẩu mạnh, tạo bằng: openssl rand -base64 24 | tr -d '/+='
CREATE ROLE ai_novel_translator LOGIN PASSWORD '<mat-khau-db>';
CREATE DATABASE ai_novel_translator OWNER ai_novel_translator;
REVOKE ALL ON DATABASE ai_novel_translator FROM PUBLIC;

-- Chỉ trên máy dev: database riêng cho pytest và e2e (bị xóa dữ liệu khi chạy test).
CREATE DATABASE ai_novel_translator_test OWNER ai_novel_translator;
REVOKE ALL ON DATABASE ai_novel_translator_test FROM PUBLIC;
```

Role chỉ có quyền trên database của mình. Bảng do app tạo khi khởi động lần đầu (migration runner
áp dụng `001_initial.sql`). Dữ liệu SQLite của bản v0.1 không được chuyển sang.

## 2. Build image

```bash
docker build -t novel-translator:$(git rev-parse --short HEAD) -t novel-translator:latest .
```

Image gồm hai bước: Node 22 build `web/` thành file tĩnh, rồi Python 3.14 slim cài app và chép
bản build vào. Cần thêm provider Anthropic/OpenAI thì build với `--build-arg EXTRAS=all`.

Luôn gắn tag theo commit như trên. Bước rollback (mục 7) cần image cũ còn trên máy.

## 3. Tạo hash mật khẩu đăng nhập

App có một chủ sở hữu, đăng nhập bằng mật khẩu. Env chỉ chứa hash argon2, không chứa mật khẩu gốc:

```bash
docker run --rm -it novel-translator:latest novel hash-password
# hoặc trên máy dev: .venv/bin/novel hash-password
```

Mật khẩu cần ít nhất 8 ký tự. Chép dòng `$argon2id$...` vào `.env` và giữ **dấu nháy đơn**, vì
hash chứa ký tự `$`.

## 4. Tìm Docker network của `shared-postgres`

Container app phải vào cùng network với `shared-postgres` để gọi được hostname `shared-postgres`:

```bash
docker inspect shared-postgres --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{$v.Aliases}}{{"\n"}}{{end}}'
# ví dụ: shared-dev-db_default [shared-postgres postgres]
```

Cột đầu là tên network (đặt vào `NT_DB_NETWORK`). Các alias là hostname dùng được (đặt vào
`NT_DB_HOST`, mặc định `shared-postgres`). Network này do compose của `shared-postgres` tạo ra.
Compose của app khai báo nó là `external`, nên không tạo mới và cũng không xóa nó.

## 5. Biến môi trường

Tạo `.env` cạnh `docker-compose.yml` (xem mẫu ở `.env.example`). Compose dùng file này cho hai
việc: thay các `${...}` trong compose, và nạp biến vào container.

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `NT_DB_NETWORK` | có | Tên Docker network của `shared-postgres` (mục 4) |
| `NT_DB_PASSWORD` | có | Mật khẩu role `ai_novel_translator`. Nếu có ký tự `@ : / ? # %` thì phải URL-encode |
| `NT_DB_HOST`, `NT_DB_PORT`, `NT_DB_USER`, `NT_DB_NAME` | không | Mặc định `shared-postgres`, `5432`, `ai_novel_translator`, `ai_novel_translator` |
| `NT_PASSWORD_HASH` | có | Hash argon2 tạo ở mục 3, trong dấu nháy đơn |
| `GEMINI_API_KEY` | có | Key Gemini (https://aistudio.google.com/apikey) |
| `NT_CHAIN` | không | Chuỗi model, mặc định `gemini:gemini-3.5-flash,gemini:gemini-3.5-flash-lite` |
| `NT_TRUSTED_PROXY` | nên đặt | IP mà reverse proxy dùng khi kết nối tới app (mục 6). Thiếu biến này thì việc chặn đăng nhập sai sẽ tính theo IP của proxy |
| `NT_COOKIE_SECURE` | không | Mặc định `true`. Chỉ đặt `false` khi thử qua `http://localhost` |
| `NT_BIND` | không | Địa chỉ publish trên host, mặc định `127.0.0.1:8000` (chỉ reverse proxy truy cập được) |
| `NT_IMAGE_TAG` | không | Tag image cần chạy, mặc định `latest` |
| `NT_GEMINI_TIMEOUT`, `NT_DB_POOL_MAX`, `NT_CHAPTER_CHAR_LIMIT` | không | Mặc định 120 giây, 5 kết nối, 20000 ký tự |

Không đặt `NT_PROVIDER`/`NT_MODEL` trên server: hai biến này bỏ qua chuỗi model và chỉ dùng cho
dev. Compose tự ghép `NT_DATABASE_URL` từ các biến `NT_DB_*`, ghi đè giá trị `localhost` dùng khi
dev ngoài Docker.

Khởi động và kiểm tra:

```bash
docker compose up -d
docker compose ps                    # STATUS phải là "healthy"
curl -s http://127.0.0.1:8000/health # {"status":"ok"}
docker compose logs -f app
```

Lỗi khởi động thường gặp:
- `docker compose up` báo `required variable ... is missing` → thiếu biến bắt buộc trong `.env`.
- Hash sai định dạng → app không khởi động, container khởi động lại liên tục, log ghi rõ nguyên nhân.
- Sai network → `could not translate host name "shared-postgres"`.
- Sai mật khẩu DB → `password authentication failed`.

## 6. Reverse proxy cho subdomain

Proxy chạy trên host, chuyển tiếp tới `127.0.0.1:8000`. Luồng dịch trực tiếp là SSE tại
`/api/novels/{id}/chapters/{n}/stream`. Đường này **phải tắt buffering** và cần timeout đọc dài,
nếu không bản dịch sẽ hiện ra một cục khi dịch xong. App đã gửi sẵn `X-Accel-Buffering: no` và
nhịp keep-alive mỗi 15 giây.

`NT_TRUSTED_PROXY` là IP mà app nhìn thấy khi proxy kết nối tới. Với cổng publish của Docker, đó
thường là gateway của network:

```bash
docker network inspect "$NT_DB_NETWORK" --format '{{(index .IPAM.Config 0).Gateway}}'
# ví dụ 172.21.0.1. Kiểm tra lại bằng `docker compose logs app`: IP đứng trước "GET /health"
```

App chỉ đọc `X-Forwarded-For` khi kết nối đến từ IP này, và lấy địa chỉ **cuối cùng** trong
header. Vì vậy proxy phải nối IP client vào cuối header (hai mẫu dưới đây đều làm vậy).

### Nginx

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name truyen.example.com;
    ssl_certificate     /etc/letsencrypt/live/truyen.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/truyen.example.com/privkey.pem;

    client_max_body_size 51m;   # upload truyện tối đa 50 MB

    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # SSE: tắt buffering, giữ kết nối lâu
    location ~ ^/api/novels/[0-9]+/chapters/[0-9]+/stream$ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
    }
}

server {
    listen 80;
    server_name truyen.example.com;
    return 301 https://$host$request_uri;
}
```

### Caddy

Caddy tự lấy chứng chỉ HTTPS và tự chuyển hướng từ HTTP.

```caddy
truyen.example.com {
    request_body {
        max_size 51MB
    }

    # SSE: đẩy từng mẩu ngay, không gom
    @stream path_regexp ^/api/novels/[0-9]+/chapters/[0-9]+/stream$
    handle @stream {
        reverse_proxy 127.0.0.1:8000 {
            flush_interval -1
        }
    }

    handle {
        reverse_proxy 127.0.0.1:8000
    }
}
```

Kiểm tra SSE qua proxy: đăng nhập, mở một chương chưa dịch, và xem chữ hiện dần từng đoạn. Có
thể đo bằng `curl -N -b 'nt_session=...' https://truyen.example.com/api/novels/1/chapters/2/stream`;
các dòng `event:` phải in ra ngay khi có, không dồn về cuối.

## 7. Sao lưu và rollback

Chỉ sao lưu database của app, ở định dạng custom của `pg_dump` (nén, khôi phục chọn lọc được):

```bash
mkdir -p ~/backups/novel-translator
docker exec shared-postgres pg_dump -U ai_novel_translator -Fc ai_novel_translator \
  > ~/backups/novel-translator/nt-$(date +%F-%H%M).dump
# Kiểm tra file đọc được (host thường không có pg_restore, dùng bản trong container):
docker exec -i shared-postgres pg_restore --list < "$(ls -t ~/backups/novel-translator/*.dump | head -1)" | head
```

Chạy định kỳ bằng cron, ví dụ 3 giờ sáng mỗi ngày và giữ 14 bản:

```cron
0 3 * * * docker exec shared-postgres pg_dump -U ai_novel_translator -Fc ai_novel_translator > $HOME/backups/novel-translator/nt-$(date +\%F).dump && find $HOME/backups/novel-translator -name 'nt-*.dump' -mtime +14 -delete
```

Luôn sao lưu ngay **trước khi** cập nhật image, vì bản mới có thể có migration.

**Rollback** về bản trước:

```bash
docker compose down                                   # 1. dừng bản mới
docker exec -i shared-postgres pg_restore -U ai_novel_translator -d ai_novel_translator \
  --clean --if-exists --no-owner --single-transaction \
  < ~/backups/novel-translator/nt-<thời-điểm-trước-khi-cập-nhật>.dump   # 2. khôi phục dữ liệu
NT_IMAGE_TAG=<tag-cũ> docker compose up -d            # 3. chạy lại image cũ
```

`--clean --if-exists` xóa rồi tạo lại các bảng của app từ bản sao lưu, kể cả `schema_migrations`.
Nhờ vậy image cũ không thấy migration lạ. `--single-transaction` bảo đảm lỗi giữa chừng không để
lại database dở dang.

## 8. Cập nhật phiên bản

```bash
git pull
docker exec shared-postgres pg_dump -U ai_novel_translator -Fc ai_novel_translator \
  > ~/backups/novel-translator/nt-truoc-cap-nhat-$(date +%F-%H%M).dump
docker build -t novel-translator:$(git rev-parse --short HEAD) -t novel-translator:latest .
docker compose up -d     # tạo lại container; migration tự chạy khi khởi động
docker compose ps        # chờ "healthy"
```

Khi container khởi động lại, các chương đang dịch dở trở về trạng thái "Chưa dịch". Người đọc
mở lại chương đó là app dịch lại.
