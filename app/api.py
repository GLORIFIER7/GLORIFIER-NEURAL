import os
import re
import secrets
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.audit import AuditEvent, SupabaseRestAuditSink
from app.database.neon import NeonConnectivityProbe
from app.neural.torch_status import pytorch_status
from app.runtime import build_orchestrator_from_environment
from app.request_limits import RequestBodyLimitMiddleware
from app.rate_limit import FixedWindowRateLimiter
from app.schemas import HealthResponse, TaskRequest, TaskResponse

NOT_VERIFIED = "NOT VERIFIED"

app = FastAPI(
    title="GLORIFIER Neural Orchestration",
    version="0.2.0",
    description="Governed, provider-neutral AI orchestration API.",
)
orchestrator = build_orchestrator_from_environment()
MAX_REQUEST_BODY_BYTES = 65_536
TASK_RATE_LIMITER = FixedWindowRateLimiter(max_requests=60, window_seconds=60)
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=MAX_REQUEST_BODY_BYTES)


_CORRELATION_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$"
)


def _request_correlation_id(request: Request) -> str:
    """Preserve only a canonical UUID-shaped correlation value; otherwise generate one."""
    candidate = request.headers.get("x-correlation-id", "").strip()
    if _CORRELATION_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Propagate a bounded correlation ID into logs and back to the caller."""
    request_id = str(uuid.uuid4())
    correlation_id = _request_correlation_id(request)
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
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
    response.headers.update(_security_response_headers(request))
    return response


def _security_response_headers(request: Request) -> dict[str, str]:
    """Build the bounded tracing and security headers for every response path."""
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

    correlation_id = getattr(request.state, "correlation_id", None)
    if not correlation_id:
        correlation_id = _request_correlation_id(request)
        request.state.correlation_id = correlation_id

    return {
        "X-Request-ID": request_id,
        "X-Correlation-ID": correlation_id,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }


@app.exception_handler(Exception)
async def unhandled_exception_response(request: Request, _exc: Exception) -> JSONResponse:
    """Keep unhandled 500 responses generic while retaining request tracing headers."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers=_security_response_headers(request),
    )


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    """Report process health separately from unverified provider and database health."""
    pytorch_installed = pytorch_status()["installed"]
    return HealthResponse(
        status="PARTIALLY VERIFIED",
        service="glorifier-neural",
        checks={
            "process": "VERIFIED",
            "providers": NOT_VERIFIED,
            "database": NOT_VERIFIED,
            "pytorch": "VERIFIED" if pytorch_installed else NOT_VERIFIED,
        },
    )


@app.get("/ready", tags=["operations"])
def readiness() -> JSONResponse:
    """Return 503 until provider readiness is verified.

    A configured Neon probe is read-only and opt-in. A successful database probe
    alone does not make the service ready while provider readiness is unverified.
    """
    database_status = NOT_VERIFIED
    try:
        probe = NeonConnectivityProbe.from_environment()
        if probe is not None:
            probe.check()
            database_status = "VERIFIED"
    except Exception:  # noqa: BLE001 - readiness must not leak connection details
        database_status = "DEGRADED"

    return JSONResponse(
        status_code=503,
        content={
            "status": "NOT READY",
            "checks": {
                "providers": NOT_VERIFIED,
                "database": database_status,
            },
            "message": (
                "Provider readiness is not verified; database status reflects only "
                "an opt-in connectivity probe."
            ),
        },
    )


@app.post("/v1/tasks", response_model=TaskResponse, tags=["orchestration"])
def run_task(
    task_request: TaskRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> TaskResponse:
    """Process a governed task request.

    Raises:
        HTTPException: 503 when the API token is missing or configured audit
            persistence is unavailable; 401 when the bearer token is invalid;
            429 when the authenticated caller exceeds the task rate limit.
        HTTPException: 503 when required audit persistence fails before or after
            orchestration. Pre-execution audit failures prevent task processing.
    """
    api_token = os.getenv("GLORIFIER_API_TOKEN")
    if not api_token:
        raise HTTPException(
            status_code=503,
            detail="API token is not configured; execution endpoint is disabled",
        )
    if not secrets.compare_digest(authorization or "", f"Bearer {api_token}"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Use the direct peer address; never trust spoofable forwarded headers here.
    client_host = request.client.host if request.client else "unknown"
    allowed, retry_after = TASK_RATE_LIMITER.allow(client_host, api_token)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Task rate limit exceeded; retry after the current minute window",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        audit_sink = SupabaseRestAuditSink.from_environment()
    except ValueError:
        # Never include environment values or credential details in client-facing errors.
        raise HTTPException(status_code=503, detail="Configured audit persistence is unavailable") from None

    request_id = request.state.request_id
    correlation_id = request.state.correlation_id
    if audit_sink is not None:
        try:
            # Pre-execution audit write: if it fails, do not start task processing.
            audit_sink.write(
                AuditEvent(
                    request_id=request_id,
                    correlation_id=correlation_id,
                    event_type="task_received",
                    status=NOT_VERIFIED,
                    action_class=task_request.action_class,
                    evidence=("execution:not-started",),
                )
            )
        except Exception:  # noqa: BLE001 - persistence must fail closed for all error types
            # Fail closed for any persistence failure without exposing implementation details.
            raise HTTPException(status_code=503, detail="Audit persistence unavailable; task not executed") from None

    result = orchestrator.run(task_request)

    if audit_sink is not None:
        event_type = _audit_event_type(result)
        try:
            audit_sink.write(
                AuditEvent(
                    request_id=request_id,
                    correlation_id=correlation_id,
                    event_type=event_type,
                    status=result.status,
                    action_class=task_request.action_class,
                    provider=result.provider,
                    evidence=tuple(result.evidence[:20]),
                )
            )
        except Exception:  # noqa: BLE001 - persistence must fail closed for all error types
            # Processing may have completed; report the audit failure without leaking internals.
            raise HTTPException(
                status_code=503,
                detail="Audit persistence failed after task processing; inspect audit status",
            ) from None
    return result


def _audit_event_type(result: TaskResponse) -> str:
    """Map bounded orchestration evidence to a sanitized audit event category."""
    if "policy:deny" in result.evidence:
        return "policy_denied"
    if "policy:approval-required" in result.evidence:
        return "approval_required"
    if "execution:failed" in result.evidence:
        return "inference_failed"
    if "execution:inference" in result.evidence:
        return "inference_completed"
    return "task_not_executed"
