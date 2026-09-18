from fastapi import APIRouter

from app.schemas import AskRequest, AskResponse
from app.services.chat_agent import run_agent

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    result = run_agent(payload.question, payload.top_k)

    return AskResponse(answer=result["answer"], sources=result["sources"])
