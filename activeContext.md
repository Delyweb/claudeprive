# Active Context: ClaudePrivé

## Focus Actuel
Le projet est stabilisé. Une mise à jour majeure a été effectuée pour aligner les identifiants de modèles avec les dernières contraintes d'AWS Bedrock (Mars 2026).

## Changements Récents
-   **Correctif "Legacy/EOL"** : Suppression de tous les anciens modèles (Claude 3 Sonnet v1, Haiku 3 v1) qui provoquaient des erreurs `ResourceNotFound` ou `Legacy`.
-   **Adoption de Claude 3.5 Sonnet v2** : Le nouveau standard pour la performance et l'intelligence (ID: `us.anthropic.claude-3-5-sonnet-20241022-v2:0`).
-   **Adoption de Claude 3.5 Haiku** : Pour la rapidité (ID: `us.anthropic.claude-3-5-haiku-20241022-v1:0`).
-   **Support Opus via Cross-Region** : Configuration spécifique pour permettre l'utilisation de Claude 3 Opus (via `us-east-1`).
-   **Nettoyage Interface** : Le menu de sélection ne propose plus que des options testées et fonctionnelles.

## Prochaines Étapes
-   Surveiller la disponibilité des modèles v2 en Europe (pour l'instant US only).
-   Redéployer l'application sur le serveur cible.
