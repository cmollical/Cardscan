"""Private Cloud Storage media with Firestore metadata."""

from hashlib import sha256
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cardscan.app.media import normalize_image
from cardscan.app.store import AppError
from cardscan.local_pricing.database import utc


class CloudMediaStore:
    def __init__(
        self,
        firestore_client,
        bucket=None,
        *,
        owner="local",
        prefix=None,
        cache_root="/tmp/tallybinder-media",
    ):
        self.client = firestore_client
        self.owner = owner
        self.prefix = prefix or os.getenv("TALLYBINDER_FIRESTORE_PREFIX", "tallybinder")
        if bucket is None:
            from google.cloud import storage

            bucket_name = os.environ["TALLYBINDER_STORAGE_BUCKET"]
            bucket = storage.Client().bucket(bucket_name)
        self.bucket = bucket
        self.cache_root = Path(cache_root)

    def _collection(self):
        return self.client.collection(f"{self.prefix}_media")

    def _metadata(self, id):
        snapshot = self._collection().document(str(id)).get()
        data = snapshot.to_dict() if snapshot.exists else None
        if not data or data.get("owner_id") != self.owner:
            raise AppError("photo_not_found", 404)
        return data

    @staticmethod
    def _public(data):
        return {k: data[k] for k in ["id", "width", "height", "bytes", "mime"]} | {
            "url": "/media/" + data["id"]
        }

    def upload(self, body):
        cleaned, width, height = normalize_image(body)
        digest = sha256(cleaned).hexdigest()
        id = str(uuid5(NAMESPACE_URL, f"tallybinder:{self.owner}:media:{digest}"))
        ref = self._collection().document(id)
        old = ref.get()
        if old.exists:
            data = old.to_dict()
            if data.get("owner_id") != self.owner or data.get("content_hash") != digest:
                raise AppError("photo_storage_conflict", 409)
            return self._public(data)
        object_name = f"photos/{self.owner}/{id}.jpg"
        blob = self.bucket.blob(object_name)
        try:
            blob.upload_from_string(
                cleaned,
                content_type="image/jpeg",
                if_generation_match=0,
                timeout=60,
            )
        except Exception as exc:
            from google.api_core.exceptions import PreconditionFailed

            if not isinstance(exc, PreconditionFailed):
                raise
        data = {
            "id": id,
            "owner_id": self.owner,
            "content_hash": digest,
            "object_name": object_name,
            "mime": "image/jpeg",
            "width": width,
            "height": height,
            "bytes": len(cleaned),
            "created_at": utc(),
        }
        ref.set(data)
        return self._public(data)

    def read(self, id):
        data = self._metadata(id)
        body = self.bucket.blob(data["object_name"]).download_as_bytes(timeout=60)
        if len(body) != data["bytes"] or sha256(body).hexdigest() != data["content_hash"]:
            raise AppError("photo_not_found", 404)
        return body

    def file(self, id):
        data = self._metadata(id)
        self.cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.cache_root / f"{data['id']}.jpg"
        if not path.exists():
            body = self.read(id)
            temp = self.cache_root / f"{data['id']}.part"
            temp.write_bytes(body)
            temp.replace(path)
        return path
