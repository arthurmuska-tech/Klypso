# KLYPSO — configuration Stripe

Le code Stripe est déjà préparé dans `klypso/billing.py` et `klypso/config.py`.
Il ne faut pas mettre de clé Stripe dans GitHub.

## Variables Render à renseigner demain

Dans **Render → Klypso → Environment** :

- `STRIPE_SECRET_KEY` — clé secrète Stripe (`sk_test_...` pendant les tests, puis `sk_live_...` en production).
- `STRIPE_WEBHOOK_SECRET` — secret du endpoint webhook (`whsec_...`).
- `STRIPE_PRO_PRICE_ID` — Price ID Pro mensuel.
- `STRIPE_ULTRA_PRICE_ID` — Price ID Ultra mensuel.
- `STRIPE_PRO_ANNUAL_PRICE_ID` — Price ID Pro annuel, lorsque l'offre annuelle est créée.
- `STRIPE_ULTRA_ANNUAL_PRICE_ID` — Price ID Ultra annuel, lorsque l'offre annuelle est créée.

Ces variables sont déjà déclarées en `sync: false` dans `render.yaml`.

## Offres prévues

Les montants actuellement affichés par défaut dans KLYPSO sont :

- Pro : 12,99 € / mois
- Ultra : 29,99 € / mois
- Essai : 10 jours sur Render

Les Price IDs doivent correspondre exactement aux prix créés dans Stripe. Ne pas inventer un Price ID.

## Webhook

Endpoint KLYPSO :

`https://klypso-2pjf.onrender.com/billing/webhook`

Événements actuellement traités :

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`

Le webhook vérifie la signature Stripe et ignore les événements déjà enregistrés.

## Ce que le code fait déjà

- Checkout Pro / Ultra mensuel ou annuel.
- Essai contrôlé par `STRIPE_TRIAL_DAYS`.
- Association du `stripe_customer_id` au compte KLYPSO.
- Synchronisation du plan et du statut d'abonnement depuis les webhooks.
- Passage en `past_due` après échec de paiement.
- Retour au plan Free après suppression de l'abonnement.
- Portail Stripe pour gérer l'abonnement.
- Protection CSRF sur les actions utilisateur.
- Vérification de signature spécifique au webhook.

## Demain : ordre conseillé

1. Créer les produits Pro et Ultra dans Stripe.
2. Créer les Price IDs mensuels.
3. Créer les Price IDs annuels si tu veux les proposer.
4. Configurer le Customer Portal.
5. Créer le webhook avec l'URL ci-dessus.
6. Copier le `whsec_...` dans Render.
7. Mettre les Price IDs dans Render.
8. Mettre la clé secrète Stripe dans Render.
9. Tester en **mode test Stripe** avant tout passage en live.
10. Tester : Checkout → webhook → compte KLYPSO → abonnement → portail → annulation.

## Important

Les clés Stripe restent uniquement dans les variables d'environnement Render. Elles ne doivent jamais être copiées dans `render.yaml`, dans le code ou dans GitHub.
