# Active Context: ClaudePrivé

## Focus Actuel
Le projet est en phase de stabilisation après une erreur critique (502). La fonctionnalité de Journal (Automatique et Manuel) a été **désactivée** pour rétablir le service.

## Changements Récents
-   **HOTFIX (03/03/2026)** : Suppression complète du module `journal` qui empêchait le démarrage de Gunicorn en production.
-   **Fonctionnalités Actives** :
    -   Chat avec modèles 2026 (Opus 4.6, Sonnet 4.5, Haiku 4.5).
    -   Recherche dans l'historique.
    -   Upload Vidéo (Pegasus via S3).
    -   Drag & Drop et Menu contextuel.
    -   Prompts personnalisés (Domotique).

## Prochaines Étapes
-   Redéployer pour valider la stabilité.
-   Réintroduire le Journal plus tard de manière isolée (micro-service ou script externe).
