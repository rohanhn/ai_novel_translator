"""Tải ảnh bìa từ link an toàn (spec novel-library "Cover image from a link", "Link fetch
safety"; design D7). Không bao giờ gọi internet thật: resolver giả + server HTTP local."""

from __future__ import annotations

import gzip
import ipaddress
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from typing import ClassVar

import httpcore
import pytest
from PIL import Image

from novel_translator.config import Settings
from novel_translator.container import build_container
from novel_translator.domain.novel_details import CoverFetchError, InvalidImageError
from novel_translator.media.http_fetcher import (
    GuardedBackend,
    SafeHttpImageFetcher,
    ip_allowed,
    resolve_checked,
    validate_url,
)

# --- 2.3: kiểm tra link và IP -------------------------------------------------------------


@pytest.mark.parametrize("url, message", [
    ("ftp://example.com/a.jpg", "http hoặc https"),
    ("file:///etc/passwd", "http hoặc https"),
    ("javascript:alert(1)", "http hoặc https"),
    ("bia.jpg", "http hoặc https"),
    ("không phải link", "hợp lệ"),
    ("http://", "hợp lệ"),
    ("http://example.com:8080/a.png", "cổng 80 hoặc 443"),
    ("https://example.com:22/a.png", "cổng 80 hoặc 443"),
    ("http://example.com:99999/a.png", "hợp lệ"),
    ("http://user:pass@example.com/a.png", "tên đăng nhập"),
    ("http://user@example.com/a.png", "tên đăng nhập"),
    ("", "dán một link"),
    ("https://example.com/" + "a" * 2000, "2000"),
])
def test_invalid_urls(url, message):
    with pytest.raises(CoverFetchError) as e:
        validate_url(url)
    assert e.value.reason == "invalid_url" and message in str(e.value)


@pytest.mark.parametrize("url", [
    "https://example.com/bia.jpg", "http://example.com:80/a.png",
    "HTTPS://Example.COM:443/x?y=1", "  https://example.com/a.webp  ",
])
def test_valid_urls(url):
    assert validate_url(url).hostname == "example.com"


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.10", "169.254.169.254", "0.0.0.0",
    "100.64.0.1", "224.0.0.1", "255.255.255.255", "192.0.2.1",
    "::1", "::", "fe80::1", "fe80::1%eth0", "fc00::1", "ff02::1",
    "::ffff:127.0.0.1", "::ffff:10.0.0.5", "64:ff9b::7f00:1", "64:ff9b::a00:5",
    "2002:7f00:1::", "2002:c0a8:10a::", "2001:0:4136:e378:8000:63bf:3fff:fdd2",
    "not-an-ip",
])
def test_internal_addresses_blocked(ip):
    assert ip_allowed(ip) is False


@pytest.mark.parametrize("ip", ["8.8.8.8", "93.184.216.34", "2606:4700::1",
                                "::ffff:8.8.8.8", "64:ff9b::808:808"])
def test_public_addresses_allowed(ip):
    assert ip_allowed(ip) is True


def _resolver(mapping):
    def resolve(host, port):
        return mapping[host]
    return resolve


def test_resolve_rejects_if_any_address_internal():
    r = _resolver({"pub.test": ["8.8.8.8"], "mixed.test": ["8.8.8.8", "192.168.1.10"],
                   "evil.test": ["192.168.1.10"]})
    assert resolve_checked("pub.test", 443, r) == ["8.8.8.8"]
    for host in ("mixed.test", "evil.test"):  # không có cờ nào bỏ qua được bước này
        with pytest.raises(CoverFetchError) as e:
            resolve_checked(host, 443, r)
        assert e.value.reason == "blocked_address" and "địa chỉ nội bộ" in str(e.value)


def test_resolve_failure_is_download_failed():
    def boom(host, port):
        raise OSError("nodename nor servname provided")
    with pytest.raises(CoverFetchError) as e:
        resolve_checked("khong-ton-tai.test", 443, boom)
    assert e.value.reason == "download_failed"


class _RecordingBackend:
    """Backend bên trong giả: ghi lại mọi lần mở socket."""

    def __init__(self):
        self.connects: list[tuple[str, int]] = []

    def connect_tcp(self, host, port, **kw):
        self.connects.append((host, port))
        return object()


