import os
import re
from typing import TypedDict, Annotated
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

# ----------------------------------------------------------------------------
# Langue : arabe / français / anglais
# ----------------------------------------------------------------------------
RE_ARABE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
MOTS_EN = {"the", "what", "when", "how", "is", "are", "i", "my", "me", "hello", "hi", "thanks",
           "thank", "please", "can", "do", "does", "exam", "exams", "deadline", "medical",
           "certificate", "internship", "where", "which", "need", "want", "write", "request"}
MOTS_FR = {"le", "la", "les", "je", "est", "quel", "quelle", "quand", "comment", "mon", "ma", "mes",
           "des", "de", "un", "une", "pour", "et", "bonjour", "merci", "puis", "dois", "veux",
           "examen", "stage", "absence", "certificat"}


def texte_message(m) -> str:
    c = getattr(m, "content", "")
    return c if isinstance(c, str) else str(c)


def dernier_texte_humain(messages) -> str:
    for m in reversed(messages):
        if m.type == "human":
            return texte_message(m)
    return ""


def detecter_langue(texte: str) -> str:
    """Retourne 'ar', 'en' ou 'fr' (français par défaut)."""
    if RE_ARABE.search(texte):
        return "ar"
    mots = set(re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", texte.lower()))
    if len(mots & MOTS_EN) > len(mots & MOTS_FR):
        return "en"
    return "fr"


CONSIGNES_LANGUE = {
    "ar": (
        "LANGUE : l'étudiant écrit en arabe. Réponds en arabe (clair et simple). "
        "Garde le format « Article N » pour citer un article (tu peux ajouter « المادة N »). "
        "Garde les noms de modules, dates et heures tels que renvoyés par les outils. "
        "Quand tu appelles outil_recherche_reglement, formule la requête en FRANÇAIS, car le règlement est en français."
    ),
    "en": (
        "LANGUAGE: the student writes in English. Answer in English. Keep the format 'Article N' to cite an article. "
        "When you call outil_recherche_reglement, write the query in FRENCH, because the regulation is in French."
    ),
    "fr": "LANGUE : réponds en français.",
}


def fabriquer_prompt(base: str, extra: str = ""):
    """Prompt dynamique : le message système dépend de la langue du dernier message de l'étudiant."""
    def _prompt(state):
        msgs = state["messages"]
        lang = detecter_langue(dernier_texte_humain(msgs))
        consigne = base + ("\n" + extra if extra else "") + "\n" + CONSIGNES_LANGUE[lang]
        return [SystemMessage(content=consigne)] + msgs
    return _prompt


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
    """Recherche dans le règlement intérieur des examens par similarité (requête en français)."""
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
    prompt=fabriquer_prompt(
        "Tu es l'assistant de scolarité de l'ISET Charguia. Réponds uniquement à partir des outils. "
        "Cite toujours le numéro de l'article utilisé (ex: Article 4). "
        "Si l'outil ne trouve rien, dis que tu ne sais pas (dans la langue de l'étudiant)."
    )
)

