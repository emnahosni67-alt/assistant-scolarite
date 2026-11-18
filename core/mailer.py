import os
import logging
from email.message import EmailMessage

# Configuration des logs pour tracer les validations et blocages de sécurité
logging.basicConfig(
    filename="assistant_production.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

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
    msg['From'] = "etudiant@isetch.rnu.tn"
    msg['To'] = destinataire
    msg['Subject'] = sujet
    msg.set_content(corps)
    
    # Création sécurisée du dossier outbox s'il n'existe pas
    os.makedirs('outbox', exist_ok=True)
    chemin_fichier = os.path.join('outbox', 'demande.eml')
    
    with open(chemin_fichier, 'wb') as f:
        f.write(bytes(msg))
        
    logging.info(f"E-mail validé et exporté avec succès vers {chemin_fichier}")
    return f"Demande validée et enregistrée avec succès dans '{chemin_fichier}'."