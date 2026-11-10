"""Tải ảnh bìa từ link an toàn (spec novel-library "Cover image from a link", "Link fetch
safety"; design D7). Không bao giờ gọi internet thật: resolver giả + server HTTP local."""

from __future__ import annotations

import pytest

from novel_translator.domain.novel_details import CoverFetchError
from novel_translator.media.http_fetcher import (
    GuardedBackend,
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
    for host in ("mixed.test", "evil.test"):
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
