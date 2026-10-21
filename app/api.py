import os
import secrets
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.neural.torch_status import pytorch_status
from app.orchestrator import Orchestrator
from app.schemas import HealthResponse, TaskRequest, TaskResponse

app = FastAPI(
    title="GLORIFIER Neural Orchestration",
    version="0.2.0",
    description="Governed, provider-neutral AI orchestration API.",
)
orchestrator = Orchestrator()
MAX_REQUEST_BODY_BYTES = 65_536


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            response = JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"},
            )
        else:
            if declared_length < 0:
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )
            elif declared_length > MAX_REQUEST_BODY_BYTES:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds the 65536-byte limit"},
                )
            else:
                response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    # Report known implementation gaps honestly; process health is not dependency health.
    pytorch_installed = pytorch_status()["installed"]
    return HealthResponse(
        status="PARTIALLY VERIFIED",
        service="glorifier-neural",
        checks={
            "process": "VERIFIED",
            "providers": "NOT VERIFIED",
            "database": "NOT VERIFIED",
            "pytorch": "VERIFIED" if pytorch_installed else "NOT VERIFIED",
        },
    )


@app.get("/ready", tags=["operations"])
def readiness() -> JSONResponse:
    """Report deployment readiness separately from process liveness."""
    return JSONResponse(
        status_code=503,
        content={
            "status": "NOT READY",
            "checks": {
                "providers": "NOT VERIFIED",
                "database": "NOT VERIFIED",
            },
            "message": "Required provider and database integrations are not configured.",
        },
    )


@app.post("/v1/tasks", response_model=TaskResponse, tags=["orchestration"])
def run_task(
    request: TaskRequest,
    authorization: str | None = Header(default=None),
) -> TaskResponse:
    api_token = os.getenv("GLORIFIER_API_TOKEN")
    if not api_token:
        raise HTTPException(
            status_code=503,
            detail="API token is not configured; execution endpoint is disabled",
        )
    if not secrets.compare_digest(authorization or "", f"Bearer {api_token}"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return orchestrator.run(request)
