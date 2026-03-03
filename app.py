"""
ClaudePrivé — Chat privé avec AWS Bedrock
Backend Flask principal
"""

import os
import json
import uuid
import time
from datetime import datetime, date
from pathlib import Path

import boto3
from flask import Flask, render_template, request, jsonify
# import journal  <-- Désactivé temporairement pour debug 502

# Gestion d'erreur si APScheduler n'est pas installé
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False
    print("[WARNING] APScheduler non trouvé. Le journal automatique ne fonctionnera pas.")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 Mo max upload pour vidéo

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
UPLOADS_DIR = DATA_DIR / "uploads"

# Créer les répertoires au démarrage
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Client Bedrock
# ─────────────────────────────────────────────

def get_bedrock_client(model_id=None):
    """
    Retourne un client Bedrock configuré pour la bonne région.
    Si le modèle est explicite sur sa région (us. ou eu.), on force cette région.
    Pour les modèles Cross-Region EU (eu.anthropic...), on utilise la région configurée (ex: Paris).
    """
    settings_region = load_settings().get("region", "eu-west-3")
    
    # Détection automatique de la région cible
    target_region = settings_region

    if model_id:
        if model_id.startswith("us."):
            target_region = "us-east-1"
        # Pour les modèles eu.*, on laisse la région par défaut (eu-west-3),
        # car les profils d'inférence EU sont accessibles depuis Paris.

    return boto3.client("bedrock-runtime", region_name=target_region)

# Tarifs Bedrock par million de tokens (USD)
# Basé sur les modèles 2026 disponibles à Paris (eu-west-3)
PRICING = {
    # ─── NEXT GEN (2026) ───
    
    # Claude Opus 4.6 (Le plus puissant)
    "eu.anthropic.claude-opus-4-6-v1:0": {"input": 15.0, "output": 75.0},
    "anthropic.claude-opus-4-6-v1:0":    {"input": 15.0, "output": 75.0},

    # Claude Sonnet 4.5
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 3.0, "output": 15.0},
    "anthropic.claude-sonnet-4-5-20250929-v1:0":    {"input": 3.0, "output": 15.0},

    # Claude Haiku 4.5
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.25, "output": 1.25},
    "anthropic.claude-haiku-4-5-20251001-v1:0":    {"input": 0.25, "output": 1.25},

    # ─── LEGACY / FALLBACK ───
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": {"input": 3.0, "output": 15.0},
}

# Liste des modèles valides (pour auto-correction)
VALID_MODELS = list(PRICING.keys())

def call_claude(messages, system_prompt, model=None):
    """Appel Claude via AWS Bedrock."""
    if model is None:
        # Par défaut : Sonnet 4.5 (EU)
        model = load_settings().get("model", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0")
    
    # Auto-correction pour les anciens IDs si nécessaire (déjà fait au chargement)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": messages,
    })

    # Obtenir le client adapté à la région du modèle
    client = get_bedrock_client(model)
    resp = client.invoke_model(modelId=model, body=body)
    result = json.loads(resp["body"].read())

    usage = result.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    # Calculer le coût
    prices = PRICING.get(model)
    if not prices:
        # Fallback prix moyen (Sonnet)
        prices = {"input": 3.0, "output": 15.0}
        
    cost_usd = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000

    # Mettre à jour le compteur
    update_costs(input_tokens, output_tokens, cost_usd)

    return result, {"input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": round(cost_usd, 6)}


# ─────────────────────────────────────────────
# Gestion des conversations (JSON)
# ─────────────────────────────────────────────

CONVERSATIONS_FILE = DATA_DIR / "conversations.json"

def load_conversations():
    if CONVERSATIONS_FILE.exists():
        return json.loads(CONVERSATIONS_FILE.read_text(encoding="utf-8"))
    return {}

def save_conversations(convs):
    CONVERSATIONS_FILE.write_text(json.dumps(convs, ensure_ascii=False, indent=2), encoding="utf-8")

def get_conversation(conv_id):
    convs = load_conversations()
    return convs.get(conv_id)

def save_conversation(conv_id, conv):
    convs = load_conversations()
    convs[conv_id] = conv
    save_conversations(convs)

