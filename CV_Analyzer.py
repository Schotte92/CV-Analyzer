"""Startet den CV-Analyzer — für den Aufruf aus dem Repository-Ordner.

Installiert man das Paket (``pip install -e .``), geht auch
``python -m cv_analyzer`` oder das Kommando ``cv-analyzer``.
"""

from cv_analyzer.main import run

if __name__ == "__main__":
    run()
