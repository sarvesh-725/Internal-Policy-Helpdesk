from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas import CurrentUserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUserResponse)
def get_me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        subject=user.subject,
        username=user.username,
        roles=sorted(user.roles, key=str),
        region=user.region,
    )
