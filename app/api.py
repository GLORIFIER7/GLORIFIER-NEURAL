import os

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
    # Process health is not evidence of provider or database connectivity.
    pytorch_installed = pytorch_status()["installed"]
    return HealthResponse(
        status="PARTIALLY VERIFIED",
        service="glorifier-neural",
        checks={
            "process": "VERIFIED",
            "providers": "NOT OBSERVABLE",
            "database": "NOT OBSERVABLE",
            "pytorch": "VERIFIED" if pytorch_installed else "NOT VERIFIED",
        },
    )


@app.post("/v1/tasks", response_model=TaskResponse, tags=["orchestration"])
def run_task(
    request: TaskRequest,
    authorization: str | None = Header(default=None),
) -> TaskResponse:
    api_token = os.getenv("GLORIFIER_API_TOKEN")
    if api_token and authorization != f"Bearer {api_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not api_token and os.getenv("GLORIFIER_REQUIRE_API_TOKEN", "true").lower() == "true":
        raise HTTPException(
            status_code=503,
            detail="API token is not configured; execution endpoint is disabled",
        )
    return orchestrator.run(request)
