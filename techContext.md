# Tech Context: ClaudePrivé

## Stack Technique
-   **Langage** : Python 3.12 (image Docker `python:3.12-slim`).
-   **Framework Web** : Flask 3.x.
-   **Serveur d'Application** : Gunicorn.
-   **Frontend** : HTML5, CSS3 (Flexbox/Grid), JavaScript (ES6, Fetch API).
-   **IA / LLM** : AWS Bedrock Runtime (via `boto3`).

## Modèles Supportés (Mars 2026)
L'application utilise les versions les plus récentes et les profils Cross-Region pour éviter les erreurs "Legacy" ou "Throughput".

1.  **Claude 3.5 Sonnet v2** (`us.anthropic.claude-3-5-sonnet-20241022-v2:0`)
    *   Le modèle par défaut. Rapide et intelligent.
    *   Hébergé aux USA (seule dispo actuelle).
2.  **Claude 3 Opus** (`us.anthropic.claude-3-opus-20240229-v1:0`)
    *   Le modèle le plus puissant ("Opus 4.6" Marketplace).
    *   Hébergé aux USA (seule dispo actuelle).
3.  **Claude 3.5 Haiku** (`us.anthropic.claude-3-5-haiku-20241022-v1:0`)
    *   Modèle ultra-rapide nouvelle génération.
    *   Hébergé aux USA.

*Note : Les modèles hébergés en Europe (v1) ont été retirés car marqués "Legacy" ou instables par AWS sur ce compte.*

## Configuration Requise
-   **Docker** : Pour conteneuriser et exécuter l'application.
-   **Compte AWS** : Avec accès activé aux modèles Anthropic (US).
-   **Crédentials AWS** : `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

## Dépendances (requirements.txt)
-   `flask`, `gunicorn`, `boto3`, `PyPDF2`, `python-docx`.
