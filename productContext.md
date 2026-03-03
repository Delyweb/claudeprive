# Product Context: ClaudePrivé

## Raison d'être du projet
De nombreuses organisations ont besoin d'utiliser des outils d'IA générative avancés (comme Claude de Anthropic) mais hésitent à utiliser les interfaces publiques en raison de :
-   **Risques de sécurité** : Fuite de données sensibles ou propriétaires dans les prompts.
-   **Conformité** : Besoin de garder les données dans certaines régions (ex: UE).
-   **Contrôle des coûts** : Les abonnements par utilisateur peuvent être coûteux ou difficiles à justifier pour un usage ponctuel.
-   **Personnalisation** : Besoin de prompts système spécifiques (expert juridique, analyse financière) facilement accessibles à toute l'équipe.

## Expérience Utilisateur
L'utilisateur accède à une interface web (SPA) responsive qui ressemble aux outils de chat standard.
-   Il peut choisir son modèle (Sonnet pour la qualité, Haiku pour la rapidité/coût).
-   Il peut créer des "Projets" pour regrouper des discussions et des fichiers de contexte (ex: "Contrat Client X").
-   Il voit en temps réel le coût de chaque requête, ce qui responsabilise l'usage.
-   L'historique est conservé localement, sans dépendance à un service cloud tiers pour le stockage des chats.

## Problèmes Résolus
-   **Confidentialité** : Utilisation de l'API Bedrock où les données ne sont pas utilisées pour l'entraînement.
-   **Simplicité** : Pas de base de données complexe à gérer (tout est en JSON plat).
-   **Flexibilité** : Déploiement Docker sur n'importe quel serveur ou machine locale.
