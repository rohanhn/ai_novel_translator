"""Tải ảnh bìa từ link mà không mở đường cho SSRF (design D7).

Hai lớp bảo vệ:
1. `validate_url`: chỉ http/https, có host, không `user:pass@`, cổng rỗng/80/443, ≤2000 ký tự.
   Sai → `CoverFetchError("invalid_url")`, chưa có request nào.
2. `GuardedBackend`: network backend của httpcore tự phân giải tên miền, chỉ chấp nhận khi MỌI
   IP đều là địa chỉ public (kể cả IPv4 nhúng trong IPv6), rồi kết nối thẳng tới IP đã kiểm.
   Không có lần phân giải thứ hai nên DNS rebinding không lách được. TLS vẫn dùng tên miền gốc
   (httpcore gọi `start_tls(server_hostname=<host gốc>)`), nên chứng chỉ và SNI đúng.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Iterable
from urllib.parse import SplitResult, urljoin, urlsplit

import httpcore
import httpx

from ..domain.novel_details import COVER_MAX_BYTES, COVER_URL_MAX, CoverFetchError

ALLOWED_PORTS = frozenset({80, 443})
NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")

Resolver = Callable[[str, int], Iterable[str]]

BLOCKED = "Không được tải ảnh từ địa chỉ nội bộ."


def _invalid(message: str) -> CoverFetchError:
    return CoverFetchError("invalid_url", message)


def validate_url(url: str) -> SplitResult:
    """Kiểm tra link trước khi gọi mạng. Trả kết quả `urlsplit` đã kiểm."""
    if not isinstance(url, str) or not url.strip():
        raise _invalid("Hãy dán một link ảnh.")
    url = url.strip()
    if len(url) > COVER_URL_MAX:
        raise _invalid(f"Link dài quá {COVER_URL_MAX} ký tự.")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise _invalid("Đây không phải một link hợp lệ.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise _invalid("Đây không phải một link hợp lệ.") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise _invalid("Chỉ nhận link http hoặc https.")
    if not parts.hostname:
        raise _invalid("Đây không phải một link hợp lệ.")
    if parts.username is not None or parts.password is not None:
        raise _invalid("Link không được chứa tên đăng nhập hoặc mật khẩu.")
    if port is not None and port not in ALLOWED_PORTS:
        raise _invalid("Link chỉ được dùng cổng 80 hoặc 443.")
    return parts


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """IPv4 nằm trong địa chỉ IPv6: IPv4-mapped, NAT64 well-known, 6to4, Teredo."""
    found: list[ipaddress.IPv4Address] = []
    if ip.ipv4_mapped is not None:
        found.append(ip.ipv4_mapped)
    if ip in NAT64_WELL_KNOWN:
        found.append(ipaddress.IPv4Address(int(ip) & 0xFFFF_FFFF))
    if ip.sixtofour is not None:
        found.append(ip.sixtofour)
    if ip.teredo is not None:
        found.extend(ip.teredo)
    return found


def _public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_global and not ip.is_multicast


def ip_allowed(address: str) -> bool:
    """Địa chỉ public (không loopback, private, link-local, CGNAT, reserved, multicast...).
    IPv6 nhúng IPv4 phải đạt ở cả hai dạng: `64:ff9b::7f00:1` có `is_global` True nhưng trỏ tới
    127.0.0.1 qua NAT64."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])  # bỏ zone id IPv6 (fe80::1%eth0)
    except ValueError:
        return False
    if not _public(ip):
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        return all(_public(v4) for v4 in _embedded_ipv4(ip))
    return True


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def resolve_checked(host: str, port: int, resolver: Resolver = system_resolver) -> list[str]:
    """Phân giải `host` và trả các IP được phép. Chỉ cần một IP không phải public là từ chối:
    tên miền trả lẫn IP nội bộ có thể bị dùng để vòng qua kiểm tra."""
    try:
        addresses = list(resolver(host, port))
    except (OSError, UnicodeError):
        raise CoverFetchError(
            "download_failed", "Không tìm thấy máy chủ của link này.") from None
    if not addresses:
        raise CoverFetchError("download_failed", "Không tìm thấy máy chủ của link này.")
    if not all(ip_allowed(a) for a in addresses):
        raise CoverFetchError("blocked_address", BLOCKED)
    return addresses


