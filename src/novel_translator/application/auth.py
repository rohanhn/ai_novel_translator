"""Đăng nhập một chủ sở hữu (design D7, spec access-control).

- Mật khẩu so với hash argon2 trong NT_PASSWORD_HASH (không lưu plaintext).
- Session token ngẫu nhiên; DB chỉ lưu SHA-256 của token. Hết hạn sau 30 ngày không dùng.
- Chặn brute-force theo IP: 5 lần sai liên tiếp trong 15 phút → khóa 15 phút (trong bộ nhớ).
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..domain.ports import SessionStore

SESSION_IDLE = timedelta(days=30)
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthConfigError(RuntimeError):
    """Thiếu/sai cấu hình mật khẩu: app không được khởi động."""


class LoginLockedError(Exception):
    def __init__(self, retry_after: timedelta):
        super().__init__("Quá nhiều lần đăng nhập sai. Thử lại sau.")
        self.retry_after = retry_after


class InvalidCredentialsError(Exception):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class _Attempts:
    failures: list[datetime]
    locked_until: datetime | None = None


class LoginThrottle:
    def __init__(self, clock: Callable[[], datetime] = _utcnow):
        self.clock = clock
        self._by_ip: dict[str, _Attempts] = {}
        self._lock = threading.Lock()

    def check(self, ip: str) -> None:
        now = self.clock()
        with self._lock:
            a = self._by_ip.get(ip)
            if a and a.locked_until and a.locked_until > now:
                raise LoginLockedError(a.locked_until - now)

    def failure(self, ip: str) -> None:
        now = self.clock()
        with self._lock:
            a = self._by_ip.setdefault(ip, _Attempts([]))
            a.failures = [t for t in a.failures if now - t < FAILURE_WINDOW] + [now]
            if len(a.failures) >= MAX_FAILURES:
                a.locked_until = now + LOCKOUT
                a.failures = []

    def success(self, ip: str) -> None:
        with self._lock:
            self._by_ip.pop(ip, None)


class AuthService:
    def __init__(self, sessions: SessionStore, password_hash: str | None,
                 verify: Callable[[str, str], bool], clock: Callable[[], datetime] = _utcnow):
        self.sessions = sessions
        self.password_hash = password_hash
        self.verify = verify
        self.clock = clock
        self.throttle = LoginThrottle(clock)

    def ensure_configured(self) -> None:
        if not self.password_hash or not self.password_hash.strip():
            raise AuthConfigError(
                "Chưa cấu hình NT_PASSWORD_HASH. Tạo bằng lệnh `novel hash-password` rồi đặt "
                "vào biến môi trường hoặc .env."
            )
        if not self.password_hash.startswith("$argon2"):
            raise AuthConfigError("NT_PASSWORD_HASH không phải hash argon2 hợp lệ "
                                  "(tạo bằng `novel hash-password`).")

    def login(self, password: str, ip: str) -> str:
        """Trả về session token (đặt vào cookie). Sai → InvalidCredentialsError;
        đang bị khóa → LoginLockedError (kể cả khi mật khẩu đúng)."""
        self.ensure_configured()
        self.throttle.check(ip)
        if not self.verify(self.password_hash, password):
            self.throttle.failure(ip)
            raise InvalidCredentialsError("Sai mật khẩu.")
        self.throttle.success(ip)
        token = secrets.token_urlsafe(32)
        self.sessions.create_session(token_hash(token), self.clock())
        return token

    def authenticate(self, token: str | None) -> bool:
        if not token:
            return False
        now = self.clock()
        return self.sessions.touch_session(token_hash(token), now, now - SESSION_IDLE)

    def logout(self, token: str | None) -> None:
        if token:
            self.sessions.delete_session(token_hash(token))
