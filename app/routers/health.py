from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
