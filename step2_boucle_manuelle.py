import os, sys, json
from dotenv import load_dotenv
from openai import OpenAI
from core.tools import get_calendrier, calcul_delai, generer_demande

load_dotenv()
client = OpenAI(base_url=os.getenv('LLM_BASE_URL'), api_key=os.getenv('LLM_API_KEY'))
MODEL = os.getenv('MODEL_NAME')

FONCTIONS = {
    'get_calendrier': get_calendrier,
    'calcul_delai': calcul_delai,
    'generer_demande': generer_demande
}

def schema(nom, desc, props, req):
    return {
        'type': 'function',
        'function': {
            'name': nom,
            'description': desc,
            'parameters': {
                'type': 'object',
                'properties': {p: {'type': t} for p, t in props.items()},
                'required': req
            }
        }
    }

TOOLS = [
    schema('get_calendrier', "Dates d'examen et de rattrapage d'un module", {'module': 'string'}, ['module']),
    schema('calcul_delai', "Date limite du certificat médical (JJ/MM/AAAA)", {'date_examen': 'string', 'hospitalisation': 'boolean'}, ['date_examen']),
    schema('generer_demande', "Rédige la demande de rattrapage", {'nom': 'string', 'numero_etudiant': 'string', 'module': 'string', 'date_examen': 'string'}, ['nom', 'numero_etudiant', 'module', 'date_examen']),
]

def appeler_outil(call):
    # LE PROGRAMME AGIT : on gère outil inconnu et arguments invalides
    nom = call.function.name
    if nom not in FONCTIONS:
        return {'erreur': f'Outil inconnu: {nom}'}
    try:
        args = json.loads(call.function.arguments)
        return FONCTIONS[nom](**args)
    except (json.JSONDecodeError, TypeError) as e:
        return {'erreur': f'Arguments invalides: {e}'}

SYSTEM = (
    "Tu es l'assistant de scolarité de l'ISET Charguia. Réponds uniquement à partir des outils. "
    "Ne devine jamais une date et ne calcule jamais un délai toi-même. "
    "Si l'information n'est pas disponible, réponds: Je ne sais pas."
)

def agent(question, verbose=True):
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': question}]
    for _ in range(5):
        msg = client.chat.completions.create(
            model=MODEL, 
            messages=messages, 
            tools=TOOLS, 
            temperature=0.1
        ).choices[0].message
        
        if not msg.tool_calls:
            return (msg.content or '').split('\n')[-1].strip()
        
        messages.append(msg)
        for call in msg.tool_calls:
            if verbose: 
                print('[MODÈLE DÉCIDE]', call.function.name, call.function.arguments)
            res = appeler_outil(call)
            if verbose: 
                print('[PROGRAMME AGIT]', res)
            messages.append({
                'role': 'tool', 
                'tool_call_id': call.id, 
                'content': json.dumps(res, ensure_ascii=False)
            })
    return "Je n'ai pas pu terminer."

if __name__ == '__main__':
    if len(sys.argv) > 1:
        print(agent(sys.argv[1]))
    else:
        print(agent("Quelle est la date du rattrapage de réseaux ?"))