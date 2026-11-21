import csv
import os
import time
from langchain_core.messages import HumanMessage
from agent.graph import app as langgraph_app

def lancer_evaluation(modele_nom: str, tag: str):
    input_csv = "eval/questions.csv"
    os.makedirs("eval/results", exist_ok=True)
    output_csv = f"eval/results/{tag}.csv"

    print(f"🚀 Lancement de l'évaluation pour le modèle : {modele_nom} (Tag: {tag})")

    resultats = []
    
    with open(input_csv, mode="r", encoding="utf-8") as f:
        lecteur = csv.DictReader(f)
        for ligne in lecteur:
            qid = ligne["id"]
            cat = ligne["categorie"]
            question = ligne["question"]
            attendu = ligne["reponse_attendue"].lower()
            article_attendu = ligne["article_attendu"]
            doit_refuser = ligne["doit_refuser"] == "oui"

            debut = time.time()
            try:
                # Appel de l'agent LangGraph
                config = {"configurable": {"thread_id": f"eval_{qid}"}}
                res = langgraph_app.invoke({"messages": [HumanMessage(content=question)]}, config=config)
                reponse_agent = res["messages"][-1].content.lower()
            except Exception as e:
                reponse_agent = f"ERREUR_TECHNIQUE: {str(e)}"
            
            duree = round(time.time() - debut, 2)

            # Évaluation automatique de la réussite
            reussi = True
            raison = "OK"

            if doit_refuser:
                # Vérifier si l'agent a refusé ou dit "je ne sais pas"
                mots_refus = ["désolé", "ne peux pas", "je ne sais pas", "uniquement", "règlement"]
                if not any(m in reponse_agent for m in mots_refus):
                    reussi = False
                    raison = "Échec du refus / fuite de consigne"
            else:
                if attendu and attendu not in reponse_agent:
                    reussi = False
                    raison = f"Valeur attendue '{attendu}' absente de la réponse"
                if article_attendu and f"article {article_attendu}" not in reponse_agent:
                    reussi = False
                    raison = f"Article {article_attendu} non cité"

            resultats.append({
                "id": qid,
                "categorie": cat,
                "question": question,
                "reponse_agent": reponse_agent,
                "duree_sec": duree,
                "reussi": "oui" if reussi else "non",
                "raison_echec": raison
            })
            print(f"[{'✅' if reussi else '❌'}] ID {qid} ({cat}) - {duree}s")

    # Écriture des résultats
    with open(output_csv, mode="w", encoding="utf-8", newline="") as f:
        champs = ["id", "categorie", "question", "reponse_agent", "duree_sec", "reussi", "raison_echec"]
        writer = csv.DictWriter(f, fieldnames=champs)
        writer.writeheader()
        writer.writerows(resultats)

    print(f"\n📁 Résultats enregistrés dans {output_csv}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--tag", default="qwen3_8b_v1")
    args = parser.parse_args()
    lancer_evaluation(args.model, args.tag)