agent_redaction_runnable = create_react_agent(
    llm,
    tools=[outil_generer_demande, outil_calendrier],
    prompt=fabriquer_prompt(
        "Tu aides l'étudiant à rédiger sa demande de rattrapage. "
        "Vérifie que tu as : nom, numero_etudiant, module et date_examen. "
        "S'il manque une information, demande-la poliment à l'étudiant avant d'appeler outil_generer_demande.",
        extra=(
            "IMPORTANT : le courrier officiel reste TOUJOURS en français, même si l'étudiant écrit en arabe. "
            "Quand outil_generer_demande renvoie la lettre, recopie-la en français, telle quelle. "
            "Tes questions et explications à l'étudiant (informations manquantes, etc.) restent dans sa langue."
        ),
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

# Salutations (français, anglais, arabe, dialecte tunisien)
SALUTATIONS = [
    "bonjour", "salut", "bonsoir", "coucou", "hello", "hi", "ça va",
    "صباح الخير", "مساء الخير", "السلام عليكم", "سلام", "مرحبا", "أهلا", "اهلا", "أهلاً", "عسلامة", "عسلامه",
    "3aslema", "aslema", "salam", "slm",
]
REMERCIEMENTS = ["merci", "thanks", "thank you", "شكرا", "شكراً", "يعطيك الصحة", "بارك الله فيك", "barcha merci"]


def _normaliser(texte: str) -> str:
    return re.sub(r"[!?.,،؟؛:;]+", " ", texte.lower()).strip()


def _commence_par(texte: str, mots: list[str]) -> bool:
    return any(texte == m or texte.startswith(m + " ") for m in mots)


def noeud_router(state: AgentState):
    messages = state["messages"]
    dernier_msg_texte = _normaliser(texte_message(messages[-1]))
    court = len(dernier_msg_texte.split()) <= 4

    # 1. Interception rapide des salutations et remerciements
    if court and _commence_par(dernier_msg_texte, REMERCIEMENTS):
        return {"route": "remerciement"}
    if court and _commence_par(dernier_msg_texte, SALUTATIONS):
        return {"route": "salutation"}

    # 2. Si l'assistant vient de demander des informations manquantes, on reste en rédaction
    if len(messages) >= 2 and messages[-2].type == "ai":
        avant_dernier = texte_message(messages[-2]).lower()
        mots_cles = ["besoin", "fournir", "nom", "numéro", "date", "module",
                     "أحتاج", "احتاج", "الاسم", "اسمك", "رقم", "تاريخ", "المادة", "المطلوب"]
        if any(mot in avant_dernier for mot in mots_cles):
            return {"route": "redaction"}

    # 3. Routage classique par le LLM pour les autres cas
    dernier_msg = texte_message(messages[-1])
    prompt_route = (
        "Classe la demande de l'étudiant en un seul mot parmi : "
        "'reglement' (questions sur les règles, dates, délais, absences, stage), "
        "'redaction' (rédiger une demande de rattrapage), "
        "'complet' (demande d'info + rédaction), ou "
        "'hors_sujet' (tout ce qui ne concerne pas la scolarité ou les examens).\n"
        "La demande peut être écrite en français, en arabe, en anglais ou en dialecte tunisien : "
        "réponds toujours avec l'un des mots ci-dessus, en lettres latines.\n"
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

TEXTES = {
    "salutation": {
        "fr": (
            "Bonjour ! 👋 Comment puis-je vous aider aujourd'hui ?\n\n"
            "Je peux vous renseigner sur le **règlement des examens**, vérifier le **calendrier** "
            "ou rédiger votre **demande de rattrapage** (article 8)."
        ),
        "ar": (
            "مرحبا بك! 👋 كيف يمكنني مساعدتك اليوم؟\n\n"
            "يمكنني الإجابة عن أسئلتك حول **نظام الامتحانات**، ومعرفة **روزنامة الامتحانات**، "
            "أو كتابة **مطلب الدورة الاستدراكية** (المادة 8)."
        ),
        "en": (
            "Hello! 👋 How can I help you today?\n\n"
            "I can answer questions about the **exam regulations**, check the **exam calendar**, "
            "or write your **make-up exam request** (article 8)."
        ),
    },
    "remerciement": {
        "fr": "Avec plaisir ! N'hésitez pas si vous avez une autre question. 😊",
        "ar": "على الرحب والسعة! لا تتردد إذا كان لديك سؤال آخر. 😊",
        "en": "You're welcome! Feel free to ask if you have another question. 😊",
    },
    "hors_sujet": {
        "fr": "Je suis uniquement l'assistant de scolarité de l'ISET Charguia. Je ne peux répondre qu'aux questions concernant le règlement, les examens et les demandes de rattrapage.",
        "ar": "أنا مساعد الدراسة والامتحانات بالمعهد العالي للدراسات التكنولوجية بالشرقية. لا يمكنني الإجابة إلا عن الأسئلة المتعلقة بالنظام الداخلي والامتحانات ومطالب الدورة الاستدراكية.",
        "en": "I'm only the academic-affairs assistant of ISET Charguia. I can only answer questions about the regulations, the exams and make-up exam requests.",
    },
}


def noeud_salutation(state: AgentState):
    lang = detecter_langue(dernier_texte_humain(state["messages"]))
    return {"messages": [AIMessage(content=TEXTES["salutation"][lang])], "route": "salutation"}


def noeud_remerciement(state: AgentState):
    lang = detecter_langue(dernier_texte_humain(state["messages"]))
    return {"messages": [AIMessage(content=TEXTES["remerciement"][lang])], "route": "remerciement"}


def noeud_hors_sujet(state: AgentState):
    lang = detecter_langue(dernier_texte_humain(state["messages"]))
    return {"messages": [AIMessage(content=TEXTES["hors_sujet"][lang])]}

def noeud_reglement(state: AgentState):
    res = agent_reglement_runnable.invoke({"messages": state["messages"]})
    reponse_finale = res["messages"][-1].content

    # Extraction des numéros d'articles renvoyés par les outils dans cet échange
    articles_vus = set()
    for m in res["messages"]:
        if m.type == "tool" and "'article':" in str(m.content):
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
builder.add_node("salutation", noeud_salutation)
builder.add_node("remerciement", noeud_remerciement)

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
        "hors_sujet": "hors_sujet",
        "salutation": "salutation",
        "remerciement": "remerciement",
    }
)
builder.add_edge("agent_reglement", END)
builder.add_edge("agent_redaction", END)
builder.add_edge("hors_sujet", END)
builder.add_edge("salutation", END)
builder.add_edge("remerciement", END)

memory = MemorySaver()
app = builder.compile(checkpointer=memory)