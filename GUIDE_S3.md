# Guide : Configurer le stockage vidéo S3 pour ClaudePrivé

Pour permettre à Claude d'analyser vos vidéos de réunion (fichiers > 25 Mo), vous devez configurer un espace de stockage sécurisé sur AWS S3.

## Étape 1 : Créer le Bucket S3

1.  Connectez-vous à la **Console AWS**.
2.  Cherchez le service **S3**.
3.  Cliquez sur le bouton orange **Créer un compartiment** (Create bucket).
4.  **Nom du compartiment** : Choisissez un nom unique, par exemple `claudeprive-videos-votre-entreprise`.
5.  **Région AWS** : Choisissez **Europe (Paris) eu-west-3**.
6.  **Paramètres de blocage de l'accès public** : Laissez tout coché (Bloquer tout l'accès public). C'est crucial pour la confidentialité.
7.  Cliquez sur **Créer le compartiment** tout en bas.

## Étape 2 : Configurer l'application

Une fois le bucket créé, vous devez dire à l'application de l'utiliser.

1.  Ouvrez votre fichier `docker-compose.yml` sur le serveur.
2.  Ajoutez la variable d'environnement `S3_VIDEO_BUCKET` dans la section `environment` :

```yaml
services:
  app:
    environment:
      - AWS_ACCESS_KEY_ID=...
      - AWS_SECRET_ACCESS_KEY=...
      - AWS_DEFAULT_REGION=eu-west-3
      - S3_VIDEO_BUCKET=claudeprive-videos-votre-entreprise  <-- Ajoutez cette ligne
```

3.  Redémarrez l'application :
    ```bash
    docker-compose up -d
    ```

## Étape 3 : Permissions IAM (Si nécessaire)

Assurez-vous que l'utilisateur IAM (dont vous utilisez les clés d'accès) a le droit d'écrire dans S3.
Vous pouvez lui attacher la politique `AmazonS3FullAccess` ou une politique plus restrictive :

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
            "Resource": "arn:aws:s3:::claudeprive-videos-votre-entreprise/*"
        }
    ]
}
```

Une fois ceci fait, l'application utilisera automatiquement ce bucket pour traiter les grosses vidéos avec Pegasus.