def delete_conversation(conv_id):
    convs = load_conversations()
    convs.pop(conv_id, None)
    save_conversations(convs)


# ─────────────────────────────────────────────
# Gestion des projets
# ─────────────────────────────────────────────

PROJECTS_FILE = DATA_DIR / "projects.json"

def load_projects():
    if PROJECTS_FILE.exists():
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return {}

def save_projects(projects):
    PROJECTS_FILE.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")

def get_project(project_id):
    return load_projects().get(project_id)

def save_project(project_id, project):
    projects = load_projects()
    projects[project_id] = project
    save_projects(projects)

def delete_project(project_id):
    projects = load_projects()
    projects.pop(project_id, None)
    save_projects(projects)


# ─────────────────────────────────────────────
# Compteur de coûts
# ─────────────────────────────────────────────

COSTS_FILE = DATA_DIR / "costs.json"

def load_costs():
    if COSTS_FILE.exists():
        return json.loads(COSTS_FILE.read_text(encoding="utf-8"))
    return {"daily": {}, "total": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}}

def save_costs(costs):
    COSTS_FILE.write_text(json.dumps(costs, ensure_ascii=False, indent=2), encoding="utf-8")

def update_costs(input_tokens, output_tokens, cost_usd):
    costs = load_costs()
    today = date.today().isoformat()

    if today not in costs["daily"]:
        costs["daily"][today] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}

    costs["daily"][today]["input_tokens"] += input_tokens
    costs["daily"][today]["output_tokens"] += output_tokens
    costs["daily"][today]["cost_usd"] = round(costs["daily"][today]["cost_usd"] + cost_usd, 6)

    costs["total"]["input_tokens"] += input_tokens
    costs["total"]["output_tokens"] += output_tokens
    costs["total"]["cost_usd"] = round(costs["total"]["cost_usd"] + cost_usd, 6)

    save_costs(costs)


# ─────────────────────────────────────────────
# Prompts système prédéfinis
# ─────────────────────────────────────────────

PROMPTS_FILE = DATA_DIR / "prompts.json"

# Prompt Socle (Sécurité & Confidentialité) - Toujours actif
GLOBAL_SYSTEM_PROMPT = """
Tu es une instance privée et sécurisée de Claude, opérée via AWS Bedrock en Europe.
IMPORTANT : Tes réponses sont strictement confidentielles.
- Tu es hébergé sur une infrastructure souveraine européenne.
- Tes données NE SONT PAS utilisées pour l'entraînement des modèles.
- Tu NE DOIS PAS dire que tu es hébergé aux USA ou sur l'interface publique d'Anthropic.
- Tu dois agir comme un assistant professionnel de confiance.
- Tu t'exprimes en français par défaut.
"""

DEFAULT_PROMPTS = [
    {
        "id": "general",
        "name": "Conseil général",
        "prompt": "Tu es un assistant business polyvalent. Tu aides avec des conseils professionnels clairs, structurés et actionnables."
    },
    {
        "id": "juridique",
        "name": "Analyse juridique",
        "prompt": "Tu es un assistant spécialisé en analyse juridique. Tu aides à analyser des contrats, clauses et documents légaux. Tu identifies les risques, les points d'attention et proposes des recommandations. Tu précises toujours que tu ne remplaces pas un avocat. Tu t'exprimes en français."
    },
    {
        "id": "commercial",
        "name": "Stratégie commerciale",
        "prompt": "Tu es un consultant en stratégie commerciale. Tu aides à définir des offres, du pricing, du positionnement marché et des stratégies de vente. Tu t'exprimes en français."
    },
    {
        "id": "redaction",
        "name": "Rédaction pro",
        "prompt": "Tu es un assistant de rédaction professionnelle. Tu aides à rédiger des emails, propositions commerciales, présentations et documents professionnels avec un ton adapté au contexte. Tu t'exprimes en français."
    },
    {
        "id": "domotique",
        "name": "Expert Domotique",
        "prompt": "Tu es un expert en domotique et en Home Assistant. Tu aides à concevoir des automatisations, à configurer des fichiers YAML, à choisir des capteurs (Zigbee, Z-Wave, WiFi) et à optimiser la consommation énergétique. Tu connais les protocoles MQTT, les intégrations ESPHome et Node-RED. Tu t'exprimes en français avec des exemples de code clairs."
    },
]

