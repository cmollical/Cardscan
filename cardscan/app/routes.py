"""TallyBinder application routes, separate from immutable market observations."""

import hmac
import os
from pathlib import Path
from uuid import UUID
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, Response
from .models import SessionWrite, IntakeWrite, ListingWrite, JobWrite, Condition
from .store import Store, AppError
from .media import MediaStore, MAX_BYTES
from .vision import Jobs, VisionSettings


def register(app, db, *, media_root=None, settings=None, vision_provider=None):
    store = Store(db)
    media = MediaStore(
        db,
        media_root
        or os.getenv("TALLYBINDER_MEDIA_DIR", str(db.path.parent / "photos")),
    )
    jobs = Jobs(store, media, settings, vision_provider)
    app.state.store = store
    app.state.jobs = jobs
    app.state.media = media
    token = os.getenv("TALLYBINDER_ACCESS_TOKEN", "")
    origins = set(
        os.getenv(
            "TALLYBINDER_ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,https://localhost:3000,https://127.0.0.1:3000",
        ).split(",")
    )

    def access(request: Request):
        if token and not app.state.security.authenticated(request):
            raise HTTPException(401, detail={"code": "access_token_required"})
        if request.method not in ("GET", "HEAD"):
            if request.headers.get("x-tallybinder-client") != "web":
                raise HTTPException(403, detail={"code": "client_header_required"})
            origin = request.headers.get("origin")
            if origin and origin not in origins:
                raise HTTPException(403, detail={"code": "origin_not_allowed"})

    router = APIRouter(dependencies=[Depends(access)])

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status, content={"detail": {"code": exc.code}}
        )

    @app.get("/app/config")
    def config(request: Request):
        return {
            "product_name": "TallyBinder",
            "auth_mode": (
                "session" if app.state.security.settings.production else "bearer"
            ),
            "authenticated": app.state.security.authenticated(
                request, allow_bearer=not app.state.security.settings.production
            ),
            "ai_enabled": jobs.settings.enabled
            and (vision_provider is not None or bool(os.getenv("OPENAI_API_KEY")))
            and not (db.path.parent / ".ai-restore-hold").exists(),
            "ai_pause_reason": (
                "restore_cost_review_required"
                if (db.path.parent / ".ai-restore-hold").exists()
                else None
            ),
            "model": jobs.settings.model if jobs.settings.enabled else None,
            "max_reservation_usd": (
                str(jobs.settings.reserve()) if jobs.settings.enabled else None
            ),
            "access_token_required": bool(token),
            "condition_notice": "Photo-based condition is preliminary; inspect surfaces and edges yourself.",
            "offline_notice": "The shell and unsent drafts can work offline. Identification, pricing and server inventory need the backend.",
        }

    @router.post("/intake/sessions")
    def session(value: SessionWrite):
        return store.session(value)

    @router.get("/intake")
    def queue(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
        return store.queue(limit, offset)

    @router.put("/intake/{id}")
    def intake(id: UUID, value: IntakeWrite):
        return store.put_intake(id, value)

    @router.get("/intake/{id}")
    def intake_get(id: UUID):
        return store.intake(id)

    @router.post("/intake/{id}/price")
    def price(id: UUID, revision: int = Query(ge=1)):
        return store.price(id, revision)

    @router.post("/media/upload")
    async def upload(file: UploadFile = File(...)):
        try:
            from starlette.concurrency import run_in_threadpool

            body = await file.read(MAX_BYTES + 1)
            return await run_in_threadpool(media.upload, body)
        finally:
            await file.close()

    @router.get("/media/{id}")
    def image(id: UUID):
        return FileResponse(
            media.file(id),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post("/intake/{id}/jobs")
    def job(id: UUID, value: JobWrite, tasks: BackgroundTasks):
        record, new = jobs.enqueue(id, value)
        if new and os.getenv("TALLYBINDER_JOB_MODE", "background") == "background":
            tasks.add_task(jobs.run, record["id"])
        return record

    @router.get("/jobs/{id}")
    def job_get(id: UUID):
        return jobs.get(id)

    @router.get("/inventory/export.csv")
    def export():
        return Response(
            store.export_csv(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="TallyBinder-inventory.csv"',
                "Cache-Control": "no-store",
            },
        )

    @router.get("/inventory")
    def inventory(
        q: str = Query("", max_length=200),
        condition: Condition | None = None,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return store.inventory(q, condition, limit, offset)

    @router.post("/inventory")
    def save(value: ListingWrite):
        return store.save_listing(value)

    @router.get("/inventory/{id}")
    def listing(id: UUID):
        return store.listing(id)

    @router.put("/inventory/{id}")
    def edit(id: UUID, value: ListingWrite):
        return store.save_listing(value, id)

    @router.delete("/inventory/{id}")
    def delete(id: UUID, confirm: bool = False):
        if not confirm:
            raise AppError("delete_confirmation_required", 422)
        return store.delete(id)

    from contextlib import asynccontextmanager

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        if (
            os.getenv("TALLYBINDER_JOB_MODE", "background") == "background"
            and db.path.exists()
            and db.health()["status"] == "ok"
        ):
            jobs.recover()
        async with previous_lifespan(application):
            yield

    app.router.lifespan_context = lifespan
    app.include_router(router)
