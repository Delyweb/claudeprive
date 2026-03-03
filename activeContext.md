# Active Context: ClaudePrivé

## Focus Actuel
Le projet a été restauré à un état stable (v2.3) après une série de problèmes liés au module de Journalisation Automatique. La priorité est la fiabilité du Chat, du RAG et de l'analyse Vidéo.

## Changements Récents
-   **ROLLBACK (03/03/2026)** : Suppression complète de la fonctionnalité "Journal" (code + dépendances) pour résoudre l'erreur 502 persistante.
-   **Fonctionnalités Actives & Stables** :
    -   Chat avec modèles 2026 (Opus 4.6, Sonnet 4.5, Haiku 4.5).
    -   **RAG (Mémoire)** : Injection automatique du contenu des fichiers texte/PDF du projet.
    -   **Vidéo** : Support upload 500Mo + Pegasus (via S3).
    -   **Interface** : Drag & Drop, Menu contextuel, Recherche.
    -   **Prompts** : Expert Domotique inclus.

## Prochaines Étapes
-   Redéploiement propre (`docker-compose down` puis `up --build`).
-   Validation du bon fonctionnement des fonctionnalités de base.
