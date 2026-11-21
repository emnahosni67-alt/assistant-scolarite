import os
import imaplib
import logging
import tempfile
import time
from email.message import EmailMessage
from email.utils import formatdate

from dotenv import load_dotenv

load_dotenv()

# Racine du projet (le dossier qui contient core/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
OUTBOX_DIR = os.path.join(BASE_DIR, "outbox")


def _setup_logging() -> None:
    """Configure les logs une seule fois, avec repli si le dossier n'est pas accessible."""
    root = logging.getLogger()
    if any(getattr(h, "_assistant_handler", False) for h in root.handlers):
        return  # déjà configuré (Streamlit réexécute le script souvent)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = logging.FileHandler(
            os.path.join(LOG_DIR, "assistant_production.log"), encoding="utf-8"
        )
    except OSError:  # PermissionError en fait partie
        handler = logging.FileHandler(
            os.path.join(tempfile.gettempdir(), "assistant_production.log"),
            encoding="utf-8",
        )

    handler._assistant_handler = True
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


# Configuration des logs pour tracer les validations et blocages de sécurité
_setup_logging()


def send_demande(destinataire: str, sujet: str, corps: str, confirmed: bool = False) -> str:
    """
    Gère l'envoi de la demande officielle de rattrapage par validation humaine (Human-in-the-Loop).
    Bloque l'exécution si l'accord explicite (confirmed=True) n'est pas fourni,
    et exporte un fichier .eml sécurisé dans le dossier outbox/.
    """
    if not confirmed:
        logging.warning("Tentative d'envoi d'e-mail bloquée : absence de validation humaine.")
        raise PermissionError("Envoi refusé : accord explicite de l'étudiant requis.")

    msg = EmailMessage()
    msg['From'] = os.getenv("GMAIL_USER", "")
    msg['To'] = destinataire
    msg['Subject'] = sujet
    msg.set_content(corps)

    # Création sécurisée du dossier outbox s'il n'existe pas
    os.makedirs(OUTBOX_DIR, exist_ok=True)
    chemin_fichier = os.path.join(OUTBOX_DIR, 'demande.eml')

    with open(chemin_fichier, 'wb') as f:
        f.write(bytes(msg))

    logging.info(f"E-mail validé et exporté avec succès vers {chemin_fichier}")
    return f"Demande validée et enregistrée avec succès dans '{chemin_fichier}'."


def _dossier_brouillons(imap: imaplib.IMAP4_SSL) -> str:
    """Trouve le dossier Brouillons quelle que soit la langue de Gmail."""
    _, dossiers = imap.list()
    for d in dossiers:
        ligne = d.decode(errors="ignore")
        if "\\Drafts" in ligne:
            return ligne.split(' "/" ')[-1].strip().strip('"')
    return "[Gmail]/Drafts"


def creer_brouillon_gmail(destinataire: str, sujet: str, corps: str) -> str:
    """Dépose le message dans les brouillons Gmail (il n'est PAS envoyé)."""
    user = os.environ["GMAIL_USER"]
    mdp = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = destinataire
    msg["Subject"] = sujet
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(corps)

    with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
        imap.login(user, mdp)
        statut, _ = imap.append(
            f'"{_dossier_brouillons(imap)}"', "\\Draft",
            imaplib.Time2Internaldate(time.time()), msg.as_bytes(),
        )
        if statut != "OK":
            raise RuntimeError("Gmail a refusé le brouillon")

    logging.info("Brouillon Gmail créé pour %s", destinataire)
    return "Brouillon créé dans Gmail. Ouvrez vos brouillons pour l'envoyer."