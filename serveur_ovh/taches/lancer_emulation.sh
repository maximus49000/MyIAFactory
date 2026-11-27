#!/usr/bin/env bash
# Enveloppe HÔTE d'une tâche d'émulation : exécutée sur le serveur (par SSH), elle prend le créneau, démarre le conteneur
# `myiafactory/emulateur` puis rend la main ; un veilleur DÉTACHÉ (setsid + nohup, survit à la fin de la session SSH) tient le
# créneau, applique les limites et écrit l'état final. Un appelant mort ne laisse donc ni conteneur ni créneau.
# Usage : lancer_emulation.sh <id> <mode> [duree_s [inactivite_s [memoire_mo [cpus [captures [octets [hotes]]]]]]]
#   hotes (facultatif, après captures et octets) : noms d'hôtes séparés par des virgules, 5 au plus. Absent : l'émulateur n'a AUCUN
#   réseau (--network none), comme toujours. Présent : réseau BORNÉ (voir « Réseau borné » plus bas). L'accord du Directeur est
#   vérifié par le lanceur du poste AVANT l'envoi (`serveur_tache_cli`), jamais ici : cette enveloppe n'a pas de moyen de le lire.
#   captures (1..50) et octets (1..104857600) facultatifs : passés au conteneur en -e PONT_CAPTURES / -e PONT_OCTETS (limites du pont) ;
#   absents, le conteneur garde les valeurs du pont (50 captures, 100 Mo).
#   id : t<AAAAMMJJ>-<HHMMSS>-<4 hexa> ; mode : scenario | pilote ; valeurs par défaut : 1200 s, 600 s, 6144 Mo, 2 processeurs
#   (inactivite_s 600 > PONT_DEMARRAGE_S 300 : un `demarrer` en cours n'est jamais pris pour de l'inactivité).
#   Chaque valeur est validée par un motif strict AVANT tout usage (nombres entiers sans zéro initial : duree_s et inactivite_s
#   1..86400, memoire_mo 256..65536, cpus 1..64) ; rien n'en est jamais interprété par un shell : les commandes sont des tableaux.
# Sortie standard : UNE ligne JSON, l'état écrit dans ~/taches/<id>/etat.json.
# Émulation liée à un agent (pilote ; ~/taches/<id>/agent écrit par le pont hôte) : arret n'est jamais effacé au lancement ;
#   agent déjà fini ou arrêt déjà demandé -> refus (code 1, état arretee) ; le veilleur s'arrête aussi (terminee, ok) dès que
#   l'agent est à l'état final ou que son pont hôte (pont-hote.pid) ne vit plus.
# Codes : 0 conteneur démarré (état en_cours) ; 1 démarrage impossible (état echouee ; arretee : émulation liée refusée) ; 2 argument refusé (rien créé) ;
#   3 tâche déjà en cours : veilleur vivant OU enveloppe vivante (démarrage en cours, enveloppe.pid) (rien modifié) ;
#   4 identifiant déjà utilisé (état final, ou en_cours sans veilleur ni enveloppe vivants : rien modifié, à nettoyer par le lanceur) ; 75 créneau occupé ou un conteneur tache-* existe déjà (en_attente, à relancer).
# Dossier de la tâche ~/taches/<id>/ : entree/ (monté en lecture seule, l'APK y est déposé avant), sortie/ (monté en écriture :
#   pont.log, captures/, plantage.txt, entree-tache.log), etat.json, arret (créé par le lanceur : demande d'arrêt),
#   enveloppe.pid, veilleur.pid, veilleur.log, docker-run.log. Créneau : verrou flock sur ~/taches/.creneau-emulation (descripteur 8, hérité
#   par le veilleur).
# etat.json : {"id","etat","statut","debut","fin","raison"}, écrit par un fichier temporaire puis mv (jamais à moitié écrit).
#   etat : en_attente | en_cours | terminee | arretee | echouee ; statut (à la fin) : ok | plantage | limite | erreur.
#   Fin par le fichier arret -> arretee, ok (plantage si sortie/plantage.txt) ; échéance duree_s ou inactivité du pilote
#   (voir Inactivité) -> terminee, limite (plantage prime) ; conteneur disparu seul -> terminee, plantage si
#   plantage.txt existe, sinon echouee, erreur ; docker en échec -> echouee, erreur ; sortie/ au-delà de 2 x 100 Mo + 50 Mo
#   (du -sk) -> terminee, limite « sortie trop volumineuse ». L'état du conteneur est constaté AVANT d'honorer arret ;
#   arret contient « fin » (fin normale demandée par le lanceur) -> terminee, ok ; tout autre contenu -> arretee, ok.
#   Inactivité du pilote = max(mtime sortie/pont.log, sortie/.activite (touché par pont.sh au début ET à la fin de chaque verbe),
#   sortie/.avd-pret, début de la tâche).
# Limite de taille : sondage toutes les ENVELOPPE_SONDE_S (5 s) de `du -sk`, PAS un quota : un dépassement entre deux sondages
#   est accepté (résiduel connu) ; la limite du pont (octets de captures) reste la première barrière.
# ÉCART VOLONTAIRE : l'échéance duree_s est appliquée par le veilleur (et, en dernier recours, par `timeout duree+60` dans le
#   conteneur : entree-tache.sh), et non par `timeout <duree_s>` autour de `docker run -d`, qui rend la main aussitôt.
# Réservées aux tests : ENVELOPPE_SONDE_S (période de surveillance, 5 s par défaut ; le veilleur se réveille plus tôt pour
#   l'échéance de durée ou d'inactivité, jamais une période en retard ; l'état du conteneur : voir etat_docker). Aucun identifiant n'est monté ni transmis ;
# le conteneur reçoit seulement les réglages posés ci-dessous (-e NOM=valeur, jamais l'environnement de l'appelant).
set -u
export LC_ALL=C
exec </dev/null

