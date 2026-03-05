"""
ClaudePrivé — Chat privé avec AWS Bedrock
Backend Flask principal — Version Multi-Utilisateurs
"""

import os
import json
import uuid
import time
import threading
import shutil
from datetime import datetime, date
from functools import wraps
from pathlib import Path

import boto3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32).hex())

# ─── Configuration de l'app (mode pro ou étudiant) ────────────────────────────
APP_MODE     = os.environ.get("APP_MODE", "pro")          # "pro" | "student"
APP_TITLE    = os.environ.get("APP_TITLE", "ClaudePrivé")
APP_SUBTITLE = os.environ.get("APP_SUBTITLE", "Chat privé · AWS Bedrock")
APP_INITIALS = APP_TITLE[:2].upper()
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "delyweb")

print("\n" + "="*50)
print(f"🚀 {APP_TITLE.upper()} - MODE={APP_MODE} - 2026-03-05 🚀")
print("="*50 + "\n")

app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024 * 1024  # 6 Go max upload pour vidéo

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MESSAGES_DIR = DATA_DIR / "messages"
MESSAGES_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# Gestion des utilisateurs
# ─────────────────────────────────────────────

USERS_FILE = DATA_DIR / "users.json"


def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}


def save_users(users):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def migrate_existing_data(username):
    """Migre les données globales existantes vers le dossier utilisateur."""
    user_dir = get_user_dir(username)
    for fname in ["conversations.json", "projects.json", "costs.json", "prompts.json", "settings.json"]:
        src = DATA_DIR / fname
        dst = user_dir / fname
        if src.exists() and not dst.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[MIGRATION] {fname} → users/{username}/{fname}")
    src_uploads = DATA_DIR / "uploads"
    dst_uploads = user_dir / "uploads"
    if src_uploads.exists() and not dst_uploads.exists():
        shutil.copytree(str(src_uploads), str(dst_uploads))
        print(f"[MIGRATION] uploads/ → users/{username}/uploads/")


def init_admin():
    """Crée l'admin au premier démarrage, ou met à jour son mot de passe si ADMIN_PASSWORD a changé."""
    admin_password = os.environ.get("ADMIN_PASSWORD", "changeme")
    if not USERS_FILE.exists():
        users = {
            ADMIN_USERNAME: {
                "password_hash": generate_password_hash(admin_password),
                "role": "admin",
                "created_at": datetime.now().isoformat()
            }
        }
        save_users(users)
        migrate_existing_data(ADMIN_USERNAME)
        print(f"[AUTH] Admin '{ADMIN_USERNAME}' créé.")
    else:
        # Si ADMIN_PASSWORD est défini et différent du hash stocké, mettre à jour
        if admin_password != "changeme":
            users = load_users()
            if ADMIN_USERNAME in users:
                if not check_password_hash(users[ADMIN_USERNAME]["password_hash"], admin_password):
                    users[ADMIN_USERNAME]["password_hash"] = generate_password_hash(admin_password)
                    save_users(users)
                    print(f"[AUTH] Mot de passe admin '{ADMIN_USERNAME}' mis à jour depuis ADMIN_PASSWORD.")


def is_admin(username):
    return load_users().get(username, {}).get("role") == "admin"


def get_current_user():
    return session.get("username")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Non authentifié"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        u = session.get("username")
        if not u:
            return jsonify({"error": "Non authentifié"}), 401
        if not is_admin(u):
            return jsonify({"error": "Accès refusé"}), 403
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
# Chemins de données par utilisateur
# ─────────────────────────────────────────────

def get_user_dir(username):
    d = DATA_DIR / "users" / username
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_uploads_dir(username):
    d = get_user_dir(username) / "uploads"
    d.mkdir(exist_ok=True)
    return d


# Initialisation au démarrage
init_admin()


# ─────────────────────────────────────────────
# Client Bedrock
# ─────────────────────────────────────────────

def get_user_forced_config(username):
    """Returns forced_model and forced_region from admin config, or empty strings."""
    if not username:
        return "", ""
    users = load_users()
    u = users.get(username, {})
    return u.get("forced_model", ""), u.get("forced_region", "")


def get_bedrock_client(model_id=None, username=None):
    _, forced_region = get_user_forced_config(username)
    settings_region = forced_region or load_settings(username).get("region", "eu-west-3")
    target_region = settings_region
    if model_id and model_id.startswith("us."):
        target_region = "us-east-1"
    return boto3.client("bedrock-runtime", region_name=target_region)


# Tarifs Bedrock par million de tokens (USD)
PRICING = {
    "eu.anthropic.claude-opus-4-6-v1": {"input": 15.0, "output": 75.0},
    "anthropic.claude-opus-4-6-v1":    {"input": 15.0, "output": 75.0},
    "eu.anthropic.claude-opus-4-5-20251101-v1:0": {"input": 15.0, "output": 75.0},
    "anthropic.claude-opus-4-5-20251101-v1:0":    {"input": 15.0, "output": 75.0},
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 3.0, "output": 15.0},
    "anthropic.claude-sonnet-4-5-20250929-v1:0":    {"input": 3.0, "output": 15.0},
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.25, "output": 1.25},
    "anthropic.claude-haiku-4-5-20251001-v1:0":    {"input": 0.25, "output": 1.25},
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": {"input": 3.0, "output": 15.0},
}
VALID_MODELS = list(PRICING.keys())


def call_claude(messages, system_prompt, model=None, username=None):
    """Appel Claude via AWS Bedrock."""
    if model is None:
        forced_model, _ = get_user_forced_config(username)
        model = forced_model or load_settings(username).get("model", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0")

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": messages,
    })

    client = get_bedrock_client(model, username)
    resp = client.invoke_model(modelId=model, body=body)
    result = json.loads(resp["body"].read())

    usage = result.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    prices = PRICING.get(model, {"input": 3.0, "output": 15.0})
    cost_usd = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
    update_costs(input_tokens, output_tokens, cost_usd, username)

    return result, {"input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": round(cost_usd, 6)}


# ─────────────────────────────────────────────
# Gestion des conversations (JSON)
# ─────────────────────────────────────────────

def load_conversations(username):
    f = get_user_dir(username) / "conversations.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_conversations(convs, username):
    f = get_user_dir(username) / "conversations.json"
    f.write_text(json.dumps(convs, ensure_ascii=False, indent=2), encoding="utf-8")


def get_conversation(conv_id, username):
    return load_conversations(username).get(conv_id)


def save_conversation(conv_id, conv, username):
    convs = load_conversations(username)
    convs[conv_id] = conv
    save_conversations(convs, username)


def delete_conversation(conv_id, username):
    convs = load_conversations(username)
    convs.pop(conv_id, None)
    save_conversations(convs, username)


# ─────────────────────────────────────────────
# Gestion des projets
# ─────────────────────────────────────────────

def load_projects(username):
    f = get_user_dir(username) / "projects.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_projects(projects, username):
    f = get_user_dir(username) / "projects.json"
    f.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")


def get_project(project_id, username):
    return load_projects(username).get(project_id)


def save_project(project_id, project, username):
    projects = load_projects(username)
    projects[project_id] = project
    save_projects(projects, username)


def delete_project(project_id, username):
    projects = load_projects(username)
    projects.pop(project_id, None)
    save_projects(projects, username)


# ─────────────────────────────────────────────
# Compteur de coûts
# ─────────────────────────────────────────────

def load_costs(username):
    f = get_user_dir(username) / "costs.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {
        "daily": {}, "total": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
    }


def save_costs(costs, username):
    f = get_user_dir(username) / "costs.json"
    f.write_text(json.dumps(costs, ensure_ascii=False, indent=2), encoding="utf-8")


def update_costs(input_tokens, output_tokens, cost_usd, username):
    if not username:
        return
    costs = load_costs(username)
    today = date.today().isoformat()
    if today not in costs["daily"]:
        costs["daily"][today] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
    costs["daily"][today]["input_tokens"] += input_tokens
    costs["daily"][today]["output_tokens"] += output_tokens
    costs["daily"][today]["cost_usd"] = round(costs["daily"][today]["cost_usd"] + cost_usd, 6)
    costs["total"]["input_tokens"] += input_tokens
    costs["total"]["output_tokens"] += output_tokens
    costs["total"]["cost_usd"] = round(costs["total"]["cost_usd"] + cost_usd, 6)
    save_costs(costs, username)


# ─────────────────────────────────────────────
# Prompts système prédéfinis
# ─────────────────────────────────────────────

