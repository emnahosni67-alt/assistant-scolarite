import os, sys
import chromadb
from rag.ingest import embed

MAX_DISTANCE = float(os.getenv('MAX_DISTANCE', '0.55'))

def search_reglement(question, k=3):
    col = chromadb.PersistentClient(path='chroma_db').get_collection('reglement')
    r = col.query(query_embeddings=embed([question]), n_results=k)
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
    col = chromadb.PersistentClient(path='chroma_db').get_collection('reglement')
    res = col.get(ids=[str(num)])
    if res and res['documents']:
        return {'article': num, 'texte': res['documents'][0]}
    return {'erreur': f"Article {num} introuvable dans la base."}
if __name__ == '__main__':
    for q in sys.argv[1:]:
        print(q)
        col = chromadb.PersistentClient(path='chroma_db').get_collection('reglement')
        r = col.query(query_embeddings=embed([q]), n_results=3)
        print([(m['article'], round(d, 3)) for m, d in zip(r['metadatas'][0], r['distances'][0])])