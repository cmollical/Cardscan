"""Cloud Run API using Firestore state, Cloud Storage media and a local snapshot."""

import os

from google.cloud import firestore, storage
from starlette.concurrency import run_in_threadpool

from cardscan.app.vision import VisionSettings
from cardscan.cloud.firestore_store import FirestoreStore
from cardscan.cloud.media import CloudMediaStore
from cardscan.cloud.snapshot import PricingSnapshot
from cardscan.cloud.vision import CloudTasksDispatcher, FirestoreJobs
from cardscan.local_pricing.api import create_app


snapshot = PricingSnapshot()
pricing_db = snapshot.ensure()
firestore_client = firestore.Client(
    database=os.getenv("TALLYBINDER_FIRESTORE_DATABASE", "(default)")
)
bucket = storage.Client().bucket(os.environ["TALLYBINDER_STORAGE_BUCKET"])
store = FirestoreStore(pricing_db, client=firestore_client)
media = CloudMediaStore(firestore_client, bucket)
vision_settings = VisionSettings.environment()
dispatcher = CloudTasksDispatcher() if vision_settings.enabled else None
jobs = FirestoreJobs(
    store,
    media,
    vision_settings,
    dispatcher=dispatcher,
)
app = create_app(
    pricing_db.path,
    app_store=store,
    media_store=media,
    vision_settings=vision_settings,
    jobs=jobs,
    job_dispatch=dispatcher,
)


@app.middleware("http")
async def refresh_pricing_snapshot(request, call_next):
    await run_in_threadpool(snapshot.refresh)
    return await call_next(request)