# Fonctions communes aux enveloppes (état, docker, veilleur détaché) et motifs MOTIF_ID, MOTIF_DUREE, MOTIF_MEMOIRE,
# MOTIF_CPUS, MOTIF_SONDE : commun.sh, à côté de ce script (déposé avec lui).
ICI="$(cd "$(dirname "$0")" && pwd)"
. "$ICI/commun.sh" || { printf '%s\n' "lancer_emulation : commun.sh introuvable à côté de l'enveloppe." >&2; exit 2; }
IMAGE="myiafactory/emulateur"
IMAGE_SYSTEME="system-images;android-34;google_apis;x86_64"   # miroir de android_sdk.emulator_image de versions.json (test de concordance)
MOTIF_IMAGE_SYSTEME='^system-images;android-[0-9]{1,3}(-[a-z0-9]+)?;[a-z0-9_]+;x86_64$'
LIMITE_SORTIE_KO=256000                   # 2 x 100 Mo de captures + 50 Mo, en Ko (du -sk)
if [[ ${ENVELOPPE_SORTIE_MAX_KO:-} =~ ^[1-9][0-9]{0,8}$ ]]; then LIMITE_SORTIE_KO="$ENVELOPPE_SORTIE_MAX_KO"; fi   # tests
# /avd est un tmpfs de 9 Go (un PLAFOND : seul ce qui est écrit occupe la mémoire, ~760 Mo constatés). Pourquoi 9 Go : au premier
# démarrage l'émulateur fait une copie inscriptible du system.img de l'hôte (4,3 Go pour android-34 google_apis, partitions
# dynamiques) dans l'AVD et exige ~6 Go x 1,2 = 7,4 Go libres (« Not enough space to create userdata partition » avec 4 Go,
# constaté sur le serveur) ; disk.dataPartition.size du config.ini n'y change rien (essayé : 2G, 2048M, 2048, -partition-size).
# Une image système plus grosse que le tmpfs moins 2 Go de marge est refusée AVANT docker run, avec sa raison.
AVD_TMPFS_GO=9
IMAGE_MAX_OCTETS=$(( (9 - 2) * 1024 * 1024 * 1024 ))
if [[ ${ENVELOPPE_IMAGE_MAX_OCTETS:-} =~ ^[1-9][0-9]{0,11}$ ]]; then IMAGE_MAX_OCTETS="$ENVELOPPE_IMAGE_MAX_OCTETS"; fi   # tests

refuser() { printf '%s\n' "lancer_emulation : $1" >&2; exit 2; }