_STYLE_RULES = """
INTERDICTIONS ABSOLUES :
- Tu n'as AUCUN outil, AUCUNE fonction, AUCUN accès fichier. N'invente jamais d'appels d'outils comme list_files, read_file, bash, execute, search ou tout autre fonction. Si tu vois des fichiers de projet, c'est parce qu'ils sont déjà injectés dans ce prompt — tu n'as pas besoin de les "lire" autrement. Si un fichier n'est pas dans le contexte, dis simplement qu'il n'est pas disponible.

STYLE DE RÉPONSE — règles absolues :
- Tu rédiges en paragraphes continus et bien construits, comme un texte professionnel.
- Tu n'utilises les listes à puces ou numérotées QUE si c'est vraiment indispensable (énumérations de plus de 5 éléments distincts, étapes séquentielles). Par défaut, tu intègres les éléments dans la prose.
- Tu n'utilises AUCUN emoji dans tes réponses texte. Les emojis à l'intérieur du code, YAML, scripts et automatisations sont autorisés et conservés tels quels.
- Tu évites les titres et sous-titres en gras sauf pour les documents longs qui l'exigent explicitement.
- Tes réponses sont denses, précises et directes — pas de phrases d'introduction creuses ni de conclusions récapitulatives inutiles.

ARTEFACTS — règles absolues :
- Tout code doit TOUJOURS être dans un bloc fencé avec le langage correct : ```python, ```javascript, ```html, ```css, ```sql, ```yaml, ```json, ```bash, ```markdown, etc. Sans exception.
- Tout email, courrier ou message rédigé doit également être dans un bloc fencé ```markdown (jamais en texte brut dans la réponse).
- Tout document ou fichier complet (page HTML, script, configuration, template, rapport Markdown) doit être dans un bloc fencé pour être affiché dans le panneau artefact.
- Les variables ou expressions courtes peuvent utiliser des `backticks` inline, mais tout bloc de code de 2 lignes ou plus va obligatoirement en bloc fencé.
- N'écris JAMAIS de code ou d'email en dehors d'un bloc fencé — même un court extrait.
- Si le contenu est trop long pour un seul bloc, découpe-le en plusieurs blocs fencés successifs clairement nommés (ex : `Partie 1/3`, `Partie 2/3`, etc.).
"""

if APP_MODE == "student":
    GLOBAL_SYSTEM_PROMPT = """
Tu es CyberMentor, un assistant pédagogique pour les étudiants du parcours "Administrateur Systèmes, Réseaux et Cybersécurité" d'OpenClassrooms (diplôme niveau 6, 13 projets, 804h supervisées).
Tu t'exprimes en français par défaut. Tu tutoies l'étudiant.

TON RÔLE
Tu aides l'étudiant à comprendre, progresser et produire ses livrables de projet. Tu ne fais pas le travail à sa place — tu guides, tu expliques, tu poses des questions pour l'amener à trouver lui-même.

POURQUOI CETTE RÈGLE
L'étudiant devra défendre son travail à l'oral devant un jury. S'il ne comprend pas ce qu'il a produit, il échouera à la soutenance. Ton aide doit donc renforcer sa compréhension, pas la remplacer.

CE QUE TU PEUX FAIRE
- Expliquer un concept technique (protocole, outil, architecture)
- Aider à structurer un document professionnel (plan, trame)
- Générer une TRAME VIDE de livrable que l'étudiant remplira avec SES résultats
- Relire un document et suggérer des améliorations de forme
- Poser des questions de compréhension pour préparer la soutenance
- Déboguer une erreur technique en guidant pas à pas
- Expliquer pourquoi une approche est bonne ou mauvaise

CE QUE TU NE FAIS PAS
- Rédiger le contenu technique à la place de l'étudiant
- Donner les réponses directes aux exercices sans explication
- Produire un livrable clé en main prêt à soumettre

GÉNÉRATION DE DOCUMENTS
Quand l'étudiant demande un document professionnel, génère une TRAME avec :
- La structure complète et les sections attendues
- Des instructions claires [EN MAJUSCULES] pour chaque section
- Des exemples de formulation professionnelle (sans le contenu réel)
- Des zones [À COMPLÉTER PAR L'ÉTUDIANT] bien visibles

CONVENTION DE NOMMAGE DES LIVRABLES
Nom_Prenom_n°_du_livrable_nom_du_livrable_mmaaaa
Exemple : Dupont_Jean_1_rapport_pentest_032026
Dossier ZIP : Titre_du_projet_nom_prenom
Dépôt : 48h avant la soutenance

POSTURE
- Ton encourageant mais exigeant
- Si une question est vague, demander des précisions avant de répondre
- Rappeler régulièrement que la soutenance est l'objectif final
- Ne jamais juger négativement les erreurs : c'est en se trompant qu'on apprend
""" + _STYLE_RULES
else:
    GLOBAL_SYSTEM_PROMPT = """
Tu es une instance privée et sécurisée de Claude, opérée via AWS Bedrock en Europe.
IMPORTANT : Tes réponses sont strictement confidentielles.
Tu es hébergé sur une infrastructure souveraine européenne. Tes données ne sont pas utilisées pour l'entraînement des modèles. Tu ne dois pas dire que tu es hébergé aux USA ou sur l'interface publique d'Anthropic. Tu agis comme un assistant professionnel de confiance. Tu t'exprimes en français par défaut.
""" + _STYLE_RULES

