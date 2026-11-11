# Les partenaires : recherche du 11 novembre 2026

Préparation du **bureau partenaire** (à concevoir). Les partenaires sont **facultatifs** : la factory doit pouvoir s'en passer ; le bureau les liste et en conseille selon le projet. Pour chaque service : API et serveur MCP, plan gratuit, plans payants, et surtout **si l'API permet de lire le quota restant**, ce qui décide de ce que le bureau pourra afficher (« reste N », « illimité », ou « inconnu »).

**Fiabilité.** (O) = lu sur la page officielle. Sans marque = agrégateurs tiers, qui se contredisent souvent : à revérifier avant d'afficher un prix. Les prix sont dans la devise d'origine. Plusieurs pages officielles étaient illisibles (Kling, Pika, HeyGen, D-ID, Hedra, Veo, Stability, Ideogram, Leonardo, Adobe).

**Popularité** (de 1 à 5) : téléchargements mensuels du SDK officiel (npm, PyPI), étoiles GitHub ou utilisateurs annoncés, relevés le 11/11/2026 ; à défaut, une estimation (section 11 pour les sections 1 à 6).

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

## 7. Hubs de connecteurs, IA et documents

Popularité de 1 à 5 : téléchargements mensuels du SDK officiel (npm, PyPI), étoiles GitHub ou utilisateurs annoncés, relevés le 11/11/2026.

### Hubs de connecteurs (un branchement, des milliers d'applications)

| Partenaire | API / MCP | Gratuit | Payant | Quota | Pop. |
|---|---|---|---|---|---|
| **Zapier** (O) | restreint / **oui**, sur tous les plans | 100 tâches/mois | Pro dès 19,99 $, Team dès 69 $ | ❔ | 4 (9 000+ applications) |
| **Composio** (O) | oui / **oui** | 10 000 appels/mois | 18 $/siège | 🟡 | 4 (npm 6,1 M ; 31 k étoiles ; 1 700+ outils) |
| **Make** (O) | oui / oui (à vérifier) | 1 000 crédits/mois | prix non lus | 🟡 API de gestion | 4 |
| **n8n** (O) | oui / oui | auto-hébergé gratuit | 20 à 667 €/mois | ❔ | 5 (210 k étoiles) |
| **Pipedream** (O) | oui / **oui** | développement | dès 99 $/mois | ❔ | 3 (npm 1,4 M ; 3 000+ connecteurs) |
| **Activepieces** (O) | oui / oui | 1 000 crédits | 20 à 200 $/mois | ❔ | 3 (25,5 k étoiles ; open source) |
| **Nango** (O) | oui / oui | 10 connexions | dès 50 $/mois | ❔ | 3 (npm 2,9 M) |
| **Merge** (O) | oui / oui | 3 comptes | dès 650 $/mois | ❔ | 2 |
| Paragon, IFTTT, Workato, Tray | restreint ou sur devis | essais | sur devis | ❔ | — |

### Annuaires de serveurs MCP

| Annuaire | Taille | Accès par API | Remarque |
|---|---|---|---|
| **Registre MCP officiel** | non mesurée | oui (`GET /v0/servers`) | la référence ; dépôt `modelcontextprotocol/servers` : 91,9 k étoiles |
| **Glama** (O) | 119 397 serveurs | oui (`GET /v1/servers`) | comptage large, doublons |
| **PulseMCP** (O) | 21 558 serveurs | ? | soumissions suspendues |
| **mcp.so** | ≈ 20 000 | ? | |
| **Smithery** | ≈ 6 000 à 7 000 | oui (registre, CLI) | héberge aussi les serveurs |
| **Annuaire des connecteurs Claude** (O) | 1 112 connecteurs, 530 plugins | ? | vérifiés par Anthropic |
| **Docker MCP Catalog** | ? | dépôt `docker/mcp-registry` | serveurs en conteneurs |

Environ 22 500 serveurs distincts une fois les doublons retirés (juin 2026). Ces annuaires sont la meilleure source pour aller encore plus large : le catalogue pourra s'en nourrir.

### Autres IA de texte et de code (prix par million de tokens, entrée / sortie)