VEILLEUR=0
if [ "${1:-}" = --veilleur ]; then VEILLEUR=1; shift; fi
[ $# -ge 2 ] && [ $# -le 9 ] || refuser "usage : <id> <scenario|pilote> [duree_s [inactivite_s [memoire_mo [cpus [captures [octets [hotes]]]]]]]"
for argument in "$@"; do                 # aucun caractère de contrôle (retour à la ligne final compris : `$` d'un motif l'accepterait)
  [[ $argument == *[[:cntrl:]]* ]] && refuser "caractère de contrôle refusé dans un argument."
done
ID="$1"; MODE="$2"; DUREE="${3-1200}"; INACTIVITE="${4-600}"; MEMOIRE="${5-6144}"; CPUS="${6-2}"
[[ $ID =~ $MOTIF_ID ]] || refuser "identifiant refusé."
[ "$MODE" = scenario ] || [ "$MODE" = pilote ] || refuser "mode refusé (scenario ou pilote)."
[[ $DUREE =~ $MOTIF_DUREE ]] && [ "$DUREE" -le 86400 ] || refuser "duree_s refusée (1 à 86400, sans zéro initial)."
[[ $INACTIVITE =~ $MOTIF_DUREE ]] && [ "$INACTIVITE" -le 86400 ] || refuser "inactivite_s refusée (1 à 86400, sans zéro initial)."
[[ $MEMOIRE =~ $MOTIF_MEMOIRE ]] && [ "$MEMOIRE" -ge 256 ] && [ "$MEMOIRE" -le 65536 ] || refuser "memoire_mo refusée (256 à 65536)."
[[ $CPUS =~ $MOTIF_CPUS ]] && [ "$CPUS" -le 64 ] || refuser "cpus refusés (1 à 64)."
SUPPL=(); ENV_SUPPL=()                   # arguments facultatifs 7 et 8 : relayés au veilleur et au conteneur
if [ $# -ge 7 ]; then
  [[ $7 =~ ^[1-9][0-9]?$ ]] && [ "$7" -le 50 ] || refuser "captures refusées (1 à 50, sans zéro initial)."
  SUPPL+=("$7"); ENV_SUPPL+=(-e "PONT_CAPTURES=$7")
fi
if [ $# -ge 8 ]; then
  [[ $8 =~ ^[1-9][0-9]{0,8}$ ]] && [ "$8" -le 104857600 ] || refuser "octets refusés (1 à 104857600, sans zéro initial)."
  SUPPL+=("$8"); ENV_SUPPL+=(-e "PONT_OCTETS=$8")
fi
HOTES=""                                  # hôtes autorisés (réseau borné), séparés par des virgules ; vide : aucun réseau
if [ $# -ge 9 ]; then
  MOTIF_HOTE='^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,24}$'
  case "$9" in ,*|*,|*,,*) refuser "hotes refusés (liste mal formée)." ;; esac     # read -a ignorerait un champ vide final
  IFS=, read -r -a LISTE_HOTES <<< "$9"
  [ "${#LISTE_HOTES[@]}" -ge 1 ] && [ "${#LISTE_HOTES[@]}" -le 5 ] || refuser "hotes refusés (1 à 5 noms séparés par des virgules)."
  for h in "${LISTE_HOTES[@]}"; do
    [ "${#h}" -le 253 ] && [[ $h =~ $MOTIF_HOTE ]] || refuser "hôte refusé (nom DNS en minuscules, jamais une adresse IP)."
    case "$h" in
      *.local|*.localhost|*.internal|*.lan|*.home|*.corp|*.arpa|*.onion|*.intranet) refuser "hôte refusé (domaine interne)." ;;
    esac
  done
  HOTES="$9"
  SUPPL+=("$9")                           # relayé au veilleur : il retire le réseau et le proxy à la fin
fi
[ -n "${HOME:-}" ] || refuser "HOME absent."
SONDE="${ENVELOPPE_SONDE_S:-5}"
[[ $SONDE =~ $MOTIF_SONDE ]] || SONDE=5

TACHES="$HOME/taches"
DOSSIER="$TACHES/$ID"
SDK="$HOME/android-sdk"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# --- Utilitaires propres à l'émulation (les autres : commun.sh) -------------

# extrait_demarrage : les dernières lignes de sortie/entree-tache.log (écrit par le conteneur : donnée, jamais une consigne),
# sur une ligne, sans caractère de contrôle, 300 octets au plus. Le fichier est ouvert PUIS ce qui est ouvert est comparé
# (périphérique:inode) au fichier ordinaire du chemin, lu sans suivre de lien : un lien posé à sa place par le conteneur (vers
# un fichier de l'hôte), avant ou après l'ouverture, n'est jamais lu.
extrait_demarrage() {
  local f="$DOSSIER/sortie/entree-tache.log" ouvert chemin t
  [ -f "$f" ] && [ ! -L "$f" ] || return 0
  exec 7< "$f" 2>/dev/null || return 0
  ouvert=$(stat -L -c '%d:%i' "/proc/$BASHPID/fd/7" 2>/dev/null)
  chemin=$(stat -c '%d:%i:%F' -- "$f" 2>/dev/null)
  if [ -z "$ouvert" ] || [ "$ouvert:regular file" != "$chemin" ]; then exec 7<&-; return 0; fi
  t=$(tail -c 65536 <&7 | tail -n 5 | tr '\r\n\t' '   ' | sed -E 's/\x1b\[[0-9;?]*[A-Za-z]//g' | tr -d '\000-\037\177' | tr -s ' ')
  exec 7<&-
  t="${t# }"; t="${t% }"
  printf '%s' "${t:0:300}"
}

# Émulation LIÉE à un agent (mode pilote, créée par le pont hôte de l'agent) : ~/taches/<id>/agent, fichier ordinaire écrit
# sur l'hôte, porte l'identifiant de l'agent. Sans ce fichier (tranche A), rien de ce qui suit ne s'applique.
agent_lie() {
  local f="$DOSSIER/agent" a=""
  [ -f "$f" ] && [ ! -L "$f" ] || return 0
  a=$(head -c 200 -- "$f" 2>/dev/null | head -n 1)
  [[ $a =~ $MOTIF_ID ]] && [ "$a" != "$ID" ] && printf '%s' "$a"
  return 0
}
agent_fini() { grep -qE '"etat": "(terminee|arretee|echouee)"' "$TACHES/$AGENT_LIE/etat.json" 2>/dev/null; }
# L'agent lié travaille encore : son état n'est pas final ET son pont hôte vit (pont-hote.pid, reconnu par sa ligne de commande).
agent_actif() { ! agent_fini && processus_vivant "$TACHES/$AGENT_LIE/pont-hote.pid" "pont_hote.py $AGENT_LIE"; }
AGENT_LIE=""
if [ "$MODE" = pilote ]; then AGENT_LIE=$(agent_lie); fi

# --- Réseau borné (seulement si des hôtes sont demandés) -----------------------
#
# Mécanisme, SANS règle de pare-feu de l'hôte ni droit root autre que `sudo docker` :
#   - un réseau Docker `--internal` (reseau-<id>) : pas de passerelle, rien n'en sort, l'hôte et ses autres conteneurs n'y
#     sont pas ; l'émulateur n'est branché QUE sur lui ;
#   - un conteneur proxy (reseau-<id>, alias proxy-sortant), de la même image, branché sur ce réseau ET sur le pont par défaut
#     de Docker : c'est le seul chemin de sortie. Il n'accepte que `CONNECT <hôte>:443` pour un hôte déclaré ; il ne résout
#     JAMAIS de nom (aucun DNS) : il ne se connecte qu'aux adresses publiques résolues et vérifiées ICI, sur l'hôte, avant le
#     lancement (adresses privées, bouclage, lien local, métadonnées, CGNAT : refus de toute la demande) ; un changement de
#     DNS par la suite (rebinding) n'a donc aucun effet ;
#   - l'émulateur reçoit ces mêmes adresses par --add-host (son DNS les lit dans /etc/hosts) et `-http-proxy` vers le proxy.
# Fermé par défaut : sans hôtes rien de tout cela n'existe (--network none). Un échec de l'une des étapes refuse la tâche.
PROXY_PORT=3128
RESEAU_NOM="reseau-$ID"
nettoyer_reseau() {   # sans effet quand aucun hôte n'était demandé ; idempotent ; garde le journal du proxy (reseau-proxy.log)
  [ -n "$HOTES" ] || return 0
  dk 30 logs --tail 500 "$RESEAU_NOM" > "$DOSSIER/reseau-proxy.log" 2>&1
  dk 30 rm -f "$RESEAU_NOM" >/dev/null 2>&1
  dk 30 network rm "$RESEAU_NOM" >/dev/null 2>&1
  return 0
}

# ip_publique <a.b.c.d> : 0 si l'adresse IPv4 est publique (ni privée, ni bouclage, ni lien local/métadonnées, ni CGNAT, ni réservée).
ip_publique() {
  local a b c d
  [[ $1 =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
  a=$((10#${BASH_REMATCH[1]})); b=$((10#${BASH_REMATCH[2]})); c=$((10#${BASH_REMATCH[3]})); d=$((10#${BASH_REMATCH[4]}))
  [ "$a" -le 255 ] && [ "$b" -le 255 ] && [ "$c" -le 255 ] && [ "$d" -le 255 ] || return 1
  [ "$a" -eq 0 ] || [ "$a" -eq 10 ] || [ "$a" -eq 127 ] || [ "$a" -ge 224 ] && return 1
  [ "$a" -eq 100 ] && [ "$b" -ge 64 ] && [ "$b" -le 127 ] && return 1
  [ "$a" -eq 169 ] && [ "$b" -eq 254 ] && return 1
  [ "$a" -eq 172 ] && [ "$b" -ge 16 ] && [ "$b" -le 31 ] && return 1
  [ "$a" -eq 192 ] && [ "$b" -eq 168 ] && return 1
  [ "$a" -eq 192 ] && [ "$b" -eq 0 ] && [ "$c" -eq 0 ] && return 1
  [ "$a" -eq 198 ] && { [ "$b" -eq 18 ] || [ "$b" -eq 19 ]; } && return 1
  return 0
}

# resoudre_hotes : remplit HOTES_IP (« hôte=ip[,ip] » séparés par des espaces) ; 1 avec RAISON_RESEAU si un hôte ne se résout pas
# ou donne une adresse non publique. Au plus 4 adresses IPv4 par hôte.
resoudre_hotes() {
  local h ip ips n
  HOTES_IP=()
  for h in "${LISTE_HOTES[@]}"; do
    ips=""; n=0
    while read -r ip _; do
      [ -n "$ip" ] || continue
      ip_publique "$ip" || { RAISON_RESEAU="hôte $h : l'adresse $ip n'est pas publique (réseau interne, bouclage, métadonnées ou réservée)."; return 1; }
      case ",$ips," in *",$ip,"*) continue ;; esac
      n=$((n + 1)); [ "$n" -le 4 ] || break
      ips="${ips:+$ips,}$ip"
    done < <(getent ahostsv4 "$h" 2>/dev/null | awk '{print $1}')
    [ -n "$ips" ] || { RAISON_RESEAU="hôte $h : aucune adresse IPv4 trouvée."; return 1; }
    HOTES_IP+=("$h=$ips")
  done
  return 0
}

# Le proxy (source Java compilée par `java` au lancement : l'image a déjà un JDK, rien de plus à installer ; écrite dans le
# dossier de la tâche, montée en lecture seule). CONNECT seulement, port 443 seulement, hôtes et adresses résolus ici seulement.
ecrire_proxy() {
  mkdir -p -- "$DOSSIER/reseau" && chmod 755 "$DOSSIER/reseau" || return 1
  cat > "$DOSSIER/reseau/ProxySortant.java" <<'FIN_PROXY_JAVA'
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;

/** Proxy sortant à liste blanche : CONNECT <hôte>:443 seulement, vers des adresses données en arguments (jamais de DNS). */
public class ProxySortant {
    static final Map<String, List<String>> HOTES = new HashMap<>();
    static final Set<String> ADRESSES = new HashSet<>();
    static final int MAX_CONNEXIONS = 32, INACTIF_MS = 120000, ENTETE_MAX = 8192;
    // 443 toujours ; la propriété système ne sert qu'aux essais automatiques (jamais posée au lancement du conteneur).
    static final int PORT_DISTANT = Integer.getInteger("proxy.portdistant", 443);
    static final java.util.regex.Pattern IPV4 = java.util.regex.Pattern.compile("[0-9]{1,3}(\\.[0-9]{1,3}){3}");

    public static void main(String[] a) throws Exception {
        int port = Integer.parseInt(a[0]);
        for (int i = 1; i < a.length; i++) {
            String[] kv = a[i].split("=", 2);
            List<String> ips = new ArrayList<>();
            for (String ip : kv[1].split(",")) {
                if (!IPV4.matcher(ip).matches()) throw new IllegalArgumentException("adresse refusée");
                ips.add(ip);
                ADRESSES.add(ip);
            }
            HOTES.put(kv[0], ips);
        }
        ExecutorService pool = Executors.newCachedThreadPool();
        Semaphore places = new Semaphore(MAX_CONNEXIONS);
        try (ServerSocket serveur = new ServerSocket(port, 50)) {
            while (true) {
                Socket client = serveur.accept();
                if (!places.tryAcquire()) { client.close(); continue; }
                pool.submit(() -> { try { traiter(client); } finally { places.release(); } });
            }
        }
    }

    static String sur(String s) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length() && i < 80; i++) { char c = s.charAt(i); b.append(c >= 32 && c < 127 ? c : '?'); }
        return b.toString();
    }

    static void refuser(Socket client, String code, String hote) throws IOException {
        System.out.println("REFUSE " + sur(hote));
        client.getOutputStream().write(("HTTP/1.1 " + code + "\r\nConnection: close\r\n\r\n").getBytes("US-ASCII"));
    }

    static void traiter(Socket client) {
        Socket sortie = null;
        try (client) {
            client.setSoTimeout(INACTIF_MS);
            BufferedInputStream in = new BufferedInputStream(client.getInputStream());
            ByteArrayOutputStream entete = new ByteArrayOutputStream();
            int dernier = 0, c;
            while ((c = in.read()) >= 0) {
                entete.write(c);
                dernier = ((dernier << 8) | c) & 0xFFFFFFFF;
                if (dernier == 0x0D0A0D0A || entete.size() > ENTETE_MAX) break;
            }
            String texte = entete.toString("ISO-8859-1");
            String ligne = texte.split("\r\n", 2)[0];
            String[] parties = ligne.split(" ");
            if (entete.size() > ENTETE_MAX || dernier != 0x0D0A0D0A || parties.length != 3 || !parties[0].equals("CONNECT")) {
                refuser(client, "405 Method Not Allowed", ligne);
                return;
            }
            int deux = parties[1].lastIndexOf(':');
            String hote = deux < 0 ? parties[1] : parties[1].substring(0, deux);
            String port = deux < 0 ? "" : parties[1].substring(deux + 1);
            if (!port.equals("443")) { refuser(client, "403 Forbidden", parties[1]); return; }
            hote = hote.toLowerCase(Locale.ROOT);
            List<String> ips = HOTES.get(hote);
            if (ips == null && ADRESSES.contains(hote)) ips = List.of(hote);
            if (ips == null) { refuser(client, "403 Forbidden", parties[1]); return; }
            for (String ip : ips) {
                try {
                    Socket s = new Socket();
                    s.connect(new InetSocketAddress(InetAddress.getByName(ip), PORT_DISTANT), 10000);
                    sortie = s;
                    break;
                } catch (IOException e) { /* adresse suivante */ }
            }
            if (sortie == null) { refuser(client, "502 Bad Gateway", parties[1]); return; }
            sortie.setSoTimeout(INACTIF_MS);
            System.out.println("OK " + sur(hote) + ":443");
            client.getOutputStream().write("HTTP/1.1 200 Connection established\r\n\r\n".getBytes("US-ASCII"));
            client.getOutputStream().flush();
            final Socket distant = sortie;
            Thread aller = new Thread(() -> copier(in, distant, client));
            aller.setDaemon(true);
            aller.start();
            copier(distant.getInputStream(), client, distant);
        } catch (IOException e) {
            // connexion coupée ou délai d'inactivité : fin normale
        } finally {
            if (sortie != null) try { sortie.close(); } catch (IOException e) { }
        }
    }

    static void copier(InputStream de, Socket vers, Socket autre) {
        byte[] tampon = new byte[16384];
        try {
            OutputStream o = vers.getOutputStream();
            int n;
            while ((n = de.read(tampon)) >= 0) { o.write(tampon, 0, n); o.flush(); }
        } catch (IOException e) {
        } finally {
            try { vers.close(); } catch (IOException e) { }
            try { autre.close(); } catch (IOException e) { }
        }
    }
}
FIN_PROXY_JAVA
  chmod 644 "$DOSSIER/reseau/ProxySortant.java"
}

# --- Veilleur (détaché) ----------------------------------------------------

veilleur() {
  { : >&8; } 2>/dev/null || exit 2                  # sans le créneau hérité de l'enveloppe, jamais de veilleur
  printf '%s\n' "$$" > "$DOSSIER/veilleur.pid"
  local debut_iso debut_s maintenant derniere m pannes=0 etat_conteneur plantage=0 motif ko prochaine pause ext
  debut_iso=$(debut_ecrit); [ -n "$debut_iso" ] || debut_iso=$(maintenant_iso)
  debut_s=$(date +%s)
  FINI=0
  conclure() {   # conclure <etat> <statut> <raison>
    FINI=1
    ecrire_etat "$1" "$2" "$debut_iso" "$(maintenant_iso)" "$3"
    nettoyer_reseau
    liberer_creneau
    exit 0
  }
  trap 'if [ "$FINI" = 0 ]; then arreter_conteneur; conclure echouee erreur "Veilleur interrompu avant la fin de la tâche."; fi' EXIT
  trap 'exit 143' TERM INT HUP
  # arreter_puis <etat> <statut> <raison> : arrête le conteneur ; plantage.txt prime sur ok et limite.
  arreter_puis() {
    local etat="$1" statut="$2" raison="$3"
    arreter_conteneur || conclure echouee erreur "$raison mais le conteneur tache-$ID ne s'arrête pas : à arrêter à la main (docker stop)."
    if [ -e "$DOSSIER/sortie/plantage.txt" ]; then plantage=1; fi       # relu APRÈS l'arrêt : un plantage écrit entre-temps compte
    if [ "$plantage" = 1 ]; then conclure "$etat" plantage "$raison ; plantage relevé (plantage.txt)."; fi
    conclure "$etat" "$statut" "$raison."
  }
  while :; do
    if [ -e "$DOSSIER/sortie/plantage.txt" ]; then plantage=1; else plantage=0; fi
    # L'état du conteneur d'abord : un conteneur mort reste une erreur même si arret existe.
    conteneur_vivant; etat_conteneur=$?
    if [ "$etat_conteneur" = 1 ]; then
      if [ "$plantage" = 1 ]; then conclure terminee plantage "Le conteneur s'est arrêté ; plantage relevé (plantage.txt)."; fi
      if [ ! -e "$DOSSIER/sortie/.avd-pret" ]; then         # mort avant que l'AVD n'existe : la raison est dans le journal d'entrée
        ext=$(extrait_demarrage)
        [ -n "$ext" ] || ext="voir sortie/entree-tache.log"
        conclure echouee erreur "Le conteneur s'est arrêté au démarrage : $ext"
      fi
      conclure echouee erreur "Le conteneur s'est arrêté de lui-même avant la fin (voir sortie/entree-tache.log)."
    elif [ "$etat_conteneur" = 2 ]; then
      pannes=$((pannes + 1))
      [ "$pannes" -lt 30 ] || conclure echouee erreur "Docker ne répond plus : état du conteneur inconnu."
    else
      pannes=0
    fi
    if [ -e "$DOSSIER/arret" ]; then
      motif=""; IFS= read -r motif < "$DOSSIER/arret" 2>/dev/null
      if [ "$motif" = fin ]; then arreter_puis terminee ok "Fin demandée par le lanceur (arret : fin)"; fi
      arreter_puis arretee ok "Arrêt demandé (fichier arret)"
    fi
    maintenant=$(date +%s)
    if [ $((maintenant - debut_s)) -ge "$DUREE" ]; then arreter_puis terminee limite "Durée maximale atteinte (${DUREE} s)"; fi
    prochaine=$((DUREE - (maintenant - debut_s)))            # secondes avant la prochaine échéance (durée, puis inactivité)
    ko=$(du -sk "$DOSSIER/sortie" 2>/dev/null | cut -f1)
    if [[ $ko =~ ^[0-9]+$ ]] && [ "$ko" -gt "$LIMITE_SORTIE_KO" ]; then
      arreter_puis terminee limite "Limite atteinte : sortie trop volumineuse (${ko} Ko, maximum ${LIMITE_SORTIE_KO} Ko)"
    fi
    if [ -n "$AGENT_LIE" ] && ! agent_actif; then             # l'agent lié a fini ou son pont est parti : plus de pilote
      arreter_puis terminee ok "Agent lié $AGENT_LIE fini ou pont hôte arrêté : émulation arrêtée"
    fi
    if [ "$MODE" = pilote ]; then
      derniere=$debut_s
      m=$(mtime "$DOSSIER/sortie/pont.log"); [ "$m" -gt "$derniere" ] && derniere=$m
      m=$(mtime "$DOSSIER/sortie/.activite"); [ "$m" -gt "$derniere" ] && derniere=$m
      m=$(mtime "$DOSSIER/sortie/.avd-pret"); [ "$m" -gt "$derniere" ] && derniere=$m      # AVD créé : le conteneur travaille
      if [ $((maintenant - derniere)) -ge "$INACTIVITE" ]; then
        arreter_puis terminee limite "Inactivité du pilote : aucun verbe depuis ${INACTIVITE} s"
      fi
      [ $((INACTIVITE - (maintenant - derniere))) -lt "$prochaine" ] && prochaine=$((INACTIVITE - (maintenant - derniere)))
    fi
    # Sommeil d'une sonde, raccourci jusqu'à l'échéance la plus proche si elle tombe avant (au moins 1 s).
    pause="$SONDE"
    [ "$prochaine" -ge 1 ] || prochaine=1
    [ "${SONDE%%.*}" -ge "$prochaine" ] && pause="$prochaine"
    sleep "$pause"
  done
}

if [ "$VEILLEUR" = 1 ]; then veilleur; exit 0; fi

# --- Enveloppe (au premier plan, rend vite la main) ------------------------

# fin_erreur, processus_vivant, honorer_final, occupe, detacher_veilleur : commun.sh.
veilleur_vivant() { processus_vivant "$DOSSIER/veilleur.pid" "--veilleur $ID"; }
# L'enveloppe d'un lancement en cours de démarrage (docker run peut durer 120 s, le veilleur n'existe pas encore).
enveloppe_vivante() { processus_vivant "$DOSSIER/enveloppe.pid" "lancer_emulation.sh $ID"; }   # paire contiguë, comme le lanceur

umask 077
mkdir -p -- "$DOSSIER/entree" "$DOSSIER/sortie" || refuser "dossier de la tâche non créable."
chmod 755 "$DOSSIER/entree"
chmod 777 "$DOSSIER/sortie"        # écrit par l'utilisateur 1000 du conteneur, quel que soit le propriétaire de l'hôte

# Un identifiant ne sert qu'une fois : seul un état absent ou en_attente (jamais démarré) peut être relancé, de sorte que
# plantage.txt, .avd-pret ou des captures d'une tâche précédente ne fuient jamais dans la suivante. Rien n'est modifié.
if [ -f "$DOSSIER/etat.json" ] && ! grep -q '"etat": "en_attente"' "$DOSSIER/etat.json"; then
  montrer_etat
  if grep -q '"etat": "en_cours"' "$DOSSIER/etat.json" && { veilleur_vivant || enveloppe_vivante; }; then exit 3; fi
  exit 4
fi
if [ -n "$AGENT_LIE" ]; then
  # Émulation liée : arret n'est JAMAIS effacé (le pont hôte ou le veilleur de l'agent a pu y écrire « fin » pendant ce
  # lancement) ; un agent déjà fini ou un arrêt déjà demandé : refusé (code 1), rien ne démarre.
  if agent_fini || [ -e "$DOSSIER/arret" ] || [ -L "$DOSSIER/arret" ]; then
    ecrire_etat arretee ok "" "$(maintenant_iso)" "Agent lié $AGENT_LIE déjà fini ou arrêt déjà demandé : émulation non démarrée."
    montrer_etat
    exit 1
  fi
else
  rm -f "$DOSSIER/arret"
fi

case "$SDK$DOSSIER" in
  *,*) fin_erreur "Chemin non admis (virgule) : montage impossible." ;;
esac

exec 8>> "$TACHES/.creneau-emulation" || { ecrire_etat echouee erreur "" "$(maintenant_iso)" "Créneau inaccessible."; exit 1; }
trap '' HUP                         # la fin de la session SSH ne doit jamais interrompre l'écriture de l'état
# Un `arreter` du lanceur a pu passer pendant l'attente du créneau (il retire l'APK puis écrit arretee) : un état FINAL est
# alors honoré, jamais réécrit (ni en_attente, ni en_cours) ; la tâche ne démarre jamais sans son APK. Relu sous le créneau,
# juste avant chaque écriture d'état. RÉSIDUEL CONNU (laissé ouvert) : entre honorer_final et ecrire_etat en_cours (moins
# d'une milliseconde), un _ARRETER du lanceur, qui ne prend pas le créneau, peut encore retirer l'APK et écrire arretee ;
# son second contrôle voit alors en_cours et n'écrase rien, et le lanceur, qui tient l'état rendu par arreter pour seul
# juge, rappelle arreter (fichier arret) : la tâche démarrée sans APK est arrêtée au tour suivant. Le fermer demanderait un
# verrou par tâche partagé par l'enveloppe et _ARRETER. (honorer_final et occupe : commun.sh ; occupe : jamais deux émulateurs.)
flock -n 8 || occupe "Créneau d'émulation occupé : une autre tâche tourne, relancez plus tard."
honorer_final
# Un conteneur tache-* étiqueté myiafactory.genre=agent (lancer_agent.sh) n'est pas un émulateur ; tout autre, sans étiquette
# (anciens conteneurs) compris, en est un. Le préfixe « genre= » donne une ligne non vide même sans étiquette.
genres=$(dk 20 ps --filter "name=^tache-" --format 'genre={{.Label "myiafactory.genre"}}') || fin_erreur "Docker ne répond pas : impossible de vérifier qu'aucun émulateur ne tourne."
while IFS= read -r genre; do
  [ -z "$genre" ] || [ "$genre" = genre=agent ] || occupe "Un conteneur tache-* tourne déjà (veilleur mort ?) : relancez plus tard."
done <<< "$genres"

kvm_gid=$(getent group kvm 2>/dev/null | cut -d: -f3)
[[ $kvm_gid =~ ^[0-9]{1,10}$ ]] || fin_erreur "Groupe kvm introuvable sur ce serveur : l'émulateur ne peut pas être accéléré."
[[ $IMAGE_SYSTEME =~ $MOTIF_IMAGE_SYSTEME ]] || fin_erreur "Image système mal formée."
# Taille du system.img de l'image épinglée (stat sans suivre de lien : absent ici, l'entrée du conteneur dira l'image absente).
taille_img=$(stat -c %s -- "$SDK/${IMAGE_SYSTEME//;//}/system.img" 2>/dev/null)
if [[ $taille_img =~ ^[0-9]{1,15}$ ]] && [ "$taille_img" -gt "$IMAGE_MAX_OCTETS" ]; then
  fin_erreur "Image système trop grosse pour /avd : system.img fait $((taille_img / 1048576)) Mo, au plus $((IMAGE_MAX_OCTETS / 1048576)) Mo (tmpfs /avd de ${AVD_TMPFS_GO} Go moins 2 Go de marge : l'émulateur en fait une copie inscriptible)."
fi

RESEAU_EMUL=none                                    # fermé par défaut : seule la présence d'hôtes (accord vérifié par le lanceur) l'ouvre
HOTES_IP=(); ADD_HOTES=(); ENV_PROXY=(); RAISON_DEMARRAGE="Conteneur en cours de démarrage."
if [ -n "$HOTES" ]; then
  RAISON_RESEAU=""
  resoudre_hotes || fin_erreur "Réseau refusé : ${RAISON_RESEAU} Rien n'a démarré."      # d'abord : un refus ne touche à rien
  # Le créneau est tenu : un proxy ou un réseau `reseau-*` qui traîne est celui d'une tâche morte, on le retire.
  for ancien in $(dk 20 ps -aq --filter "label=myiafactory.genre=proxy" 2>/dev/null); do dk 30 rm -f "$ancien" >/dev/null 2>&1; done
  for ancien in $(dk 20 network ls -q --filter "label=myiafactory.genre=reseau" 2>/dev/null); do dk 30 network rm "$ancien" >/dev/null 2>&1; done
  case "$ICI$DOSSIER" in *,*) fin_erreur "Chemin non admis (virgule) : montage impossible." ;; esac
  ecrire_proxy || fin_erreur "Réseau refusé : le proxy n'a pas pu être écrit. Rien n'a démarré."
  RESEAU_EMUL="$RESEAU_NOM"
  for hip in "${HOTES_IP[@]}"; do
    for ip in $(printf '%s' "${hip#*=}" | tr ',' ' '); do ADD_HOTES+=(--add-host "${hip%%=*}:$ip"); done
  done
  ENV_PROXY=(-e "PONT_PROXY=http://proxy-sortant:$PROXY_PORT")
  RAISON_DEMARRAGE="Conteneur en cours de démarrage ; réseau ouvert (HTTPS, port 443) vers : ${HOTES_IP[*]}."
  printf '%s\n' "$(maintenant_iso) réseau ouvert (CONNECT :443 seulement) vers : ${HOTES_IP[*]}" > "$DOSSIER/reseau.txt"
fi

honorer_final                                       # relu juste avant d'écrire en_cours
printf '%s\n' "$$" > "$DOSSIER/enveloppe.pid"      # AVANT en_cours : un second lancement voit une enveloppe vivante, pas un veilleur mort
ecrire_etat en_cours "" "$(maintenant_iso)" "" "$RAISON_DEMARRAGE"

if [ -n "$HOTES" ]; then
  # Réseau interne (sans passerelle), puis le proxy : démarré sur le pont par défaut, puis branché sur le réseau interne.
  PROXY=(run --pull never --rm -d --init --name "$RESEAU_NOM" --network bridge --label myiafactory.genre=proxy
    --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:size=64m,mode=1777
    --memory 192m --memory-swap 192m --cpus 0.5 --pids-limit 128 -e HOME=/tmp --entrypoint java
    --mount "type=bind,src=$DOSSIER/reseau,dst=/proxy,readonly"
    "$IMAGE" -Xmx96m /proxy/ProxySortant.java "$PROXY_PORT" "${HOTES_IP[@]}")
  if ! dk 30 network create --internal --label myiafactory.genre=reseau "$RESEAU_NOM" >/dev/null 2>"$DOSSIER/docker-reseau.log" \
     || ! dk 120 "${PROXY[@]}" >/dev/null 2>>"$DOSSIER/docker-reseau.log" \
     || ! dk 30 network connect --alias proxy-sortant "$RESEAU_NOM" "$RESEAU_NOM" >/dev/null 2>>"$DOSSIER/docker-reseau.log"; then
    nettoyer_reseau
    fin_erreur "Réseau borné impossible à établir (voir docker-reseau.log) : rien n'a démarré."
  fi
fi

# --mount (et non -v) : un chemin source absent est une erreur, jamais un dossier créé par root ; SDK et entree en lecture seule.
COMMANDE=(run --pull never --rm -d --init --name "tache-$ID" --network "$RESEAU_EMUL" ${ADD_HOTES[@]+"${ADD_HOTES[@]}"} --device /dev/kvm
  --user 1000:1000 --group-add "$kvm_gid" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:size=512m,mode=1777 --tmpfs "/avd:size=${AVD_TMPFS_GO}g,mode=1777"
  --memory "${MEMOIRE}m" --memory-swap "${MEMOIRE}m" --cpus "$CPUS" --pids-limit 512 --ulimit nofile=4096:4096
  -e ANDROID_AVD_HOME=/avd -e HOME=/tmp -e ANDROID_USER_HOME=/tmp/.android -e PONT_SORTIE=/sortie -e PONT_AVD=emul
  -e PONT_EMULATEUR=/opt/android-sdk/emulator/emulator -e PONT_ADB=/opt/android-sdk/platform-tools/adb
  -e "TACHE_DUREE_S=$DUREE" -e "TACHE_IMAGE_SYSTEME=$IMAGE_SYSTEME" ${ENV_SUPPL[@]+"${ENV_SUPPL[@]}"} ${ENV_PROXY[@]+"${ENV_PROXY[@]}"}
  --mount "type=bind,src=$SDK,dst=/opt/android-sdk,readonly"
  --mount "type=bind,src=$DOSSIER/entree,dst=/entree,readonly"
  --mount "type=bind,src=$DOSSIER/sortie,dst=/sortie"
  "$IMAGE")
if ! dk 120 "${COMMANDE[@]}" >/dev/null 2>"$DOSSIER/docker-run.log"; then
  dk 30 rm -f "tache-$ID" >/dev/null 2>&1          # un docker run figé (délai) a pu laisser un conteneur à demi créé
  nettoyer_reseau
  fin_erreur "Démarrage du conteneur impossible (docker run en échec : voir docker-run.log)."
fi

# Veilleur détaché : il hérite du descripteur 8 (donc du créneau) et le libère à la fin, même si cette session SSH a disparu ;
# l'enveloppe rend la main seulement quand veilleur.pid existe (detacher_veilleur, commun.sh).
detacher_veilleur "$ID" "$MODE" "$DUREE" "$INACTIVITE" "$MEMOIRE" "$CPUS" ${SUPPL[@]+"${SUPPL[@]}"}
montrer_etat
exit 0