if APP_MODE == "student":
    DEFAULT_PROMPTS = [
        {"id": "p1", "name": "P1 — Onboarding formation", "prompt": "## CONTEXTE DU PROJET 1\nL'étudiant débute sa formation. Ce projet d'onboarding lui permet de clarifier le fonctionnement de la formation OC, de définir son objectif professionnel et de planifier son parcours sur 13 projets.\n\nLIVRABLE : Fiche de début de formation validée par le mentor (objectif pro, dates cibles, outils collaboratifs).\n\nCE QUE L'ÉTUDIANT DOIT COMPRENDRE : la structure des 13 projets, la différence entre mentorat et soutenances, l'importance d'un planning réaliste, l'utilisation de GLPI.\n\nQUESTIONS UTILES : Quel est ton objectif pro ? Dans quel secteur ? Combien d'heures/semaine ? Qu'est-ce qui t'a motivé ?\n\nATTENTION : Validé par le mentor uniquement, pas de soutenance externe."},
        {"id": "p2", "name": "P2 — Support utilisateurs GLPI", "prompt": "## CONTEXTE DU PROJET 2\nL'étudiant est admin systèmes et réseaux chez OpenShowroom (e-commerce). Il doit remettre en état un serveur GLPI défaillant, traiter des tickets d'incidents et créer une base de connaissances. Responsable : Marina. Collègue : Malek.\n\nLIVRABLES : Export tickets GLPI (PDF), Rapport d'activité (PDF), Base de connaissances (PDF), Diaporama (PDF).\n\nCOMPÉTENCES : Gérer incidents/demandes ITIL, mettre en place GLPI, rédiger une base de connaissances, communiquer sur son activité.\n\nNOTIONS CLÉS : Cycle ITIL (ouverture→résolution→clôture), catégories ITIL, indicateurs TRS/délai/SLA, GLPI, niveau 1 vs niveau 2.\n\nQUESTIONS JURY : Comment as-tu priorisé les tickets ? Différence incident/problème ? Structure base de connaissances ? Indicateurs mis en place ?"},
        {"id": "p3", "name": "P3 — Conception réseau local", "prompt": "## CONTEXTE DU PROJET 3\nL'étudiant conçoit l'architecture réseau d'une entreprise et organise son déploiement. Il produit un DAT (Document d'Architecture Technique) et un diagramme de Gantt.\n\nLIVRABLES : DAT simplifié (schéma physique + logique + plan d'adressage) — PDF, Diagramme de Gantt — PDF.\n\nCOMPÉTENCES : Présenter la solution technique et ses choix (DAT), organiser les tâches (Gantt).\n\nNOTIONS CLÉS : Modèle OSI/TCP-IP, schéma logique vs physique, plan d'adressage CIDR/sous-réseaux, VLAN, topologies réseau (étoile/hiérarchique), Gantt (tâches, dépendances, jalons).\n\nOUTILS : Draw.io, Packet Tracer, GanttProject.\n\nQUESTIONS JURY (rôle Thibault Charbi) : Pourquoi cette topologie ? Comment as-tu calculé tes sous-réseaux ? Si +50 postes dans 6 mois ? Explique ton schéma logique."},
        {"id": "p4", "name": "P4 — Services Web sécurisés", "prompt": "## CONTEXTE DU PROJET 4\nConfiguration d'un serveur Linux avec services web sécurisés : Apache (HTTPS/SSL), FTP sécurisé (FTPS), protection CrowdSec. Principe de moindre privilège.\n\nLIVRABLES : Configs Apache, config FTP sécurisé, configs protection services (archives), document d'autoévaluation (PDF).\n\nCRITÈRES : SSL valide + HTTPS fonctionnel + HTTP→HTTPS, FTPS + chroot + patte privée uniquement, CrowdSec installé + simulation attaque détectée.\n\nNOTIONS CLÉS : HTTP/HTTPS/SSL/TLS, différence SFTP vs FTPS, moindre privilège, CrowdSec (agents/hub/bouncer), iptables/firewalld, virtual hosts Apache.\n\nATTENTION : Validé par le mentor (session de bilan), pas de soutenance externe.\n\nQUESTIONS BILAN : Différence SFTP/FTPS ? Pourquoi certificat pour FTP ? Comment CrowdSec détecte une attaque ? Que se passe-t-il en HTTP ?"},
        {"id": "p5", "name": "P5 — AD multi-sites + VPN", "prompt": "## CONTEXTE DU PROJET 5\nDéploiement AD multi-sites (Paris + Nantes) avec DC principal et RODC. Sites reliés par VPN IPSec via firewalls Stormshield. Proxy HTTP/HTTPS + VPN SSL avec MFA et ZTNA pour les nomades.\n\nLIVRABLES (11) : Captures Windows Server, AD, GPO, VPN IPSec, CA, auth, ACL, VPN SSL, ACL SSL, procédure PDF, capture Proxy.\n\nSTRUCTURE AD : UO Direction/Paris/Nantes/IT/Banque. Utilisateurs : Louise Chapat, Samir Assaf, Paul Bokadi, Sabrina Ouazani, Lucie Garrido, David Azoulay, Théo Perrier, Ana Garcia, Salif Diallo.\n\nGPO REQUISES : Interdire connexion AD entre 20h-6h, connexion sans VPN pour nomades, USB uniquement IT, accessibilité pour Ana Garcia.\n\nNOTIONS CLÉS : AD (UO/GPO/réplication), RODC, VPN IPSec (IKEv2/certificats), Stormshield SNS, VPN SSL + ZTNA, proxy HTTP/HTTPS.\n\nQUESTIONS JURY : Pourquoi RODC à Nantes ? Auth avec certificats IPSec ? ZTNA vs VPN classique ? Si VPN IPSec tombe ?"},
        {"id": "p6", "name": "P6 — Maquette IPv6", "prompt": "## CONTEXTE DU PROJET 6\nMaquette Packet Tracer démontrant la transition IPv4→IPv6 avec cohabitation. Configuration SLAAC, EUI-64, DHCPv6, OSPFv3, ACL IPv6.\n\nLIVRABLES : Maquette Packet Tracer fonctionnelle (PKT), Résultats des tests (PDF).\n\nCRITÈRES : Tous équipements avec adresses IPv6 conformes, routage fonctionnel (statique + OSPFv3), services mail/DNS/web opérationnels en IPv6, ACL correctement configurées.\n\nNOTIONS CLÉS : Structure IPv6 (128 bits, hexadécimal), types d'adresses (lien-local fe80::, globale unicast, multicast, loopback ::1), SLAAC, EUI-64, DHCPv6 (stateful vs stateless), OSPFv3 vs OSPFv2, dual stack/tunneling.\n\nATTENTION : Validé par le mentor uniquement. Maquette 100% fonctionnelle + tests documentés.\n\nQUESTIONS BILAN : Comment un poste obtient son adresse IPv6 en SLAAC ? Différence SLAAC/DHCPv6 ? Problème vie privée EUI-64 ? Routage OSPFv3 ?"},
        {"id": "p7", "name": "P7 — Infrastructure réseau robuste", "prompt": "## CONTEXTE DU PROJET 7\nInfrastructure réseau complète avec redondance : VLAN, trunking, OSPF, NAT, HSRP/VRRP, filtrages. Maquette Packet Tracer + procédures de test et mise en production.\n\nLIVRABLES : Document de configuration équipements (PDF), maquette PT (PKT), procédure de test (PDF), diagramme des flux/schéma logique (PDF), schéma physique (PDF).\n\nARCHITECTURE : Routeurs RED-1 et RED-2 avec liens WAN redondants. Routes par défaut + de secours croisées. Sous-réseaux WAN dans 132.186.32.64/26.\n\nVLAN : Direction, RH, Commerciaux, Informatique, Finance, DNS. IT accède à tous.\n\nNOTIONS CLÉS : VLAN/trunking 802.1Q, STP/RSTP, OSPF, HSRP/VRRP, NAT/PAT, ACL (standard vs étendue), LACP.\n\nQUESTIONS JURY (rôle Thibault Charbi) : Pourquoi OSPF plutôt que statique ? Si RED-1 tombe ? Fonctionnement trunking ? Comment as-tu validé la redondance ?"},
        {"id": "p8", "name": "P8 — IA générative + PowerShell", "prompt": "## CONTEXTE DU PROJET 8\nUtilisation de l'IA générative (ChatGPT, Claude, Copilot...) pour améliorer, documenter et déboguer des scripts PowerShell. Apprentissage du prompt engineering + documentation technique générée avec l'IA.\n\nLIVRABLES : Script PowerShell amélioré + documentation (PDF/PS1), rapport sur l'utilisation de l'IA avec prompts utilisés (PDF), documentation technique (PDF).\n\nNOTIONS CLÉS PowerShell : structure script (fonctions/paramètres/erreurs), cmdlets Get-*/Set-*/New-*/Remove-*, pipeline/Select-Object/Where-Object, Try/Catch/Finally, Comment-Based Help.\n\nIA générative : prompt engineering (contexte+instruction+format), itération, vérification critique (l'IA peut se tromper), limites (hallucinations, code non sécurisé).\n\nCONSEILS : Donner le contexte exact, spécifier le format de sortie, demander des explications pas juste le code, tester chaque modification.\n\nQUESTIONS JURY : Explique ton script ligne par ligne. Quelles limites avec l'IA ? Comment as-tu vérifié le code ? Exemple de prompt amélioré ?"},
        {"id": "p9", "name": "P9 — Automatisation + sauvegardes", "prompt": "## CONTEXTE DU PROJET 9\nAutomatisation des tâches d'administration : gestion AD avec scripts PowerShell, sauvegardes incrémentales et différentielles avec rsync (Linux), chiffrement, planification (cron/Task Scheduler).\n\nLIVRABLES : Support de présentation (PDF), traces rsync sauvegardes incrémentales (.log), traces restaurations incrémentales (.log), traces sauvegardes différentielles (.log), traces restaurations différentielles (.log), scripts + crontab.txt.\n\nNOTIONS CLÉS Ansible : inventory, playbooks, modules (user/group/service/copy), idempotence, Vault.\nrsync : options -a/-v/--delete/--backup, sauvegarde incrémentale vs différentielle.\nPlanification : crontab syntax, Windows Task Scheduler.\nChiffrement : gpg --symmetric/--encrypt.\n\nQUESTIONS JURY : Différence incrémentale/différentielle ? Comment restaurer un fichier supprimé ? Si Ansible échoue à mi-chemin ? Pourquoi chiffrer les sauvegardes ?"},
        {"id": "p10", "name": "P10 — Migration Cloud AWS", "prompt": "## CONTEXTE DU PROJET 10\nPréparation de la migration vers AWS : veille technologique, DAT Cloud, calcul budget migration et maintenance, lab pratique AWS.\n\nLIVRABLES : Diaporama veille technologique (PDF), document de préparation migration (problématique/schéma/stratégies/procédure restauration) (PDF), diaporama brief équipe (PDF).\n\nNOTIONS CLÉS AWS : régions/AZ, VPC/subnets/SG/Route Tables, EC2, S3, IAM, RDS.\nStratégies migration 6R : Rehost, Replatform, Refactor, Repurchase, Retire, Retain.\nModèles coût : CapEx vs OpEx, pay-as-you-go, Reserved/Spot, TCO.\nVeille : Feedly, Google Alerts, AWS Blog, ANSSI, Gartner.\n\nQUESTIONS JURY : Pourquoi cette stratégie de migration ? Comment as-tu calculé le ROI ? Quels risques et comment les mitiger ? Explique ton architecture VPC ?"},
        {"id": "p11", "name": "P11 — Supervision SIEM", "prompt": "## CONTEXTE DU PROJET 11\nDéploiement d'une solution de supervision (Wazuh ou Nagios/Zabbix) : collecte de logs, alertes, tableaux de bord SIEM, détection d'incidents de sécurité.\n\nLIVRABLES : Documentation architecture supervision (PDF), captures dashboard (PDF), procédure réponse aux incidents (PDF), rapport de test de détection (PDF).\n\nNOTIONS CLÉS Wazuh : Manager+Agent+Indexer+Dashboard, règles et décodeurs, alertes (niveaux 0-15), intégrations Syslog/Filebeat/AD.\nNagios/Zabbix : checks actifs/passifs, NRPE.\nSIEM : log management, corrélation, SIEM vs SOC, faux positifs.\nIncident response : Détection→Analyse→Containment→Éradication→Récupération.\n\nQUESTIONS JURY : Comment Wazuh détecte un brute force ? Comment as-tu configuré une alerte ? IDS vs SIEM ? Comment tu priorises 500 alertes/jour ?"},
        {"id": "p12", "name": "P12 — Pentest Active Directory", "prompt": "## CONTEXTE DU PROJET 12\nPentest interne d'un domaine Active Directory (environnement lab). Outils offensifs (BloodHound, Mimikatz, Impacket) pour identifier les vulnérabilités. Rapport de pentest + plan de remédiation.\n\nLIVRABLES : Rapport de pentest (PDF), plan d'action de remédiation (PDF), support de restitution (PDF).\n\nATTAQUES AD : Kerberoasting, Pass-the-Hash, Pass-the-Ticket, AS-REP Roasting, LLMNR/NBT-NS Poisoning (Responder), mouvement latéral (impacket-psexec/wmiexec).\nOUTILS : BloodHound, Mimikatz (sekurlsa::logonpasswords), Impacket suite, Responder, nmap, enum4linux.\nREMÉDIATION : Politique MDP forte, LSASS protection, SMB Signing, désactiver LLMNR/NBT-NS, Tiering AD (Tier 0/1/2), Protected Users.\n\nSTRUCTURE RAPPORT : Résumé exécutif, périmètre/méthodologie, résultats par vuln (criticité/preuve/impact), plan remédiation priorisé, conclusion.\n\nATTENTION ÉTHIQUE : Ces techniques sont UNIQUEMENT pour environnement lab contrôlé. Utilisation sans autorisation écrite = illégal.\n\nQUESTIONS JURY (rôle DSI) : Explique le Kerberoasting et sa protection ? Pourquoi SMB Signing ? Comment credentials admin en clair ? Comment priorises-tu les remédiations ?"},
        {"id": "p13", "name": "P13 — Audit sécurité infrastructure critique", "prompt": "## CONTEXTE DU PROJET 13\nProjet de fin de parcours. Audit de sécurité complet d'une infrastructure critique + plan de durcissement conforme ANSSI. Mobilise toutes les compétences : réseau, système, supervision, sécurité offensive et défensive.\n\nLIVRABLES : Rapport d'audit sécurité (PDF), plan de durcissement/hardening (PDF), procédures de sécurité documentées (PDF), support de restitution (PDF).\n\nRÉFÉRENTIELS ANSSI : Guide sécurité AD, recommandations MDP, Guide d'hygiène informatique (42 recommandations), PGSSI-S.\nDÉFENSE EN PROFONDEUR : Périmètre→Réseau→Hôte→Application→Données. Si une couche compromise, les autres protègent encore.\nHARDENING SYSTÈME : Désactivation services inutiles, patch management, comptes locaux, audit/journalisation.\nHARDENING RÉSEAU : Segmentation DMZ/VLAN management, filtrage whitelist, TLS 1.2+/SSHv2.\n\nSTRUCTURE RAPPORT : Résumé exécutif, périmètre/méthodologie, constats par domaine, évaluation risques (probabilité×impact), recommandations ANSSI, plan remédiation avec échéances, conclusion.\n\nQUESTIONS JURY : Défense en profondeur illustrée ? Recommandation ANSSI la plus difficile ? Comment prioriser les recommandations ? Une seule action urgente, laquelle ? Que signifie être admin dans un OIV ?"},
    ]
