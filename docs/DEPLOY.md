# Triển khai Novel Translator

Mô hình **"CI build, VPS chỉ chạy"**: GitHub Actions kiểm tra, build image, quét Trivy rồi đẩy lên
GHCR. VPS không build gì. Thư mục `/opt/novel-translator` chỉ có `compose.yaml`, `.env` và
`backup.sh`; image được ghim theo tag phát hành.

```
Trình duyệt ──HTTPS──▶ Traefik v3 (dùng chung, publish 80/443)
                          │ network `traefik`
                          ▼
                    container app (read-only, không port, không volume)
                          │ network `postgres`
                          ▼
                    Postgres 16 (dùng chung) / database ai_novel_translator
```

> **Chỉ chạy MỘT worker, một container.** Job dịch, hàng đợi và luồng SSE nằm trong bộ nhớ của
> process. Image đã cố định `uvicorn --workers 1`; đừng tăng số worker hay scale container.

Repo này chỉ lo phần của app. Traefik, Postgres, hai network, việc chép bản sao lưu ra ngoài VPS
và giữ private key là việc của admin hạ tầng.

## 1. Yêu cầu đối với hạ tầng

- **Docker Engine 25+ và Compose 2.20+.** Bản cũ bỏ qua `--start-interval` của HEALTHCHECK, nên
  sau mỗi lần cập nhật site sẽ trả 404 khoảng 30 giây.
- **Hai Docker network ngoài**, mặc định tên `traefik` và `postgres` (đổi được bằng
  `TRAEFIK_NETWORK`, `POSTGRES_NETWORK`). App nối vào cả hai.
- **Traefik v3** trên network `traefik`, là container duy nhất publish 80/443:
  - provider Docker với `exposedByDefault=false` (app tự bật bằng label `traefik.enable=true`);
  - entrypoint HTTPS (mặc định tên `websecure`) và certresolver Let's Encrypt (mặc định tên
    `letsencrypt`); tên khác thì đặt `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER`;
  - **không** gắn middleware `buffering` cho router của app, và không đặt
    `respondingTimeouts.writeTimeout` ngắn trên entrypoint. Luồng dịch là SSE, phải được đẩy
    ngay từng mẩu. Traefik v3 mặc định không buffer, và app gửi keep-alive mỗi 15 giây nên
    không vướng `idleTimeout` (mặc định 180 giây);
  - `respondingTimeouts.readTimeout` (mặc định 60 giây) phải đủ để upload một file TXT tới 50 MB
    trên mạng chậm, ví dụ `300s`. Traefik không giới hạn kích thước body theo mặc định.
- **Postgres 16** trên network `postgres`, mỗi app một role và database riêng (mục 2). Không
  publish port.
- **`age`** trên host để sao lưu: `sudo apt install age`.

## 2. Tạo role và database (thủ công, một lần)

App không tự tạo role hay database. Mở `psql` bằng tài khoản quản trị của Postgres dùng chung
(thay `<postgres-container>` và `postgres` bằng tên container và superuser thật):

```bash
docker exec -it <postgres-container> psql -U postgres
```

```sql
-- Mật khẩu mạnh, tạo bằng: openssl rand -base64 24 | tr -d '/+='
CREATE ROLE ai_novel_translator LOGIN PASSWORD '<mat-khau-db>';
CREATE DATABASE ai_novel_translator OWNER ai_novel_translator;
REVOKE ALL ON DATABASE ai_novel_translator FROM PUBLIC;
```

Role chỉ có quyền trên database của mình. Bảng do app tạo: mỗi lần container khởi động,
entrypoint chạy `novel migrate` (giữ advisory lock, nên an toàn khi hai container chồng lên nhau
lúc cập nhật) rồi mới chạy server.

## 3. Chuẩn bị `/opt/novel-translator`

