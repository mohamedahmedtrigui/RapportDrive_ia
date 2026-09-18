import json

from openai import OpenAI

from app.config import get_settings
from app.schemas import AnalyzeResult, EntryIn

_settings = get_settings()
_client = OpenAI(api_key=_settings.groq_api_key, base_url=_settings.groq_api_base)

_ANALYSIS_TOOL = {
    "type": "function",
    "function": {
        "name": "report_analysis",
        "description": "Renvoie l'analyse structuree de chaque entree de rapport.",
        "parameters": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "categorie": {"type": "string"},
                            "severite": {
                                "type": "string",
                                "enum": ["faible", "moyenne", "haute"],
                            },
                            "texte_normalise": {"type": "string"},
                        },
                        "required": ["id", "categorie", "severite", "texte_normalise"],
                    },
                },
                "resume": {
                    "type": "string",
                    "description": (
                        "Resume court (2-3 phrases, en francais) des elements graves ou problematiques a "
                        "signaler a un manager, base uniquement sur les entrees de severite 'haute' ou "
                        "'moyenne' presentes dans ce lot — un vrai recap des elements a surveiller. Nomme "
                        "explicitement le chauffeur concerne par son nom (champ driver_nom de l'entree) et, "
                        "si l'entree porte sur un client identifie (champ client_nom), nomme aussi ce client, "
                        "pour chaque incident cite — jamais juste 'un chauffeur'/'un client' ou "
                        "'le chauffeur'/'le client' si un nom est fourni. Si aucun chauffeur ni client n'est "
                        "rattache a l'entree, formule sans nom. Chaine vide si aucune entree ne necessite "
                        "une attention particuliere (tout est en severite 'faible')."
                    ),
                },
            },
            "required": ["results", "resume"],
        },
    },
}

_ANALYZE_SYSTEM_PROMPT = (
    "Tu es un assistant qui analyse des rapports d'incidents de transport (chauffeurs, clients, service). "
    "Chaque entree peut inclure un champ driver_nom (nom du chauffeur concerne) et/ou un champ client_nom "
    "(nom du client concerne), s'ils sont identifies. "
    "Pour chaque entree fournie, determine une categorie courte (ex: retard, comportement, securite, proprete, "
    "mecanique, autre), une severite parmi faible/moyenne/haute, et reformule le texte en une phrase normalisee "
    "et concise en francais — integre le nom du chauffeur et/ou du client dans cette reformulation quand "
    "driver_nom et/ou client_nom sont fournis. "
    "Produis aussi un resume global (champ resume), veritable recap des elements a surveiller pour ce lot, en "
    "nommant explicitement le ou les chauffeurs (via driver_nom) et le ou les clients (via client_nom) "
    "concernes plutot que de rester generique. "
    "Reponds uniquement via l'outil report_analysis, un resultat par entree recue."
)


def analyze_entries(entries: list[EntryIn]) -> dict:
    payload = [entry.model_dump() for entry in entries]

    response = _client.chat.completions.create(
        model=_settings.groq_model,
        messages=[
            {"role": "system", "content": _ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"entries": payload}, ensure_ascii=False)},
        ],
        tools=[_ANALYSIS_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_analysis"}},
    )

    tool_calls = response.choices[0].message.tool_calls or []

    if not tool_calls:
        # Fallback in case a given Groq model ignores the forced tool_choice:
        # retry with JSON mode and manual parsing instead of failing outright.
        return _analyze_entries_json_fallback(entries)

    arguments = json.loads(tool_calls[0].function.arguments)

    return {
        "results": [AnalyzeResult(**item) for item in arguments["results"]],
        "resume": arguments.get("resume") or "",
    }


def _analyze_entries_json_fallback(entries: list[EntryIn]) -> dict:
    payload = [entry.model_dump() for entry in entries]

    response = _client.chat.completions.create(
        model=_settings.groq_model,
        messages=[
            {
                "role": "system",
                "content": _ANALYZE_SYSTEM_PROMPT + (
                    ' Reponds UNIQUEMENT avec un objet JSON de la forme '
                    '{"results": [{"id": int, "categorie": str, "severite": str, "texte_normalise": str}], '
                    '"resume": str}.'
                ),
            },
            {"role": "user", "content": json.dumps({"entries": payload}, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )

    data = json.loads(response.choices[0].message.content)

    return {
        "results": [AnalyzeResult(**item) for item in data["results"]],
        "resume": data.get("resume") or "",
    }
