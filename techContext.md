# Tech Context: ClaudePrivé

## Stack Technique
-   **Langage** : Python 3.12 (image Docker `python:3.12-slim`).
-   **Framework Web** : Flask 3.x.
-   **Serveur d'Application** : Gunicorn.
-   **Frontend** : HTML5, CSS3 (Flexbox/Grid), JavaScript (ES6, Fetch API). Aucune dépendance frontend (pas de React/Vue/Angular).
-   **IA / LLM** : AWS Bedrock Runtime (via `boto3`).
-   **Manipulation de Fichiers** : `PyPDF2` (PDF), `python-docx` (Word).

## Configuration Requise
-   **Docker** : Pour conteneuriser et exécuter l'application.
-   **Compte AWS** : Avec accès activé aux modèles Claude (Sonnet 3.5, Haiku 3) dans la région cible (ex: `eu-west-3`, `us-east-1`).
-   **Crédentials AWS** : Configurés via variables d'environnement (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`) ou profil `~/.aws/credentials` monté dans le conteneur.

## Dépendances (requirements.txt)
-   `flask` : Framework web.
-   `gunicorn` : Serveur WSGI de production.
-   `boto3` : SDK AWS pour Python.
-   `PyPDF2` : Extraction de texte PDF.
-   `python-docx` : Extraction de texte Word.

## Environnement de Développement
-   **Local** : `python app.py` (Flask debug server).
-   **Docker** : `docker build -t claudeprive . && docker run -p 8009:8009 -v $(pwd)/data:/app/data -e AWS_PROFILE=default -v ~/.aws:/root/.aws claudeprive`.

## Contraintes Techniques
-   **Stockage** : Les fichiers uploadés et les JSON sont stockés dans `/app/data`. Ce dossier doit être persisté (volume Docker) pour ne pas perdre l'historique au redémarrage.
-   **Taille Fichier** : Limite d'upload fixée à 20 Mo (`MAX_CONTENT_LENGTH`).
-   **Concurrence** : Gérée par Gunicorn (2 workers, 8 threads par défaut dans `start.sh`).