```bash
sudo mkdir -p /opt/novel-translator && cd /opt/novel-translator
# Lấy ba file từ repo, đúng tag sẽ chạy:
for f in compose.yaml .env.example backup.sh; do
  sudo curl -fsSLo "$f" "https://raw.githubusercontent.com/rohanhn/ai_novel_translator/v0.2.0/deploy/$f"
done
sudo mv .env.example .env
sudo chmod 600 .env && sudo chmod 755 backup.sh
sudoedit .env
```

Mọi bí mật chỉ nằm trong `.env`; `deploy/.env.example` liệt kê và giải thích từng biến. Tối
thiểu cần đặt:

| Biến | Ý nghĩa |
|---|---|
| `IMAGE_TAG` | Tag phát hành, ví dụ `v0.2.0` (mục 6). Thiếu thì compose từ chối chạy |
| `APP_HOST` | Tên miền của app, DNS trỏ về VPS. Thiếu thì compose từ chối chạy |
| `NT_DATABASE_URL` | `postgresql://ai_novel_translator:<mat-khau-db>@<postgres-host>:5432/ai_novel_translator`; host là tên/alias của container Postgres trên network `postgres`. URL-encode mật khẩu nếu có `@ : / ? # %`. Không đặt trong dấu nháy |
| `NT_PASSWORD_HASH` | Hash argon2 của mật khẩu đăng nhập web, **trong dấu nháy đơn** (hash có ký tự `$`) |
| `GEMINI_API_KEY` | Key Gemini (https://aistudio.google.com/apikey) |
| `NT_TRUSTED_PROXY` | IP (hoặc subnet) của Traefik, mục 4 |
| `BACKUP_AGE_RECIPIENT` | Public key age cho sao lưu, mục 8 |

Tạo hash mật khẩu (mật khẩu ít nhất 8 ký tự; lệnh này không cần database):

```bash
docker run --rm -it ghcr.io/rohanhn/ai_novel_translator:v0.2.0 novel hash-password
```

Không đặt `NT_PROVIDER`/`NT_MODEL` trên server: hai biến này bỏ qua chuỗi model, chỉ dùng cho
dev. Đừng đặt `NT_COOKIE_SECURE=false` (site chạy HTTPS).

**Package GHCR private?** Package public thì `docker compose pull` chạy ngay. Nếu để private, đăng
nhập một lần bằng PAT (classic) chỉ có quyền `read:packages`, dưới đúng user sẽ chạy
`docker compose`:

```bash
echo '<PAT>' | docker login ghcr.io -u <github-user> --password-stdin
```

## 4. `NT_TRUSTED_PROXY`: tin đúng Traefik

App chỉ đọc `X-Forwarded-For` (lấy địa chỉ **cuối cùng**) khi kết nối đến từ một địa chỉ trong
`NT_TRUSTED_PROXY`. Nhờ vậy việc chặn đăng nhập sai tính theo IP thật của người dùng. Biến nhận
danh sách IP và CIDR (IPv4/IPv6), cách nhau bằng dấu phẩy; mục sai thì app không khởi động và
log nêu rõ mục đó.

**Khuyến nghị: gán IP tĩnh cho Traefik rồi tin đúng IP đó.** Trong compose của hạ tầng:

```yaml
services:
  traefik:
    networks:
      traefik:
        ipv4_address: 172.30.0.2
networks:
  traefik:
    name: traefik
    ipam:
      config:
        - subnet: 172.30.0.0/24
```

```dotenv
NT_TRUSTED_PROXY=172.30.0.2
```

**Dự phòng (không gán được IP tĩnh): tin cả subnet của network `traefik`.**

```bash
docker network inspect traefik --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}'
# ví dụ 172.18.0.0/16  →  NT_TRUSTED_PROXY=172.18.0.0/16
```

Cái giá: **mọi container khác trên network `traefik`** (các app khác trên VPS) cũng được tin.
Một container bị chiếm có thể gọi thẳng vào app với `X-Forwarded-For` giả để né việc chặn đăng
nhập sai. Mật khẩu argon2 vẫn là lớp bảo vệ chính, nhưng chỉ dùng cách này khi không còn lựa
chọn.

Traefik mặc định ghi đè `X-Forwarded-For` từ client không tin cậy và nối IP client vào cuối,
nên quy tắc "lấy hop cuối" đúng với cấu hình mặc định.

## 5. Khởi động và kiểm tra

```bash
cd /opt/novel-translator
docker compose pull
docker compose up -d
docker compose ps                                   # STATUS phải là "healthy"
docker compose logs app | grep 'Novel Translator'   # dòng log có đúng version
curl -s https://truyen.example.com/api/health       # {"status":"ok"}
```

`/api/health` công khai và kiểm tra cả database: lỗi DB thì trả 503 `{"status":"unavailable"}`.
Trường `version` chỉ có khi đã đăng nhập. Admin xem version mà không cần đăng nhập bằng log như
trên, hoặc `docker inspect` label `org.opencontainers.image.version`.

Lỗi khởi động thường gặp (`docker compose logs app`):
- `required variable IMAGE_TAG/APP_HOST is missing` → thiếu biến trong `.env`.
- `network traefik declared as external, but could not be found` → hạ tầng chưa tạo network, hoặc
  tên khác (đặt `TRAEFIK_NETWORK`/`POSTGRES_NETWORK`).
- `Không kết nối được PostgreSQL` / `password authentication failed` → sai host hoặc mật khẩu
  trong `NT_DATABASE_URL`. Container thoát trước khi mở cổng và được khởi động lại liên tục.
- Hash hoặc `NT_TRUSTED_PROXY` sai định dạng → app không khởi động, log ghi rõ nguyên nhân.
- Site trả 404 trong khi container `healthy` → sai `APP_HOST`, hoặc tên entrypoint/certresolver
  không khớp cấu hình Traefik.

Kiểm tra SSE qua Traefik: đăng nhập, mở một chương chưa dịch, và xem chữ hiện dần từng đoạn.

## 6. Phát hành, cập nhật, rollback

**CI** (`.github/workflows/ci.yml`):
- PR: lint, test, e2e, build image và quét Trivy; **không push**.
- Merge vào `main`: thêm push `sha-<7 ký tự>` và `latest`.
- Git tag `vX.Y.Z` (phải trỏ vào commit đã nằm trên `main`): push đúng một tag `vX.Y.Z`; không dời
  `latest`.
- Trivy chặn release nếu image có lỗ hổng HIGH/CRITICAL **đã có bản vá**. Thường chỉ cần chạy lại
  CI để build lại trên base image mới.

**Phát hành** một bản:

```bash
git switch main && git pull
git tag -a v0.2.1 -m "v0.2.1"
git push origin v0.2.1     # chờ CI xanh, image có trên GHCR
```

**Cập nhật** trên VPS (nên làm vào giờ ít người đọc):

```bash
cd /opt/novel-translator
sudo ./backup.sh /opt/novel-translator    # bản sao lưu ngay trước khi cập nhật
sudoedit .env                             # IMAGE_TAG=v0.2.1
docker compose pull && docker compose up -d
docker compose ps                         # chờ "healthy"
```

Gián đoạn khoảng 15 giây: container cũ dừng trong tối đa 10 giây, container mới migrate rồi
healthy sau vài giây. Luồng dịch đang mở bị cắt, trang đọc báo "Mất kết nối tới máy chủ." và
chương đang dịch dở trở về "Chưa dịch". Mở lại chương là app dịch lại.

**Rollback**: đặt lại `IMAGE_TAG` cũ rồi `docker compose pull && docker compose up -d`. **Không
cần khôi phục database**, vì migration chỉ thêm (mục 7): image cũ chạy được trên schema mới và
bỏ qua các migration nó không biết.

## 7. Quy tắc migration: chỉ thêm

Mọi file trong `src/novel_translator/storage/migrations/` chỉ được **thêm**: bảng mới, cột mới
(nullable, hoặc `NOT NULL` kèm `DEFAULT`), index thường, `UPDATE` để điền dữ liệu, `DROP NOT
NULL`. Cấm xoá hay đổi tên bảng/cột, đổi kiểu, `SET NOT NULL`, `TRUNCATE`, `DELETE`, và thêm
constraint/unique index trên bảng đã có. `tests/test_migration_rules.py` kiểm tra tĩnh các luật
này trên CI.

**Quy ước cho code:** code đọc cột do migration mới thêm phải chịu được `NULL`, kể cả cột có
`DEFAULT`. Khi rollback, image cũ vẫn ghi dòng mới mà không biết cột đó; nâng cấp lại thì bản mới
gặp các dòng ấy. Review PR có migration phải kiểm điểm này.

Khi thật sự cần thay đổi phá vỡ (xoá, đổi tên), làm thành change riêng theo hai bước: expand (thêm
cái mới, code dùng cái mới), rồi contract (xoá cái cũ) sau khi chắc không còn rollback về bản cũ.

## 8. Sao lưu và khôi phục

`backup.sh` chạy `pg_dump --format=custom` trong image `postgres:16` trên network `postgres`,
bằng chính `NT_DATABASE_URL` của app (không cần superuser), rồi pipe thẳng vào `age`. Không có bản
rõ nào chạm đĩa. Thành công thì ghi `novel-translator-YYYYMMDD-HHMMSS.dump.age` (giờ UTC, không
ghi đè) và giữ 14 bản mới nhất. Lỗi thì xoá file tạm và không đụng các bản cũ.

**Tạo cặp key** trên máy của admin (không phải VPS):

```bash
age-keygen -o nt-backup.key    # private key: cất ngoài VPS (và một bản offline)
# dòng "Public key: age1..." → đặt vào .env
```

```dotenv
BACKUP_AGE_RECIPIENT=age1...admin,age1...du-phong   # nhiều key cách nhau bằng dấu phẩy
# BACKUP_DIR=/var/backups/novel-translator
# BACKUP_PG_IMAGE=postgres:16                       # cùng major với server Postgres
```

**Cài cron.** Script phải chạy dưới user sở hữu `.env` (mode 600) và dùng được Docker, thường là
`root`:

```bash
sudo install -d -m 700 -o root -g root /var/backups/novel-translator
echo '15 3 * * * root /opt/novel-translator/backup.sh /opt/novel-translator >> /var/log/novel-translator-backup.log 2>&1' \
  | sudo tee /etc/cron.d/novel-translator
sudo /opt/novel-translator/backup.sh /opt/novel-translator    # chạy thử ngay
```

Nếu dùng user deploy thay cho root: user đó phải thuộc nhóm `docker`, mà **nhóm `docker` tương
đương quyền root** trên host. `.env` và `BACKUP_DIR` (mode 700) phải thuộc cùng user đó.

Chép bản sao lưu ra ngoài VPS (rsync, object storage…) là việc của admin; file đã mã hoá nên chép
đi đâu cũng được.

**Tập khôi phục** ngay sau khi cài, và định kỳ: trên máy giữ private key, giải mã và đọc mục lục.

```bash
age -d -i nt-backup.key novel-translator-20261110-031500.dump.age \
  | docker run --rm -i postgres:16 pg_restore --list | head
```

Thấy danh sách bảng (`novels`, `chapters`, `schema_migrations`…) là key và bản sao lưu dùng được.

**Khôi phục thật** (ghi đè dữ liệu hiện tại của app): dừng app, giải mã trên máy admin và stream
qua SSH vào VPS, để bản rõ không nằm trên đĩa nào:

```bash
ssh admin@vps 'cd /opt/novel-translator && docker compose stop app'
age -d -i nt-backup.key novel-translator-20261110-031500.dump.age \
  | ssh admin@vps 'sudo docker run --rm -i --network postgres \
      --env-file /opt/novel-translator/.env postgres:16 \
      sh -c "exec pg_restore --clean --if-exists --no-owner --single-transaction -d \"\$NT_DATABASE_URL\""'
ssh admin@vps 'cd /opt/novel-translator && docker compose up -d'
```

`--clean --if-exists` xoá rồi tạo lại các bảng từ bản sao lưu, kể cả `schema_migrations`.
`--single-transaction` bảo đảm lỗi giữa chừng không để lại database dở dang. (`--env-file` của
`docker run` không bỏ dấu nháy, nên `NT_DATABASE_URL` trong `.env` phải không có nháy, như mẫu.)
Nếu bản sao lưu cũ hơn image đang chạy, entrypoint sẽ migrate lại khi `up -d`.

## 9. Chuyển từ mô hình cũ (build trên VPS + Nginx/Caddy)

| Mô hình cũ (`docker-compose.yml` ở gốc repo) | Mô hình mới (`/opt/novel-translator/.env`) |
|---|---|
| `NT_DB_NETWORK` | `POSTGRES_NETWORK` (network do hạ tầng tạo) |
| `NT_DB_PASSWORD`, `NT_DB_HOST`, `NT_DB_PORT`, `NT_DB_USER`, `NT_DB_NAME` | Ghép tay thành một `NT_DATABASE_URL` |
| `NT_IMAGE_TAG` (image build tại chỗ) | `IMAGE_TAG=vX.Y.Z` (image từ GHCR) |
| `NT_BIND` + cấu hình Nginx/Caddy | Bỏ; `APP_HOST` + label Traefik, không publish port |
| `NT_TRUSTED_PROXY` = gateway của network | `NT_TRUSTED_PROXY` = IP tĩnh hoặc subnet của Traefik (mục 4) |
| Cron `docker exec … pg_dump` (bản rõ) | `backup.sh` + `BACKUP_AGE_RECIPIENT` (mã hoá) |
| `NT_PASSWORD_HASH`, `GEMINI_API_KEY`, `NT_CHAIN`, `NT_GEMINI_TIMEOUT`, `NT_DB_POOL_MAX`, `NT_CHAPTER_CHAR_LIMIT` | Giữ nguyên |

Các bước:

1. Gắn tag phát hành (ví dụ `v0.2.0`) và chờ CI đẩy image lên GHCR.
2. Bảo đảm hạ tầng có network `traefik`, `postgres`, Traefik v3 và Postgres 16 (mục 1). Database
   và role của app giữ nguyên, chỉ cần container Postgres nằm trên network `postgres`.
3. Sao lưu thủ công lần cuối theo cách cũ:
   `docker exec <postgres-container> pg_dump -U ai_novel_translator -Fc ai_novel_translator > nt-truoc-chuyen.dump`.
4. Chuẩn bị `/opt/novel-translator` (mục 3), chép giá trị từ `.env` cũ theo bảng trên,
   `chmod 600 .env`, `docker login ghcr.io` nếu cần.
5. Dừng bản cũ (`docker compose down` ở thư mục cũ), bỏ cấu hình Nginx/Caddy của subdomain (để
   Traefik nhận 80/443), rồi `docker compose pull && docker compose up -d` ở thư mục mới và kiểm
   tra như mục 5.
6. Cài cron sao lưu, chạy thử một lần, tập khôi phục (mục 8). Xoá file dump bản rõ của bước 3 khi
   đã có bản mã hoá.

**Lùi lại việc chuyển đổi:** dừng compose mới, bật lại compose cũ và proxy cũ. Schema không đổi
nên không cần khôi phục database.

## 10. Chạy thử image trên máy dev

`docker-compose.yml` ở gốc repo **chỉ để build và chạy thử local**, không dùng trên VPS. Nó build
từ mã nguồn, publish `127.0.0.1:8000`, chạy với cùng hardening như production (rootfs read-only,
`cap_drop ALL`, user 10001, `/tmp` là tmpfs) và đọc `NT_DB_*` từ `.env` ở gốc (xem đầu file).

```bash
docker compose up -d --build
docker compose ps                        # healthy
curl -s http://127.0.0.1:8000/api/health
```
