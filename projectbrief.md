# Project Brief: ClaudePrivé

## Vue d'ensemble
ClaudePrivé est une application de chat professionnel sécurisée, auto-hébergée, qui utilise les modèles d'IA **Claude** (via **AWS Bedrock**) pour garantir la confidentialité des données. Elle est conçue pour être déployée en interne (sur un serveur privé ou en local) afin d'offrir une alternative à ChatGPT/Claude.ai pour les équipes soucieuses de la sécurité de leurs données.

## Objectifs Principaux
1.  **Confidentialité Totale** : Les conversations et les fichiers uploadés restent dans l'infrastructure de l'utilisateur (disque local) et ne transitent que vers le compte AWS de l'utilisateur (via Bedrock), sans entraînement de modèle public.
2.  **Maîtrise des Coûts** : Suivi précis de la consommation de tokens (input/output) par jour et par mois.
3.  **Productivité** : Interface de chat moderne, gestion de projets contextuels, et prompts système personnalisables pour des tâches spécifiques (juridique, dev, rédaction, etc.).
4.  **Simplicité de Déploiement** : Architecture légère (Docker, Flask, JSON storage) facile à installer et à maintenir.

## Fonctionnalités Clés
-   Chat avec historique persistant.
-   Support des modèles Claude 3.5 Sonnet et Claude 3 Haiku.
-   Upload et analyse de documents (PDF, DOCX, TXT, etc.).
-   Organisation par "Projets" (regroupement de chats et de documents).
-   Bibliothèque de prompts système.
-   Dashboard de suivi des coûts d'API.
