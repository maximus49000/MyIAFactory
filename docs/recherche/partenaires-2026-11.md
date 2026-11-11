# Les partenaires de génération : recherche du 11 novembre 2026

Préparation du **bureau partenaire** (à concevoir). Pour chaque service : API et serveur MCP, plan gratuit, plans payants, et surtout **si l'API permet de lire le quota restant**, ce qui décide de ce que le bureau pourra afficher (« reste N », « illimité », ou « inconnu »).

**Fiabilité.** (O) = lu sur la page officielle. Sans marque = agrégateurs tiers, qui se contredisent souvent : à revérifier avant d'afficher un prix. Les prix sont dans la devise d'origine. Plusieurs pages officielles étaient illisibles (Kling, Pika, HeyGen, D-ID, Hedra, Veo, Stability, Ideogram, Leonardo, Adobe).

Légende de la colonne Quota : ✅ endpoint confirmé · 🟡 probable ou partiel · ❌ pas par l'API (console ou cloud) · ❔ inconnu.

## Ce qu'il faut retenir pour le bureau

- **Rares sont ceux qui donnent leur solde par l'API** : ElevenLabs, Black Forest Labs (FLUX), Stability, Leonardo, Meshy, remove.bg. Probables : fal.ai, Runway, AutoSprite (outil MCP `get_account`). Le bureau doit donc gérer proprement l'état « quota inconnu ».
- **Serveur MCP officiel** : ElevenLabs, Runway, HeyGen, Meshy, Replicate, PixelLab, AutoSprite, Krea. Probables : Cartesia, Deepgram, fal.ai.
- **Les agrégateurs** (fal.ai, Replicate, Runway API, Picsart) donnent accès à beaucoup de modèles avec une seule connexion : c'est un bon candidat pour les « connecteurs conseillés ».
- **Aucune offre API n'est illimitée.**
- **À écarter** : LMNT et PlayHT (fermés), OpenAI Sora (API arrêtée le 24/09/2026), Suno, Udio, Midjourney et Mixamo (aucune API officielle). Clipdrop est incertain (tarifs retirés).

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

## Pas couverts dans cette passe

Speechify, Hume (Octave), Rime, Rev, Google Cloud STT, Amazon Transcribe, Descript, Respeecher ; Captions, Akool, Colossyan, Argil ; SpriteCook, Ludo.ai ; textures dédiées. Les sources de chaque ligne sont gardées dans les rapports de recherche et peuvent être rejointes au besoin.