@pytest.mark.parametrize("host, ips", [
    ("127.0.0.1", ["127.0.0.1"]),
    ("169.254.169.254", ["169.254.169.254"]),
    ("::1", ["::1"]),
    ("evil.test", ["192.168.1.10"]),
    ("nat64.test", ["64:ff9b::7f00:1"]),
    ("mapped.test", ["::ffff:127.0.0.1"]),
    ("mixed.test", ["93.184.216.34", "10.0.0.5"]),
])
def test_backend_refuses_before_opening_socket(host, ips):
    inner = _RecordingBackend()
    backend = GuardedBackend(resolver=_resolver({host: ips}), inner=inner)
    with pytest.raises(CoverFetchError) as e:
        backend.connect_tcp(host, 443)
    assert e.value.reason == "blocked_address"
    assert inner.connects == []


def test_backend_connects_to_checked_ip_not_hostname():
    """Kết nối thẳng tới IP đã kiểm: không có lần phân giải thứ hai (chống DNS rebinding)."""
    calls = []

    def resolver(host, port):
        calls.append(host)
        return ["93.184.216.34"] if len(calls) == 1 else ["127.0.0.1"]

    inner = _RecordingBackend()
    GuardedBackend(resolver=resolver, inner=inner).connect_tcp("rebind.test", 443)
    assert inner.connects == [("93.184.216.34", 443)] and calls == ["rebind.test"]


def test_backend_refuses_other_ports():
    inner = _RecordingBackend()
    backend = GuardedBackend(resolver=_resolver({"pub.test": ["8.8.8.8"]}), inner=inner)
    with pytest.raises(CoverFetchError):
        backend.connect_tcp("pub.test", 8080)
    assert inner.connects == []


# --- 2.4: tải thật qua server HTTP local (giả làm máy chủ public) ---------------------------

PUBLIC_IP = "93.184.216.34"  # IP "public" giả: mọi kết nối tới nó được chuyển về server local


def _png_bytes(w=120, h=180) -> bytes:
    out = BytesIO()
    Image.new("RGB", (w, h), "orange").save(out, "PNG")
    return out.getvalue()


class _Handler(BaseHTTPRequestHandler):
    seen: ClassVar[list[dict[str, str]]] = []

    def log_message(self, *a):  # im lặng
        pass

    def _send(self, code=200, body=b"", headers=None, length=True):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if length:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        _Handler.seen.append({k.lower(): v for k, v in self.headers.items()})
        p = self.path
        if p == "/bia.png":
            self._send(200, _png_bytes(), {"Set-Cookie": "sid=abc", "Content-Type": "image/png"})
        elif p.startswith("/hop/"):  # /hop/N: chuyển hướng N lần rồi trả ảnh
            n = int(p.rsplit("/", 1)[1])
            target = f"/hop/{n - 1}" if n > 1 else "/bia.png"
            self._send(302, headers={"Location": target, "Set-Cookie": "hop=1"})
        elif p == "/to-internal":
            self._send(302, headers={"Location": "http://10.0.0.5/bia.png"})
        elif p == "/to-loopback-name":
            self._send(302, headers={"Location": "http://localhost.test/bia.png"})
        elif p == "/missing":
            self._send(404, b"not found")
        elif p == "/slow":
            time.sleep(1.5)
            self._send(200, _png_bytes())
        elif p == "/big-declared":
            self._send(200, b"x" * 10, {"Content-Length": "99999999"}, length=False)
        elif p == "/big-stream":  # không có Content-Length: đọc tới khi đóng kết nối
            self.send_response(200)
            self.end_headers()
            for _ in range(50):
                self.wfile.write(b"x" * 1024)
        elif p == "/gzip":
            self._send(200, gzip.compress(_png_bytes()), {"Content-Encoding": "gzip"})
        elif p == "/page.html":
            self._send(200, b"<html><body>Trang web</body></html>",
                       {"Content-Type": "text/html"})
        else:
            self._send(404)


