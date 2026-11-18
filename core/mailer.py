import os
from email.message import EmailMessage

def send_demande(destinataire: str, sujet: str, corps: str, confirmed: bool = False) -> str:
    if not confirmed:
        raise PermissionError("Envoi refusé : accord explicite de l'étudiant requis.")
    
    msg = EmailMessage()
    msg['From'] = "etudiant@isetch.rnu.tn"
    msg['To'] = destinataire
    msg['Subject'] = sujet
    msg.set_content(corps)
    
    os.makedirs('outbox', exist_ok=True)
    chemin_fichier = os.path.join('outbox', 'demande.eml')
    
    with open(chemin_fichier, 'wb') as f:
        f.write(bytes(msg))
        
    return f"Demande validée et enregistrée avec succès dans '{chemin_fichier}'."