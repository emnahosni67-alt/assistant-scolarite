import os, sys, json
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError

load_dotenv()
client = OpenAI(base_url=os.getenv("LLM_BASE_URL"),
                api_key=os.getenv("LLM_API_KEY"))
MODEL = os.getenv("MODEL_NAME")

SYSTEM = (
    "Tu es l'assistant de scolarité de l'ISET Charguia. "
    'Réponds uniquement en JSON : {"type": "question|hors_sujet", "reponse": "..."}. '
    "Si la question ne concerne pas la scolarité, type=hors_sujet. Ne devine jamais."
)

class Rep(BaseModel):
    type: str
    reponse: str

def demander(question, essais=3):
    for i in range(essais):
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": question}],
            temperature=0.1)
        texte = r.choices[0].message.content
        texte = texte.split("</think>")[-1].strip()   # retire la réflexion de Qwen3
        texte = texte.replace("```json", "").replace("```", "").strip()
        try:
            return Rep(**json.loads(texte))
        except (json.JSONDecodeError, ValidationError):
            print(f"JSON invalide (essai {i+1}), nouvelle tentative")
    return None

if __name__ == "__main__":
    print(demander(sys.argv[1]))