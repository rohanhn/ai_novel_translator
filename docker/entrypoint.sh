#!/bin/sh
# Entrypoint của image (design D3): chạy server thì migrate trước, lệnh khác chạy thẳng.
# - `uvicorn ...` (CMD mặc định): `novel migrate` giữ advisory lock; lỗi → set -e làm container
#   thoát với mã khác 0, không phục vụ request nào.
# - Lệnh chạy một lần (vd. `novel hash-password`) không cần database nên không migrate.
# `exec` để server là PID 1 và nhận SIGTERM trực tiếp khi `docker stop`.
set -eu

if [ "${1:-}" = "uvicorn" ]; then
    novel migrate
fi

exec "$@"