else:
    DEFAULT_PROMPTS = [
        {"id": "general", "name": "Conseil général", "prompt": "Tu es un assistant business polyvalent. Tu aides avec des conseils professionnels clairs, structurés et actionnables."},
        {"id": "juridique", "name": "Analyse juridique", "prompt": "Tu es un assistant spécialisé en analyse juridique. Tu aides à analyser des contrats, clauses et documents légaux. Tu identifies les risques, les points d'attention et proposes des recommandations. Tu précises toujours que tu ne remplaces pas un avocat. Tu t'exprimes en français."},
        {"id": "commercial", "name": "Stratégie commerciale", "prompt": "Tu es un consultant en stratégie commerciale. Tu aides à définir des offres, du pricing, du positionnement marché et des stratégies de vente. Tu t'exprimes en français."},
        {"id": "redaction", "name": "Rédaction pro", "prompt": "Tu es un assistant de rédaction professionnelle. Tu aides à rédiger des emails, propositions commerciales, présentations et documents professionnels avec un ton adapté au contexte. Tu t'exprimes en français."},
        {"id": "domotique", "name": "Expert Domotique", "prompt": "Tu es un expert en domotique et en Home Assistant. Tu aides à concevoir des automatisations, à configurer des fichiers YAML, à choisir des capteurs (Zigbee, Z-Wave, WiFi) et à optimiser la consommation énergétique. Tu connais les protocoles MQTT, les intégrations ESPHome et Node-RED. Tu t'exprimes en français avec des exemples de code clairs."},
    ]


def load_prompts(username):
    f = get_user_dir(username) / "prompts.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    save_prompts(DEFAULT_PROMPTS, username)
    return list(DEFAULT_PROMPTS)


def save_prompts(prompts, username):
    f = get_user_dir(username) / "prompts.json"
    f.write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "model": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "region": "eu-west-3",
    "active_prompt": "general",
}


def load_settings(username=None):
    if username:
        f = get_user_dir(username) / "settings.json"
    else:
        f = DATA_DIR / "settings.json"
    if f.exists():
        try:
            settings = json.loads(f.read_text(encoding="utf-8"))
            if settings.get("model") not in VALID_MODELS:
                settings["model"] = DEFAULT_SETTINGS["model"]
                save_settings(settings, username)
            return settings
        except Exception:
            pass
    save_settings(DEFAULT_SETTINGS.copy(), username)
    return DEFAULT_SETTINGS.copy()


def save_settings(settings, username=None):
    if username:
        f = get_user_dir(username) / "settings.json"
    else:
        f = DATA_DIR / "settings.json"
    f.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
# Extraction de texte (fichiers uploadés)
# ─────────────────────────────────────────────

def call_pegasus_video(filepath, existing_s3_uri=None, existing_s3_key=None):
    """Appelle Twelve Labs Pegasus via S3 pour transcrire une vidéo."""
    s3_bucket = os.environ.get("S3_VIDEO_BUCKET")
    if not s3_bucket:
        return "[INFO] Vidéo stockée. Pour l'analyse IA (transcription), veuillez configurer la variable S3_VIDEO_BUCKET dans docker-compose.yml (voir GUIDE_S3.md)."

    try:
        s3 = boto3.client("s3")

        if existing_s3_uri:
            s3_uri = existing_s3_uri
            s3_key = existing_s3_key
        else:
            filename = Path(filepath).name
            s3_key = f"uploads/{uuid.uuid4().hex[:8]}/{filename}"
            s3_uri = f"s3://{s3_bucket}/{s3_key}"
            s3.upload_file(filepath, s3_bucket, s3_key)

        account_id = boto3.client("sts").get_caller_identity()["Account"]
        model_id = "twelvelabs.pegasus-1-2-v1:0"
        prompt = "Génère une transcription détaillée (diarisation) et un résumé exécutif de cette réunion."

        body = json.dumps({
            "inputPrompt": prompt,
            "mediaSource": {
                "s3Location": {
                    "uri": s3_uri,
                    "bucketOwner": account_id
                }
            },
            "maxOutputTokens": 4096
        })

        bedrock = get_bedrock_client()
        response = bedrock.invoke_model(modelId=model_id, body=body)
        result = json.loads(response["body"].read())
        text = result.get("message", f"[Réponse Pegasus brute] {json.dumps(result)}")

        try:
            s3.delete_object(Bucket=s3_bucket, Key=s3_key)
        except Exception:
            pass

        return text

    except Exception as e:
        import traceback
        print(f"[PEGASUS ERROR] {str(e)}\n{traceback.format_exc()}")
        return f"[Erreur Analyse Vidéo : {str(e)}]"


def is_pegasus_allowed(username):
    if not username:
        return True
    users = load_users()
    return users.get(username, {}).get("pegasus_enabled", True)


def extract_text_from_file(filepath, username=None):
    """Extrait le texte d'un fichier uploadé."""
    ext = Path(filepath).suffix.lower()

    if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        if not is_pegasus_allowed(username):
            return "[Analyse vidéo désactivée pour ce compte]"
        return call_pegasus_video(filepath)

    if ext == ".pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip()
        except Exception as e:
            return f"[Erreur extraction PDF : {str(e)}]"

    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except Exception as e:
            return f"[Erreur extraction DOCX : {str(e)}]"

    if ext in (".txt", ".md", ".csv", ".json", ".xml", ".html", ".py", ".js",
               ".yml", ".yaml"):
        try:
            return Path(filepath).read_text(encoding="utf-8", errors="replace").strip()
        except Exception as e:
            return f"[Erreur lecture fichier : {str(e)}]"

    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return f"[Image : {Path(filepath).name}]"

    return f"[Format non supporté pour extraction : {ext}]"


# ─────────────────────────────────────────────
# Routes — Authentification
# ─────────────────────────────────────────────

@app.route("/login", methods=["GET"])
def login_page():
    if session.get("username"):
        return redirect(url_for("index"))
    error = request.args.get("error", "")
    return render_template("login.html", error=error,
        app_title=APP_TITLE, app_subtitle=APP_SUBTITLE, app_initials=APP_INITIALS)


@app.route("/login", methods=["POST"])
def login_post():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    users = load_users()
    user = users.get(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return redirect(url_for("login_page", error="Identifiants incorrects"))
    session.permanent = True
    session["username"] = username
    session["role"] = user.get("role", "user")
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/api/me", methods=["GET"])
@login_required
def api_me():
    u = get_current_user()
    return jsonify({"username": u, "role": "admin" if is_admin(u) else "user"})


# ─────────────────────────────────────────────
# Routes — Admin
# ─────────────────────────────────────────────

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def api_admin_list_users():
    users = load_users()
    result = []
    for u, d in users.items():
        costs = load_costs(u)
        total = costs.get("total", {})
        conv_count = 0
        try:
            conv_file = get_user_dir(u) / "conversations.json"
            if conv_file.exists():
                conv_count = len(json.loads(conv_file.read_text(encoding="utf-8")))
        except Exception:
            pass
        result.append({
            "username": u,
            "role": d.get("role", "user"),
            "created_at": d.get("created_at", ""),
            "forced_model": d.get("forced_model", ""),
            "forced_region": d.get("forced_region", ""),
            "pegasus_enabled": d.get("pegasus_enabled", True),
            "cost_total": round(total.get("cost_usd", 0), 4),
            "conv_count": conv_count,
        })
    global_total = round(sum(u.get("cost_total", 0) for u in result), 4)
    active_users = sum(1 for u in result if u["conv_count"] > 0)
    return jsonify({"users": result, "models": VALID_MODELS,
                    "global_total": global_total, "active_users": active_users})


@app.route("/api/admin/users/<username>", methods=["PUT"])
@admin_required
def api_admin_update_user(username):
    users = load_users()
    if username not in users:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    data = request.get_json(silent=True) or {}
    if "role" in data and data["role"] in ("admin", "user"):
        users[username]["role"] = data["role"]
    if "forced_model" in data:
        val = data["forced_model"].strip()
        users[username]["forced_model"] = val if val in VALID_MODELS else ""
    if "forced_region" in data:
        val = data["forced_region"].strip()
        users[username]["forced_region"] = val if val in ("eu-west-3", "us-east-1", "") else ""
    if "pegasus_enabled" in data:
        users[username]["pegasus_enabled"] = bool(data["pegasus_enabled"])
    save_users(users)
    return jsonify({"ok": True})


@app.route("/api/admin/users", methods=["POST"])
@admin_required
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "user")
    if not username or not password:
        return jsonify({"error": "Username et password requis"}), 400
    users = load_users()
    if username in users:
        return jsonify({"error": "Utilisateur déjà existant"}), 409
    users[username] = {
        "password_hash": generate_password_hash(password),
        "role": role,
        "created_at": datetime.now().isoformat(),
        "pegasus_enabled": True,
    }
    save_users(users)
    get_user_dir(username)
    return jsonify({"ok": True, "username": username}), 201