def load_prompts():
    if PROMPTS_FILE.exists():
        return json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
    # Initialiser avec les prompts par défaut
    save_prompts(DEFAULT_PROMPTS)
    return DEFAULT_PROMPTS

def save_prompts(prompts):
    PROMPTS_FILE.write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────

SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "model": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "region": "eu-west-3",
    "active_prompt": "general",
}

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            # Auto-correction : Si le modèle n'est pas valide/actif, on force le défaut
            if settings.get("model") not in VALID_MODELS:
                print(f"[AUTO-FIX] Modèle invalide/legacy détecté : {settings.get('model')}. Remplacement par défaut.")
                settings["model"] = DEFAULT_SETTINGS["model"]
                save_settings(settings)
            return settings
        except Exception:
            pass # Fichier corrompu ou illisible
        
    save_settings(DEFAULT_SETTINGS)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
# Extraction de texte (fichiers uploadés)
# ─────────────────────────────────────────────

def call_pegasus_video(filepath):
    """Appelle Twelve Labs Pegasus via S3 pour transcrire une vidéo."""
    s3_bucket = os.environ.get("S3_VIDEO_BUCKET")
    if not s3_bucket:
        return "[INFO] Vidéo stockée. Pour l'analyse IA (transcription), veuillez configurer la variable S3_VIDEO_BUCKET dans docker-compose.yml (voir GUIDE_S3.md)."

    try:
        filename = Path(filepath).name
        s3_key = f"uploads/{uuid.uuid4().hex[:8]}/{filename}"
        s3_uri = f"s3://{s3_bucket}/{s3_key}"
        
        # 1. Upload vers S3
        s3 = boto3.client("s3")
        s3.upload_file(filepath, s3_bucket, s3_key)
        
        # 2. Appel Pegasus (Twelve Labs) via Bedrock
        # Note: L'ID exact dépend de l'abonnement marketplace, on tente le générique ou on laisse l'utilisateur configurer
        model_id = "twelvelabs.pegasus-1-2-v1:0" # ID standard Marketplace
        
        prompt = "Génère une transcription détaillée (diarisation) et un résumé exécutif de cette réunion."
        
        body = json.dumps({
            "prompt": prompt,
            "videoS3Uri": s3_uri
        })
        
        bedrock = get_bedrock_client("us.anthropic.claude") # On utilise le client US par défaut pour Pegasus qui est souvent US
        response = bedrock.invoke_model(modelId=model_id, body=body)
        
        result = json.loads(response["body"].read())
        # Le format de réponse dépend de Pegasus, on extrait le texte générique
        return result.get("generated_text", f"[Réponse Pegasus brute] {json.dumps(result)}")

    except Exception as e:
        return f"[Erreur Analyse Vidéo : {str(e)}]"

def extract_text_from_file(filepath):
    """Extrait le texte d'un fichier uploadé."""
    ext = Path(filepath).suffix.lower()
    
    if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        return call_pegasus_video(filepath)

    if ext == ".pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip()
        except Exception as e:
            return f"[Erreur extraction PDF : {e}]"

    elif ext == ".docx":
        try:
            from docx import Document
            doc = Document(filepath)
            text = "\n".join(para.text for para in doc.paragraphs)
            return text.strip()
        except Exception as e:
            return f"[Erreur extraction DOCX : {e}]"

    elif ext in (".txt", ".md", ".csv", ".json", ".xml", ".html", ".py", ".js", ".yml", ".yaml"):
        try:
            return Path(filepath).read_text(encoding="utf-8").strip()
        except Exception as e:
            return f"[Erreur lecture fichier : {e}]"

    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return f"[Image : {Path(filepath).name}]"

    return f"[Format non supporté : {ext}]"


# ═════════════════════════════════════════════
# ROUTES
# ═════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ── Recherche ──

