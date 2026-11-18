"""
Portail étudiant ISET Charguia – assistant de scolarité (agent IA).
Interface Streamlit. Nécessite streamlit >= 1.39 (clés de widgets -> classes CSS).

Logo : le fichier images.jpg placé à côté de app.py (ex. E:\\assistant-scolarite\\images.jpg)
est recadré automatiquement (le fond blanc est retiré), puis utilisé :
barre de navigation, icône de l'onglet, avatar de l'assistant.
Prénom affiché : variable d'environnement STUDENT_NAME (prénom fictif en démo).
"""
import base64
import html
import os
import time
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path

import streamlit as st
from langchain_core.messages import HumanMessage

from agent.graph import app as langgraph_app
from core.mailer import send_demande

# ----------------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------------
PRENOM = os.getenv("STUDENT_NAME", "Emna")
MAX_QUESTION = 500  # limite de longueur (garde-fou sécurité)

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
CANDIDATS_LOGO = [
    BASE_DIR / "images.jpg",
    BASE_DIR.parent / "images.jpg",
    BASE_DIR / "assets" / "logo_iset.png",
    BASE_DIR / "assets" / "logo_iset.jpg",
]

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]

# Calendrier de la session de janvier 2027 (affichage uniquement : l'agent,
# lui, passe toujours par l'outil MCP get_calendrier).
EXAMENS = [
    ("Algorithmique", date(2027, 1, 5), "9h, amphi A", date(2027, 1, 13), "14h, salle B10"),
    ("Bases de données", date(2027, 1, 8), "9h, amphi A", date(2027, 1, 15), "9h, salle B12"),
    ("Réseaux", date(2027, 1, 11), "9h, amphi B", date(2027, 1, 18), "9h, salle B14"),
    ("Anglais", date(2027, 1, 12), "14h, salle B11", date(2027, 1, 19), "10h, salle B11"),
]
PROJET_REMISE = date(2027, 1, 20)

SUJETS = {
    "topic_cert": ("📜 **Certificat médical**", "Quel est le délai exact pour déposer un certificat médical en cas d'absence à un examen ?"),
    "topic_cal": ("📅 **Dates d'examen**", "Quelles sont les dates d'examen et de rattrapage pour le module Algorithmique ?"),
    "topic_demande": ("✍️ **Demande de rattrapage**", "Je veux rédiger une demande officielle de rattrapage pour mon absence."),
    "topic_stage": ("🧳 **Mon stage**", "Quelle est la durée minimale du stage et quand dois-je déposer la convention ?"),
}


def fr_date(d: date) -> str:
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


@lru_cache(maxsize=1)
def charger_logo() -> tuple[str | None, str]:
    """Retourne (chemin du logo recadré, data-URI pour le HTML).

    Le JPG d'origine a beaucoup de blanc autour : on le recadre sur le dessin.
    Sans logo trouvé, on retourne (None, "") et l'app affiche un texte à la place.
    """
    source = next((p for p in CANDIDATS_LOGO if p.exists()), None)
    if source is None:
        return None, ""
    chemin = source
    try:
        from PIL import Image, ImageChops  # Pillow est déjà installé avec Streamlit

        img = Image.open(source).convert("RGB")
        fond = Image.new("RGB", img.size, (255, 255, 255))
        masque = ImageChops.difference(img, fond).convert("L").point(lambda p: 255 if p > 30 else 0)
        bbox = masque.getbbox()
        if bbox:
            m = 6
            bbox = (max(bbox[0] - m, 0), max(bbox[1] - m, 0),
                    min(bbox[2] + m, img.width), min(bbox[3] + m, img.height))
            img = img.crop(bbox)
        CACHE_DIR.mkdir(exist_ok=True)
        chemin = CACHE_DIR / "logo_iset_recadre.png"
        img.save(chemin)
    except Exception:  # noqa: BLE001 - on retombe sur l'image d'origine
        chemin = source
    mime = "image/png" if chemin.suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(chemin.read_bytes()).decode()
    return str(chemin), f"data:{mime};base64,{data}"


