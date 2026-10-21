import os
import secrets
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.audit import AuditEvent, SupabaseRestAuditSink
from app.neural.torch_status import pytorch_status
from app.orchestrator import Orchestrator
from app.request_limits import RequestBodyLimitMiddleware
from app.schemas import HealthResponse, TaskRequest, TaskResponse

app = FastAPI(
    title="GLORIFIER Neural Orchestration",
    version="0.2.0",
    description="Governed, provider-neutral AI orchestration API.",
)
orchestrator = Orchestrator()
MAX_REQUEST_BODY_BYTES = 65_536
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=MAX_REQUEST_BODY_BYTES)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
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
    response.headers["X-Request-ID"] = request_id
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
    task_request: TaskRequest,
    request: Request,
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

    try:
        audit_sink = SupabaseRestAuditSink.from_environment()
    except ValueError:
        # Never include environment values or credential details in client-facing errors.
        raise HTTPException(status_code=503, detail="Configured audit persistence is unavailable") from None

    request_id = request.state.request_id
    if audit_sink is not None:
        try:
            # Pre-execution audit write: if it fails, do not start task processing.
            audit_sink.write(
                AuditEvent(
                    request_id=request_id,
                    event_type="task_received",
                    status="NOT VERIFIED",
                    action_class=task_request.action_class,
                    evidence=("execution:not-started",),
                )
            )
        except (RuntimeError, ValueError):
            raise HTTPException(status_code=503, detail="Audit persistence unavailable; task not executed") from None

    result = orchestrator.run(task_request)

    if audit_sink is not None:
        if "policy:deny" in result.evidence:
            event_type = "policy_denied"
        elif "policy:approval-required" in result.evidence:
            event_type = "approval_required"
        elif "execution:inference" in result.evidence:
            event_type = "inference_completed"
        else:
            event_type = "inference_failed"
        try:
            audit_sink.write(
                AuditEvent(
                    request_id=request_id,
                    event_type=event_type,
                    status=result.status,
                    action_class=task_request.action_class,
                    provider=result.provider,
                    evidence=tuple(result.evidence[:20]),
                )
            )
        except (RuntimeError, ValueError):
            raise HTTPException(
                status_code=503,
                detail="Audit persistence failed after task processing; inspect audit status",
            ) from None
    return result