@app.route("/api/admin/users/<username>", methods=["DELETE"])
@admin_required
def api_admin_delete_user(username):
    if username == get_current_user():
        return jsonify({"error": "Impossible de supprimer son propre compte"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    del users[username]
    save_users(users)
    return jsonify({"ok": True})


@app.route("/api/admin/users/<username>/password", methods=["PUT"])
@admin_required
def api_admin_reset_password(username):
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "Mot de passe requis"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    users[username]["password_hash"] = generate_password_hash(password)
    save_users(users)
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
# Routes — Application principale
# ─────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html",
        app_title=APP_TITLE, app_subtitle=APP_SUBTITLE,
        app_initials=APP_INITIALS, app_mode=APP_MODE)


# ── Recherche ──

@app.route("/api/search", methods=["GET"])
@login_required
def api_search():
    u = get_current_user()
    query = request.args.get("q", "").lower().strip()
    if not query or len(query) < 3:
        return jsonify([])

    convs = load_conversations(u)
    results = []

    for conv_id, conv in convs.items():
        title = conv.get("title", "Sans titre")
        if query in title.lower():
            results.append({"conversation_id": conv_id, "title": title, "snippet": "[Titre correspondant]", "date": conv.get("updated_at")})
            continue
        for msg in conv.get("messages", []):
            content = msg.get("content", "")
            if query in content.lower():
                idx = content.lower().find(query)
                start = max(0, idx - 60)
                end = min(len(content), idx + 140)
                snippet = "..." + content[start:end].replace("\n", " ") + "..."
                results.append({"conversation_id": conv_id, "title": title, "snippet": snippet, "date": conv.get("updated_at")})
                break
        if len(results) >= 20:
            break

    return jsonify(results)


# ── Conversations ──

@app.route("/api/conversations", methods=["GET"])
@login_required
def api_list_conversations():
    u = get_current_user()
    convs = load_conversations(u)
    project_id = request.args.get("project_id")
    result = []
    for cid, conv in sorted(convs.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True):
        if project_id and conv.get("project_id") != project_id:
            continue
        if not project_id and conv.get("project_id"):
            continue
        result.append({
            "id": cid,
            "title": conv.get("title", "Sans titre"),
            "created_at": conv.get("created_at", ""),
            "updated_at": conv.get("updated_at", ""),
            "message_count": len(conv.get("messages", [])),
            "project_id": conv.get("project_id"),
        })
    return jsonify(result)


@app.route("/api/conversations", methods=["POST"])
@login_required
def api_create_conversation():
    u = get_current_user()
    data = request.get_json(silent=True) or {}
    conv_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conv = {
        "title": data.get("title", "Nouvelle conversation"),
        "messages": [],
        "created_at": now,
        "updated_at": now,
        "prompt_id": data.get("prompt_id", load_settings(u).get("active_prompt", "general")),
        "project_id": data.get("project_id"),
    }
    save_conversation(conv_id, conv, u)
    return jsonify({"id": conv_id, **conv}), 201


@app.route("/api/conversations/<conv_id>", methods=["GET"])
@login_required
def api_get_conversation(conv_id):
    u = get_current_user()
    conv = get_conversation(conv_id, u)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404
    return jsonify({"id": conv_id, **conv})


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
@login_required
def api_delete_conversation(conv_id):
    u = get_current_user()
    delete_conversation(conv_id, u)
    return jsonify({"ok": True})


@app.route("/api/conversations/<conv_id>/title", methods=["PUT"])
@login_required
def api_rename_conversation(conv_id):
    u = get_current_user()
    conv = get_conversation(conv_id, u)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404
    data = request.get_json(silent=True) or {}
    conv["title"] = data.get("title", conv["title"])
    conv["updated_at"] = datetime.now().isoformat()
    save_conversation(conv_id, conv, u)
    return jsonify({"ok": True})


@app.route("/api/conversations/<conv_id>/project", methods=["PUT"])
@login_required
def api_move_conversation(conv_id):
    u = get_current_user()
    conv = get_conversation(conv_id, u)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    if project_id and not get_project(project_id, u):
        return jsonify({"error": "Projet introuvable"}), 404
    conv["project_id"] = project_id
    conv["updated_at"] = datetime.now().isoformat()
    save_conversation(conv_id, conv, u)
    return jsonify({"ok": True})


# ── Chat ──

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    u = get_current_user()
    data = request.get_json(silent=True) or {}
    conv_id = data.get("conversation_id")
    user_message = data.get("message", "").strip()
    file_content = data.get("file_content")
    image_data = data.get("image_data", [])  # list of {base64, media_type}

    if not conv_id or (not user_message and not image_data):
        return jsonify({"error": "conversation_id et message (ou image) requis"}), 400

    conv = get_conversation(conv_id, u)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404

    text_content = user_message
    if file_content:
        text_content = f"{user_message}\n\n--- Contenu du fichier joint ---\n{file_content}"

    if image_data:
        # Multimodal content: images + optional text
        content_blocks = []
        for img in image_data:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("media_type", "image/png"),
                    "data": img["base64"],
                }
            })
        if text_content:
            content_blocks.append({"type": "text", "text": text_content})
        conv["messages"].append({"role": "user", "content": content_blocks})
    else:
        conv["messages"].append({"role": "user", "content": text_content})

    prompt_id = conv.get("prompt_id", "general")
    prompts = load_prompts(u)
    user_system_prompt = "Tu es un assistant professionnel."
    for p in prompts:
        if p["id"] == prompt_id:
            user_system_prompt = p["prompt"]
            break

    final_system_prompt = f"{GLOBAL_SYSTEM_PROMPT}\n\n--- Instructions Spécifiques ---\n{user_system_prompt}"

    project_id = conv.get("project_id")
    if project_id:
        proj = get_project(project_id, u)
        uploads_dir = get_uploads_dir(u)
        if proj:
            project_context = f"\n\n--- PROJET : {proj.get('name', project_id)} ---\n"
            if proj.get("description"):
                project_context += f"Description : {proj['description']}\n"
            files = proj.get("files", [])
            if files:
                # Grouper par dossier
                folders_map = {}
                for f in files:
                    fld = f.get("folder", "") or ""
                    folders_map.setdefault(fld, []).append(f)

                project_context += f"\nFichiers disponibles dans ce projet ({len(files)}) :\n"
                for fld in sorted(folders_map.keys()):
                    label = f"Dossier \"{fld}\"" if fld else "Racine"
                    project_context += f"{label} :\n"
                    for f in folders_map[fld]:
                        status = f.get("status", "ready")
                        ref = f"{fld}/{f['filename']}" if fld else f['filename']
                        project_context += f"  - {ref} ({status})\n"

                project_context += "\n--- CONTENU DES DOCUMENTS ---\n"
                has_content = False
                for fld in sorted(folders_map.keys()):
                    for file in folders_map[fld]:
                        saved_as = file.get("saved_as")
                        if not saved_as:
                            continue
                        ref = f"{fld}/{file['filename']}" if fld else file['filename']
                        if file.get("status") == "processing":
                            project_context += f"\n[{ref}] : analyse en cours, contenu non disponible.\n"
                            continue
                        txt_path = uploads_dir / (saved_as + ".txt")
                        if txt_path.exists():
                            try:
                                file_text = txt_path.read_text(encoding="utf-8")
                                print(f"[DEBUG] Injection {ref} ({len(file_text)} chars)")
                                if len(file_text) > 50000:
                                    file_text = file_text[:50000] + "\n...[Tronqué à 50000 chars]..."
                                project_context += f"\n[{ref}]\n{file_text}\n"
                                has_content = True
                            except Exception as e:
                                print(f"[ERREUR] Lecture contexte {saved_as}: {e}")
                                project_context += f"\n[{ref}] : erreur de lecture ({e}).\n"
                        else:
                            original_path = uploads_dir / saved_as
                            text_exts = {".md", ".txt", ".csv", ".json", ".xml", ".html",
                                         ".py", ".js", ".yml", ".yaml"}
                            if original_path.exists() and Path(saved_as).suffix.lower() in text_exts:
                                try:
                                    file_text = original_path.read_text(encoding="utf-8", errors="replace").strip()
                                    txt_path.write_text(file_text, encoding="utf-8")
                                    print(f"[DEBUG] Fallback lecture directe {ref} ({len(file_text)} chars)")
                                    if len(file_text) > 50000:
                                        file_text = file_text[:50000] + "\n...[Tronqué à 50000 chars]..."
                                    project_context += f"\n[{ref}]\n{file_text}\n"
                                    has_content = True
                                except Exception as e:
                                    print(f"[ERREUR] Fallback lecture {saved_as}: {e}")
                                    project_context += f"\n[{ref}] : erreur de lecture ({e}).\n"
                            else:
                                print(f"[DEBUG] .txt manquant pour {ref} ({saved_as})")
                                project_context += f"\n[{ref}] : contenu non disponible.\n"

                final_system_prompt += project_context
                if has_content:
                    final_system_prompt += "\nINSTRUCTIONS : Utilise les documents ci-dessus comme contexte principal. Si une information n'est pas dans les documents, dis-le clairement sans inventer."
            else:
                project_context += "Aucun fichier dans ce projet.\n"
                final_system_prompt += project_context

    print(f"[DEBUG] System Prompt Size: {len(final_system_prompt)} chars")

    try:
        result, usage = call_claude(conv["messages"], final_system_prompt, username=u)
    except Exception as e:
        conv["messages"].pop()
        save_conversation(conv_id, conv, u)
        return jsonify({"error": f"Erreur Bedrock : {str(e)}"}), 500

    assistant_text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            assistant_text += block["text"]

    conv["messages"].append({"role": "assistant", "content": assistant_text})
    conv["updated_at"] = datetime.now().isoformat()

    if len(conv["messages"]) == 2 and conv["title"] == "Nouvelle conversation":
        conv["title"] = user_message[:50] + ("..." if len(user_message) > 50 else "")

    save_conversation(conv_id, conv, u)

    return jsonify({"response": assistant_text, "usage": usage, "conversation_id": conv_id})


