from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.persistence.database import get_db
from app.policy.enforcement import PolicyEnforcementPoint
from app.schemas import CapabilitySet, UserContext

DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[UserContext, Depends(get_current_user)]


def get_capabilities(user: CurrentUser) -> CapabilitySet:
    return PolicyEnforcementPoint().capabilities_for(user)


CurrentCapabilities = Annotated[CapabilitySet, Depends(get_capabilities)]