@app.route("/api/search", methods=["GET"])
def api_search():
    query = request.args.get("q", "").lower().strip()
    if not query or len(query) < 3:
        return jsonify([])

    convs = load_conversations()
    results = []
    
    for conv_id, conv in convs.items():
        title = conv.get("title", "Sans titre")
        found = False
        
        # Chercher dans le titre
        if query in title.lower():
            results.append({
                "conversation_id": conv_id,
                "title": title,
                "snippet": "[Titre correspondant]",
                "date": conv.get("updated_at")
            })
            continue

        # Chercher dans les messages
        for msg in conv.get("messages", []):
            content = msg.get("content", "")
            if query in content.lower():
                # Extraire un extrait
                idx = content.lower().find(query)
                start = max(0, idx - 60)
                end = min(len(content), idx + 140)
                snippet = "..." + content[start:end].replace("\n", " ") + "..."
                
                results.append({
                    "conversation_id": conv_id,
                    "title": title,
                    "snippet": snippet,
                    "date": conv.get("updated_at")
                })
                found = True
                break # Un seul résultat par conversation pour ne pas spammer
        
        if len(results) >= 20: # Limite de résultats
            break
            
    return jsonify(results)


# ── Conversations ──

@app.route("/api/conversations", methods=["GET"])
def api_list_conversations():
    convs = load_conversations()
    project_id = request.args.get("project_id")
    result = []
    for cid, conv in sorted(convs.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True):
        # Filtrer par projet si demandé
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
def api_create_conversation():
    data = request.get_json(silent=True) or {}
    conv_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conv = {
        "title": data.get("title", "Nouvelle conversation"),
        "messages": [],
        "created_at": now,
        "updated_at": now,
        "prompt_id": data.get("prompt_id", load_settings().get("active_prompt", "general")),
        "project_id": data.get("project_id"),
    }
    save_conversation(conv_id, conv)
    return jsonify({"id": conv_id, **conv}), 201


@app.route("/api/conversations/<conv_id>", methods=["GET"])
def api_get_conversation(conv_id):
    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404
    return jsonify({"id": conv_id, **conv})


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def api_delete_conversation(conv_id):
    delete_conversation(conv_id)
    return jsonify({"ok": True})


@app.route("/api/conversations/<conv_id>/title", methods=["PUT"])
def api_rename_conversation(conv_id):
    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404
    data = request.get_json(silent=True) or {}
    conv["title"] = data.get("title", conv["title"])
    conv["updated_at"] = datetime.now().isoformat()
    save_conversation(conv_id, conv)
    return jsonify({"ok": True})


@app.route("/api/conversations/<conv_id>/project", methods=["PUT"])
def api_move_conversation(conv_id):
    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404
    data = request.get_json(silent=True) or {}
    
    # project_id peut être None (pour sortir d'un projet)
    project_id = data.get("project_id")
    
    if project_id and not get_project(project_id):
        return jsonify({"error": "Projet introuvable"}), 404

    conv["project_id"] = project_id
    conv["updated_at"] = datetime.now().isoformat()
    save_conversation(conv_id, conv)
    return jsonify({"ok": True})


