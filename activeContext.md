# Active Context: ClaudePrivé

## Focus Actuel
Le projet est terminé et fonctionnel. Une mise à jour majeure a été effectuée pour supporter les **nouveaux modèles 2026** (Claude Opus 4.6, Sonnet 4.5) disponibles dans la région Europe.

## Changements Récents (03/03/2026)
-   **Découverte** : Le compte AWS utilise les modèles 2026, rendant les modèles 2024 obsolètes (Legacy).
-   **Mise à niveau** : Remplacement de tous les identifiants par les versions "Inférence interrégionale" (Cross-Region) Europe.
    -   **Opus** : `eu.anthropic.claude-opus-4-6-v1:0` (Claude Opus 4.6)
    -   **Sonnet** : `eu.anthropic.claude-sonnet-4-5-20250929-v1:0` (Claude Sonnet 4.5)
    -   **Haiku** : `eu.anthropic.claude-haiku-4-5-20251001-v1:0` (Claude Haiku 4.5)
-   **Interface** : Passage à la version v2.0 pour marquer le saut générationnel.
-   **Nettoyage** : Suppression de toutes les options "US Only" et "Legacy".

## Prochaines Étapes
-   Surveiller les logs pour valider que les nouveaux IDs sont bien acceptés par Bedrock Paris.
-   Aucune action requise si ce n'est la mise à jour du serveur.
