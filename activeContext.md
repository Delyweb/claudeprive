# Active Context: ClaudePrivé

## Focus Actuel
Le projet est en phase de maintenance et d'utilisation. La tâche actuelle consistait à corriger les identifiants (IDs) des modèles Claude dans le code pour qu'ils correspondent aux versions disponibles sur AWS Bedrock, et à préparer la documentation (Memory Bank).

## Changements Récents
-   **Correctif Modèles (03/03/2026)** :
    -   Mise à jour de `app.py` pour utiliser les bons IDs Bedrock : `anthropic.claude-3-5-sonnet-20240620-v1:0` et `anthropic.claude-3-haiku-20240307-v1:0`.
    -   Mise à jour de `templates/index.html` pour refléter ces changements dans l'interface de réglages.
    -   Commit et Push vers le dépôt Git distant.
-   **Documentation** : Création de la Memory Bank (`projectbrief.md`, `productContext.md`, etc.).

## Prochaines Étapes
-   Redéployer l'application sur le serveur cible (pull + restart docker).
-   Vérifier que les coûts sont bien calculés avec les nouveaux tarifs (définis dans `app.py`).
-   Surveiller les logs pour s'assurer que les appels Bedrock ne génèrent plus d'erreur `ValidationException`.
