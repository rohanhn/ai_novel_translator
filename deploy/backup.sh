#!/usr/bin/env bash
# Sao lưu database của app (spec database-backup, design D9). Chạy bằng cron hằng ngày:
#
#   15 3 * * * /opt/novel-translator/backup.sh /opt/novel-translator >> /var/log/novel-translator-backup.log 2>&1
#
# - pg_dump -Fc chạy trong image Postgres (BACKUP_PG_IMAGE) trên network POSTGRES_NETWORK, dùng
#   chính NT_DATABASE_URL của app: không cần superuser hay tên container Postgres.
# - Dump đi thẳng qua pipe vào `age` (mã hoá bằng public key), nên không có bản rõ nào chạm đĩa.
# - Lỗi ở bất kỳ bước nào: xoá file tạm, không đụng các bản cũ, thoát mã khác 0.
# - Thành công: <prefix>-YYYYMMDD-HHMMSS.dump.age (UTC), không ghi đè; giữ 14 bản mới nhất.
#
# Chỉ đọc vài khoá cần thiết từ .env (không `source`, để nội dung .env không bao giờ bị chạy
# như lệnh shell).
set -euo pipefail
umask 077

KEEP=14
APP_DIR="${1:-/opt/novel-translator}"
ENV_FILE="$APP_DIR/.env"

die() {
    echo "backup: $*" >&2
    exit 1
}

# Giá trị của khoá trong .env: dòng cuối cùng khớp, bỏ khoảng trắng hai đầu, bỏ một cặp nháy
# đơn/kép bao ngoài; giá trị không có nháy thì bỏ chú thích ` # ...` ở cuối.
env_get() {
    local key="$1" line value
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$ENV_FILE" | tail -n 1)" || true
    [ -n "$line" ] || return 0
    value="${line#*=}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" =~ ^\'(.*)\'$ ]] || [[ "$value" =~ ^\"(.*)\"$ ]]; then
        value="${BASH_REMATCH[1]}"
    else
        value="$(printf '%s' "$value" | sed -E 's/[[:space:]]+#.*$//')"
    fi
    printf '%s' "$value"
}

[ -f "$ENV_FILE" ] || die "không thấy file cấu hình $ENV_FILE (cách gọi: backup.sh <thư mục app>)"
command -v docker >/dev/null 2>&1 || die "thiếu lệnh docker"
command -v age >/dev/null 2>&1 || die "thiếu lệnh age (cài: apt install age)"

DB_URL="$(env_get NT_DATABASE_URL)"
[ -n "$DB_URL" ] || die "thiếu NT_DATABASE_URL trong $ENV_FILE"
RECIPIENTS="$(env_get BACKUP_AGE_RECIPIENT)"
[ -n "$RECIPIENTS" ] || die "thiếu BACKUP_AGE_RECIPIENT (public key age1...) trong $ENV_FILE"
BACKUP_DIR="$(env_get BACKUP_DIR)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/novel-translator}"
NETWORK="$(env_get POSTGRES_NETWORK)"
NETWORK="${NETWORK:-postgres}"
PG_IMAGE="$(env_get BACKUP_PG_IMAGE)"
PG_IMAGE="${PG_IMAGE:-postgres:16}"
PREFIX="$(env_get APP_NAME)"
PREFIX="${PREFIX:-novel-translator}"

recipient_args=()
IFS=',' read -r -a keys <<<"$RECIPIENTS"
for key in "${keys[@]}"; do
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    [ -n "$key" ] && recipient_args+=(-r "$key")
done
[ "${#recipient_args[@]}" -gt 0 ] || die "BACKUP_AGE_RECIPIENT không có key nào"

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%d-%H%M%S)"
final="$BACKUP_DIR/$PREFIX-$stamp.dump.age"
tmp="$BACKUP_DIR/.$PREFIX-$stamp.dump.age.tmp"
[ ! -e "$final" ] || die "đã có $final, không ghi đè"
trap 'rm -f "$tmp"' EXIT

# URL đi qua biến môi trường của tiến trình docker (-e PGURL không kèm giá trị), không nằm trên
# dòng lệnh nên không lộ qua `ps`.
PGURL="$DB_URL" docker run --rm --network "$NETWORK" -e PGURL "$PG_IMAGE" \
    sh -c 'exec pg_dump --format=custom "$PGURL"' \
    | age "${recipient_args[@]}" -o "$tmp" \
    || die "pg_dump hoặc age lỗi; không tạo bản sao lưu mới, các bản cũ giữ nguyên"
[ -s "$tmp" ] || die "bản sao lưu rỗng; các bản cũ giữ nguyên"

mv -n "$tmp" "$final"
[ ! -e "$tmp" ] || die "đã có $final, không ghi đè"
trap - EXIT

# Tên chứa thời điểm UTC nên sắp theo tên = sắp theo thời gian; giữ KEEP bản mới nhất.
mapfile -t backups < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name "$PREFIX-*.dump.age" | sort -r)
for old in "${backups[@]:$KEEP}"; do
    rm -f -- "$old"
done

echo "backup: đã lưu $final ($(wc -c <"$final") byte), giữ tối đa $KEEP bản"
