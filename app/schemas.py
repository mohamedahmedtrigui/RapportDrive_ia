from typing import Literal

from pydantic import BaseModel


class EntryIn(BaseModel):
    id: int
    description: str
    driver_nom: str | None = None
    client_nom: str | None = None


class AnalyzeRequest(BaseModel):
    entries: list[EntryIn]


class AnalyzeResult(BaseModel):
    id: int
    categorie: str
    severite: Literal["faible", "moyenne", "haute"]
    texte_normalise: str


class AnalyzeResponse(BaseModel):
    results: list[AnalyzeResult]
    resume: str = ""


class EmbedRequest(BaseModel):
    id: int
    text: str


class EmbedResponse(BaseModel):
    status: str
    id: int


class AskRequest(BaseModel):
    question: str
    top_k: int = 5


class AskResponse(BaseModel):
    answer: str
    sources: list[int]


class HealthResponse(BaseModel):
    status: str
