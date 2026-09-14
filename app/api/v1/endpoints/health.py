from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Returns the operational status of the LOGO Backend service.",
    tags=["Health"],
)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", service="LOGO Backend")
