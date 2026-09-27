# KLYPSO V23 — Production Runbook

## Architecture cible

- Web KLYPSO sur Render avec plusieurs instances possibles.
- PostgreSQL durable pour les comptes, projets, jobs, abonnements et métriques.
- S3/Cloudflare R2 ou stockage objet compatible pour les VOD, MP4, images et audio.
- Worker Render séparé pour les analyses IA et traitements lourds.
- Cron Render toutes les 10 minutes pour déclencher la publication programmée.
- Stripe pour les abonnements.
- Google OAuth facultatif.
- Gemini/Groq/OpenRouter et ElevenLabs facultatifs selon les fonctionnalités activées.

## Garde-fous applicatifs

En production, le Blueprint active :

- AI_WORKER_MODE=external
- REQUIRE_POSTGRES=true
- REQUIRE_OBJECT_STORAGE=true
- JOB_STALE_SECONDS=1800
- JOB_MAX_ATTEMPTS=3
- WORKER_HEARTBEAT_SECONDS=30
- TRIAL_DAYS=14
- STRIPE_TRIAL_DAYS=14

`/readyz` refuse alors un déploiement qui n'a pas PostgreSQL ou le stockage objet réellement disponibles.

## Secrets à renseigner

Les valeurs marquées `sync: false` dans `render.production.yaml` doivent être renseignées avec les vraies valeurs du projet.

Ne jamais committer de clé Stripe, OAuth, IA, e-mail, stockage objet ou secret de cron dans Git.

Les champs légaux doivent contenir les informations réelles de l'opérateur de KLYPSO avant une commercialisation publique.

## Migration de la base

Le dépôt fournit `scripts/migrate_sqlite_to_postgres.py` pour transférer une base SQLite existante vers PostgreSQL.

Après migration, vérifier au minimum :

1. nombre de comptes ;
2. projets ;
3. jobs ;
4. médias ;
5. métriques ;
6. abonnements Stripe.

## Stockage média

Les nouvelles créations utilisent désormais l'URI persistée renvoyée par le stockage objet. Le worker ne dépend plus du chemin local temporaire créé pendant l'upload.

Le stockage local reste disponible pour le développement et les tests.

## Jobs

Les jobs IA passent par la table `jobs`.

Le worker :

- verrouille les jobs concurrents sur PostgreSQL ;
- incrémente les tentatives ;
- envoie un heartbeat pendant les traitements longs ;
- récupère automatiquement un job abandonné après le délai configuré ;
- marque un job en échec après trop de tentatives ;
- supporte un mode `WORKER_ONCE=true` pour les smoke tests.

## Avant d'ouvrir les ventes

- vérifier `/healthz` et `/readyz` ;
- lancer la CI GitHub ;
- tester un upload vidéo réel ;
- tester une analyse IA réelle ;
- tester un rendu MP4 réel ;
- tester un téléchargement ;
- connecter YouTube/TikTok avec un compte de test ;
- tester une publication programmée ;
- tester le webhook Stripe ;
- tester l'annulation d'abonnement ;
- vérifier les CGU/CGV/confidentialité et les mentions légales ;
- vérifier les métriques d'administration.

## Note coût

Le profil `render.production.yaml` utilise des services payants pour sortir des limites du déploiement gratuit. Le profil gratuit actuel n'est pas considéré comme l'architecture de montée en charge finale.