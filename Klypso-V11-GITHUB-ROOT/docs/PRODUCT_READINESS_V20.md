# KLYPSO V22 — Product Readiness & Buyer Dossier

## Positionnement

KLYPSO est une plateforme de transformation de streams en contenu social. Le produit combine détection de moments, analyse transcript/média/chat, mémoire du créateur, rendu social, distribution programmée, performance feedback et Klypso Studio.

Le différenciateur produit n'est pas un nombre de lignes de code : c'est la combinaison d'un workflow cohérent, de modules indépendants, de données persistées, d'intégrations, de tests et d'une capacité à apprendre des performances réelles.

## Modules fonctionnels

### Intelligence de clipping
- couverture temporelle large + candidats déclenchés par signaux
- détection de changements de scène, pics audio et silences
- import et analyse de chat Twitch/Kick/YouTube
- 15 agents de scoring spécialisés
- Creator DNA : préférences, feedbacks et historiques de performance
- sélection multicritère hook/payoff/émotion/nouveauté/contexte/partage/replay
- diversité anti-doublons
- fallback local sans fournisseur cloud

### Vision et rendu
- suivi facial local OpenCV
- focalisation X/Y pour cadrage vertical
- heuristique gameplay (FPS, battle royale, MOBA, football, variété)
- formats 9:16 / 4:5 / 1:1 / 16:9
- captions SRT et styles Dynamic / Classic / Minimal
- zoom, contraste, saturation, sharpen, fades
- normalisation audio + nettoyage Clean / Broadcast / None
- motion graphic de progression
- rendu multi-réseaux

### Assets génératifs
- B-roll image via Gemini, lorsque la clé Gemini est configurée
- voiceover via ElevenLabs, lorsque la clé et la voix sont configurées
- composition B-roll + voiceover + clip en MP4

### Distribution
- file de publication
- cadence quotidienne / hebdomadaire / mensuelle
- analytics vues / likes / commentaires / partages / complétion
- apprentissage Creator DNA à partir des métriques
- stratégie de distribution basée sur les créneaux, jours et réseaux observés
- publication native OAuth YouTube
- publication native OAuth TikTok
- webhooks/adapters pour Instagram et X

### Klypso Studio
- projets persistés par utilisateur
- sauvegarde et autosave
- aperçu vidéo navigateur
- undo / redo
- export JSON de projet
- split / trim / move / duplicate / delete
- markers
- réglages persistés : ratio, audio cleanup, caption style, social preset

## Architecture technique

- Flask
- SQLite avec clés étrangères et index ciblés
- stockage média par utilisateur
- FFmpeg / FFprobe
- Authlib pour OAuth Google
- Fernet pour chiffrement des tokens sociaux au repos
- Stripe pour les abonnements
- Google Credential Sign-In pour l'authentification, avec e-mail + mot de passe comme parcours principal
- Gemini / Groq / OpenRouter pour les moteurs IA optionnels
- ElevenLabs pour la voix optionnelle
- Render web service + cron de distribution
- GitHub Actions pour compilation, syntaxe JS/CSS et suite pytest

## Intégrations natives

YouTube : OAuth serveur, scope youtube.upload, upload média résumable, et choix de confidentialité via les métadonnées serveur.

TikTok : OAuth Login Kit v2, scope video.publish, Direct Post API, lecture des options de confidentialité du créateur avant publication et suivi du statut asynchrone.

### Contraintes externes

Les API sociales restent soumises aux validations, audits, limites de quota, règles de comptes et configurations développeur propres aux plateformes.

TikTok impose notamment l'approbation du scope video.publish pour le Direct Post. Les clients non audités peuvent être limités au privé, et PULL_FROM_URL exige une propriété de domaine/URL vérifiée.

Instagram et X disposent encore de chemins adapter/webhook dans cette version et ne doivent pas être présentés comme des publications OAuth natives déjà entièrement opérationnelles.

## Déploiement

Le service web est configuré pour Python 3.12 et Gunicorn. Le cron appelle le service web avec un secret partagé pour exécuter les publications dues et synchroniser les publications TikTok en cours.

Variables sensibles principales : SECRET_KEY, STRIPE_*, GOOGLE_CLIENT_*, GEMINI_*, GROQ_*, OPENROUTER_*, ELEVENLABS_*, TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET.

## Qualité et preuve de maturité

La suite CI V20 compile explicitement les modules critiques et exécute l'ensemble du dossier tests. Les tests couvrent le moteur média et chat, le suivi facial et gameplay, le scoring et Creator DNA, le rendu et l'audio, le lifecycle/isolation des projets Studio, le chiffrement des connexions sociales, OAuth TikTok, publication native YouTube et stratégie de distribution.

## Ce qui augmente réellement la valeur de revente

Pour un acquéreur, la valeur vient surtout de la fonctionnalité réellement démontrable, du code modulaire, du déploiement reproductible, des tests, des intégrations, des utilisateurs et de la rétention, du revenu récurrent, des coûts d'infrastructure, de la propriété des assets et de la documentation.

Le nombre de lignes peut servir de métrique descriptive, mais ne doit pas être utilisé comme proxy direct de la valeur.

## État V22

Version : 22.0.0

Objectif produit : disposer d'un produit démontrable et transmissible, de la VOD à la publication et à l'apprentissage par la performance.

Limites connues : tracking vidéo encore heuristique, Studio pas encore au niveau d'un NLE complet, B-roll/voiceover dépendants de fournisseurs configurés, Instagram/X encore adapter-based, Google/les publications sociales nécessitent leurs identifiants développeur respectifs.