class _ToLocal:
    """Backend bên trong cho test: kết nối tới PUBLIC_IP:80 thật ra vào server local."""

    def __init__(self, port: int):
        self.port = port
        self.inner = httpcore.SyncBackend()

    def connect_tcp(self, host, port, **kw):
        assert host == PUBLIC_IP and port == 80, (host, port)
        return self.inner.connect_tcp("127.0.0.1", self.port, **kw)

    def sleep(self, s):
        time.sleep(s)


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def _dns(host, port):
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    return {"anh.test": [PUBLIC_IP], "localhost.test": ["127.0.0.1"]}[host]


@pytest.fixture
def fetcher(server):
    _Handler.seen.clear()
    return SafeHttpImageFetcher(timeout=0.8, connect_timeout=0.5, max_bytes=20 * 1024,
                                resolver=_dns, inner_backend=_ToLocal(server.server_port))


def test_fetch_success_and_request_headers(fetcher):
    data = fetcher.fetch("http://anh.test/bia.png")
    assert data == _png_bytes()
    h = _Handler.seen[-1]
    assert "cookie" not in h and "authorization" not in h and "referer" not in h
    assert h["user-agent"].startswith("NovelTranslator/") and h["accept-encoding"] == "identity"
    assert "@" not in h["user-agent"]


def test_three_redirects_ok_four_rejected(fetcher):
    assert fetcher.fetch("http://anh.test/hop/3") == _png_bytes()
    # cookie do máy chủ đặt ở bước trước không được gửi lại ở bước sau
    assert all("cookie" not in h for h in _Handler.seen)
    with pytest.raises(CoverFetchError, match="chuyển hướng quá 3 lần") as e:
        fetcher.fetch("http://anh.test/hop/4")
    assert e.value.reason == "download_failed"


@pytest.mark.parametrize("path", ["/to-internal", "/to-loopback-name"])
def test_redirect_to_internal_address_refused(fetcher, path):
    with pytest.raises(CoverFetchError) as e:
        fetcher.fetch(f"http://anh.test{path}")
    assert e.value.reason == "blocked_address"
    assert len(_Handler.seen) == 1  # không có request thứ hai nào tới đâu cả


def test_http_error_and_timeout(fetcher):
    with pytest.raises(CoverFetchError, match="máy chủ trả lỗi 404") as e:
        fetcher.fetch("http://anh.test/missing")
    assert e.value.reason == "download_failed"
    start = time.monotonic()
    with pytest.raises(CoverFetchError, match="không trả lời") as e:
        fetcher.fetch("http://anh.test/slow")
    assert e.value.reason == "download_failed" and time.monotonic() - start < 1.4


@pytest.mark.parametrize("path", ["/big-declared", "/big-stream"])
def test_too_large_stops_early(fetcher, path):
    with pytest.raises(CoverFetchError) as e:
        fetcher.fetch(f"http://anh.test{path}")
    assert e.value.reason == "too_large" and "MB" in str(e.value)


def test_compressed_response_refused(fetcher):
    with pytest.raises(CoverFetchError, match="nén") as e:
        fetcher.fetch("http://anh.test/gzip")
    assert e.value.reason == "download_failed"


def test_html_page_is_not_an_image(container, fetcher):
    container.library.cover_fetcher = fetcher
    with pytest.raises(InvalidImageError, match="không phải ảnh"):
        container.library.preview_cover_from_url("http://anh.test/page.html")


def test_preview_from_url_processes_and_saves_nothing(container, fetcher):
    container.library.cover_fetcher = fetcher
    img = container.library.preview_cover_from_url("http://anh.test/bia.png")
    assert (img.mime, img.width, img.height) == ("image/webp", 120, 180)
    assert container.library.list_novels() == []


def test_invalid_url_makes_no_request(fetcher):
    with pytest.raises(CoverFetchError):
        fetcher.fetch("ftp://anh.test/bia.png")
    assert _Handler.seen == []


def test_container_accepts_fake_fetcher(db, password_hash):
    class Fake:
        def fetch(self, url):
            return _png_bytes(10, 10)

    c = build_container(Settings(provider="echo", password_hash=password_hash,
                                 cookie_secure=False), pool=db, cover_fetcher=Fake())
    assert c.cover_fetcher.__class__ is Fake
    assert c.library.preview_cover_from_url("https://x.test/a.png").width == 10
