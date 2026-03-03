# Active Context: ClaudePrivé

## Focus Actuel
Le projet est en phase d'extension fonctionnelle. Des capacités avancées de **Recherche** (Mémoire Globale) et d'**Analyse Vidéo** (Pegasus) ont été ajoutées.

## Changements Récents
-   **Recherche Globale** : Ajout d'une barre de recherche dans la sidebar pour scanner toutes les conversations passées et retrouver des informations.
-   **Support Vidéo (Pegasus)** : Intégration de Twelve Labs Pegasus pour transcrire les vidéos. Nécessite une configuration S3 pour les fichiers > 10 Mo.
-   **Documentation S3** : Ajout d'un guide (`GUIDE_S3.md`) pour aider l'utilisateur à configurer son bucket.
-   **Interface v2.3** : Ajout de la barre de recherche.

## Prochaines Étapes
-   L'utilisateur doit configurer son bucket S3 et les variables d'environnement sur le serveur pour activer pleinement Pegasus.
-   Mise à jour du serveur requise.