| Partenaire | API / MCP | Gratuit | Tarif | Quota | Pop. |
|---|---|---|---|---|---|
| **OpenAI** (O) | oui / ? | non | de 0,05 $ / 0,40 $ à 10 $ / 50 $ | ❔ | 5 (npm 203 M ; PyPI 296 M) |
| **Google Gemini** (O) | oui / ? | oui (Flash) | de 0,30 $ / 2,50 $ à 2 $ / 10 $ | ❔ | 5 (npm 111 M ; PyPI 138 M) |
| **Mistral** (O) | oui / ? | ? | Large 0,50 $ / 1,50 $ | ❔ | 4 (npm 25,6 M) |
| **DeepSeek** (O) | oui (compatible OpenAI) | ? | 0,15 $ / 0,60 $ à 0,66 $ / 1,98 $ | 🟡 | 4 |
| **xAI Grok** (O) | oui | ? | 1 $ / 2 $ à 2 $ / 6 $ | ❔ | 3 |
| **Cohere** (O) | oui | clé d'essai | Command 2,50 $ / 10 $ | ❔ | 3 |
| **Groq** (O) | oui | oui | non lu | ❔ | 4 |
| **OpenRouter** (O) | oui (un accès à des centaines de modèles) | modèles gratuits limités | prix des modèles | ✅ `GET /api/v1/key` | 3 |
| **Fireworks** (O), **Together**, **AI21** (O), **Qwen** | oui | crédits d'essai | dès 0,05 $ | ❔ | 2 à 3 |

### Documents et OCR

| Partenaire | API | Gratuit | Tarif | Pop. |
|---|---|---|---|---|
| **AWS Textract** (O) | oui | 1 000 pages/mois (3 mois) | 1,50 $ les 1 000 pages | 4 |
| **Azure Document Intelligence** (O) | oui | 500 pages/mois | non lu | 4 |
| **Mistral OCR** | oui | ? | ≈ 4 $ les 1 000 pages | 4 |
| **Google Document AI** | oui | ? | non lu | 3 |
| **LlamaParse** (O) | oui / oui | 10 000 crédits | 1,50 $ les 1 000 crédits | 3 |
| **Unstructured** (O) | oui | 10 000 pages | 0,015 $ la page | 3 |
| **Reducto** (O) | oui | 150 $ d'usage | 1 à 40 $ les 1 000 pages | 2 |
| **Nanonets** (O) | oui | 50 $ de crédits | dès 100 $/mois | — |
| **Docling** | bibliothèque libre | gratuit | — | 4 (70 k étoiles) |

### Recherche vectorielle et embeddings

| Partenaire | Gratuit | Tarif | Pop. |
|---|---|---|---|
| **Qdrant** (O) | 1 nœud, 1 Go | à l'usage | 4 (PyPI 12 M) |
| **Weaviate** (O) | 100 000 objets | dès 45 $/mois | 4 |
| **Chroma** (O) | 5 $ de crédits | Team 250 $/mois | 4 |
| **Pinecone** (O) | 2 Go | dès 20 $/mois | 3 |
| **Voyage AI** (O) | 200 M de tokens | 0,02 à 0,12 $ / M | 3 |
| **Turbopuffer** (O) | non | dès 16 $/mois | 3 |

## 8. Infrastructure : e-mail, paiement, comptes, surveillance, intégration continue

Popularité : téléchargements npm sur 30 jours (5 ≥ 20 M, 4 = 5 à 20 M, 3 = 1 à 5 M, 2 = 0,1 à 1 M, 1 < 0,1 M) ; sinon estimation.

### E-mail, SMS, notifications

| Partenaire | MCP | Gratuit | Payant | Quota | Pop. |
|---|---|---|---|---|---|
| **Resend** (O) | ? | 3 000 mails/mois | Pro 20 à 35 $, Scale 90 à 1 150 $ | ❔ | 5 (63 M) |
| **Amazon SES** (O) | ? | crédits AWS | 0,10 $ les 1 000 | ✅ GetSendQuota | 5 (20,5 M) |
| **SendGrid** | communautaire | essai | non lu | 🟡 statistiques | 5 (23 M) |
| **Twilio** (SMS) (O) | documentation | essai | SMS US 0,0083 $ | ✅ `/Balance.json` | 5 (33,6 M) |
| **Firebase Cloud Messaging** (O) | oui (Firebase) | gratuit | — | sans objet | 5 |
| **Postmark** (O) | oui (expérimental) | 100 mails/mois | dès 15 $ | 🟡 | 4 (5,9 M) |
| **Mailgun** (O) | oui (local) | 100 mails/jour | 15 à 90 $ | 🟡 | 4 (5,1 M) |
| **Brevo** | oui (accès anticipé) | ? | ? | 🟡 `GET /v3/account` | 3 |
| **Mailchimp** (O) | documentation | 500 mails/mois | 11,73 à 315,93 € | ❔ | 4 |
| **OneSignal** (O) | ? | 10 000 mails, push 1 000 MAU | dès 19 $ | ❔ | 2 |
| **Pusher** (O) | ? | 200 000 messages/jour | 49 à 499 $ | ❔ | 3 |
| **Knock** (O), **Novu** (O), **Bird** (O), **Vonage** | ? | paliers gratuits | 15 à 250 $ | ❔ (Vonage 🟡 solde) | 2 à 3 |

