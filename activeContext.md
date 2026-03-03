# Active Context: ClaudePrivé

## Focus Actuel
Le projet est stabilisé après un correctif d'urgence sur le journal automatique (erreur 502). Les fonctionnalités de **Journal Manuel** et **Expertise Domotique** ont été ajoutées.

## Changements Récents
-   **Journal** : Désactivation du scheduler automatique (cron 23h) en production pour éviter les conflits Gunicorn. La génération manuelle (bouton) reste active.
-   **Prompts** : Ajout du prompt "Expert Domotique" par défaut.
-   **Correctifs** : Résolution du bug d'ajout de prompt et de l'erreur 502.

## Prochaines Étapes
-   Surveiller la stabilité.
-   Réactiver le scheduler automatique plus tard via un worker dédié si besoin.
