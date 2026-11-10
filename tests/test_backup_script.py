"""deploy/backup.sh (spec database-backup; design D9) chạy với `docker` và `age` giả.

`PATH` của script chỉ gồm các lệnh cần thiết (symlink) cộng hai stub, nên test không phụ thuộc
máy có Docker/age thật hay không, và không bao giờ chạm database.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "backup.sh"
TOOLS = ["bash", "env", "grep", "sed", "tail", "tr", "date", "mkdir", "mv", "rm", "find", "sort",
         "wc", "cat", "printf"]
NAME_RE = re.compile(r"^novel-translator-\d{8}-\d{6}\.dump\.age$")
URL = "postgresql://app:bi-mat@postgres:5432/app"
KEY1 = "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"
KEY2 = "age1lggyhqrw2nlhcxprm67z43rta597azn8gknawjehu9d9dl0jq3yqqvfafg"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="cần bash để chạy script")

DOCKER_STUB = """#!/bin/bash
printf '%s\\n' "$@" > "$STUB_DIR/docker.args"
printf '%s' "${PGURL:-}" > "$STUB_DIR/docker.pgurl"
if [ "${DOCKER_MODE:-ok}" = fail ]; then
    echo "pg_dump: error: connection to server failed" >&2
    exit 1
fi
printf 'PGDMP-du-lieu-gia'
"""

AGE_STUB = """#!/bin/bash
printf '%s\\n' "$@" > "$STUB_DIR/age.args"
out=""
while [ $# -gt 0 ]; do
    if [ "$1" = -o ]; then out="$2"; shift 2; else shift; fi
done
data="$(cat)"
printf 'AGE(%s)' "$data" > "$out"
"""


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        real = shutil.which(tool)
        if real:
            (bin_dir / tool).symlink_to(real)
    for name, body in (("docker", DOCKER_STUB), ("age", AGE_STUB)):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    app = tmp_path / "app"
    app.mkdir()
    out = tmp_path / "backups"
    stubs = tmp_path / "stubs"
    stubs.mkdir()

    class Env:
        app_dir = app
        backup_dir = out
        stub_dir = stubs
        bin = bin_dir

        def write_env(self, **values):
            lines = [f"{k}={v}" for k, v in values.items()]
            (app / ".env").write_text("\n".join(lines) + "\n")

        def run(self, docker_mode="ok"):
            return subprocess.run(
                [str(SCRIPT), str(app)], check=False, capture_output=True, text=True, timeout=30,
                env={"PATH": str(bin_dir), "STUB_DIR": str(stubs), "DOCKER_MODE": docker_mode,
                     "HOME": str(tmp_path)},
            )

        def stub_args(self, name):
            p = stubs / f"{name}.args"
            return p.read_text().splitlines() if p.exists() else None

    e = Env()
    e.write_env(NT_DATABASE_URL=URL, BACKUP_AGE_RECIPIENT=KEY1, BACKUP_DIR=str(out),
                POSTGRES_NETWORK="pg-net")
    return e


def _old_backups(directory: Path, n: int) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 1, 1, 3, 15, 0)
    files = []
    for i in range(n):
        f = directory / f"novel-translator-{(base + timedelta(days=i)):%Y%m%d-%H%M%S}.dump.age"
        f.write_text(f"cu {i}")
        files.append(f)
    return files


def test_successful_run_encrypts_and_names_file(env):
    r = env.run()
    assert r.returncode == 0, r.stderr
    files = sorted(p.name for p in env.backup_dir.iterdir())
    assert len(files) == 1 and NAME_RE.match(files[0]), files
    out = env.backup_dir / files[0]
    assert out.read_text() == "AGE(PGDMP-du-lieu-gia)"  # mọi byte đi qua age
    assert out.stat().st_mode & 0o777 == 0o600
    assert env.backup_dir.stat().st_mode & 0o777 == 0o700
    args = env.stub_args("docker")
    assert args[:4] == ["run", "--rm", "--network", "pg-net"]
    assert "postgres:16" in args


def test_file_name_uses_utc(env):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    assert env.run().returncode == 0
    after = datetime.now(timezone.utc)
    name = next(env.backup_dir.iterdir()).name
    stamp = datetime.strptime(name[len("novel-translator-"):-len(".dump.age")],
                              "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    assert before <= stamp <= after


def test_database_url_not_on_command_line(env):
    assert env.run().returncode == 0
    assert all("bi-mat" not in a for a in env.stub_args("docker"))
    assert (env.stub_dir / "docker.pgurl").read_text() == URL


def test_quoted_values_are_read(env):
    env.write_env(NT_DATABASE_URL=f"'{URL}'", BACKUP_AGE_RECIPIENT=f'"{KEY1}"',
                  BACKUP_DIR=f"  {env.backup_dir}  ", POSTGRES_NETWORK="pg-net  # chú thích")
    r = env.run()
    assert r.returncode == 0, r.stderr
    assert (env.stub_dir / "docker.pgurl").read_text() == URL
    assert env.stub_args("age")[:2] == ["-r", KEY1]
    assert env.stub_args("docker")[3] == "pg-net"


def test_two_recipients_each_get_r_flag(env):
    env.write_env(NT_DATABASE_URL=URL, BACKUP_AGE_RECIPIENT=f"{KEY1}, {KEY2}",
                  BACKUP_DIR=str(env.backup_dir))
    assert env.run().returncode == 0
    args = env.stub_args("age")
    assert args[:4] == ["-r", KEY1, "-r", KEY2]


def test_fifteenth_backup_keeps_fourteen(env):
    old = _old_backups(env.backup_dir, 14)
    r = env.run()
    assert r.returncode == 0, r.stderr
    remaining = sorted(p.name for p in env.backup_dir.iterdir())
    assert len(remaining) == 14
    assert old[0].name not in remaining  # bản cũ nhất bị xoá
    assert all(f.name in remaining for f in old[1:])


def test_unrelated_files_are_not_deleted(env):
    _old_backups(env.backup_dir, 14)
    other = env.backup_dir / "ghi-chu.txt"
    other.write_text("giữ")
    assert env.run().returncode == 0
    assert other.exists()


def test_dump_failure_keeps_old_backups_and_leaves_no_tmp(env):
    old = _old_backups(env.backup_dir, 14)
    r = env.run(docker_mode="fail")
    assert r.returncode != 0
    assert "lỗi" in r.stderr
    remaining = sorted(env.backup_dir.iterdir())
    assert remaining == sorted(old)  # không thêm, không xoá
    assert not list(env.backup_dir.glob(".*"))


def test_missing_recipient_dumps_nothing(env):
    env.write_env(NT_DATABASE_URL=URL, BACKUP_DIR=str(env.backup_dir))
    r = env.run()
    assert r.returncode != 0
    assert "BACKUP_AGE_RECIPIENT" in r.stderr
    assert env.stub_args("docker") is None


def test_missing_database_url(env):
    env.write_env(BACKUP_AGE_RECIPIENT=KEY1, BACKUP_DIR=str(env.backup_dir))
    r = env.run()
    assert r.returncode != 0
    assert "NT_DATABASE_URL" in r.stderr
    assert env.stub_args("docker") is None


def test_missing_env_file(env):
    (env.app_dir / ".env").unlink()
    r = env.run()
    assert r.returncode != 0
    assert ".env" in r.stderr


def test_missing_age_tool(env):
    (env.bin / "age").unlink()
    r = env.run()
    assert r.returncode != 0
    assert "age" in r.stderr
    assert env.stub_args("docker") is None


def test_never_overwrites_existing_backup(env):
    env.backup_dir.mkdir()
    now = datetime.now(timezone.utc)
    taken = []
    for s in range(6):  # chiếm mọi tên trong vài giây tới
        f = env.backup_dir / f"novel-translator-{(now + timedelta(seconds=s)):%Y%m%d-%H%M%S}.dump.age"
        f.write_text("cu")
        taken.append(f)
    r = env.run()
    assert r.returncode != 0
    assert "không ghi đè" in r.stderr
    assert all(f.read_text() == "cu" for f in taken)
    assert not list(env.backup_dir.glob(".*"))


def test_script_is_executable():
    assert os.access(SCRIPT, os.X_OK)
