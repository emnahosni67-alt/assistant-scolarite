import sys
import os

# Permet d'importer core et rag depuis le dossier parent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from core import tools
from rag.store import search_reglement as _search, lire_article_direct as _lire_article

mcp = FastMCP('scolarite')

@mcp.tool()
def search_reglement(question: str) -> dict:
    """Recherche dans le règlement des études et renvoie les articles pertinents."""
    return {'resultats': _search(question)}

@mcp.tool()
def lire_article_direct(numero: int) -> dict:
    """Lit directement un article précis du règlement (numéros 1 à 15)."""
    return _lire_article(numero)

@mcp.tool()
def get_calendrier(module: str) -> dict:
    """Date d'examen et de rattrapage d'un module."""
    return tools.get_calendrier(module)

@mcp.tool()
def calcul_delai(date_examen: str, hospitalisation: bool = False) -> dict:
    """Date limite du certificat médical (JJ/MM/AAAA)."""
    return tools.calcul_delai(date_examen, hospitalisation)

@mcp.tool()
def generer_demande(nom: str, numero_etudiant: str, module: str, date_examen: str) -> dict:
    """Génère la demande de rattrapage (article 8)."""
    return tools.generer_demande(nom, numero_etudiant, module, date_examen)

if __name__ == '__main__':
    mcp.run(transport='stdio')