"""Isolated E2E backend. Saved pricing evidence + synthetic photos; paid AI disabled."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cardscan.local_pricing.database import Database
from cardscan.local_pricing.cli import seed
from cardscan.local_pricing.api import create_app
from cardscan.app.vision import VisionSettings
import uvicorn

if __name__ == "__main__":
    with TemporaryDirectory(prefix="tallybinder-e2e-") as tmp:
        db = Database(Path(tmp) / "pricing.sqlite")
        db.migrate()
        seed(db)
        app = create_app(
            db.path,
            media_root=Path(tmp) / "photos",
            vision_settings=VisionSettings(enabled=False),
        )
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
