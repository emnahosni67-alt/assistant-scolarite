import re

INJECTION = re.compile(r'ignore.{0,20}(instructions|consignes)|prompt syst|tu es maintenant|oublie tes r', re.I)
REFUS = "Je ne peux pas répondre à cette demande. Je réponds uniquement aux questions sur le règlement et le calendrier."

def guard(texte):
    return REFUS if INJECTION.search(texte) else None

def verifier_citations(reponse, articles_renvoyes):
    # chaque Article N cité doit exister (1 à 15) ET avoir été renvoyé par un outil
    for n in re.findall(r'[Aa]rticle (\d+)', reponse):
        if not (1 <= int(n) <= 15) or int(n) not in articles_renvoyes:
            return "Je ne peux pas confirmer cette information à partir du règlement."
    return reponse