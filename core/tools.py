import json, unicodedata
from datetime import datetime, timedelta

ALIAS = {
    'bdd': 'bases de données',
    'base de donnees': 'bases de données',
    'bases de donnees': 'bases de données',
    'reseaux': 'réseaux',
    'algo': 'algorithmique',
    'projet': 'projet de fin de module'
}

def norm(s):
    s = unicodedata.normalize('NFD', s.lower().strip())
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')

CAL = json.load(open('data/calendrier.json', encoding='utf-8'))
CAL_N = {norm(k): v for k, v in CAL.items()}
ALIAS_N = {norm(k): norm(v) for k, v in ALIAS.items()}

def get_calendrier(module):
    cle = norm(module)
    cle = ALIAS_N.get(cle, cle)
    return CAL_N.get(cle, {'erreur': 'Module introuvable'})

def _ajouter_ouvrables(d, n):
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:      # lundi à vendredi
            n -= 1
    return d

def calcul_delai(date_examen, hospitalisation=False):
    # date_examen au format JJ/MM/AAAA ; le jour de l'examen n'est pas compté (article 4)
    try:
        d = datetime.strptime(date_examen, '%d/%m/%Y')
    except ValueError:
        return {'erreur': 'Format attendu JJ/MM/AAAA'}
    limite = _ajouter_ouvrables(d, 7 if hospitalisation else 3)   # articles 4 et 6
    return {'date_limite': limite.strftime('%d/%m/%Y'), 'article': 6 if hospitalisation else 4}

def generer_demande(nom, numero_etudiant, module, date_examen):
    manquants = [k for k, v in {'nom': nom, 'numero_etudiant': numero_etudiant,
                                'module': module, 'date_examen': date_examen}.items() if not str(v).strip()]
    if manquants:
        return {'erreur': 'Champs manquants', 'manquants': manquants}
    
    cal = get_calendrier(module)
    if 'erreur' in cal:
        return cal
    if 'Pas de rattrapage' in cal['rattrapage']:
        return {'erreur': 'Ce module n a pas de session de rattrapage (article 10)'}
    
    texte = (f"À l'attention du responsable de scolarité,\n\n"
             f"Je soussigné(e) {nom}, numéro étudiant {numero_etudiant}, "
             f"sollicite le passage à la session de rattrapage du module {module}, "
             f"l'examen du {date_examen} ayant été manqué. Le justificatif est joint (article 8).\n\n"
             f"Cordialement, {nom}")
    return {'demande': texte}