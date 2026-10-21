from app.policy import evaluate_task
from app.schemas import TaskRequest, TaskResponse

class Orchestrator:
    """Safe orchestration shell; no provider or external action is enabled by default."""

    def run(self, request: TaskRequest) -> TaskResponse:
        decision = evaluate_task(require_approval=request.require_approval, action_class=request.action_class)
        if not decision.allowed:
            return TaskResponse(status="DEGRADED", message=decision.reason, evidence=["policy:deny"])
        if decision.requires_human_approval:
            return TaskResponse(status="NOT VERIFIED", message=decision.reason, evidence=["policy:approval-required"])
        return TaskResponse(
            status="NOT VERIFIED",
            message="No provider adapter is registered; no inference was performed.",
            evidence=["provider:none", "execution:none"],
        )