### Paiement et vente

| Partenaire | MCP | Frais | Quota | Pop. |
|---|---|---|---|---|
| **Stripe** (O) | **oui** (`https://mcp.stripe.com`) | à la transaction (cartes EEE 1,5 % + 0,25 €) | ✅ `GET /v1/balance` | 5 (119 M) |
| **PayPal** (O) | **oui** (`https://mcp.paypal.com`) | à la transaction | 🟡 | 4 |
| **Paddle** (O), **Lemon Squeezy** (O) | ? | 5 % + 0,50 $ | ❔ | 2 |
| **Mollie** (O) | ? | 1,80 % + 0,25 € | 🟡 | 2 |
| **RevenueCat** (O) | ? | gratuit jusqu'à 2 500 $/mois, puis 1 % | 🟡 | 3 |
| **Gumroad** (O) | ? | 10 % + 0,50 $ | ❔ | 3 |
| **Chargebee** (O), **Adyen**, **Square** | ? | selon l'offre | ❔ | 3 |

### Comptes et bases de données

| Partenaire | MCP | Gratuit | Payant | Pop. |
|---|---|---|---|---|
| **Supabase** (O) | **oui** (`https://mcp.supabase.com/mcp`) | 50 000 MAU, 500 Mo | dès 25 $ | 5 (211 M) |
| **MongoDB Atlas** (O) | **oui** | 512 Mo | dès 56,94 $ | 5 (76 M) |
| **Neon** (O) | oui | 100 projets, 1 Go | à l'usage | 5 (25 M) |
| **Upstash** (O) | oui | 500 000 commandes/mois | à l'usage | 5 (26 M) |
| **Turso** (O) | ? | 5 Go | 4,99 à 416,58 $ | 4 (20 M) |
| **Firebase Auth** (O) | oui (Firebase) | 50 000 MAU | à l'usage | 5 |
| **Auth0** (O) | oui | 25 000 MAU | 35 à 800 $ | 4 |
| **WorkOS** (O) | ? | 1 M MAU | SSO dès 125 $ | 4 |
| **Clerk** (O) | ? | 50 000 MRU | 25 à 300 $ | 4 |
| **Convex** (O) | oui | 1 M appels | Pro 25 $ | 4 |
| **Stytch** (O), **PlanetScale** (O) | ? | 10 000 MAU / non | à l'usage / dès 10 $ | 3 |

### Surveillance des erreurs et journaux

| Partenaire | MCP | Gratuit | Payant | Pop. |
|---|---|---|---|---|
| **Sentry** (O) | **oui** (`https://mcp.sentry.dev/mcp`) | 5 000 erreurs | 29 à 89 $ | 5 (198 M) |
| **Datadog** (O) | contradictoire | 5 hôtes | dès 15 $/hôte | 5 (51 M) |
| **Grafana Cloud** (O) | oui | gratuit | Pro 19 $ | 4 |
| **New Relic** (O) | ? | 100 Go/mois | 0,40 $/Go | 4 |
| **Better Stack** (O), **Honeybadger** (O), **Rollbar** (O), **LogRocket** (O) | ? | paliers gratuits | 26 à 292 $ | 2 à 3 |

### Intégration continue

| Partenaire | Gratuit | Payant | Pop. |
|---|---|---|---|
| **GitHub Actions** (O) | 2 000 min/mois | 0,006 $/min | 5 |
| **GitLab CI** (O) | 400 min/mois | Premium 29 $ | 4 |
| **Expo EAS** (O) | 15 + 15 builds/mois | 19 à 199 $ | 4 |
| **CircleCI** (O) | 30 000 crédits | dès 15 $ | 4 |
| **Bitrise** (O), **Codemagic** (O), **Buildkite** (O) | paliers gratuits | 30 à 218 $ | 3 |