# ── Chat ──

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    conv_id = data.get("conversation_id")
    user_message = data.get("message", "").strip()
    file_content = data.get("file_content")  # texte extrait d'un fichier uploadé

    if not conv_id or not user_message:
        return jsonify({"error": "conversation_id et message requis"}), 400

    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation introuvable"}), 404

    # Construire le message utilisateur
    content = user_message
    if file_content:
        content = f"{user_message}\n\n--- Contenu du fichier joint ---\n{file_content}"

    # Ajouter le message à l'historique
    conv["messages"].append({"role": "user", "content": content})

    # Récupérer le prompt système actif
    prompt_id = conv.get("prompt_id", "general")
    prompts = load_prompts()
    user_system_prompt = "Tu es un assistant professionnel."
    for p in prompts:
        if p["id"] == prompt_id:
            user_system_prompt = p["prompt"]
            break
            
    # Combiner avec le socle global
    final_system_prompt = f"{GLOBAL_SYSTEM_PROMPT}\n\n--- Instructions Spécifiques ---\n{user_system_prompt}"

    # Injection du contexte du projet (Fichiers)
    project_id = conv.get("project_id")
    if project_id:
        proj = get_project(project_id)
        if proj and proj.get("files"):
            project_context = "\n\n--- DOCUMENTS DU PROJET (CONTEXTE RAG) ---\n"
            has_docs = False
            for file in proj["files"]:
                saved_as = file.get("saved_as")
                if saved_as:
                    # Chercher le fichier .txt associé
                    txt_path = UPLOADS_DIR / (saved_as + ".txt")
                    if txt_path.exists():
                        try:
                            content = txt_path.read_text(encoding="utf-8")
                            # Log pour debug
                            print(f"[DEBUG] Injection du document {file['filename']} ({len(content)} chars)")
                            
                            # Limiter la taille pour ne pas exploser le contexte (ex: 50k caractères par fichier)
                            if len(content) > 50000:
                                content = content[:50000] + "\n...[Tronqué]..."
                            project_context += f"\n[Document: {file['filename']}]\n{content}\n"
                            has_docs = True
                        except Exception as e:
                            print(f"[ERREUR] Erreur lecture contexte {saved_as}: {e}")
                    else:
                        print(f"[DEBUG] Fichier texte manquant pour {file['filename']} ({saved_as}.txt)")
            
            if has_docs:
                final_system_prompt += project_context
                final_system_prompt += "\n\nINSTRUCTIONS: Utilise EXCLUSIVEMENT les documents ci-dessus pour répondre aux questions sur le projet. Si la réponse n'y est pas, dis-le clairement."
            else:
                print("[DEBUG] Aucun document texte trouvé pour ce projet.")

    # Log du prompt système final (pour debug serveur)
    print(f"[DEBUG] System Prompt Size: {len(final_system_prompt)} chars")

    # Appel Bedrock
    try:
        result, usage = call_claude(conv["messages"], final_system_prompt)
    except Exception as e:
        # Retirer le message user si l'appel échoue
        conv["messages"].pop()
        save_conversation(conv_id, conv)
        return jsonify({"error": f"Erreur Bedrock : {str(e)}"}), 500

    # Extraire la réponse
    assistant_text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            assistant_text += block["text"]

    # Ajouter la réponse à l'historique
    conv["messages"].append({"role": "assistant", "content": assistant_text})
    conv["updated_at"] = datetime.now().isoformat()

    # Auto-titre sur le premier message
    if len(conv["messages"]) == 2 and conv["title"] == "Nouvelle conversation":
        conv["title"] = user_message[:50] + ("..." if len(user_message) > 50 else "")

    save_conversation(conv_id, conv)

    return jsonify({
        "response": assistant_text,
        "usage": usage,
        "conversation_id": conv_id,
    })


# ── Upload ──

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".xml", ".html",
                      ".py", ".js", ".yml", ".yaml", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                      ".mp4", ".mov", ".avi", ".mkv", ".webm"}

@app.route("/api/debug/context/<project_id>", methods=["GET"])
def api_debug_context(project_id):
    """Affiche le contexte qui serait envoyé à Claude pour ce projet."""
    proj = get_project(project_id)
    if not proj:
        return "Projet introuvable"
        
    context = "--- SIMULATION CONTEXTE ---\n"
    if proj.get("files"):
        for file in proj["files"]:
            saved_as = file.get("saved_as")
            if saved_as:
                txt_path = UPLOADS_DIR / (saved_as + ".txt")
                if txt_path.exists():
                    content = txt_path.read_text(encoding="utf-8")
                    context += f"\n[Document: {file['filename']}] ({len(content)} chars)\n{content[:500]}...\n"
                else:
                    context += f"\n[Document: {file['filename']}] : PAS DE FICHIER TEXTE (.txt manquant)\n"
    else:
        context += "Aucun fichier dans ce projet."
        
    return f"<pre>{context}</pre>"

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Nom de fichier vide"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Format non supporté : {ext}"}), 400

    # Sauvegarder le fichier
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
    filepath = UPLOADS_DIR / safe_name
    f.save(str(filepath))

    text = extract_text_from_file(str(filepath))
    
    # Sauvegarder le texte complet pour le RAG / Contexte
    txt_path = filepath.with_suffix(filepath.suffix + ".txt")
    txt_path.write_text(text, encoding="utf-8")

    file_info = {
        "filename": f.filename,
        "saved_as": safe_name,
        "size": os.path.getsize(str(filepath)),
        "uploaded_at": datetime.now().isoformat(),
        "text_preview": text[:200] + "..." if len(text) > 200 else text,
    }

    return jsonify(file_info)

