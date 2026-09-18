from fastapi import APIRouter

from app.schemas import EmbedRequest, EmbedResponse
from app.services.vector_store import upsert_entry

router = APIRouter()


@router.post("/embed", response_model=EmbedResponse)
def embed(payload: EmbedRequest) -> EmbedResponse:
    upsert_entry(payload.id, payload.text)

    return EmbedResponse(status="ok", id=payload.id)