## 9. Boutiques et services pour le jeu

### Boutiques et portails

| Partenaire | API / MCP | Frais | Quota | Pop. |
|---|---|---|---|---|
| **App Store Connect** (O) | oui | 99 $/an, part des ventes | ✅ en-tête `X-Rate-Limit` | 5 |
| **Google Play** (O) | oui | 25 $ une fois | ❌ (console) | 5 |
| **Steamworks** | oui (Web API) | 100 $ par jeu ; 30 / 25 / 20 % | ❔ | 5 |
| **Roblox Open Cloud** (O) | oui / **oui** (intégré à Roblox Studio) | — | ❔ | 5 |
| **Epic Games Store** | oui (EOS) | 12 %, 0 % sur le premier million | ❔ | 4 |
| **itch.io** (O) | oui (`butler`) | part libre, 10 % par défaut | sans objet | 4 |
| **Microsoft Store** | oui (soumission) | inscription gratuite (particuliers) | ❔ | 4 |
| **Meta Quest** (O) | oui (serveur à serveur) | 30 % | ❔ | 4 |
| **CrazyGames**, **Poki** | SDK obligatoire | part des revenus publicitaires | ❔ | 4 |
| **Newgrounds**, **Game Jolt** | ? | ≤ 10 % | ❔ | 3 |
| **Nintendo**, **PlayStation**, **Xbox** | sur validation, pas d'API publique | kits, sans frais (Xbox) | sans objet | 5 |
| **GOG**, **Fab** (O), **Unity Asset Store** | pas d'API publique | 70/30 ; 88 % au créateur (Fab) | sans objet | 3 à 4 |

### Services pour le jeu

| Partenaire | API / MCP | Gratuit | Payant | Pop. |
|---|---|---|---|---|
| **FMOD**, **Wwise** | outils locaux | gratuits pour les indépendants (sous 200 k$ et 250 k$) | licences | 5 |
| **Unity Gaming Services** (O) | oui | paliers gratuits par service | à l'usage | 4 |
| **Photon** (O) | SDK | 20 joueurs simultanés | 95 $ et plus | 4 |
| **PlayFab** | oui | palier réduit en mars 2026 | ≈ 99 $/mois | 4 |
| **Nakama / Heroic Labs** | oui | open source | dès 600 $/mois | 4 |
| **GameAnalytics** | oui / oui (PipelineIQ) | gratuit | ≈ 499 $/mois | 4 |
| **AccelByte** (O) | oui / **oui** | 30 joueurs en développement | à l'usage | 3 |
| **Modulate ToxMod** (O) | oui | Starter 0 $ | dès 2 500 $/mois | 3 |
| **Lokalise**, **Gridly** (O) | oui | ? | 54 à 999 $/mois | 2 à 4 |
| Edgegap, Community Sift, Inworld, Convai | oui | ? | sur devis ou contradictoire | 2 à 3 |

Fermé : **Hathora** (mai 2026).

## 10. Publication, sites, agenda et messageries

### Réseaux sociaux et publication

