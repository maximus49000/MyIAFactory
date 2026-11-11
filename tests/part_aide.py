"""Aide des tests de l'espace partenaire : un champ `partenaires` de relevé tel que la tâche 19 le remplit."""
import copy


def _carte(i, nom, cat, **x):
    return {
        "id": i, "nom": nom, "categorie": cat, "sous_categorie": "generation", "site": "https://exemple.org",
        "inscription": "https://exemple.org/inscription",
        "connexions": [{"type": "mcp", "url": "https://mcp.exemple.org",
                        "commande": f"claude mcp add --transport http {i} https://mcp.exemple.org"}],
        "plans": [{"nom": "Gratuit", "prix": 0, "devise": "USD", "periode": "mois", "quota": "10 crédits", "tarif": "gratuit"},
                  {"nom": "Pro", "prix": 20, "devise": "USD", "periode": "mois", "quota": None, "tarif": "inclus"}],
        "gratuit": "10 crédits", "quota_lisible": "oui", "illimite": False, "statut": "actif",
        "fiabilite": "officielle", "verifie_le": "2026-11-11", **x}


def partenaires_exemple():
    return copy.deepcopy({
        "categories": {
            "voix-audio": [_carte("vox", "Vox", "voix-audio"), _carte("echo", "Echo", "voix-audio", fiabilite="tiers")],
            "video-3d-avatars": [_carte("tripo", "Tripo", "video-3d-avatars", quota_lisible="inconnu")],
            "mise-en-ligne-equipe": [_carte("libre", "Libre", "mise-en-ligne-equipe", illimite=True)],
        },
        "etat": {
            "connexions": {"vox": {"etat": "connecte", "source": "serveur MCP déclaré", "abonnement": "Pro",
                                   "vu_le": "2026-11-11T10:00:00"},
                           "tripo": {"etat": "declare", "source": "déclaré par l'utilisateur", "vu_le": "2026-11-11"}},
            "quotas": {"vox": {"reste": 4200, "unite": "caractères", "lu_le": "2026-11-11T10:05:00"},
                       "libre": {"illimite": True, "lu_le": "2026-11-11T10:05:00"}},
            "limites": {"echo": {"depuis": "2026-11-11T09:00:00", "raison": "quota épuisé"}},
            "regles": {"tripo": [{"id": "r1", "texte": "Générer en un seul prompt.", "cree_le": "2026-11-11"}]},
        },
        "conseils": {"voix": [{"id": "vox", "raison": "Voix naturelles."}, {"id": "echo", "raison": "Secours."}]},
        "maj_catalogue": "2026-11-11",
        "cout_maj": {"euros": 0.4, "texte": "Environ 40 fiches sur Sonnet."},
    })
