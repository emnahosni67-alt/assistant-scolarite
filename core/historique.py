"""
Historique des conversations : stockage local dans une base SQLite.

Chaque message (question de l'étudiant ou réponse de l'assistant) est enregistré
avec l'identifiant de la conversation (thread_id), les étapes suivies par l'agent
et la durée de la réponse. La base est créée dans historique/conversations.db
(avec repli vers le dossier temporaire si le dossier du projet est protégé).
"""
import json
import logging
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "historique")

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    role      TEXT NOT NULL,
    texte     TEXT NOT NULL,
    etapes    TEXT,
    duree     REAL,
    cree_le   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, id);
"""


def _initialiser() -> str | None:
    """Crée la base et retourne son chemin (None si aucun emplacement n'est accessible)."""
    for dossier in (DB_DIR, tempfile.gettempdir()):
        try:
            os.makedirs(dossier, exist_ok=True)
            chemin = os.path.join(dossier, "conversations.db")
            with closing(sqlite3.connect(chemin)) as con:
                con.executescript(SCHEMA)
                con.commit()
            return chemin
        except (OSError, sqlite3.Error) as e:
            logging.warning("Historique : dossier %s inutilisable (%s)", dossier, e)
    logging.error("Historique : aucune base accessible, les conversations ne seront pas enregistrées.")
    return None


DB_PATH = _initialiser()


def enregistrer_message(thread_id: str, role: str, texte: str,
                        etapes: list | None = None, duree: float | None = None) -> None:
    """Ajoute un message à la conversation. N'interrompt jamais l'application en cas d'erreur."""
    if not DB_PATH:
        return
    try:
        with closing(sqlite3.connect(DB_PATH)) as con:
            con.execute(
                "INSERT INTO messages (thread_id, role, texte, etapes, duree, cree_le) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    role,
                    texte,
                    json.dumps(etapes or [], ensure_ascii=False),
                    duree,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            con.commit()
    except sqlite3.Error as e:
        logging.error("Historique : enregistrement impossible (%s)", e)


def lister_conversations(limite: int = 30) -> list[dict]:
    """Conversations récentes d'abord : [{thread_id, titre, date}]."""
    if not DB_PATH:
        return []
    try:
        with closing(sqlite3.connect(DB_PATH)) as con:
            lignes = con.execute(
                """
                SELECT m.thread_id,
                       MAX(m.cree_le) AS derniere,
                       (SELECT texte FROM messages q
                         WHERE q.thread_id = m.thread_id AND q.role = 'user'
                         ORDER BY q.id LIMIT 1) AS premiere_question
                FROM messages m
                GROUP BY m.thread_id
                ORDER BY derniere DESC
                LIMIT ?
                """,
                (limite,),
            ).fetchall()
    except sqlite3.Error as e:
        logging.error("Historique : lecture impossible (%s)", e)
        return []

    resultat = []
    for thread_id, derniere, question in lignes:
        titre = " ".join((question or "Conversation").split())
        if len(titre) > 50:
            titre = titre[:49] + "…"
        resultat.append({
            "thread_id": thread_id,
            "titre": titre,
            "date": datetime.fromisoformat(derniere).strftime("%d/%m %H:%M"),
        })
    return resultat


def charger_conversation(thread_id: str) -> list[dict]:
    """Messages d'une conversation, dans l'ordre, au format utilisé par app.py."""
    if not DB_PATH:
        return []
    try:
        with closing(sqlite3.connect(DB_PATH)) as con:
            lignes = con.execute(
                "SELECT role, texte, etapes, duree FROM messages WHERE thread_id = ? ORDER BY id",
                (thread_id,),
            ).fetchall()
    except sqlite3.Error as e:
        logging.error("Historique : lecture impossible (%s)", e)
        return []

    messages = []
    for role, texte, etapes, duree in lignes:
        item = {"role": role, "texte": texte}
        if role == "assistant":
            try:
                item["etapes"] = json.loads(etapes) if etapes else []
            except json.JSONDecodeError:
                item["etapes"] = []
            item["duree"] = duree or 0.0
        messages.append(item)
    return messages


def supprimer_conversation(thread_id: str) -> None:
    """Supprime définitivement une conversation."""
    if not DB_PATH:
        return
    try:
        with closing(sqlite3.connect(DB_PATH)) as con:
            con.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            con.commit()
    except sqlite3.Error as e:
        logging.error("Historique : suppression impossible (%s)", e)