| Partenaire | API / MCP | Payant | Quota | Pop. |
|---|---|---|---|---|
| **YouTube Data API** (O) | oui | quota gratuit (10 000 unités/jour) | ❌ (console) | 5 |
| **Instagram / Facebook** | oui (revue d'application) | — | 🟡 en-tête `X-App-Usage` | 5 |
| **TikTok** | oui (audit pour publier en public) | — | ❔ | 4 |
| **X** | oui | paiement à l'usage, plus de gratuit | ❔ | 4 |
| **LinkedIn** | restreint | — | ❔ | 4 |
| **Twitch** (O) | oui | — | ✅ en-têtes `Ratelimit-*` | 4 |
| **Mastodon** (O) | oui | — | ✅ en-têtes `X-RateLimit-*` | 3 |
| **Bluesky** | oui | — | points par heure | 3 |
| **Reddit** | restreint | ≈ 0,24 $ les 1 000 appels | ❔ | 4 — **fermeture de l'API ouverte annoncée (à vérifier)** |
| **Metricool** (O) | oui / **oui** | ? | ❔ | 3 |
| **Buffer**, **Hootsuite**, **Later**, **Sprout Social**, **Ayrshare** (O) | oui | 5 à 599 $/mois | ❔ | 2 à 4 |
| **Pinterest**, **Threads** | oui | — | ❔ | 3 |

### Sites, CMS et commerce

| Partenaire | MCP | Gratuit | Payant | Pop. |
|---|---|---|---|---|
| **WordPress.com** (O) | ? | 1 Go | 9 à 70 $ | 5 |
| **Shopify** (O) | ? | non | 36 à 384 €/mois | 5 |
| **Wix** | **oui** (`https://mcp.wix.com/mcp`) | ? | ? | 5 |
| **WooCommerce** (O) | **oui** (natif, aperçu) | extension gratuite | — | 5 |
| **Webflow** (O) | **oui** (`https://mcp.webflow.com/sse`) | ? | ? | 4 |
| **Contentful** (O) | **oui** (`https://mcp.contentful.com/mcp`) | ? | ? | 4 |
| **Strapi** (O) | ? | open source | Cloud 35 à 450 $ | 4 |
| **Ghost** (O) | ? | auto-hébergé | 18 à 199 $ | 4 |
| **Sanity** (O), **Storyblok** (O) | ? | paliers gratuits | 15 $/siège ; 99 à 349 $ | 3 |
| **Directus**, **Payload**, **Squarespace**, **Framer CMS**, **Prismic**, **Hygraph** | Directus oui (à confirmer) | auto-hébergés ou ? | ? | 2 à 3 |

### Agenda, formulaires et visio

| Partenaire | MCP | Gratuit | Payant | Pop. |
|---|---|---|---|---|
| **Microsoft 365 / Teams** (Graph) | ? | — | — | 5 |
| **Google Agenda, Meet, Forms** | communautaire (Workspace) | gratuits | — | 4 à 5 |
| **Zoom** (O) | ? | réunions de 40 min | Pro 16,99 $ | 5 |
| **Calendly** (O) | ? | 1 type d'événement | 10 à 16 $ | 5 |
| **Cal.com** (O) | ? | 1 utilisateur | Teams 12 $ | 4 |
| **Typeform** (O) | ? | limité | 39 à 379 $ | 4 |
| **Jotform** (O) | **oui** (`https://mcp.jotform.com`) | ? | ? | 3 |
| **Tally** (O) | **oui** | formulaires sans limite | 20 à 65 € | 3 |
| **SurveyMonkey**, **Loom**, **Whereby**, **Fillout** | ? | ? | ? | 2 à 4 |

### Messageries

| Partenaire | MCP | Remarque | Pop. |
|---|---|---|---|
| **Slack** (O) | **oui** | voir section 6 | 5 |
| **Discord** | communautaire seulement | en-têtes de limite | 5 |
| **Telegram Bot API** | ? | gratuit | 5 |
| **WhatsApp Business** (O) | ? | facturation par message depuis juillet 2025 | 5 |

## 11. Popularité des partenaires des sections 1 à 6

Téléchargements npm sur 30 jours au 11/11/2026 quand ils existent ; « est. » = estimation.

| Niveau | Partenaires |
|---|---|
| **5** | OpenAI (203 M), ElevenLabs (≈ 11 M sur ses SDK, leader de sa catégorie), Google Gemini (112 M), OpenAI Moderation, Unsplash, Figma, Canva (est.), Mapbox (21 M), Google Maps (29 M), OpenStreetMap, Supabase (211 M), Vercel, Cloudflare (145 M), GitHub (94 M), Notion, Slack (65 M), Jira/Confluence, Google Drive, Trello, Discord (est.), PostHog (86 M), GitHub Pages |
| **4** | Google Cloud TTS, Amazon Polly, Azure Speech (est.), Deepgram (4,9 M), AssemblyAI, DeepL, Amazon Translate, Google Translation, Azure Translator (est.), Lokalise, Black Forest Labs, Stability, Adobe Firefly, fal.ai (8,4 M), Replicate (2,9 M), Runway, Google Veo, HeyGen, Synthesia, Meshy (est.), Firecrawl (5,4 M), Exa (4,5 M), Tavily, Apify, Browserbase (10,6 M), Brave, Jina, Perplexity, Vapi, Pexels, Pixabay, Epidemic Sound, Shutterstock, Getty, Adobe Stock, Artlist, Iconify, Noun Project, Google Fonts, Flaticon, Font Awesome, Poly Haven, Sketchfab, Kenney, Fab, Adobe Substance, Framer, Netlify, GitLab, Linear (15 M), Asana, Render, Fly.io, itch.io, BrowserStack, Sauce Labs, TestMu AI, Firebase Test Lab |
| **3** | Cartesia, Murf, WellSaid, Resemble, Fish Audio, Speechmatics, Gladia, Crowdin, Phrase, Ideogram, Leonardo, Recraft, Freepik/Magnific, Krea, Picsart, remove.bg, Photoroom, Topaz, Scenario, Tripo, Kling, MiniMax, Luma, Seedance, SerpAPI, Retell, Bland, Inworld, Freesound, Openverse, ambientCG, KIRI Engine, Polycam, RealityScan, Gamma, Penpot, MapTiler, Plausible, Railway, Backblaze, AWS Device Farm |
| **2** | Mubert, Soundraw, Stable Audio, Clipdrop, AutoSprite, PixelLab, D-ID, Tavus, Hedra, Sync Labs, JSON2Video, Creatomate, Shotstack, Rodin, CSM, Move.ai, Hume, Convai, Sightengine, Hive, Reality Defender, Stadia, QuickChart, Datawrapper |

## 12. Compléments des services « pas couverts »

| Partenaire | API / MCP | Gratuit | Payant | Pop. |
|---|---|---|---|---|
| **Google Cloud STT** (O) | oui | 60 min/mois | ≈ 0,016 à 0,024 $/min | 4 (3,1 M) |
| **Amazon Transcribe** (O) | oui | 60 min/mois (12 mois) | 0,006 à 0,024 $/min | 4 (3,1 M) |
| **Descript** | bêta / **oui** | 60 min/mois | crédits du plan | 4 |
| **Hume Octave** (O) | oui | 10 000 car./mois (non commercial) | 3 à 900 $/mois | 3 |
| **Speechify** | oui | contradictoire | dès 6 $ le million de car. | 3 |
| **Rev AI** | oui | ≈ 5 h | 0,10 à 0,30 $/h | 3 |
| **Rime** | oui | crédits d'essai | 30 à 50 $ le million de car. | 2 |
| **LiveKit** (O) | oui | 1 000 min d'agent | ≈ 50 à 500 $/mois | 4 (25 M) |
| **Bright Data** (O) | oui / **oui** | 5 000 crédits/mois | à l'usage | 4 |
| **ScrapingBee** (O) | oui | 1 000 crédits | dès 19,99 $ | 3 |
| **Smartling** | oui | ? | ≈ 500 $/mois | 3 |
| **Mixpanel** (O) | oui / **oui** | 1 M événements/mois | à l'usage | 4 (13 M) |
| **Firebase Hosting** | oui | Spark | Blaze à l'usage | 5 (50 M) |
| **Bunny.net** (O) | oui | non (1 $/mois minimum) | 0,01 $/Go | 3 |
| **Umami** (O) | oui | Cloud Hobby gratuit | ≈ 9 $/mois | 3 |
| **Geoapify** (O) | oui | 3 000 crédits/jour | dès 59 $ | 2 |
| **Captions**, **Colossyan**, **Akool**, **Argil** | oui | ? | 39 à 149 $/mois | 2 à 3 |
| **Ludo.ai** | bêta / **oui** (bêta) | ? | ≈ 50 $/mois | 2 |
| **Storyblocks**, **Pond5** | partenariat | clé développeur | sur devis | 3 |
| **Jamendo** | ? | non commercial | ? | 2 |
| Textures PBR : **fal.ai Patina** | oui | — | ≈ 0,10 $ le matériau | — |

À écarter : **Envato Elements** (aucune API publique pour les médias), **Respeecher** et **You.com** (API non confirmée), SpriteCook (introuvable). À instruire : Seedream, Imagen, Higgsfield, Moonvalley, Genmo, Sloyd, Gradium.

## Encore à instruire

Les sources de chaque ligne sont gardées dans les rapports de recherche. Les annuaires de serveurs MCP (section 7, environ 22 500 serveurs distincts) restent la meilleure source pour aller encore plus large ; le bouton « Mettre à jour les offres » et les prochaines recherches compléteront le catalogue.
