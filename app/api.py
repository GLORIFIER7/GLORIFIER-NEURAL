import os
from fastapi import FastAPI, HTTPException
from app.neural.torch_status import pytorch_status
from app.orchestrator import Orchestrator
from app.schemas import HealthResponse, TaskRequest, TaskResponse

app = FastAPI(title="GLORIFIER Neural Orchestration", version="0.2.0",
              description="Governed, provider-neutral AI orchestration API.")
orchestrator = Orchestrator()
API_TOKEN = os.getenv("GLORIFIER_API_TOKEN")

@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    # Process health is not evidence of provider or database connectivity.
    return HealthResponse(
        status="PARTIALLY VERIFIED", service="glorifier-neural",
        checks={"process": "VERIFIED", "providers": "NOT OBSERVABLE",
                "database": "NOT OBSERVABLE", "pytorch": pytorch_status()["installed"] and "VERIFIED" or "NOT VERIFIED"},
    )

@app.post("/v1/tasks", response_model=TaskResponse, tags=["orchestration"])
def run_task(request: TaskRequest, authorization: str | None = None) -> TaskResponse:
    if API_TOKEN and authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not API_TOKEN and os.getenv("GLORIFIER_REQUIRE_API_TOKEN", "true").lower() == "true":
        raise HTTPException(status_code=503, detail="API token is not configured; execution endpoint is disabled")
    return orchestrator.run(request)
