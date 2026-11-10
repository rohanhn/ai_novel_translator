"""Xử lý ảnh bìa (spec novel-library "Cover image processing", "Novel cover upload"; design D3).
Ảnh test tạo bằng Pillow ngay trong test."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from novel_translator.domain.novel_details import InvalidImageError
from novel_translator.media.pillow_cover import BACKGROUND, PillowCoverProcessor


def _encode(img: Image.Image, fmt: str, **kw) -> bytes:
    out = BytesIO()
    img.save(out, fmt, **kw)
    return out.getvalue()


def phone_jpeg() -> bytes:
    """3000×4000 lưu theo cảm biến; nửa trái đỏ, nửa phải xanh; EXIF Orientation=6 + GPS."""
    img = Image.new("RGB", (3000, 4000), (255, 0, 0))
    img.paste((0, 0, 255), (1500, 0, 3000, 4000))
    exif = Image.Exif()
    exif[0x0112] = 6  # xoay 90° theo chiều kim đồng hồ khi hiển thị
    exif[0x010F] = "PhoneMaker"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (21.0, 1.0, 30.0)
    return _encode(img, "JPEG", exif=exif.tobytes(), quality=70)


def _open(data: bytes) -> Image.Image:
    img = Image.open(BytesIO(data))
    img.load()
    return img


@pytest.fixture
def proc():
    return PillowCoverProcessor()


def test_large_phone_photo_scaled_upright_without_metadata(proc):
    raw = phone_jpeg()
    assert Image.open(BytesIO(raw)).getexif().get_ifd(0x8825)  # ảnh gốc có GPS
    cover = proc.process(raw)
    assert cover.mime == "image/webp"
    # hiển thị đúng chiều là 4000×3000 → thu về khung 600×900 giữ tỉ lệ = 600×450
    assert (cover.width, cover.height) == (600, 450)
    out = _open(cover.data)
    assert out.format == "WEBP" and out.size == (600, 450)
    # nửa trái (đỏ) của ảnh cảm biến nằm ở nửa trên sau khi xoay
    top, bottom = out.convert("RGB").getpixel((300, 50)), out.convert("RGB").getpixel((300, 400))
    assert top[0] > 200 and top[2] < 60 and bottom[2] > 200 and bottom[0] < 60
    assert len(out.getexif()) == 0 and "exif" not in out.info
    assert len(cover.data) < 100_000


def test_small_png_not_enlarged_and_alpha_on_paper(proc):
    img = Image.new("RGBA", (300, 450), (0, 128, 0, 255))
    img.paste((0, 0, 0, 0), (0, 0, 50, 50))  # góc trong suốt
    cover = proc.process(_encode(img, "PNG"))
    assert (cover.width, cover.height) == (300, 450)
    out = _open(cover.data).convert("RGB")
    corner = out.getpixel((10, 10))
    assert all(abs(a - b) <= 6 for a, b in zip(corner, BACKGROUND, strict=True))
    assert out.getpixel((200, 300))[1] > 100


def test_webp_and_palette_png_accepted(proc):
    assert proc.process(_encode(Image.new("RGB", (50, 80), "white"), "WEBP")).width == 50
    pal = Image.new("P", (40, 40))
    pal.info["transparency"] = 0
    assert proc.process(_encode(pal, "PNG", transparency=0)).height == 40


@pytest.mark.parametrize("data", [
    b"Day la file text doi duoi thanh .jpg\n" * 10,
    b"",
    b"\xff\xd8\xff\xe0" + b"\x00" * 50,  # header JPEG nhưng hỏng
])
def test_not_an_image(proc, data):
    with pytest.raises(InvalidImageError, match="không phải ảnh JPG, PNG hoặc WebP"):
        proc.process(data)


def test_gif_rejected(proc):
    with pytest.raises(InvalidImageError):
        proc.process(_encode(Image.new("RGB", (20, 20)), "GIF"))


def test_truncated_png_rejected(proc):
    data = _encode(Image.effect_noise((200, 200), 50).convert("RGB"), "PNG")
    with pytest.raises(InvalidImageError):
        proc.process(data[: len(data) // 2])


def test_pixel_bomb_rejected():
    proc = PillowCoverProcessor(max_pixels=10_000)  # hạ ngưỡng thay vì tạo ảnh khổng lồ
    with pytest.raises(InvalidImageError, match="quá nhiều điểm ảnh"):
        proc.process(_encode(Image.new("L", (200, 200)), "PNG"))
