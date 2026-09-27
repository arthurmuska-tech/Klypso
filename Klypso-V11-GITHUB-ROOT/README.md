# KLYPSO V22

Workspace vidéo Flask pour créateurs : Clips, Studio, Brand Kit et abonnements.

## Déploiement Render

Le projet est prévu pour être placé avec `requirements.txt` à la racine du dépôt GitHub.

Build Command :

```bash
pip install -r requirements.txt
```

Start Command :

```bash
gunicorn --workers 2 --threads 4 --timeout 120 web_app:app
```

Le frontend est une refonte de l'interface avec une navigation latérale, des écrans de création, une bibliothèque de projets, un éditeur à trois zones et des panneaux d'inspection. L'authentification web principale utilise e-mail + mot de passe avec Google Credential Sign-In en option.

Les contrôles visuels qui ne disposent pas encore d'un endpoint serveur restent clairement des contrôles d'interface ; ils ne prétendent pas exécuter un traitement backend non présent.


## Dossier produit

Voir `docs/PRODUCT_READINESS_V20.md` pour l'architecture, les intégrations, la couverture de tests, les contraintes des API sociales et les éléments utiles à une reprise par un acquéreur.

## Publication sociale native

YouTube et TikTok disposent d'une couche OAuth native optionnelle. Instagram et X restent compatibles via adapters/webhooks dans V22. L'authentification Apple n'est pas proposée dans cette version.
