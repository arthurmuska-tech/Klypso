# KLYPSO V10

KLYPSO est un workspace vidéo pour créateurs qui réunit **Klypso Clips**, **Klypso Studio**, le montage assisté local et un **Brand Kit**.

La V10 est une fusion de la base fonctionnelle de la V3 et de l'expérience produit de la V8, avec conservation des protections, pages légales, authentification, plans, promotions, Stripe et tests de la V3.

## Démarrage local

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

FFmpeg et FFprobe sont nécessaires aux traitements vidéo réels.

## Déploiement Render

- Root Directory : `Klypso-legal-audit-v3`
- Build Command : `apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt`
- Start Command : `gunicorn --workers 2 --threads 4 --timeout 120 web_app:app`
- Health check : `/healthz`
- Python : 3.12.x

## Stripe

Les vrais identifiants Stripe doivent rester dans les variables d'environnement :

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRO_PRICE_ID`
- `STRIPE_ULTRA_PRICE_ID`
- `STRIPE_PRO_ANNUAL_PRICE_ID`
- `STRIPE_ULTRA_ANNUAL_PRICE_ID`

Aucun identifiant de production n'est inventé dans le dépôt.

## V10 : montage assisté

`POST /studio/ai-edit` produit réellement une nouvelle vidéo avec les traitements FFmpeg disponibles, notamment réduction de certains silences et normalisation audio. La V10 n'affiche pas une génération LLM distante comme si elle était active sans service externe configuré.

## Juridique

Les pages juridiques restent présentes. Les informations inconnues sur l'éditeur, l'entreprise, les coordonnées, l'hébergeur et les mentions commerciales sont volontairement laissées sous forme de paramètres à compléter.
