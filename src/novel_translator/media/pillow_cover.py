"""Chuẩn hoá ảnh bìa bằng Pillow (design D3): chỉ JPEG/PNG/WebP thật, xoay theo EXIF,
ghép nền cho ảnh trong suốt, thu về khung 600×900, mã hoá lại WebP không metadata."""

from __future__ import annotations

import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from ..domain.novel_details import COVER_MAX_SIZE, CoverImage, InvalidImageError

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
MAX_PIXELS = 40_000_000  # chặn bom giải nén (vd. PNG 100000×100000 vài KB)
BACKGROUND = (0xF3, 0xED, 0xE0)  # --paper: nền cho ảnh có vùng trong suốt
NOT_AN_IMAGE = "File không phải ảnh JPG, PNG hoặc WebP."


class PillowCoverProcessor:
    def __init__(self, max_size: tuple[int, int] = COVER_MAX_SIZE, max_pixels: int = MAX_PIXELS,
                 quality: int = 82):
        self.max_size = max_size
        self.max_pixels = max_pixels
        self.quality = quality

    def process(self, data: bytes) -> CoverImage:
        if not data:
            raise InvalidImageError(NOT_AN_IMAGE)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                img = Image.open(BytesIO(data))
                if img.format not in ALLOWED_FORMATS:  # định dạng theo nội dung, không theo đuôi
                    raise InvalidImageError(NOT_AN_IMAGE)
                w, h = img.size
                if w * h > self.max_pixels:
                    raise InvalidImageError("Ảnh quá lớn (quá nhiều điểm ảnh) để xử lý an toàn.")
                img.load()  # giải mã thật: file hỏng báo lỗi ở đây
                img = ImageOps.exif_transpose(img)
                img = self._flatten(img)
                img.thumbnail(self.max_size, Image.Resampling.LANCZOS)  # không phóng to ảnh nhỏ
                out = BytesIO()
                img.save(out, "WEBP", quality=self.quality, method=4)  # không truyền exif
        except InvalidImageError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise InvalidImageError(
                "Ảnh quá lớn (quá nhiều điểm ảnh) để xử lý an toàn.") from None
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
            raise InvalidImageError(NOT_AN_IMAGE) from None
        return CoverImage("image/webp", out.getvalue(), img.width, img.height)

    @staticmethod
    def _flatten(img: Image.Image) -> Image.Image:
        has_alpha = img.mode in ("RGBA", "LA", "PA") or (
            img.mode == "P" and "transparency" in img.info)
        if not has_alpha:
            return img.convert("RGB")
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, BACKGROUND)
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