# Route spécifique pour lier un fichier uploadé à un projet (si appelé depuis api_project_upload)
@app.route("/api/projects/<project_id>/upload", methods=["POST"])
def api_project_upload(project_id):
    proj = get_project(project_id)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404

    # On réutilise la logique d'upload standard mais on lie au projet
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400
        
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Nom de fichier vide"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Format non supporté : {ext}"}), 400

    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
    filepath = UPLOADS_DIR / safe_name
    f.save(str(filepath))

    text = extract_text_from_file(str(filepath))
    
    # Sauvegarder le texte complet pour le RAG / Contexte
    txt_path = filepath.with_suffix(filepath.suffix + ".txt")
    txt_path.write_text(text, encoding="utf-8")

    file_info = {
        "filename": f.filename,
        "saved_as": safe_name,
        "size": os.path.getsize(str(filepath)),
        "uploaded_at": datetime.now().isoformat(),
        "text_preview": text[:200] + "..." if len(text) > 200 else text,
    }

    proj["files"].append(file_info)
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj)

    return jsonify({**file_info, "text": text})


@app.route("/api/projects/<project_id>/files/<saved_as>", methods=["DELETE"])
def api_project_delete_file(project_id, saved_as):
    proj = get_project(project_id)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404

    proj["files"] = [f for f in proj["files"] if f["saved_as"] != saved_as]
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj)

    # Supprimer le fichier physique et son .txt
    filepath = UPLOADS_DIR / saved_as
    if filepath.exists():
        filepath.unlink()
    
    txt_path = UPLOADS_DIR / (saved_as + ".txt")
    if txt_path.exists():
        txt_path.unlink()

    return jsonify({"ok": True})


# @app.route("/api/projects/<project_id>/journal", methods=["POST"])
# def api_generate_journal_manual(project_id):
#     """Génère manuellement le journal du jour pour un projet."""
#     context = {
#         'get_project': get_project,
#         'load_conversations': load_conversations,
#         'call_claude': call_claude,
#         'save_project': save_project,
#         'UPLOADS_DIR': UPLOADS_DIR,
#         'load_projects': load_projects
#     }
    
#     result = journal.generate_journal(project_id, context)
    
#     if result:
#         return jsonify(result)
#     else:
#         return jsonify({"message": "Aucun journal généré (pas d'activité ou déjà existant)"}), 200


# ── Réglages ──

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(load_settings())


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.get_json(silent=True) or {}
    settings = load_settings()
    if "model" in data:
        settings["model"] = data["model"]
    if "region" in data:
        settings["region"] = data["region"]
    if "active_prompt" in data:
        settings["active_prompt"] = data["active_prompt"]
    save_settings(settings)
    return jsonify(settings)


# ═════════════════════════════════════════════

def start_scheduler():
    # Désactivé temporairement pour éviter le crash 502
    return
    
    # if not HAS_SCHEDULER:
    #     return

    # try:
    #     scheduler = BackgroundScheduler()
        
    #     context = {
    #         'get_project': get_project,
    #         'load_conversations': load_conversations,
    #         'call_claude': call_claude,
    #         'save_project': save_project,
    #         'UPLOADS_DIR': UPLOADS_DIR,
    #         'load_projects': load_projects
    #     }
        
    #     # Job quotidien à 23h00
    #     scheduler.add_job(func=journal.run_daily_journals, trigger="cron", hour=23, minute=0, args=[context])
    #     scheduler.start()
    #     print("[INFO] Scheduler démarré pour le journal quotidien.")
    # except Exception as e:
    #     print(f"[ERROR] Impossible de démarrer le scheduler : {e}")

if __name__ == "__main__":
    # Démarrer le scheduler uniquement en mode dev local
    # if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    #     start_scheduler()
        
    app.run(debug=True, port=8009)
