from typing import Literal
from pydantic import BaseModel, Field

Status = Literal["FULLY VERIFIED", "VERIFIED", "PARTIALLY VERIFIED", "NOT VERIFIED", "DEGRADED", "NOT OBSERVABLE"]

class HealthResponse(BaseModel):
    status: Status
    service: str
    checks: dict[str, Status | str]

class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20_000)
    purpose: str = Field(default="general", min_length=1, max_length=100)
    require_approval: bool = True
    action_class: str = "read_only"

class TaskResponse(BaseModel):
    status: Status
    provider: str | None = None
    result: str | None = None
    evidence: list[str] = Field(default_factory=list)
    message: str