LOGO_PATH, LOGO_URI = charger_logo()
AVATAR_BOT = LOGO_PATH or "🎓"
AVATAR_USER = "🧑‍🎓"

# ----------------------------------------------------------------------------
# Page + style
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Assistant de scolarité • ISET Charguia",
    page_icon=LOGO_PATH or "🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=DM+Sans:wght@400;500;700&display=swap');

/* Palette tirée du logo ISET : bleu roi, turquoise, jaune */
:root {
    --nuit: #14235C;
    --ciel: #2F5BD6;
    --soleil: #FFB703;
    --turquoise: #5CC3CC;
    --rose: #FF7A9A;
    --lilas: #8B7CF6;
    --fond: #F3F6FF;
    --texte: #1B2340;
    --texte-doux: #5B6485;
    --trait: #DCE3FF;
}

html, body, [class*="css"], .stApp { font-family: 'DM Sans', sans-serif; color: var(--texte); }
.stApp { background: var(--fond); }
header[data-testid="stHeader"], [data-testid="stSidebar"], footer { display: none; }
.block-container { padding-top: 1rem; padding-bottom: 6rem; max-width: 1240px; }
h1, h2, h3, .titre { font-family: 'Bricolage Grotesque', sans-serif; }

/* ---------- Barre de navigation ---------- */
.nav {
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
    background: #fff; border-radius: 999px; padding: 0.4rem 0.6rem 0.4rem 0.5rem;
    border: 1px solid var(--trait); margin-bottom: 1.1rem;
}
.marque { display: flex; align-items: center; gap: 0.8rem; }
.marque img { height: 56px; width: auto; display: block; }
.marque .nom { line-height: 1.15; }
.marque .nom b { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.05rem; color: var(--nuit); display: block; }
.marque .nom span { font-size: 0.8rem; color: var(--texte-doux); }
.nav-liens { display: flex; gap: 0.4rem; font-weight: 500; font-size: 0.92rem; color: var(--texte-doux); }
.nav-liens a, .nav-liens a:visited { padding: 0.45rem 0.95rem; border-radius: 999px; color: var(--texte-doux); text-decoration: none; transition: background .15s ease, color .15s ease; }
.nav-liens a:hover { background: var(--fond); color: var(--nuit); }
.nav-liens a.actif { background: var(--nuit); color: #fff; }
html { scroll-behavior: smooth; }
.nav-profil { display: flex; align-items: center; gap: 0.6rem; font-weight: 700; font-size: 0.92rem; }
.nav-profil .rond {
    width: 38px; height: 38px; border-radius: 50%; background: var(--soleil); color: var(--nuit);
    display: grid; place-items: center; font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800;
}
@media (max-width: 860px) { .nav-liens { display: none; } }

/* ---------- Hero ---------- */
.hero {
    position: relative; overflow: hidden; background: var(--nuit); color: #fff;
    border-radius: 32px; padding: 2.6rem 2.8rem; margin-bottom: 1.4rem; min-height: 330px;
    background-image: radial-gradient(rgba(255,255,255,.09) 1.5px, transparent 1.5px);
    background-size: 22px 22px;
}
.hero .soleil { position: absolute; right: -90px; bottom: -110px; width: 360px; height: 360px; border-radius: 50%; background: var(--soleil); }
.hero .anneau { position: absolute; right: 270px; top: -70px; width: 190px; height: 190px; border-radius: 50%; border: 26px solid var(--turquoise); opacity: .9; }
.hero .petit { position: absolute; left: 46%; bottom: 34px; width: 22px; height: 22px; border-radius: 50%; background: var(--rose); }
.hero-texte { position: relative; max-width: 560px; z-index: 2; }
.hero-date { color: #AFC4FF; font-size: 0.95rem; margin-bottom: 0.7rem; }
.hero h1 {
    color: #fff; font-size: clamp(1.9rem, 3.4vw, 2.9rem); line-height: 1.08; font-weight: 800;
    letter-spacing: -0.02em; margin: 0 0 0.9rem 0; padding: 0;
}
.hero p { color: #D7E2FF; font-size: 1.02rem; line-height: 1.55; max-width: 480px; margin: 0 0 1.2rem 0; }
.pastilles { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.pastille { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25); border-radius: 999px; padding: 0.35rem 0.85rem; font-size: 0.85rem; }

/* La carte « article » : l'élément mémorable du hero */
.article-carte {
    position: absolute; z-index: 3; right: 70px; top: 52px; width: 290px; background: #fff; color: var(--texte);
    border-radius: 20px; padding: 1.1rem 1.2rem; transform: rotate(3.5deg);
    box-shadow: 0 18px 40px rgba(5, 12, 40, .35);
}
.article-carte .tag { display: inline-block; background: var(--turquoise); color: #06383D; font-weight: 700; font-size: 0.8rem; border-radius: 8px; padding: 0.15rem 0.55rem; margin-bottom: 0.6rem; }
.article-carte .q { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; font-size: 1.02rem; margin-bottom: 0.45rem; }
.article-carte .r { font-size: 0.9rem; color: var(--texte-doux); line-height: 1.45; }
@media (max-width: 980px) { .article-carte { display: none; } .hero .soleil { opacity: .5; } }

/* ---------- Titres de section ---------- */
.section-titre { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; font-size: 1.25rem; margin: 0.4rem 0 0.7rem 0; color: var(--nuit); }

/* ---------- Cartes de sujets (boutons colorés) ---------- */
.stButton > button, .stDownloadButton > button { border-radius: 18px; font-family: 'DM Sans', sans-serif; transition: transform .15s ease, box-shadow .15s ease; }
[class*="st-key-topic_"] button {
    width: 100%; min-height: 92px; justify-content: flex-start; text-align: left;
    padding: 1rem 1.2rem; border: none; border-radius: 24px; color: var(--texte); font-size: 1rem; white-space: normal;
}
[class*="st-key-topic_"] button:hover { transform: translateY(-3px) rotate(-.6deg); box-shadow: 0 10px 22px rgba(20, 35, 92, .14); color: var(--texte); }
[class*="st-key-topic_"] button p { font-size: 1.02rem; }
.st-key-topic_cert button { background: #C9EEF1; }
.st-key-topic_cal button { background: #FFE6A0; }
.st-key-topic_demande button { background: #FFD0DB; }
.st-key-topic_stage button { background: #DAD4FF; }

/* Bouton « nouvelle conversation » et téléchargement */
.st-key-btn_reset button, .stDownloadButton > button {
    background: #fff; color: var(--nuit); border: 1px solid var(--trait); padding: 0.35rem 0.9rem; font-weight: 500;
}
.st-key-btn_reset button:hover, .stDownloadButton > button:hover:not(:disabled) { border-color: var(--ciel); color: var(--ciel); }

/* ---------- Panneau de discussion ---------- */
.st-key-chatpanel {
    background: #fff; border: 1px solid var(--trait); border-radius: 28px; padding: 1.2rem 1.3rem; min-height: 280px;
}
[data-testid="stChatMessage"] { background: var(--fond); border-radius: 20px; padding: 0.9rem 1rem; border: none; }
/* Champ de saisie : un seul contour (le conteneur externe n'a plus de bordure) */
[data-testid="stChatInput"] { border: none !important; background: transparent !important; box-shadow: none !important; padding: 0 !important; }
[data-testid="stChatInput"] > div {
    border: 2px solid var(--nuit) !important; border-radius: 999px !important;
    background: #fff !important; box-shadow: none !important; padding-left: 0.6rem;
}
[data-testid="stChatInput"] > div:focus-within { border-color: var(--ciel) !important; }
[data-testid="stChatInput"] textarea { background: transparent !important; border: none !important; box-shadow: none !important; outline: none !important; }

/* ---------- Chemin de l'agent (timeline) ---------- */
.tl { border-left: 3px solid var(--trait); margin: 0.3rem 0 0.3rem 0.5rem; padding-left: 1.1rem; }
.tl-item { position: relative; margin-bottom: 0.85rem; font-size: 0.9rem; line-height: 1.4; }
.tl-item::before { content: ""; position: absolute; left: -1.62rem; top: 0.3rem; width: 14px; height: 14px; border-radius: 50%; background: var(--c, var(--ciel)); border: 3px solid #fff; box-shadow: 0 0 0 1px var(--trait); }
.tl-item b { display: block; }
.tl-item code { background: #fff; border: 1px solid var(--trait); border-radius: 6px; padding: 0.05rem 0.35rem; font-size: 0.82rem; word-break: break-word; }
.tl-route { --c: var(--lilas); } .tl-outil { --c: var(--ciel); } .tl-resultat { --c: var(--turquoise); }

/* ---------- Cartes latérales ---------- */
.carte { background: #fff; border: 1px solid var(--trait); border-radius: 26px; padding: 1.25rem 1.3rem; margin-bottom: 1rem; }
.carte h3 { font-size: 1.15rem; font-weight: 700; margin: 0 0 0.3rem 0; padding: 0; color: var(--nuit); }
.carte .doux { color: var(--texte-doux); font-size: 0.88rem; margin: 0 0 0.8rem 0; }
.ligne-examen { display: flex; justify-content: space-between; gap: 0.6rem; padding: 0.55rem 0; border-top: 1px dashed var(--trait); font-size: 0.88rem; }
.ligne-examen:first-of-type { border-top: none; }
.ligne-examen .mod { font-weight: 700; }
.ligne-examen .dates { text-align: right; color: var(--texte-doux); }
.ligne-examen .rat { color: #B4325A; font-weight: 500; }
.bientot { background: var(--soleil); color: var(--nuit); border-radius: 18px; padding: 0.8rem 1rem; font-weight: 700; margin-bottom: 0.7rem; font-size: 0.95rem; }

/* ---------- Étapes de la demande ---------- */
.etapes { display: flex; gap: 0.4rem; margin: 0.2rem 0 0.2rem 0; }
.etape { flex: 1; text-align: center; font-size: 0.78rem; padding: 0.45rem 0.2rem; border-radius: 12px; background: var(--fond); color: var(--texte-doux); font-weight: 500; }
.etape.fait { background: #C9EEF1; color: #06383D; font-weight: 700; }
.etape.en-cours { background: var(--nuit); color: #fff; font-weight: 700; }

.st-key-btn_valider button { background: var(--nuit); color: #fff; border: none; width: 100%; padding: 0.7rem 1rem; font-weight: 700; }
.st-key-btn_valider button:hover:not(:disabled) { background: var(--ciel); color: #fff; }
.st-key-btn_valider button:disabled { background: #E3E8FA; color: #98A2C3; }

.pied { text-align: center; color: var(--texte-doux); font-size: 0.8rem; margin-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# État de session
# ----------------------------------------------------------------------------
defaults = {
    "thread_id": str(uuid.uuid4()),
    "historique": [],
    "derniere_demande": "",
    "question_injectee": None,
    "demande_enregistree": False,
}
for cle, val in defaults.items():
    if cle not in st.session_state:
        st.session_state[cle] = val


def nouvelle_conversation() -> None:
    """Repart de zéro : nouveau thread LangGraph, historique et courrier vides."""
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.historique = []
    st.session_state.derniere_demande = ""
    st.session_state.demande_enregistree = False


# ----------------------------------------------------------------------------
# Composants HTML
# ----------------------------------------------------------------------------
def rendre_timeline(etapes: list[dict]) -> str:
    """Transforme les étapes de l'agent en chronologie visuelle (texte échappé)."""
    blocs = []
    for e in etapes:
        blocs.append(
            f'<div class="tl-item tl-{e["type"]}"><b>{html.escape(e["titre"])}</b>'
            f'<code>{html.escape(e["detail"])}</code></div>'
        )
    return '<div class="tl">' + "".join(blocs) + "</div>"


def afficher_etapes(etapes: list[dict]) -> None:
    if etapes:
        with st.expander(f"🔍 Voir le chemin suivi par l'agent ({len(etapes)} étapes)"):
            st.markdown(rendre_timeline(etapes), unsafe_allow_html=True)


def carte_calendrier() -> str:
    aujourdhui = date.today()
    prochain = next(((m, d) for m, d, *_ in EXAMENS if d >= aujourdhui), None)
    if prochain:
        n = (prochain[1] - aujourdhui).days
        quand = "aujourd'hui" if n == 0 else f"dans {n} jour{'s' if n > 1 else ''}"
        bandeau = f'<div class="bientot">Prochain examen : {html.escape(prochain[0])}, {quand}</div>'
    else:
        bandeau = '<div class="bientot">La session de janvier 2027 est terminée.</div>'

    lignes = ""
    for mod, d_ex, h_ex, d_ra, h_ra in EXAMENS:
        lignes += (
            f'<div class="ligne-examen"><span class="mod">{html.escape(mod)}</span>'
            f'<span class="dates">Examen {d_ex:%d/%m}, {h_ex}<br>'
            f'<span class="rat">Rattrapage {d_ra:%d/%m}, {h_ra}</span></span></div>'
        )
    lignes += (
        '<div class="ligne-examen"><span class="mod">Projet de fin de module</span>'
        f'<span class="dates">Remise {PROJET_REMISE:%d/%m}<br><span class="rat">Pas de rattrapage</span></span></div>'
    )
    return (
        '<div id="examens" class="carte"><h3>Session de janvier 2027</h3>'
        '<p class="doux">Pour une date officielle, demandez à l\'assistant : il cite l\'article.</p>'
        f'{bandeau}{lignes}</div>'
    )


def carte_etapes_demande(a_texte: bool, autorise: bool, envoye: bool) -> str:
    def etat(fait: bool, actif: bool) -> str:
        return "fait" if fait else ("en-cours" if actif else "")

    e1 = etat(a_texte, not a_texte)
    e2 = etat(autorise or envoye, a_texte and not autorise)
    e3 = etat(envoye, autorise and not envoye)
    return (
        '<div id="demande" class="carte"><h3>Votre demande en 3 étapes</h3>'
        '<p class="doux">L\'IA prépare le courrier, vous décidez de l\'enregistrer. Rien ne part sans votre accord.</p>'
        '<div class="etapes">'
        f'<div class="etape {e1}">1. Rédiger<br>dans le chat</div>'
        f'<div class="etape {e2}">2. Relire et autoriser</div>'
        f'<div class="etape {e3}">3. Enregistrer</div>'
        '</div></div>'
    )


def interroger_agent(question: str) -> tuple[str, list[dict], float]:
    """Appelle l'agent LangGraph. Retourne (réponse, étapes suivies, durée en s)."""
    debut = time.perf_counter()
    config = {"configurable": {"thread_id": st.session_state.thread_id}}

    etat_avant = langgraph_app.get_state(config)
    nb_msg_avant = len(etat_avant.values.get("messages", [])) if etat_avant.values else 0

    resultat = langgraph_app.invoke({"messages": [HumanMessage(content=question)]}, config=config)

    tous_messages = resultat["messages"]
    nouveaux_messages = tous_messages[nb_msg_avant:]
    reponse = tous_messages[-1].content

    etapes = [{
        "type": "route",
        "titre": "Le modèle choisit la route",
        "detail": str(resultat.get("route", "N/A")),
    }]
    for m in nouveaux_messages:
        if m.type == "ai" and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                etapes.append({
                    "type": "outil",
                    "titre": f"Le modèle demande l'outil {tc['name']}",
                    "detail": str(tc["args"]),
                })
        elif m.type == "tool":
            contenu = str(m.content)
            etapes.append({
                "type": "resultat",
                "titre": "Le programme exécute l'outil et renvoie le résultat",
                "detail": contenu[:300] + ("..." if len(contenu) > 300 else ""),
            })
    return reponse, etapes, time.perf_counter() - debut


# ----------------------------------------------------------------------------
# Navigation + hero
# ----------------------------------------------------------------------------
if LOGO_URI:
    logo_html = f'<img src="{LOGO_URI}" alt="Logo ISET Charguia">'
else:
    logo_html = '<span style="font-size:2rem;padding-left:.6rem">🎓</span>'

st.markdown(f"""
<div id="accueil"></div>
<div class="nav">
    <div class="marque">
        {logo_html}
        <div class="nom"><b>Portail étudiant</b><span>Assistant de scolarité</span></div>
    </div>
    <div class="nav-liens">
        <a class="actif" href="#accueil" target="_self">Accueil</a><a href="#sujets" target="_self">Mes études</a><a href="#examens" target="_self">Règlement et examens</a><a href="#demande" target="_self">Service scolarité</a>
    </div>
    <div class="nav-profil"><span>{html.escape(PRENOM)}</span><span class="rond">{html.escape(PRENOM[:1].upper())}</span></div>
</div>

<div class="hero">
    <div class="soleil"></div><div class="anneau"></div><div class="petit"></div>
    <div class="hero-texte">
        <div class="hero-date">Bonjour {html.escape(PRENOM)}, nous sommes le {fr_date(date.today())}.</div>
        <h1>Une absence, un doute, une date : demandez à l'assistant.</h1>
        <p>Il lit le règlement des études et le calendrier des examens à votre place, cite l'article utilisé et prépare votre demande de rattrapage.</p>
        <div class="pastilles">
            <span class="pastille">Règlement 2026-2027</span>
            <span class="pastille">Session de janvier 2027</span>
            <span class="pastille">Réponses avec article cité</span>
        </div>
    </div>
    <div class="article-carte">
        <span class="tag">Article 4</span>
        <div class="q">Malade le jour de l'examen ?</div>
        <div class="r">Le certificat médical est remis à la scolarité dans un délai de 3 jours ouvrables, sans compter le jour de l'examen.</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# Cartes de sujets (raccourcis vers l'agent)
# ----------------------------------------------------------------------------
st.markdown('<div id="sujets" class="section-titre">Par où commencer ?</div>', unsafe_allow_html=True)
cols_sujets = st.columns(4, gap="medium")
for col, (cle, (libelle, question_type)) in zip(cols_sujets, SUJETS.items()):
    with col:
        if st.button(libelle, key=cle):
            st.session_state.question_injectee = question_type

st.write("")

# ----------------------------------------------------------------------------
# Corps : discussion à gauche, calendrier et demande à droite
# ----------------------------------------------------------------------------
col_chat, col_side = st.columns([1.75, 1.05], gap="large")

with col_chat:
    entete_titre, entete_bouton = st.columns([3, 1.3], vertical_alignment="center")
    with entete_titre:
        st.markdown('<div class="section-titre">Discuter avec l\'assistant</div>', unsafe_allow_html=True)
    with entete_bouton:
        st.button("Nouvelle conversation", key="btn_reset", on_click=nouvelle_conversation)

    chat_box = st.container(key="chatpanel")
    with chat_box:
        if not st.session_state.historique:
            with st.chat_message("assistant", avatar=AVATAR_BOT):
                st.markdown(
                    f"Bonjour **{html.escape(PRENOM)}** ! Posez-moi une question sur le **règlement**, "
                    "les **dates d'examen** ou le **stage**, ou demandez-moi de rédiger votre "
                    "**demande de rattrapage** (article 8). Je réponds uniquement à partir des documents officiels."
                )
        for item in st.session_state.historique:
            avatar = AVATAR_USER if item["role"] == "user" else AVATAR_BOT
            with st.chat_message(item["role"], avatar=avatar):
                st.write(item["texte"])
                if item["role"] == "assistant":
                    afficher_etapes(item.get("etapes", []))
                    if item.get("duree"):
                        st.caption(f"Réponse en {item['duree']:.1f} s")

question_saisie = st.chat_input(
    "Écrivez votre question (ex : j'étais malade le jour de l'examen de réseaux)",
    max_chars=MAX_QUESTION,
)

with col_side:
    slot_etapes = st.empty()  # rempli plus bas, une fois l'état du courrier connu

    st.markdown(carte_calendrier(), unsafe_allow_html=True)

    destinataire = st.text_input("Destinataire", value="scolarite@isetch.rnu.tn", disabled=True)
    sujet_mail = st.text_input("Objet", value="Demande de passage en session de rattrapage")
    texte_a_envoyer = st.text_area(
        "Courrier prêt à l'enregistrement",
        value=st.session_state.derniere_demande,
        height=190,
        placeholder="Demandez une demande de rattrapage dans le chat : elle apparaîtra ici.",
    )
    ok = st.checkbox(
        "J'ai relu le courrier et j'autorise son enregistrement.",
        key="autorisation",
    )

    if st.button("Valider et enregistrer dans outbox/", key="btn_valider",
                 disabled=not (ok and texte_a_envoyer.strip())):
        try:
            msg_succes = send_demande(
                destinataire=destinataire,
                sujet=sujet_mail,
                corps=texte_a_envoyer,
                confirmed=True,
            )
            st.session_state.demande_enregistree = True
            st.success(msg_succes)
            st.balloons()
        except Exception as e:  # noqa: BLE001
            st.error(f"L'enregistrement a échoué : {e}")

    st.download_button(
        "Télécharger le courrier (.txt)",
        data=texte_a_envoyer or "",
        file_name="demande_rattrapage.txt",
        mime="text/plain",
        disabled=not texte_a_envoyer.strip(),
    )

    # Les 3 étapes sont dessinées en haut de la colonne, avec l'état à jour
    slot_etapes.markdown(
        carte_etapes_demande(
            a_texte=bool(texte_a_envoyer.strip()),
            autorise=ok,
            envoye=st.session_state.demande_enregistree,
        ),
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------------
# Traitement d'une question (clavier ou carte de sujet)
# ----------------------------------------------------------------------------
question = st.session_state.question_injectee or question_saisie
if st.session_state.question_injectee:
    st.session_state.question_injectee = None

if question:
    question = question.strip()[:MAX_QUESTION]
    demande_detectee = False

    with chat_box:
        st.chat_message("user", avatar=AVATAR_USER).write(question)
        st.session_state.historique.append({"role": "user", "texte": question})

        try:
            with st.spinner("L'assistant cherche dans le règlement et le calendrier..."):
                reponse_finale, etapes_traces, duree = interroger_agent(question)
        except Exception as e:  # noqa: BLE001 - modèle éteint, quota, outil MCP en panne...
            reponse_finale = (
                "Je n'arrive pas à joindre le modèle pour le moment. Vérifiez qu'Ollama est lancé "
                "(commande `ollama serve`) et que le modèle est téléchargé, puis réessayez."
            )
            etapes_traces = [{"type": "route", "titre": "Erreur technique", "detail": f"{type(e).__name__}: {e}"}]
            duree = 0.0

        if any(k in reponse_finale for k in ["À l'attention", "Je soussigné", "Objet :", "Objet:"]):
            st.session_state.derniere_demande = reponse_finale
            st.session_state.demande_enregistree = False
            demande_detectee = True

        with st.chat_message("assistant", avatar=AVATAR_BOT):
            st.write(reponse_finale)
            afficher_etapes(etapes_traces)
            if duree:
                st.caption(f"Réponse en {duree:.1f} s")

        st.session_state.historique.append({
            "role": "assistant",
            "texte": reponse_finale,
            "etapes": etapes_traces,
            "duree": duree,
        })

    # Le courrier est dans la colonne de droite, déjà dessinée : on relance
    # la page pour qu'il apparaisse tout de suite dans la zone de texte.
    if demande_detectee:
        st.rerun()

st.markdown(
    '<div class="pied">Règlement et calendrier fictifs, à usage pédagogique. '
    "L'assistant peut se tromper : vérifiez auprès de la scolarité.</div>",
    unsafe_allow_html=True,
)