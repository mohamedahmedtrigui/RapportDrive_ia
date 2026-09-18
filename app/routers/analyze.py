from fastapi import APIRouter

from app.schemas import AnalyzeRequest, AnalyzeResponse
from app.services.groq_client import analyze_entries

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    outcome = analyze_entries(payload.entries)

    return AnalyzeResponse(results=outcome["results"], resume=outcome["resume"])
