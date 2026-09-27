# KLYPSO V22 — Sale Handoff

## Produit
KLYPSO est une plateforme web Flask de transformation de streams en contenu social : détection de moments, rendu vertical, captions, Creator DNA, publication sociale et Klypso Studio.

## Inclus dans le dépôt
- Application Flask + templates + interface responsive
- Pipeline de clipping et scoring multi-signaux
- Analyse média, audio, chat, vision et heuristiques gameplay
- Rendu FFmpeg pour 9:16, 4:5, 1:1 et 16:9
- Captions et presets sociaux
- Klypso Studio avec projets, autosave, undo/redo, split/trim/move/duplicate/delete et rendu
- Publisher avec file d'attente et cadence
- Intégrations YouTube/TikTok optionnelles
- Creator DNA et mémoire de performance
- Stripe pour les abonnements
- Suite de tests pytest + contrôles syntaxiques Python/JS/CSS
- Déploiement Render avec service web et cron
- Authentification e-mail + mot de passe et Google Credential Sign-In optionnel

## Authentification
La connexion Apple a été retirée du code, des templates et du blueprint Render.
Le parcours principal est e-mail + mot de passe. Google reste optionnel et dépend de GOOGLE_CLIENT_ID côté Render ainsi que de la configuration du projet Google.

## Configuration acheteur
Les clés et comptes externes ne font pas partie du code :
- Stripe : clés et Price IDs
- Google : Client ID / Secret
- Gemini / Groq / OpenRouter : clés IA selon les fonctions activées
- ElevenLabs : clé et voix si le voiceover est vendu
- TikTok : Client Key / Secret si Direct Post est activé
- Variables légales et coordonnées du vendeur/exploitant
- Domaine personnalisé, lorsque l'acheteur remplace le sous-domaine Render

## Point de vérité commercial
Les fonctionnalités doivent être présentées selon leur état réel. Les API sociales restent soumises aux comptes développeur, validations, quotas et restrictions des plateformes. Instagram/X ne doivent pas être présentés comme des publications OAuth natives entièrement opérationnelles sans configuration supplémentaire.

## État technique
Version : 22.0.0
Déploiement cible : Render
Service : Klypso
Health endpoint : /healthz

## Valeur de reprise
La valeur d'un produit de ce type dépend surtout des fonctions démontrables, de la qualité du code, des intégrations, du déploiement, des tests, de la documentation, des utilisateurs, du revenu récurrent, des coûts et de la transférabilité. Le volume de code seul n'est pas une méthode de valorisation.

## Avant une vente
Un acheteur devra recevoir le dépôt, les instructions de déploiement, la liste des variables d'environnement sans les secrets eux-mêmes, les comptes/contrats transférables et les informations légales nécessaires au changement d'exploitation.
