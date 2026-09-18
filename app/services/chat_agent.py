import json
from datetime import date

import pymysql
from openai import OpenAI

from app.config import get_settings
from app.services import db_client, vector_store

_settings = get_settings()
_client = OpenAI(api_key=_settings.groq_api_key, base_url=_settings.groq_api_base)

MAX_ITERATIONS = 5

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_entries",
            "description": (
                "Recherche des entrees de rapport (incidents) selon des filtres precis. A utiliser pour toute "
                "question portant sur un chauffeur, un client, une zone, une categorie, une severite ou une "
                "periode donnee. Renvoie une liste paginee, la plus recente en premier."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chauffeur": {"type": ["string", "null"], "description": "Nom (ou partie du nom) du chauffeur"},
                    "client": {"type": ["string", "null"], "description": "Nom (ou partie du nom) du client"},
                    "zone": {"type": ["string", "null"], "description": "Nom de la zone"},
                    "categorie": {"type": ["string", "null"], "description": "Categorie de l'incident (ex: retard, comportement, securite)"},
                    "severite": {"type": ["string", "null"], "enum": ["faible", "moyenne", "haute", None]},
                    "from": {"type": ["string", "null"], "description": "Date de debut au format YYYY-MM-DD"},
                    "to": {"type": ["string", "null"], "description": "Date de fin au format YYYY-MM-DD"},
                    "per_page": {"type": ["integer", "null"], "description": "Nombre max de resultats, 10 par defaut, 30 maximum"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_cited_drivers",
            "description": (
                "Renvoie les chauffeurs les plus cites dans des incidents, groupes par categorie, avec le nombre "
                "d'occurrences. A utiliser pour identifier les chauffeurs problematiques ou comparer une tendance "
                "sur une periode (ex: qui se degrade ce mois-ci)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "categorie": {"type": ["string", "null"]},
                    "from": {"type": ["string", "null"], "description": "Date de debut au format YYYY-MM-DD"},
                    "to": {"type": ["string", "null"], "description": "Date de fin au format YYYY-MM-DD"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dashboard_stats",
            "description": (
                "Renvoie des chiffres globaux fiables : nombre total de rapports, nombre total d'entrees, nombre "
                "d'entrees deja analysees par l'IA. A utiliser pour toute question de comptage ou de total."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": (
                "Recherche semantique dans le texte normalise des incidents, pour les questions ouvertes qui ne "
                "correspondent a aucun filtre precis (ex: 'des plaintes sur la proprete du vehicule')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": ["integer", "null"]},
                },
                "required": ["query"],
            },
        },
    },
]


def _run_tool(name: str, arguments: dict, sources: set[int]) -> str:
    try:
        if name == "search_entries":
            per_page = min(int(arguments.get("per_page") or 10), 30)
            data = db_client.search_entries(
                chauffeur=arguments.get("chauffeur"),
                client=arguments.get("client"),
                zone=arguments.get("zone"),
                categorie=arguments.get("categorie"),
                severite=arguments.get("severite"),
                date_from=arguments.get("from"),
                date_to=arguments.get("to"),
                per_page=per_page,
            )
            sources.update(row["id"] for row in data["entries"] if row.get("id") is not None)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "top_cited_drivers":
            rows = db_client.top_cited_drivers(
                categorie=arguments.get("categorie"),
                date_from=arguments.get("from"),
                date_to=arguments.get("to"),
            )
            return json.dumps(rows, ensure_ascii=False, default=str)

        if name == "dashboard_stats":
            return json.dumps(db_client.dashboard_stats(), ensure_ascii=False, default=str)

        if name == "semantic_search":
            matches = vector_store.query_similar(arguments.get("query", ""), int(arguments.get("top_k") or 5))
            sources.update(m["entry_id"] for m in matches)
            return json.dumps(matches, ensure_ascii=False)

        return json.dumps({"error": f"Outil inconnu: {name}"})
    except pymysql.MySQLError as exc:
        return json.dumps({"error": f"Erreur base de donnees: {exc}"})


_SYSTEM_PROMPT = (
    "Tu es l'assistant IA de MiralDrive, une plateforme de gestion de rapports d'incidents de transport "
    "(chauffeurs, clients, zones). Reponds en francais, de maniere concise et factuelle. "
    f"Nous sommes le {date.today().isoformat()}. "
    "Tu disposes d'outils pour interroger les vraies donnees de l'application (recherche d'entrees, "
    "chauffeurs les plus cites, statistiques globales, recherche semantique) — utilise-les activement, y compris "
    "plusieurs fois de suite si necessaire, plutot que de deviner ou de dire que tu ne peux pas repondre. "
    "Pour une question de comptage/total, utilise dashboard_stats. Pour une question de tendance ou de "
    "degradation sur une periode, compare avec top_cited_drivers ou search_entries filtres par dates. "
    "Ne reponds JAMAIS a partir de connaissances generales sur le transport : base-toi uniquement sur ce que "
    "les outils renvoient. Si les outils ne permettent pas de repondre, dis-le clairement."
)


def run_agent(question: str, top_k: int = 5) -> dict:
    sources: set[int] = set()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for _ in range(MAX_ITERATIONS):
        response = _client.chat.completions.create(
            model=_settings.groq_model,
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            return {"answer": message.content or "", "sources": sorted(sources)}

        messages.append(message.model_dump(exclude_unset=True))

        for call in tool_calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            result = _run_tool(call.function.name, arguments, sources)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    # Ran out of iterations — force a final plain-text answer from whatever was gathered.
    final = _client.chat.completions.create(
        model=_settings.groq_model,
        messages=messages,
        tool_choice="none",
    )
    return {"answer": final.choices[0].message.content or "", "sources": sorted(sources)}
