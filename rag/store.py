import os
import sys
import chromadb
from rag.ingest import embed

MAX_DISTANCE = float(os.getenv('MAX_DISTANCE', '0.70'))

# Tentative d'importation de streamlit pour le cache (optionnel si exécuté en CLI)
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


# Fonction avec cache Streamlit si l'app tourne, sinon client standard
if HAS_STREAMLIT:
    @st.cache_resource
    def get_chroma_collection():
        client = chromadb.PersistentClient(path='chroma_db')
        return client.get_collection('reglement')
else:
    def get_chroma_collection():
        client = chromadb.PersistentClient(path='chroma_db')
        return client.get_collection('reglement')


def search_reglement(question, k=3):
    col = get_chroma_collection()
    r = col.query(query_embeddings=embed([question]), n_results=k)
    
    # Sécurité si aucun résultat n'est retourné par ChromaDB
    if not r['metadatas'] or not r['metadatas'][0]:
        return {'resultat': 'Aucune information trouvée dans le règlement'}
        
    res = [{'article': m['article'], 'texte': d, 'distance': round(dist, 3)}
           for m, d, dist in zip(r['metadatas'][0], r['documents'][0], r['distances'][0])]
    
    bons = [x for x in res if x['distance'] <= MAX_DISTANCE]
    return bons if bons else {'resultat': 'Aucune information trouvée dans le règlement'}


def lire_article_direct(numero):
    try:
        num = int(numero)
    except ValueError:
        return {'erreur': 'Numéro d’article invalide.'}
        
    if not (1 <= num <= 15):
        return {'erreur': f"L'article {num} n'existe pas. Le règlement comporte uniquement les articles 1 à 15."}
        
    col = get_chroma_collection()
    res = col.get(ids=[str(num)])
    
    if res and res['documents']:
        return {'article': num, 'texte': res['documents'][0]}
    return {'erreur': f"Article {num} introuvable dans la base."}


if __name__ == '__main__':
    for q in sys.argv[1:]:
        print(f"Question : {q}")
        col = get_chroma_collection()
        r = col.query(query_embeddings=embed([q]), n_results=3)
        if r['metadatas'] and r['metadatas'][0]:
            print([(m['article'], round(d, 3)) for m, d in zip(r['metadatas'][0], r['distances'][0])])
        else:
            print("Aucun résultat.")