# ── Upload ──

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".xml", ".html",
                      ".py", ".js", ".yml", ".yaml", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                      ".mp4", ".mov", ".avi", ".mkv", ".webm"}


@app.route("/api/debug/context/<project_id>", methods=["GET"])
@login_required
def api_debug_context(project_id):
    u = get_current_user()
    proj = get_project(project_id, u)
    if not proj:
        return "Projet introuvable"
    uploads_dir = get_uploads_dir(u)
    context = "--- SIMULATION CONTEXTE ---\n"
    if proj.get("files"):
        for file in proj["files"]:
            saved_as = file.get("saved_as")
            if saved_as:
                txt_path = uploads_dir / (saved_as + ".txt")
                if txt_path.exists():
                    content = txt_path.read_text(encoding="utf-8")
                    context += f"\n[Document: {file['filename']}] ({len(content)} chars)\n{content[:500]}...\n"
                else:
                    context += f"\n[Document: {file['filename']}] : PAS DE FICHIER TEXTE (.txt manquant)\n"
    else:
        context += "Aucun fichier dans ce projet."
    return f"<pre>{context}</pre>"


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Nom de fichier vide"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Format non supporté : {ext}"}), 400
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
    filepath = uploads_dir / safe_name
    f.save(str(filepath))
    text = extract_text_from_file(str(filepath))
    txt_path = Path(str(filepath) + ".txt")
    txt_path.write_text(text, encoding="utf-8")
    file_info = {
        "filename": f.filename,
        "saved_as": safe_name,
        "size": os.path.getsize(str(filepath)),
        "uploaded_at": datetime.now().isoformat(),
        "text_preview": text[:200] + "..." if len(text) > 200 else text,
        "text": text,
    }
    return jsonify(file_info)


@app.route("/api/projects/<project_id>/files/<saved_as>/folder", methods=["PUT"])
@login_required
def api_project_file_move_folder(project_id, saved_as):
    u = get_current_user()
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "").strip().strip("/")
    for fi in proj.get("files", []):
        if fi["saved_as"] == saved_as:
            fi["folder"] = folder
            # Also persist folder name in project's explicit folders list
            if folder:
                known = proj.get("folders", [])
                if folder not in known:
                    known.append(folder)
                    proj["folders"] = known
            proj["updated_at"] = datetime.now().isoformat()
            save_project(project_id, proj, u)
            return jsonify({"ok": True, "folder": folder})
    return jsonify({"error": "Fichier introuvable"}), 404


@app.route("/api/projects/<project_id>/folders", methods=["POST"])
@login_required
def api_project_add_folder(project_id):
    u = get_current_user()
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "").strip().strip("/")
    if not folder:
        return jsonify({"error": "Nom de dossier invalide"}), 400
    known = proj.get("folders", [])
    if folder not in known:
        known.append(folder)
        proj["folders"] = known
        proj["updated_at"] = datetime.now().isoformat()
        save_project(project_id, proj, u)
    return jsonify({"ok": True, "folders": proj.get("folders", [])})


@app.route("/api/projects/<project_id>/journal", methods=["POST"])
@login_required
def api_project_journal(project_id):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404

    today = date.today().isoformat()
    project_name = proj.get("name", "Projet")
    journal_filename = f"Journal_{project_name.replace(' ', '_')}_{today}.md"

    if any(f.get("filename") == journal_filename for f in proj.get("files", [])):
        return jsonify({"message": "Journal déjà existant pour aujourd'hui.", "filename": journal_filename})

    conversations_text = get_today_conversations_text(project_id, u)
    if not conversations_text.strip():
        return jsonify({"message": "Aucune activité aujourd'hui dans ce projet."})

    if len(conversations_text) > 15000:
        conversations_text = conversations_text[:15000] + "\n...[Conversations tronquées]"

    prompt = f"""Tu es l'assistant de synthèse de ClaudePrivé.

Voici les conversations du jour pour le projet "{project_name}".

Génère un journal quotidien concis au format markdown :

# Journal {project_name} - {today}

## Actions réalisées
Liste des actions concrètes effectuées aujourd'hui.

## Informations clés
Nouvelles informations apprises, réponses reçues, clarifications obtenues.

## Prochaines étapes
Actions identifiées à faire ou en attente.

## Points d'attention
Risques, blocages, sujets sensibles.

---

Règles : sois factuel et concis. Pas d'emojis. Si une section est vide, ne pas l'inclure. Maximum 30 lignes.

Conversations du jour :
{conversations_text}"""

    try:
        result, usage = call_claude(
            [{"role": "user", "content": prompt}],
            "Tu es un assistant de synthèse. Réponds uniquement en markdown.",
            username=u,
        )
        journal_content = "".join(
            block["text"] for block in result.get("content", []) if block.get("type") == "text"
        )

        safe_name = f"{uuid.uuid4().hex[:8]}_{journal_filename}"
        filepath = uploads_dir / safe_name
        filepath.write_text(journal_content, encoding="utf-8")
        Path(str(filepath) + ".txt").write_text(journal_content, encoding="utf-8")

        file_info = {
            "filename": journal_filename,
            "saved_as": safe_name,
            "size": len(journal_content.encode()),
            "uploaded_at": datetime.now().isoformat(),
            "text_preview": journal_content[:200] + "..." if len(journal_content) > 200 else journal_content,
        }
        proj = get_project(project_id, u)
        proj["files"].append(file_info)
        proj["updated_at"] = datetime.now().isoformat()
        save_project(project_id, proj, u)

        return jsonify({"filename": journal_filename, "usage": usage})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/artifact", methods=["POST"])
@login_required
def api_project_artifact(project_id):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404

    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "").strip()
    content = data.get("content", "")
    folder = data.get("folder", "").strip().strip("/")
    replace = data.get("replace", False)
    if not filename:
        return jsonify({"error": "Nom de fichier requis"}), 400

    # Check for existing file with same name
    existing = next((f for f in proj.get("files", []) if f.get("filename") == filename), None)
    if existing and not replace:
        return jsonify({"conflict": True, "filename": filename}), 409

    # If replacing, remove old file entry (keep disk file, it will be orphaned)
    if existing and replace:
        proj["files"] = [f for f in proj["files"] if f.get("filename") != filename]

    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
    filepath = uploads_dir / safe_name
    filepath.write_text(content, encoding="utf-8")
    Path(str(filepath) + ".txt").write_text(content, encoding="utf-8")

    file_info = {
        "filename": filename,
        "saved_as": safe_name,
        "folder": folder,
        "size": len(content.encode()),
        "uploaded_at": datetime.now().isoformat(),
        "text_preview": content[:200] + "..." if len(content) > 200 else content,
    }
    proj["files"].append(file_info)
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj, u)

    return jsonify({"ok": True, "filename": filename, "file_count": len(proj["files"])})


