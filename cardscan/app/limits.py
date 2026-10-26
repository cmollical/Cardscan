"""Streaming request limits; never buffers an unbounded multipart upload."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class BodyLimits:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in (
            "POST",
            "PUT",
            "PATCH",
        ):
            return await self.app(scope, receive, send)
        maximum = 9_000_000 if scope["path"] == "/media/upload" else 1_000_000
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = maximum + 1
        if length > maximum:
            return await JSONResponse(
                {"detail": {"code": "request_too_large"}}, status_code=413
            )(scope, receive, send)
        received = 0

        async def bounded():
            nonlocal received
            msg = await receive()
            received += len(msg.get("body", b""))
            if received > maximum:
                raise HTTPException(413, detail={"code": "request_too_large"})
            return msg

        await self.app(scope, bounded, send)
