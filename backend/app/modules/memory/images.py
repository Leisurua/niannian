"""Decode/re-encode a bounded raster; metadata and appended payloads are discarded.

This is a raster content policy, not a claim of antivirus scanning arbitrary files.
Only fresh pixel data are written to a separate, never client-writable object key.
"""
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.modules.memory.file_validation import FilePreflightError


def sanitize_photo(data, mime, max_pixels, max_bytes):
    expected = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}[mime]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=['JPEG', 'PNG', 'WEBP']) as probe:
                if probe.format != expected or probe.width * probe.height > max_pixels or getattr(probe, 'n_frames', 1) != 1:
                    raise FilePreflightError('FILE_CONTENT_REJECTED')
                probe.verify()
            with Image.open(BytesIO(data), formats=['JPEG', 'PNG', 'WEBP']) as image:
                image.load()
                rotated = ImageOps.exif_transpose(image)
                mode = 'RGB' if expected == 'JPEG' else 'RGBA'
                pixels = rotated.convert(mode)
                clean = Image.new(mode, pixels.size)
                clean.paste(pixels)
                output = BytesIO()
                clean.save(output, format=expected)
                result = output.getvalue()
                if len(result) > max_bytes:
                    raise FilePreflightError('FILE_SIZE_INVALID')
                return result
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise FilePreflightError('FILE_CONTENT_REJECTED') from None
