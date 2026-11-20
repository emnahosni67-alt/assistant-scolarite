import os
import logging
import tempfile
from email.message import EmailMessage

# Racine du projet (le dossier qui contient core/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
OUTBOX_DIR = os.path.join(BASE_DIR, "outbox")


def _setup_logging() -> None:
    """Configure les logs une seule fois, avec repli si le dossier n'est pas accessible."""
    root = logging.getLogger()
    if root.handlers:  # déjà configuré (Streamlit réexécute le script souvent)
        return

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
    msg['From'] = "emnahosni67@gmail.com"
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