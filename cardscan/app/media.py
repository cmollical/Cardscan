"""Bounded decoded image ingestion; generated names and stripped metadata."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import warnings
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from .store import AppError
from cardscan.local_pricing.database import utc

MAX_BYTES = 8_000_000


class MediaStore:
    def __init__(self, db, root, owner="local"):
        self.db, self.root, self.owner = db, Path(root).resolve(), owner

    def upload(self, body):
        if not body or len(body) > MAX_BYTES:
            raise AppError("image_too_large_or_empty", 413)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(body)) as im:
                    if im.format not in ("JPEG", "PNG", "WEBP"):
                        raise AppError("use_jpeg_png_or_webp", 415)
                    if (
                        min(im.size) < 160
                        or max(im.size) > 6000
                        or im.width * im.height > 25_000_000
                    ):
                        raise AppError("image_dimensions_out_of_range", 422)
                    if getattr(im, "n_frames", 1) != 1:
                        raise AppError("animated_images_not_supported", 415)
                    im.load()
                    im = ImageOps.exif_transpose(im)
                    im.thumbnail((1920, 1920))
                    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
                        rgba = im.convert("RGBA")
                        rgb = Image.new("RGB", im.size, "white")
                        rgb.paste(rgba, mask=rgba.getchannel("A"))
                        im = rgb
                    else:
                        im = im.convert("RGB")
                    out = BytesIO()
                    im.save(out, "JPEG", quality=90, optimize=True)
                    width, height = im.size
        except AppError:
            raise
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise AppError("invalid_image", 415)
        cleaned = out.getvalue()
        digest = sha256(cleaned).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        id = str(uuid4())
        filename = id + ".jpg"
        path = self.root / filename
        with self.db.transaction() as c:
            old = c.execute(
                "SELECT * FROM app_media WHERE owner_id=? AND content_hash=?",
                (self.owner, digest),
            ).fetchone()
            if old:
                return self._public(old)
            temp = self.root / (id + ".part")
            try:
                with temp.open("xb") as f:
                    f.write(cleaned)
                temp.replace(path)
                c.execute(
                    "INSERT INTO app_media VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        id,
                        self.owner,
                        digest,
                        filename,
                        "image/jpeg",
                        width,
                        height,
                        len(cleaned),
                        utc(),
                    ),
                )
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            finally:
                temp.unlink(missing_ok=True)
        return {
            "id": id,
            "width": width,
            "height": height,
            "bytes": len(cleaned),
            "mime": "image/jpeg",
            "url": "/media/" + id,
        }

    @staticmethod
    def _public(row):
        return {k: row[k] for k in ["id", "width", "height", "bytes", "mime"]} | {
            "url": "/media/" + row["id"]
        }

    def file(self, id):
        with self.db.connect(readonly=True) as c:
            r = c.execute(
                "SELECT * FROM app_media WHERE id=? AND owner_id=?",
                (str(id), self.owner),
            ).fetchone()
        if not r:
            raise AppError("photo_not_found", 404)
        path = (self.root / r["filename"]).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise AppError("photo_not_found", 404)
        return path
