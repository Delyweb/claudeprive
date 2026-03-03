# Active Context: ClaudePrivé

## Focus Actuel
Le projet est en phase d'enrichissement fonctionnel. Les dernières mises à jour incluent une **Mémoire Globale** (Recherche), l'**Upload Vidéo** (Pegasus) et maintenant un **Journal Quotidien Automatique**.

## Changements Récents
-   **Journal Quotidien** : Un job automatique (Cron) scanne chaque soir à 23h00 les projets actifs et génère un document de synthèse Markdown (Actions, Infos clés, Risques). Un bouton permet aussi de le déclencher manuellement.
-   **Recherche Globale** : Ajout d'une barre de recherche dans la sidebar pour scanner toutes les conversations passées.
-   **Support Vidéo (Pegasus)** : Intégration de Twelve Labs Pegasus pour transcrire les vidéos (avec S3).
-   **Documentation S3** : Guide `GUIDE_S3.md` disponible.
-   **Interface v2.3** : Ajout de la barre de recherche et du bouton Journal.

## Prochaines Étapes
-   L'utilisateur doit configurer son bucket S3 pour la vidéo.
-   Mise à jour du serveur requise pour activer le Journal et la Recherche.