@app.route("/api/projects/<project_id>/upload", methods=["POST"])
@login_required
def api_project_upload(project_id):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404

    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Nom de fichier vide"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Format non supporté : {ext}"}), 400

    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
    filepath = uploads_dir / safe_name
    f.save(str(filepath))

    VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    is_video = ext in VIDEO_EXTS

    folder = request.form.get("folder", "").strip().strip("/")
    file_info = {
        "filename": f.filename,
        "saved_as": safe_name,
        "folder": folder,
        "size": os.path.getsize(str(filepath)),
        "uploaded_at": datetime.now().isoformat(),
        "status": "processing" if is_video else "ready",
        "text_preview": "",
    }

    proj["files"].append(file_info)
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj, u)

    if is_video:
        def process_video_bg(pid, sname, fpath, username):
            text = extract_text_from_file(fpath, username=username)
            txt_path = Path(str(fpath) + ".txt")
            txt_path.write_text(text, encoding="utf-8")
            p = get_project(pid, username)
            if p:
                for fi in p.get("files", []):
                    if fi["saved_as"] == sname:
                        fi["status"] = "ready"
                        fi["text_preview"] = text[:200] + "..." if len(text) > 200 else text
                        break
                save_project(pid, p, username)

        threading.Thread(target=process_video_bg, args=(project_id, safe_name, str(filepath), u), daemon=True).start()
        return jsonify({**file_info})
    else:
        text = extract_text_from_file(str(filepath))
        txt_path = Path(str(filepath) + ".txt")
        txt_path.write_text(text, encoding="utf-8")
        file_info["text_preview"] = text[:200] + "..." if len(text) > 200 else text
        for fi in proj["files"]:
            if fi["saved_as"] == safe_name:
                fi["text_preview"] = file_info["text_preview"]
                break
        save_project(project_id, proj, u)
        return jsonify({**file_info, "text": text})


@app.route("/api/projects/<project_id>/upload-url", methods=["GET"])
@login_required
def api_project_upload_url(project_id):
    u = get_current_user()
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    s3_bucket = os.environ.get("S3_VIDEO_BUCKET")
    if not s3_bucket:
        return jsonify({"error": "S3_VIDEO_BUCKET non configuré"}), 500
    filename = request.args.get("filename", "video.mp4")
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
    s3_key = f"uploads/{safe_name}"
    s3 = boto3.client("s3")
    try:
        s3.put_bucket_cors(Bucket=s3_bucket, CORSConfiguration={"CORSRules": [{
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["PUT"],
            "AllowedOrigins": ["*"],
            "ExposeHeaders": []
        }]})
    except Exception:
        pass
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": s3_bucket, "Key": s3_key, "ContentType": "video/mp4"},
        ExpiresIn=7200
    )
    return jsonify({"upload_url": upload_url, "s3_key": s3_key, "safe_name": safe_name, "filename": filename})


@app.route("/api/projects/<project_id>/upload-complete", methods=["POST"])
@login_required
def api_project_upload_complete(project_id):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    data = request.get_json(silent=True) or {}
    s3_key = data.get("s3_key", "")
    safe_name = data.get("safe_name", "")
    filename = data.get("filename", "")
    size = data.get("size", 0)
    s3_bucket = os.environ.get("S3_VIDEO_BUCKET")
    s3_uri = f"s3://{s3_bucket}/{s3_key}"

    filepath = uploads_dir / safe_name
    filepath.touch()

    folder = data.get("folder", "").strip().strip("/")
    file_info = {
        "filename": filename,
        "saved_as": safe_name,
        "folder": folder,
        "size": size,
        "uploaded_at": datetime.now().isoformat(),
        "status": "processing",
        "text_preview": "",
    }
    proj["files"].append(file_info)
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj, u)

    def process_video_bg(pid, sname, fpath, uri, key, username):
        text = call_pegasus_video(fpath, existing_s3_uri=uri, existing_s3_key=key)
        txt_path = Path(str(fpath) + ".txt")
        txt_path.write_text(text, encoding="utf-8")
        p = get_project(pid, username)
        if p:
            for fi in p.get("files", []):
                if fi["saved_as"] == sname:
                    fi["status"] = "ready"
                    fi["text_preview"] = text[:200] + "..." if len(text) > 200 else text
                    break
            save_project(pid, p, username)

    threading.Thread(target=process_video_bg, args=(project_id, safe_name, str(filepath), s3_uri, s3_key, u), daemon=True).start()
    return jsonify({**file_info})


@app.route("/api/projects/<project_id>/files/<saved_as>/reextract", methods=["POST"])
@login_required
def api_project_reextract_file(project_id, saved_as):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    file_info = next((f for f in proj.get("files", []) if f["saved_as"] == saved_as), None)
    if not file_info:
        return jsonify({"error": "Fichier introuvable dans le projet"}), 404
    filepath = uploads_dir / saved_as
    if not filepath.exists():
        return jsonify({"error": "Fichier source introuvable sur le disque"}), 404

    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    ext = Path(saved_as).suffix.lower()
    if ext in video_exts:
        file_info["status"] = "processing"
        file_info["text_preview"] = ""
        save_project(project_id, proj, u)
        def process_video_bg(pid, sname, fpath, username):
            text = extract_text_from_file(fpath, username=username)
            txt_path = Path(str(fpath) + ".txt")
            txt_path.write_text(text, encoding="utf-8")
            p = get_project(pid, username)
            if p:
                for fi in p.get("files", []):
                    if fi["saved_as"] == sname:
                        fi["status"] = "ready"
                        fi["text_preview"] = text[:200] + "..." if len(text) > 200 else text
                        break
                save_project(pid, p, username)
        threading.Thread(target=process_video_bg, args=(project_id, saved_as, str(filepath), u), daemon=True).start()
        return jsonify({"ok": True, "status": "processing"})

    text = extract_text_from_file(str(filepath), username=u)
    txt_path = uploads_dir / (saved_as + ".txt")
    txt_path.write_text(text, encoding="utf-8")
    file_info["text_preview"] = text[:200] + "..." if len(text) > 200 else text
    file_info["status"] = "ready"
    save_project(project_id, proj, u)
    return jsonify({"ok": True, "preview": file_info["text_preview"]})


@app.route("/api/projects/<project_id>/files/<saved_as>", methods=["DELETE"])
@login_required
def api_project_delete_file(project_id, saved_as):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404

    proj["files"] = [f for f in proj["files"] if f["saved_as"] != saved_as]
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj, u)

    filepath = uploads_dir / saved_as
    if filepath.exists():
        filepath.unlink()
    txt_path = uploads_dir / (saved_as + ".txt")
    if txt_path.exists():
        txt_path.unlink()

    return jsonify({"ok": True})


@app.route("/api/projects/<project_id>/files/<saved_as>/content", methods=["GET"])
@login_required
def api_project_file_content(project_id, saved_as):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    file_info = next((f for f in proj.get("files", []) if f["saved_as"] == saved_as), None)
    if not file_info:
        return jsonify({"error": "Fichier introuvable"}), 404
    # Try .txt first, then original file
    txt_path = uploads_dir / (saved_as + ".txt")
    if txt_path.exists():
        content = txt_path.read_text(encoding="utf-8", errors="replace")
    else:
        orig = uploads_dir / saved_as
        if orig.exists():
            content = orig.read_text(encoding="utf-8", errors="replace")
        else:
            return jsonify({"error": "Contenu non disponible"}), 404
    return jsonify({"ok": True, "content": content, "filename": file_info["filename"]})


@app.route("/api/projects/<project_id>/files/<saved_as>/content", methods=["PUT"])
@login_required
def api_project_file_update_content(project_id, saved_as):
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    file_info = next((f for f in proj.get("files", []) if f["saved_as"] == saved_as), None)
    if not file_info:
        return jsonify({"error": "Fichier introuvable"}), 404
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    # Write to both original and .txt
    orig = uploads_dir / saved_as
    orig.write_text(content, encoding="utf-8")
    txt_path = uploads_dir / (saved_as + ".txt")
    txt_path.write_text(content, encoding="utf-8")
    # Update metadata
    file_info["size"] = len(content.encode())
    file_info["text_preview"] = content[:200] + "..." if len(content) > 200 else content
    file_info["updated_at"] = datetime.now().isoformat()
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj, u)
    return jsonify({"ok": True})


# ── Journal Quotidien ──

def get_today_conversations_text(project_id, username):
    today = date.today().isoformat()
    convs = load_conversations(username)
    formatted_parts = []
    for conv_id, conv in convs.items():
        if conv.get("project_id") != project_id:
            continue
        if not conv.get("updated_at", "").startswith(today):
            continue
        messages = conv.get("messages", [])
        if not messages:
            continue
        part = f"### {conv.get('title', 'Conversation')}\n"
        for msg in messages[-20:]:
            role = "Utilisateur" if msg["role"] == "user" else "Claude"
            content = msg["content"]
            if len(content) > 800:
                content = content[:800] + "...[tronqué]"
            part += f"\n**{role}** : {content}\n"
        formatted_parts.append(part)
    return "\n---\n".join(formatted_parts)


