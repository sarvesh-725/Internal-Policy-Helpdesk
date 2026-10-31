from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.deps import CurrentCapabilities, CurrentUser, DatabaseSession
from app.graph.runner import SupportGraphRunner
from app.schemas import ReviewDecisionCreate, ReviewTaskResponse
from app.services.events import ThreadEventService
from app.services.review import ReviewTaskService
from app.tools.mock_adapters import MockReviewToolAdapter

router = APIRouter(prefix="/review/tasks", tags=["review"])


@router.get("", response_model=list[ReviewTaskResponse])
def list_review_tasks(user: CurrentUser, db: DatabaseSession) -> list[ReviewTaskResponse]:
    return ReviewTaskService().list_for_reviewer(db, user)


@router.get("/{task_id}", response_model=ReviewTaskResponse)
def get_review_task(task_id: UUID, user: CurrentUser, db: DatabaseSession) -> ReviewTaskResponse:
    try:
        task = MockReviewToolAdapter().get_demo_case_status(db, task_id=task_id, actor=user)
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Review task not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="You cannot view this review task.") from exc
    return ReviewTaskService._to_response(task)


@router.post("/{task_id}/decision", response_model=ReviewTaskResponse)
def decide_review_task(task_id: UUID, body: ReviewDecisionCreate, background_tasks: BackgroundTasks, user: CurrentUser, capabilities: CurrentCapabilities, db: DatabaseSession) -> ReviewTaskResponse:
    try:
        task = MockReviewToolAdapter().resume_mock_review(db, task_id=task_id, reviewer=user, capabilities=capabilities, decision=body.decision, edited_response=body.edited_response)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Review task not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="You cannot decide this review task.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    ThreadEventService().emit(db, thread_id=task.thread_id, request_id=task.request_id, event_type="review_decision_recorded", payload={"decision": body.decision.value})
    db.commit()
    background_tasks.add_task(SupportGraphRunner().resume, thread_id=task.thread_id, decision={"decision": body.decision.value, "edited_response": task.edited_response})
    return ReviewTaskService._to_response(task)