class GuardedBackend(httpcore.NetworkBackend):
    """Backend của httpcore: kiểm IP ở tầng kết nối và chỉ kết nối tới IP đã kiểm."""

    def __init__(self, resolver: Resolver = system_resolver,
                 inner: httpcore.NetworkBackend | None = None):
        self.resolver = resolver
        self.inner = inner or httpcore.SyncBackend()

    def connect_tcp(self, host: str, port: int, timeout: float | None = None,
                    local_address: str | None = None,
                    socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
                    ) -> httpcore.NetworkStream:
        if port not in ALLOWED_PORTS:
            raise CoverFetchError("invalid_url", "Link chỉ được dùng cổng 80 hoặc 443.")
        addresses = resolve_checked(host, port, self.resolver)
        last: Exception | None = None
        for ip in addresses:
            try:
                return self.inner.connect_tcp(ip, port, timeout=timeout,
                                              local_address=local_address,
                                              socket_options=socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as e:
                last = e
        assert last is not None
        raise last

    def connect_unix_socket(self, *args, **kwargs):  # pragma: no cover - không bao giờ dùng
        raise CoverFetchError("invalid_url", "Đây không phải một link hợp lệ.")

    def sleep(self, seconds: float) -> None:
        self.inner.sleep(seconds)


class _GuardedTransport(httpx.HTTPTransport):
    """`HTTPTransport` của httpx nhưng pool dùng `GuardedBackend` và không bao giờ qua proxy."""

    def __init__(self, backend: GuardedBackend):
        super().__init__(trust_env=False, retries=0)
        assert hasattr(self, "_pool"), "httpx đổi cấu trúc HTTPTransport: kiểm lại adapter"
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=1, max_keepalive_connections=0, retries=0,
            network_backend=backend,
        )


_REDIRECTS = frozenset({301, 302, 303, 307, 308})
USER_AGENT = "NovelTranslator/1.0 (cover fetch)"


def _failed(message: str) -> CoverFetchError:
    return CoverFetchError("download_failed", message)


class SafeHttpImageFetcher:
    """Hiện thực port `CoverImageFetcher` (design D7): mỗi lần gọi là đúng một lượt tải,
    không thử lại, không cache, không cookie/Authorization/Referer, không proxy từ môi trường.

    `resolver` và `inner_backend` chỉ để test thay DNS và socket; không có cờ nào tắt được
    việc chặn địa chỉ nội bộ."""

    def __init__(self, timeout: float = 15.0, connect_timeout: float = 5.0,
                 max_bytes: int = COVER_MAX_BYTES, max_redirects: int = 3,
                 resolver: Resolver = system_resolver,
                 inner_backend: httpcore.NetworkBackend | None = None):
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.resolver = resolver
        self.inner_backend = inner_backend

    def fetch(self, url: str) -> bytes:
        deadline = time.monotonic() + self.timeout
        current = url.strip() if isinstance(url, str) else url
        backend = GuardedBackend(self.resolver, self.inner_backend)
        headers = {"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/png,image/webp",
                   "Accept-Encoding": "identity"}
        try:
            with httpx.Client(transport=_GuardedTransport(backend), trust_env=False,
                              follow_redirects=False, headers=headers) as client:
                for _hop in range(self.max_redirects + 1):
                    validate_url(current)
                    client.cookies.clear()  # cookie của máy chủ trước không đi theo chuyển hướng
                    location = self._get(client, current, deadline)
                    if isinstance(location, bytes):
                        return location
                    current = urljoin(current, location)
        except CoverFetchError:
            raise
        except httpx.TimeoutException:
            raise _failed(
                f"Máy chủ không trả lời trong {self.timeout:g} giây, không tải được ảnh.") from None
        except httpx.HTTPError:
            raise _failed("Không tải được ảnh từ link này (không kết nối được máy chủ).") from None
        raise _failed(f"Link chuyển hướng quá {self.max_redirects} lần, không tải được ảnh.")

    def _remaining(self, deadline: float) -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise httpx.TimeoutException("deadline")
        return left

    def _get(self, client: httpx.Client, url: str, deadline: float) -> bytes | str:
        """Một lượt GET. Trả byte ảnh, hoặc `Location` (str) nếu là chuyển hướng."""
        left = self._remaining(deadline)
        timeout = httpx.Timeout(left, connect=min(self.connect_timeout, left))
        with client.stream("GET", url, timeout=timeout) as resp:
            if resp.status_code in _REDIRECTS:
                location = resp.headers.get("location")
                if not location:
                    raise _failed("Máy chủ chuyển hướng nhưng không cho địa chỉ mới.")
                return location
            if not 200 <= resp.status_code < 300:
                raise _failed(
                    f"Không tải được ảnh từ link này (máy chủ trả lỗi {resp.status_code}).")
            encoding = resp.headers.get("content-encoding", "identity").strip().lower()
            if encoding not in ("", "identity"):
                raise _failed("Máy chủ gửi dữ liệu nén, không tải được ảnh từ link này.")
            too_large = CoverFetchError(
                "too_large", f"Ảnh ở link này lớn hơn {self.max_bytes // (1024 * 1024)} MB.")
            length = resp.headers.get("content-length")
            if length and length.isdigit() and int(length) > self.max_bytes:
                raise too_large
            chunks, size = [], 0
            for chunk in resp.iter_raw():
                size += len(chunk)
                if size > self.max_bytes:
                    raise too_large
                chunks.append(chunk)
                self._remaining(deadline)
            return b"".join(chunks)
