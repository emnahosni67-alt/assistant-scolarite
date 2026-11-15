import os
from typing import TypedDict, Annotated, Literal
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from core.tools import get_calendrier, calcul_delai, generer_demande
from rag.store import search_reglement, lire_article_direct
from agent.guardrails import guard, verifier_citations

load_dotenv()

llm = ChatOpenAI(
    base_url=os.getenv('LLM_BASE_URL'),
    api_key=os.getenv('LLM_API_KEY'),
    model=os.getenv('MODEL_NAME'),
    temperature=0.1
)

# --- Définition des outils LangChain ---
@tool
def outil_calendrier(module: str):
    """Retourne les dates d'examen et de rattrapage d'un module."""
    return get_calendrier(module)

@tool
def outil_calcul_delai(date_examen: str, hospitalisation: bool = False):
    """Calcule la date limite pour déposer un certificat médical (format JJ/MM/AAAA)."""
    return calcul_delai(date_examen, hospitalisation)

@tool
def outil_recherche_reglement(question: str):
    """Recherche dans le règlement intérieur des examens par similarité."""
    return search_reglement(question)

@tool
def outil_article_direct(numero: int):
    """Lit directement un article précis du règlement (numéros 1 à 15)."""
    return lire_article_direct(numero)

@tool
def outil_generer_demande(nom: str, numero_etudiant: str, module: str, date_examen: str):
    """Rédige la lettre officielle de demande de rattrapage une fois tous les champs fournis."""
    return generer_demande(nom, numero_etudiant, module, date_examen)

# --- Sous-agents ReAct ---
agent_reglement_runnable = create_react_agent(
    llm,
    tools=[outil_recherche_reglement, outil_article_direct, outil_calendrier, outil_calcul_delai],
    prompt=(
        "Tu es l'assistant de scolarité de l'ISET Charguia. Réponds uniquement à partir des outils. "
        "Cite toujours le numéro de l'article utilisé (ex: Article 4). "
        "Si l'outil ne trouve rien, réponds : Je ne sais pas."
    )
)

agent_redaction_runnable = create_react_agent(
    llm,
    tools=[outil_generer_demande, outil_calendrier],
    prompt=(
        "Tu aides l'étudiant à rédiger sa demande de rattrapage. "
        "Vérifie que tu as : nom, numero_etudiant, module et date_examen. "
        "S'il manque une information, demande-la poliment à l'étudiant avant d'appeler outil_generer_demande."
    )
)

# --- État du graphe ---
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    route: str
    bloque: bool

# --- Nœuds du graphe ---
def noeud_guard(state: AgentState):
    dernier_msg = state["messages"][-1].content
    refus = guard(dernier_msg)
    if refus:
        return {"messages": [AIMessage(content=refus)], "bloque": True}
    return {"bloque": False}

def noeud_router(state: AgentState):
    messages = state["messages"]
    # Si l'assistant vient de demander des informations manquantes, on reste impérativement en rédaction
    if len(messages) >= 2 and messages[-2].type == "ai":
        avant_dernier = messages[-2].content.lower()
        if any(mot in avant_dernier for mot in ["besoin", "fournir", "nom", "numéro", "date", "module"]):
            return {"route": "redaction"}

    dernier_msg = messages[-1].content
    prompt_route = (
        "Classe la demande de l'étudiant en un seul mot parmi : "
        "'reglement' (questions sur les règles, dates, délais, absences), "
        "'redaction' (rédiger une demande de rattrapage), "
        "'complet' (demande d'info + rédaction), ou "
        "'hors_sujet' (tout ce qui ne concerne pas la scolarité ou les examens).\n"
        f"Demande : {dernier_msg}\nRéponse (un seul mot) :"
    )
    choix = llm.invoke([SystemMessage(content=prompt_route)]).content.strip().lower()
    if "redaction" in choix or "complet" in choix:
        route = "redaction"
    elif "reglement" in choix:
        route = "reglement"
    else:
        route = "hors_sujet"
    return {"route": route}

def noeud_hors_sujet(state: AgentState):
    msg = "Je suis uniquement l'assistant de scolarité de l'ISET Charguia. Je ne peux répondre qu'aux questions concernant le règlement, les examens et les demandes de rattrapage."
    return {"messages": [AIMessage(content=msg)]}

def noeud_reglement(state: AgentState):
    res = agent_reglement_runnable.invoke({"messages": state["messages"]})
    reponse_finale = res["messages"][-1].content
    
    # Extraction des numéros d'articles renvoyés par les outils dans cet échange
    articles_vus = set()
    for m in res["messages"]:
        if m.type == "tool" and "'article':" in str(m.content):
            import re
            for num in re.findall(r"'article':\s*(\d+)", str(m.content)):
                articles_vus.add(int(num))
                
    reponse_verifiee = verifier_citations(reponse_finale, articles_vus)
    return {"messages": [AIMessage(content=reponse_verifiee)]}

def noeud_redaction(state: AgentState):
    res = agent_redaction_runnable.invoke({"messages": state["messages"]})
    return {"messages": [res["messages"][-1]]}

# --- Construction et compilation du graphe ---
builder = StateGraph(AgentState)
builder.add_node("guard", noeud_guard)
builder.add_node("router", noeud_router)
builder.add_node("hors_sujet", noeud_hors_sujet)
builder.add_node("agent_reglement", noeud_reglement)
builder.add_node("agent_redaction", noeud_redaction)

builder.add_edge(START, "guard")
builder.add_conditional_edges(
    "guard",
    lambda s: END if s.get("bloque") else "router"
)
builder.add_conditional_edges(
    "router",
    lambda s: s["route"],
    {
        "reglement": "agent_reglement",
        "redaction": "agent_redaction",
        "hors_sujet": "hors_sujet"
    }
)
builder.add_edge("agent_reglement", END)
builder.add_edge("agent_redaction", END)
builder.add_edge("hors_sujet", END)

memory = MemorySaver()
app = builder.compile(checkpointer=memory)