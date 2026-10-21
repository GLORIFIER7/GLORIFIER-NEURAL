import os
import secrets

from fastapi import FastAPI, Header, HTTPException

from app.neural.torch_status import pytorch_status
from app.orchestrator import Orchestrator
from app.schemas import HealthResponse, TaskRequest, TaskResponse

app = FastAPI(
    title="GLORIFIER Neural Orchestration",
    version="0.2.0",
    description="Governed, provider-neutral AI orchestration API.",
)
orchestrator = Orchestrator()


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
