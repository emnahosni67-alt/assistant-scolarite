import os, re
from pypdf import PdfReader
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(base_url=os.getenv('LLM_BASE_URL'), api_key=os.getenv('LLM_API_KEY'))
EMB = os.getenv('EMBED_MODEL', 'bge-m3')

def embed(textes):
    r = client.embeddings.create(model=EMB, input=textes)
    return [d.embedding for d in r.data]

def lire_articles():
    texte = ' '.join(p.extract_text() for p in PdfReader('data/reglement.pdf').pages)
    texte = texte.split('Calendrier des examens')[0]         # on exclut le tableau
    morceaux = re.split(r'(?=Article \d+\.)', texte)
    arts = []
    for m in morceaux:
        g = re.match(r'Article (\d+)\.', m)
        if g:
            arts.append({'article': int(g.group(1)), 'texte': ' '.join(m.split())})
    return arts

if __name__ == '__main__':
    arts = lire_articles()
    db = chromadb.PersistentClient(path='chroma_db')
    try: 
        db.delete_collection('reglement')
    except Exception: 
        pass
    col = db.create_collection('reglement', metadata={'hnsw:space': 'cosine'})
    col.add(
        ids=[str(a['article']) for a in arts], 
        documents=[a['texte'] for a in arts],
        metadatas=[{'article': a['article']} for a in arts], 
        embeddings=embed([a['texte'] for a in arts])
    )
    print(f'{len(arts)} articles indexés')