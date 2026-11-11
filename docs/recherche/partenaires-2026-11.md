# Les partenaires : recherche du 11 novembre 2026

Préparation du **bureau partenaire** (à concevoir). Les partenaires sont **facultatifs** : la factory doit pouvoir s'en passer ; le bureau les liste et en conseille selon le projet. Pour chaque service : API et serveur MCP, plan gratuit, plans payants, et surtout **si l'API permet de lire le quota restant**, ce qui décide de ce que le bureau pourra afficher (« reste N », « illimité », ou « inconnu »).

**Fiabilité.** (O) = lu sur la page officielle. Sans marque = agrégateurs tiers, qui se contredisent souvent : à revérifier avant d'afficher un prix. Les prix sont dans la devise d'origine. Plusieurs pages officielles étaient illisibles (Kling, Pika, HeyGen, D-ID, Hedra, Veo, Stability, Ideogram, Leonardo, Adobe).

Légende de la colonne Quota : ✅ endpoint confirmé · 🟡 probable ou partiel · ❌ pas par l'API (console ou cloud) · ❔ inconnu.

## Ce qu'il faut retenir pour le bureau

- **Rares sont ceux qui donnent leur solde par l'API** : ElevenLabs, Black Forest Labs (FLUX), Stability, Leonardo, Meshy, remove.bg, DeepL, KIRI Engine ; les banques de médias (Unsplash, Pexels, Pixabay, Openverse) donnent leur limite dans les en-têtes de réponse. Probables : fal.ai, Runway, AutoSprite (outil MCP `get_account`). Le bureau doit donc gérer proprement l'état « quota inconnu ».
- **Serveur MCP officiel** : ElevenLabs, Runway, HeyGen, Meshy, Replicate, PixelLab, AutoSprite, Krea ; Exa, Tavily, Firecrawl, Brave, Jina ; Epidemic Sound, Figma, Canva, Gamma ; Vercel, Netlify, Cloudflare, Supabase, Render ; GitHub, GitLab, Linear, Atlassian, Notion, Google Drive, Slack, Trello, Asana. Probables : Cartesia, Deepgram, fal.ai.
- **Les agrégateurs** (fal.ai, Replicate, Runway API, Picsart) donnent accès à beaucoup de modèles avec une seule connexion : c'est un bon candidat pour les « connecteurs conseillés ».
- **Aucune offre de génération n'est illimitée** ; gratuits sans quota payant : Poly Haven, ambientCG, Iconify, Google Fonts, OpenStreetMap, OpenAI Moderation.
- **À écarter** : LMNT et PlayHT (fermés), OpenAI Sora (API arrêtée le 24/09/2026), Suno, Udio, Midjourney, Mixamo et Fab/Megascans (aucune API officielle), Tome (arrêté), la capture 3D de Luma (pas d'API). Clipdrop est incertain (tarifs retirés).

## 1. Voix et audio

### Synthèse vocale et clonage

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **ElevenLabs** (O) | oui / oui | 10 000 caractères et 4,5 h de transcription par mois | Starter 6 $/mois (75 k car.), Creator 22 $ (275 k), Pro 99 $ (1,24 M), Scale 299 $, Business 990 $ ; à l'usage 0,04 à 0,08 $ / 1 000 car. | ✅ `GET /v1/user/subscription` |
| **Cartesia** (O) | oui / oui (signalé) | 20 000 crédits/mois | Pro 5 $ (100 k crédits), Startup 49 $ (1,25 M), Scale 299 $ (8 M) ; ≈ 1 crédit par caractère | ❔ |
| **OpenAI audio** (O) | oui / non | non | tts-1 15 $, tts-1-hd 30 $ par million de caractères | ❌ |
| **Google Cloud TTS** | oui / non | palier mensuel (à vérifier) | 4 à 160 $ par million de caractères selon la voix (à vérifier) | ❌ |
| **Azure Speech** | oui / non | 0,5 M car./mois, 5 h de transcription | prix non lus | ❌ |
| **Amazon Polly** (O) | oui / non | 5 M car./mois (Standard) | 4 à 100 $ par million de caractères | ❌ |
| **AssemblyAI TTS** | oui / doc seulement | 50 $ de crédits | 15 $ par million de caractères | ❔ |
| **Deepgram Aura** | oui / CLI | 200 $ de crédits | 0,015 à 0,045 $ / 1 000 car. | ❔ |
| Murf, WellSaid, Resemble, Fish Audio | oui | essais | prix tiers seulement | ❔ |

### Transcription

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **ElevenLabs Scribe** | oui / oui | 4,5 h/mois | 0,20 $/h | 🟡 même endpoint |
| **Deepgram** (O) | oui / CLI | 200 $ de crédits | Nova-3 0,0043 $/min | ❔ |
| **AssemblyAI** (O) | oui / doc | 50 $ de crédits | 0,15 à 0,45 $/h | ❔ |
| **OpenAI** (O) | oui / non | non | 0,0045 à 0,006 $/min | ❌ |
| Speechmatics, Gladia, Cartesia Ink | oui | crédits d'essai | prix tiers | ❔ |

### Musique et effets sonores

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **ElevenLabs Music / SFX** | oui / oui | selon le plan | musique 0,15 $/min, effets 0,12 $/min | ✅ |
| **Mubert** (O) | oui (sur contact) | 25 pistes, sans usage commercial | 14 à 89 $/mois (app) ; API non publiée | ❔ |
| **Soundraw** (O) | oui | non trouvé | API Starter ≈ 30 $/mois (100 morceaux), Pro 300 $ | ❔ |
| **Stable Audio** | probable | non trouvé | non trouvé | 🟡 (solde Stability) |

Doublage : seul ElevenLabs est confirmé (0,33 à 0,50 $/min).

## 2. Images et graphisme

### Génération d'images

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **OpenAI Images** (O) | oui / non | non | gpt-image-2 : 8 $ / 30 $ par million de tokens (entrée / sortie) | ❌ |
| **Google Gemini image** (O) | oui / non | non | 0,034 à 0,24 $ par image selon le modèle et la taille | ❌ |
| **Black Forest Labs (FLUX)** | oui / non | non trouvé | crédits prépayés (1 crédit = 0,01 $), ≈ 0,014 à 0,03 $ par image | ✅ `GET /v1/credits` |
| **Stability AI** | oui / non | 25 crédits | 10 $ les 1 000 crédits | ✅ `GET /v1/user/balance` |
| **Ideogram** | oui / non | app seulement | API ≈ 0,003 à 0,03 $ par image | ❌ (tableau de bord) |
| **Leonardo** | oui / non | app (montant incertain) | crédits rechargés ; plans app 12 à 60 $ | ✅ `GET /api/rest/v1/me` |
| **Runway images** (O) | oui / oui | non trouvé | 1 crédit = 0,01 $ ; 1 à 8 crédits par image | 🟡 |
| **Krea** | oui / oui | non trouvé | solde prépayé ; ≈ 0,03 à 0,06 $ par image | ❔ |
| **Freepik / Magnific** | oui / non | ≈ 5 € d'essai | à la consommation | ❔ |
| **Adobe Firefly** | restreint (contrat) | app : 25 crédits | engagement ≈ 1 000 $/mois | ❔ |

### Plateformes multi-modèles

| Partenaire | API / MCP | Payant | Quota |
|---|---|---|---|
| **fal.ai** | oui / oui | prépayé, par image ou par seconde | 🟡 |
| **Replicate** | oui / **oui** (mcp.replicate.com) | prépayé, à l'usage | ❔ |
| **Picsart API** | oui / oui | ≈ 0,005 $ le crédit | 🟡 |

### Retouche, détourage, agrandissement, vectoriel

| Partenaire | Spécialité | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Recraft** (O) | vectoriel (SVG), retouche, logos | app seulement | ≈ 0,001 $ l'unité ; vecteur 0,09 à 0,33 $ | ❔ |
| **remove.bg** | détourage | basse résolution | 0,08 à 0,20 $ l'image | ✅ `GET /v1.0/account` |
| **Photoroom** | détourage, photo produit | bac à sable | dès 20 $/mois ; 0,02 à 0,10 $ l'image | 🟡 |
| **Topaz** (O) | agrandissement | 100 crédits | ≈ 0,12 $ le crédit | ❔ |
| **Clipdrop** | retouche | ? | tarifs retirés : à surveiller | ❔ |

### Sprites et assets de jeu 2D

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **AutoSprite** (déjà branché ici) | oui / **oui** | 15 crédits/mois | Starter 12 $, Pro 29 $ (API et MCP), Enterprise 99 $ | 🟡 outil `get_account` |
| **PixelLab** | oui / **oui** | essai | prix non confirmés (≈ 12 $/mois) | ❔ |
| **Scenario** | oui (plans payants) | 50 crédits/jour | Starter 15 $ (1 500 crédits), Pro ≈ 45 $ | ❔ (coût avant appel par `dryRun`) |

Textures : pas de recherche dédiée (Scenario et Stability les couvrent).

## 3. Vidéo, 3D et avatars

### Génération de vidéo

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Runway** (O) | oui / **oui** | app : 125 crédits | API : 1 crédit = 0,01 $ ; 5 à 30 crédits par seconde selon le modèle (donne aussi Veo, Kling, Seedance) | 🟡 `/v1/organization` |
| **Google Veo** | oui / ? | non | 0,05 à 0,60 $ par seconde | ❌ |
| **Kling** | oui / non | ? | ≈ 0,06 à 0,42 $/s (forfaits prépayés) | ❔ |
| **MiniMax Hailuo** (O) | oui / non | non | 0,10 à 0,49 $ la vidéo de 6 s | ❌ (console) |
| **Luma** (O) | oui / non | non | API à l'usage ; app 30 à 300 $/mois | ❔ |
| **Seedance** (ByteDance) | oui / non | ? | au million de jetons | ❔ |
| **Wan, LTX, Vidu, PixVerse** | oui / non | ? | ≈ 0,05 à 0,80 $ | ❔ |
| **fal.ai** (O) | oui / oui | non | par seconde (Kling 0,07 à 0,14 $/s) | 🟡 |

Pika : plus d'API publique autonome (passe par fal.ai).

### Avatars parlants et synchronisation labiale

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **HeyGen** | oui / **oui** | non (depuis fév. 2026) | portefeuille API dès 5 $ ; ≈ 1 à 4 $/min | 🟡 |
| **Synthesia** (O) | oui | 10 min/mois avec filigrane | Starter 19 $, Creator ≈ 89 $ | ❔ |
| **Sync Labs** (O) | oui | 3 générations de 15 s/mois | 5 à 249 $/mois + 0,04 à 0,13 $/s | 🟡 (estimation de coût) |
| **D-ID, Tavus, Hedra** | oui | essais | 6 à 975 $/mois selon l'offre (tiers) | ❔ |

Montage automatique par API : JSON2Video (600 crédits gratuits), Creatomate, Shotstack (prix non confirmés).

### Modèles 3D, rigging, animation

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Meshy** (O) | oui (dès Pro) / **oui** | 100 crédits/mois, sans API | Pro 19 €, Premium 38 €, Ultra 95 € par mois | ✅ `GET /openapi/v1/balance` |
| **Tripo** (O, déjà utilisé ici) | oui / CLI | ? | API : 1 crédit = 0,01 $ ; 10 à 30 crédits par modèle, auto-rig 25 | ❔ |
| **Rodin / Hyper3D** | oui (Business) | paiement au téléchargement | Creator 30 $, Business 120 $ | ❔ |
| **CSM** | oui | 1 crédit | 20 à 60 $/mois | ❔ |
| **Stability 3D** | oui | 25 crédits | ≈ 0,10 $ par appel | 🟡 |
| **Move.ai** | oui (sur demande) | 30 crédits | capture par seconde de vidéo ; API sur devis | ❔ |
| DeepMotion, Kaedim, Hunyuan3D, Rokoko, Plask | restreint ou incertain | — | sur devis ou inconnu | ❔ |

## 4. Langue, web et agents

### Traduction et localisation

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **DeepL** (O) | oui / non | API Free 500 000 car./mois | app de 7,49 à 49,99 €/mois ; API Pro (prix non lu) | ✅ `GET /v2/usage` |
| **Amazon Translate** (O) | oui / non | 2 M car./mois pendant 12 mois | 15 $ par million de caractères | ❌ |
| **Azure Translator** (O) | oui / non | 2 M car./mois | à l'usage (prix non lu) | ❌ |
| **Google Translation** | oui / non | ≈ 500 000 car./mois | ≈ 20 $ par million (à vérifier) | ❌ |
| **Lokalise** (O) | oui / non | essai 14 jours | 149 à 1 049 $/mois | ❔ |
| **Phrase** (O) | oui / non | essai 14 jours | 27 à 1 245 /mois | ❔ |
| **Crowdin** (O) | oui / non | gratuit pour l'open source | prix non lus | ❔ |

### Sous-titres et texte depuis la vidéo

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Rev AI** (O) | oui / non | 5 h de transcription | 0,20 $/h ; humain 1,99 $/min | ❔ |
| **Descript** (O) | oui / oui (annoncé) | 60 min/mois | 16 à 65 $/mois par personne | ❔ |
| **Vizard** (O) | oui / non | 60 min/mois, filigrane | 600 min/mois et plus (prix non lus) | ❔ |
| Opus Clip | liste d'attente | ? | ? | ❔ |

### Recherche et collecte web pour les agents

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Exa** (O) | oui / oui | 10 $/mois de crédits | dès 4 $ les 1 000 recherches | ❔ |
| **Tavily** (O) | oui / oui | 1 000 crédits/mois | 30 $/mois (4 000) ou 0,008 $ le crédit | 🟡 `GET /usage` |
| **Firecrawl** (O) | oui / oui | 1 000 crédits/mois | 19 à 749 $/mois | 🟡 |
| **Brave Search** | oui / oui | 5 $/mois de crédits | 5 $ les 1 000 requêtes | 🟡 en-têtes de limite |
| **Jina Reader** (O) | oui / oui | 10 M de tokens | tokens à l'achat | ❌ (tableau de bord) |
| **SerpAPI** (O) | oui / communautaire | 250 recherches/mois | 25 à 725 $/mois | 🟡 `GET /account.json` |
| **Perplexity** (O) | oui / ? | non | 5 $ les 1 000 recherches | ❌ (coût par réponse seulement) |
| **Apify** (O) | oui / ? | 5 $ d'usage/mois | 19 à 999 $/mois | 🟡 |
| **Browserbase** (O) | oui / ? | 1 h de navigateur | 20 à 99 $/mois | ❔ |

### Agents vocaux et personnages conversationnels

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Vapi** (O) | oui / ? | 5 $ de crédits | 0,05 $/min + modèles ; Core 29 $/mois | ❔ |
| **Retell** (O) | oui / ? | 10 $ de crédits | 0,07 à 0,31 $/min | ❔ |
| **Bland** (O) | oui / ? | plan Start à 0 $ | Build 299 $/mois | ❔ |
| **Inworld** (O) | oui / ? | 70 min de voix | 25 à 1 500 $/mois | ❔ |
| Hume, Convai | oui | essais | prix tiers contradictoires | ❔ |

### Détection et modération

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **OpenAI Moderation** (O) | oui | **gratuit** (texte et image) | — | sans objet |
| **Sightengine** (O) | oui | 2 000 opérations/mois | 29 à 99 $/mois | ❔ |
| **Hive / Deploy** (O) | oui | non | 0,50 à 3 $ les 1 000 requêtes | ❔ |
| **Reality Defender** | oui | 50 analyses/mois | sur devis | ❔ |
| Resemble Detect | oui | contradictoire | ≈ 0,04 $ par seconde d'audio | ❔ |

## 5. Médias et design

### Banques de médias

| Partenaire | API / MCP | Gratuit | Payant | Quota | Licence |
|---|---|---|---|---|---|
| **Unsplash** (O) | oui / ? | 50 req/h (démo), 1 000 req/h en production | aucun | ✅ en-têtes `X-Ratelimit-*` | attribution obligatoire |
| **Pexels** (O) | oui / ? | 200 req/h, 20 000/mois | aucun | ✅ en-têtes `X-Ratelimit-*` | gratuit, crédit conseillé |
| **Pixabay** (O) | oui / ? | 100 req/min | aucun | ✅ en-têtes `X-RateLimit-*` | licence Pixabay |
| **Freesound** (O) | oui / ? | 2 000 req/jour | aucun | 🟡 | CC, selon le son |
| **Openverse** (O) | oui / ? | limites par heure et par jour | aucun | ✅ `/v1/rate_limit` | CC / domaine public |
| **Epidemic Sound** (O) | oui / **oui** | API gratuite pour prototyper | MCP : abonnement Epidemic | ❔ | selon l'abonnement |
| **Shutterstock** (O) | oui / ? | compte test (500 licences/mois) | sur devis | 🟡 | commerciale |
| Getty, Adobe Stock, Artlist | restreint (contrat) | — | sur devis | ❔ | commerciale |

### Icônes et polices

| Partenaire | API / MCP | Gratuit | Payant | Quota | Licence |
|---|---|---|---|---|---|
| **Iconify** (O) | oui, sans clé / ? | gratuit | aucun | sans objet | selon le jeu d'icônes |
| **Noun Project** (O) | oui / ? | essai 30 jours | dès 25 $/mois à l'usage | ❌ (tableau de bord) | commerciale incluse |
| **Google Fonts** (O) | oui (clé) / ? | gratuit | aucun | ❌ | OFL / Apache, commercial permis |
| Flaticon, Font Awesome | flou | version gratuite | ≈ 8 à 13 $/mois ; Pro ≈ 99 à 120 $/an | ❔ | attribution en gratuit |

### Textures, matériaux et assets 3D prêts à l'emploi

| Partenaire | API / MCP | Gratuit | Payant | Quota | Licence |
|---|---|---|---|---|---|
| **Poly Haven** (O) | oui, sans clé / communautaire | tout gratuit | aucun | sans limite documentée | **CC0** |
| **ambientCG** (O) | oui / ? | tout gratuit | aucun | ❔ | CC0 |
| **Sketchfab** (O) | oui (téléchargement en bêta) / ? | 500 000 modèles CC | Pro ≈ 15 $/mois | ❔ | CC selon le modèle |
| **Adobe Substance 3D** (O) | oui (contrat) / ? | non | sur contrat | ❔ | commerciale |
| Kenney, Fab / Megascans | pas d'API | gratuits | — | sans objet | CC0 / licence Fab |

### Scan 3D

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **KIRI Engine** (O) | oui / ? | ? | ? | ✅ endpoint « Balance » |
| Polycam | API Entreprise seulement | offre gratuite | ≈ 30 $/mois (contradictoire) | ❔ |
| RealityScan | logiciel de bureau, pas d'API | gratuit sous 1 M$ de revenu | 1 250 $/poste/an | sans objet |

### Design, maquettes, présentations

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Figma** (O) | oui / **oui** | 20 appels MCP/mois (sièges lecture) | siège Full ≈ 15 $ : 200 appels/jour | ❌ (rien de lisible) |
| **Canva** | oui / **oui** | plan gratuit | Pro ≈ 13 à 18 $/mois | ❔ |
| **Gamma** | oui / **oui** | clé API dès le plan gratuit (crédits) | Plus 9 $, Pro 18 $ | 🟡 crédits |
| **Framer** | bêta / oui (préversion) | plan gratuit | ≈ 10 $/mois | ❔ |
| **Penpot** | oui (jeton) / communautaire | open source | — | sans objet |

## 6. Mise en ligne et outils d'équipe

### Mise en ligne et hébergement

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Vercel** (O) | oui / **oui** | Hobby (non commercial) | Pro 20 $/mois | ❌ (tableau de bord) |
| **Netlify** (O) | oui / **oui** | 300 crédits/mois | 9 à 20 $/mois | ❔ |
| **Cloudflare** (Pages, R2, Workers) (O) | oui / **oui** | R2 : 10 Go, sortie gratuite | R2 0,015 $/Go-mois | ❔ |
| **GitHub Pages** (O) | via GitHub / oui | inclus (1 Go par site) | — | ❔ |
| **Supabase** (O) | oui / **oui** | 500 Mo de base, 1 Go de fichiers | Pro dès 25 $/mois | ❔ |
| **Render** (O) | oui / oui | 750 h/mois, mise en veille | Professional ≈ 19 $ (à revérifier) | ❔ |
| **Railway** (O) | oui / ? | 1 $/mois de crédit | 5 à 20 $/mois | ❔ |
| **Fly.io** (O) | oui / ? | **plus de plan gratuit** | à la seconde | ❔ |
| **itch.io** (O) | `butler` (envoi de builds) / ? | publication gratuite | partage de revenus | sans objet |

### Tests sur appareils réels

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **TestMu AI** (ex-LambdaTest) (O) | oui / ? | 100 min d'automatisation, 300 min HyperExecute | 15 à 199 $/mois | ❔ |
| **BrowserStack** (O) | oui / ? | essai | 12,50 à 225 $/mois | ❔ |
| **Sauce Labs** (O) | oui / ? | essai | 39 à 299 $/mois | ❔ |
| **Firebase Test Lab** (O) | oui / ? | 30 min/jour d'appareils réels | 5 $/h réel, 1 $/h virtuel | ❔ |
| **AWS Device Farm** (O) | oui / ? | 1 000 min d'essai | 0,17 $/min | ❔ |

### Cartes et graphiques

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Mapbox** (O) | oui / ? | 50 000 chargements de carte/mois | à l'usage | ❔ |
| **Google Maps** (O) | oui / ? | 1 000 à 10 000 appels gratuits par service/mois | 100 à 1 200 $/mois | ❌ |
| **MapTiler** (O) | oui / ? | 100 000 requêtes (non commercial) | 30 $/mois | ❔ |
| **Stadia Maps** (O) | oui / ? | 200 000 crédits (non commercial) | 20 à 250 $/mois | ❔ |
| **OpenStreetMap / Nominatim** (O) | oui, sans clé | gratuit, 1 requête/s, pas en masse | — | sans objet |
| **QuickChart** (O) | oui / ? | gratuit avec limite de débit | 39 €/mois | ❔ |
| **Datawrapper** (O) | oui / ? | gratuit | 21 à 39 €/mois | ❔ |

### Outils d'équipe (avec serveur MCP officiel)

| Partenaire | MCP officiel | Remarque |
|---|---|---|
| **GitHub** (O) | oui (`api.githubcopilot.com/mcp`) | code, tickets, demandes de fusion |
| **GitLab** (O) | oui, inclus dans le plan gratuit | l'administrateur doit l'autoriser |
| **Linear** (O) | oui (`mcp.linear.app`) | suivi des tâches |
| **Jira / Confluence** | oui (Atlassian Rovo) | suivi, documentation |
| **Notion** (O) | oui (`mcp.notion.com`) | tous les plans |
| **Google Drive** | oui (préversion) | aussi Gmail, Agenda, Docs |
| **Slack** (O) | oui (`mcp.slack.com`) | réservé aux applications validées |
| **Trello** | oui | |
| **Asana** (O) | oui (`/v2/mcp`) | l'ancien point d'accès est coupé depuis le 05/11/2026 |
| Discord | documentation seulement | piloter un serveur : communautaire |

### Stockage et statistiques d'usage

| Partenaire | API / MCP | Gratuit | Payant | Quota |
|---|---|---|---|---|
| **Cloudflare R2** (O) | oui / oui | 10 Go, sortie gratuite | 0,015 $/Go-mois | ❔ |
| **Backblaze B2** (O) | oui (compatible S3) / ? | 10 Go | 6,95 $/To/mois | ❔ |
| **PostHog** | oui / ? | allocations mensuelles par produit | à l'usage | ❔ |
| **Plausible** (O) | oui (plan Business) / ? | essai 30 jours | 9 à 19 $/mois | ❔ |

## Pas couverts dans ces deux passes

Voix : Speechify, Hume (Octave), Rime, Rev, Google Cloud STT, Amazon Transcribe, Descript, Respeecher. Vidéo : Captions, Akool, Colossyan, Argil. Jeu : SpriteCook, Ludo.ai, textures dédiées. Langue et web : Smartling, Captions, LiveKit, You.com, ScrapingBee, Bright Data. Médias : Pond5, Storyblocks, Jamendo, Envato. Mise en ligne : Firebase Hosting, Bunny.net, Geoapify, Mixpanel, Umami, Sentry. Les sources de chaque ligne sont gardées dans les rapports de recherche.
