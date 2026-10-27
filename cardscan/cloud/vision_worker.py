"""Private Cloud Run target for authenticated Cloud Tasks vision requests."""

import os

from fastapi import FastAPI, HTTPException
from google.cloud import firestore, storage

from cardscan.app.vision import VisionSettings
from cardscan.cloud.firestore_store import FirestoreStore
from cardscan.cloud.media import CloudMediaStore
from cardscan.cloud.snapshot import PricingSnapshot
from cardscan.cloud.vision import FirestoreJobs


snapshot = PricingSnapshot()
pricing_db = snapshot.ensure()
firestore_client = firestore.Client(database=os.getenv("TALLYBINDER_FIRESTORE_DATABASE", "(default)"))
bucket = storage.Client().bucket(os.environ["TALLYBINDER_STORAGE_BUCKET"])
store = FirestoreStore(pricing_db, client=firestore_client)
media = CloudMediaStore(firestore_client, bucket)
jobs = FirestoreJobs(store, media, VisionSettings.environment())
app = FastAPI(title="TallyBinder Vision Worker", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tasks/vision/{job_id}", status_code=204)
def vision(job_id: str):
    if not jobs.settings.enabled:
        raise HTTPException(503, detail={"code": "ai_disabled"})
    jobs.run(job_id)