@app.route("/api/journal/generate", methods=["POST"])
@login_required
def api_generate_journals():
    u = get_current_user()
    uploads_dir = get_uploads_dir(u)
    today = date.today().isoformat()
    projects = load_projects(u)
    results = []

    for project_id, proj in projects.items():
        project_name = proj.get("name", "Projet")
        journal_filename = f"Journal_{project_name.replace(' ', '_')}_{today}.md"

        if any(f.get("filename") == journal_filename for f in proj.get("files", [])):
            results.append({"project": project_name, "status": "skipped", "reason": "déjà existant"})
            continue

        conversations_text = get_today_conversations_text(project_id, u)
        if not conversations_text.strip():
            results.append({"project": project_name, "status": "skipped", "reason": "aucune activité"})
            continue

        if len(conversations_text) > 15000:
            conversations_text = conversations_text[:15000] + "\n...[Conversations tronquées]"

        prompt = f"""Tu es l'assistant de synthèse de ClaudePrivé.

Voici les conversations du jour pour le projet "{project_name}".

Génère un journal quotidien concis au format markdown :

# Journal {project_name} - {today}

## Actions réalisées
## Informations clés
## Prochaines étapes
## Points d'attention

Règles : sois factuel et concis. Maximum 30 lignes.

Conversations du jour :
{conversations_text}"""

        try:
            result, usage = call_claude(
                [{"role": "user", "content": prompt}],
                "Tu es un assistant de synthèse. Réponds uniquement en markdown.",
                username=u,
            )
            journal_content = "".join(
                block["text"] for block in result.get("content", []) if block.get("type") == "text"
            )
            safe_name = f"{uuid.uuid4().hex[:8]}_{journal_filename}"
            filepath = uploads_dir / safe_name
            filepath.write_text(journal_content, encoding="utf-8")
            Path(str(filepath) + ".txt").write_text(journal_content, encoding="utf-8")

            file_info = {
                "filename": journal_filename,
                "saved_as": safe_name,
                "size": len(journal_content.encode()),
                "uploaded_at": datetime.now().isoformat(),
                "text_preview": journal_content[:200] + "..." if len(journal_content) > 200 else journal_content,
            }
            proj = get_project(project_id, u)
            proj["files"].append(file_info)
            proj["updated_at"] = datetime.now().isoformat()
            save_project(project_id, proj, u)
            results.append({"project": project_name, "status": "generated", "filename": journal_filename, "usage": usage})

        except Exception as e:
            results.append({"project": project_name, "status": "error", "reason": str(e)})

    return jsonify({"date": today, "results": results})


# ── Projets ──

@app.route("/api/projects", methods=["GET"])
@login_required
def api_list_projects():
    u = get_current_user()
    projects = load_projects(u)
    result = [{"id": pid, **proj} for pid, proj in sorted(projects.items(), key=lambda x: x[1].get("created_at", ""), reverse=True)]
    return jsonify(result)


@app.route("/api/projects", methods=["POST"])
@login_required
def api_create_project():
    u = get_current_user()
    data = request.get_json(silent=True) or {}
    project_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    project = {
        "name": data.get("name", "Nouveau projet"),
        "description": data.get("description", ""),
        "default_prompt_id": data.get("default_prompt_id"),
        "files": [],
        "created_at": now,
        "updated_at": now,
    }
    save_project(project_id, project, u)
    return jsonify({"id": project_id, **project}), 201


@app.route("/api/projects/<project_id>", methods=["GET"])
@login_required
def api_get_project_route(project_id):
    u = get_current_user()
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    return jsonify({"id": project_id, **proj})


@app.route("/api/projects/<project_id>", methods=["PUT"])
@login_required
def api_update_project(project_id):
    u = get_current_user()
    proj = get_project(project_id, u)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    data = request.get_json(silent=True) or {}
    if "name" in data:
        proj["name"] = data["name"]
    if "description" in data:
        proj["description"] = data["description"]
    if "default_prompt_id" in data:
        proj["default_prompt_id"] = data["default_prompt_id"]
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj, u)
    return jsonify({"id": project_id, **proj})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
@login_required
def api_delete_project_route(project_id):
    u = get_current_user()
    convs = load_conversations(u)
    for cid, conv in convs.items():
        if conv.get("project_id") == project_id:
            conv["project_id"] = None
    save_conversations(convs, u)
    delete_project(project_id, u)
    return jsonify({"ok": True})


# ── Coûts ──

@app.route("/api/costs", methods=["GET"])
@login_required
def api_costs():
    u = get_current_user()
    costs = load_costs(u)
    today = date.today().isoformat()
    month = today[:7]
    daily_today = costs["daily"].get(today, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0})
    monthly = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
    for day_key, day_val in costs["daily"].items():
        if day_key.startswith(month):
            monthly["input_tokens"] += day_val["input_tokens"]
            monthly["output_tokens"] += day_val["output_tokens"]
            monthly["cost_usd"] = round(monthly["cost_usd"] + day_val["cost_usd"], 6)
    return jsonify({"today": daily_today, "month": monthly, "total": costs["total"]})


# ── Prompts ──

@app.route("/api/prompts", methods=["GET"])
@login_required
def api_get_prompts():
    u = get_current_user()
    return jsonify(load_prompts(u))


@app.route("/api/prompts", methods=["POST"])
@login_required
def api_save_prompt():
    u = get_current_user()
    data = request.get_json(silent=True) or {}
    prompts = load_prompts(u)
    prompt_id = data.get("id") or str(uuid.uuid4())[:8]
    name = data.get("name", "Sans nom")
    prompt_text = data.get("prompt", "")
    found = False
    for p in prompts:
        if p["id"] == prompt_id:
            p["name"] = name
            p["prompt"] = prompt_text
            found = True
            break
    if not found:
        prompts.append({"id": prompt_id, "name": name, "prompt": prompt_text})
    save_prompts(prompts, u)
    return jsonify({"ok": True, "id": prompt_id})


@app.route("/api/prompts/<prompt_id>", methods=["DELETE"])
@login_required
def api_delete_prompt(prompt_id):
    u = get_current_user()
    prompts = load_prompts(u)
    prompts = [p for p in prompts if p["id"] != prompt_id]
    save_prompts(prompts, u)
    return jsonify({"ok": True})


# ── Réglages ──

@app.route("/api/settings", methods=["GET"])
@login_required
def api_get_settings():
    u = get_current_user()
    return jsonify(load_settings(u))


@app.route("/api/settings", methods=["POST"])
@login_required
def api_save_settings():
    u = get_current_user()
    data = request.get_json(silent=True) or {}
    settings = load_settings(u)
    if "model" in data:
        settings["model"] = data["model"]
    if "region" in data:
        settings["region"] = data["region"]
    if "active_prompt" in data:
        settings["active_prompt"] = data["active_prompt"]
    save_settings(settings, u)
    return jsonify(settings)


# ─────────────────────────────────────────────
# Messagerie entre utilisateurs
# ─────────────────────────────────────────────

def _msg_file(u1, u2):
    """Fichier JSON pour la conversation entre deux utilisateurs (noms triés)."""
    pair = "__".join(sorted([u1, u2]))
    return MESSAGES_DIR / f"{pair}.json"


def _load_thread(u1, u2):
    f = _msg_file(u1, u2)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return []


def _save_thread(u1, u2, msgs):
    _msg_file(u1, u2).write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")


@app.route("/api/messages", methods=["GET"])
@login_required
def api_messages_inbox():
    """Liste des threads avec dernier message et nb non lus."""
    u = get_current_user()
    users = load_users()
    threads = []
    for other in users:
        if other == u:
            continue
        msgs = _load_thread(u, other)
        if not msgs:
            continue
        last = msgs[-1]
        unread = sum(1 for m in msgs if m["to"] == u and not m.get("read", False))
        threads.append({
            "with": other,
            "last_text": last["text"][:80],
            "last_at": last["at"],
            "unread": unread,
        })
    threads.sort(key=lambda t: t["last_at"], reverse=True)
    return jsonify(threads)


@app.route("/api/messages/<other>", methods=["GET"])
@login_required
def api_messages_thread(other):
    """Historique complet avec un utilisateur."""
    u = get_current_user()
    users = load_users()
    if other not in users:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    msgs = _load_thread(u, other)
    return jsonify(msgs)


@app.route("/api/messages/<other>", methods=["POST"])
@login_required
def api_messages_send(other):
    """Envoyer un message à un utilisateur."""
    u = get_current_user()
    users = load_users()
    if other not in users:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Message vide"}), 400
    msgs = _load_thread(u, other)
    msg = {
        "id": str(uuid.uuid4()),
        "from": u,
        "to": other,
        "text": text,
        "at": datetime.now().isoformat(),
        "read": False,
    }
    msgs.append(msg)
    _save_thread(u, other, msgs)
    return jsonify(msg), 201


@app.route("/api/messages/<other>/read", methods=["POST"])
@login_required
def api_messages_mark_read(other):
    """Marquer tous les messages d'un thread comme lus."""
    u = get_current_user()
    msgs = _load_thread(u, other)
    for m in msgs:
        if m["to"] == u:
            m["read"] = True
    _save_thread(u, other, msgs)
    return jsonify({"ok": True})


@app.route("/api/messages/unread-count", methods=["GET"])
@login_required
def api_messages_unread_count():
    """Nombre total de messages non lus (pour le badge)."""
    u = get_current_user()
    users = load_users()
    total = 0
    for other in users:
        if other == u:
            continue
        msgs = _load_thread(u, other)
        total += sum(1 for m in msgs if m["to"] == u and not m.get("read", False))
    return jsonify({"unread": total})


# ═════════════════════════════════════════════

if __name__ == "__main__":
    print(app.url_map)
    app.run(debug=True, port=8009)
else:
    print("Chargement de l'application ClaudePrivé...")
    print(app.url_map)
