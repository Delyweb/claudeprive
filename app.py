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

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 Mo max upload

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
UPLOADS_DIR = DATA_DIR / "uploads"

# Créer les répertoires au démarrage
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Client Bedrock
# ─────────────────────────────────────────────

def get_bedrock_client():
    region = load_settings().get("region", "eu-west-3")
    return boto3.client("bedrock-runtime", region_name=region)

# Tarifs Bedrock par million de tokens (USD)
PRICING = {
    # Cross-region Inference Profiles (EU)
    "eu.anthropic.claude-3-5-sonnet-20240620-v1:0": {"input": 3.0, "output": 15.0},
    "eu.anthropic.claude-3-haiku-20240307-v1:0": {"input": 0.25, "output": 1.25},
    "eu.anthropic.claude-3-opus-20240229-v1:0": {"input": 15.0, "output": 75.0},
    
    # Cross-region Inference Profiles (US)
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": {"input": 3.0, "output": 15.0},
    "us.anthropic.claude-3-haiku-20240307-v1:0": {"input": 0.25, "output": 1.25},
    "us.anthropic.claude-3-opus-20240229-v1:0": {"input": 15.0, "output": 75.0},

    # Legacy / Direct regional IDs (fallback)
    "anthropic.claude-3-5-sonnet-20240620-v1:0": {"input": 3.0, "output": 15.0},
    "anthropic.claude-3-haiku-20240307-v1:0": {"input": 0.25, "output": 1.25},
    "anthropic.claude-3-opus-20240229-v1:0": {"input": 15.0, "output": 75.0},
}

def call_claude(messages, system_prompt, model=None):
    """Appel Claude via AWS Bedrock."""
    if model is None:
        # Par défaut : Cross-region EU Sonnet 3.5
        model = load_settings().get("model", "eu.anthropic.claude-3-5-sonnet-20240620-v1:0")

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": messages,
    })

    client = get_bedrock_client()
    resp = client.invoke_model(modelId=model, body=body)
    result = json.loads(resp["body"].read())

    usage = result.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    # Calculer le coût
    prices = PRICING.get(model, PRICING.get("eu.anthropic.claude-3-5-sonnet-20240620-v1:0"))
    if not prices:
        # Fallback prix moyen si modèle inconnu
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

DEFAULT_PROMPTS = [
    {
        "id": "general",
        "name": "Conseil général",
        "prompt": "Tu es un assistant business polyvalent. Tu aides avec des conseils professionnels clairs, structurés et actionnables. Tu t'exprimes en français."
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
    "model": "eu.anthropic.claude-3-5-sonnet-20240620-v1:0",
    "region": "eu-west-3",
    "active_prompt": "general",
}

def load_settings():
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    save_settings(DEFAULT_SETTINGS)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
# Extraction de texte (fichiers uploadés)
# ─────────────────────────────────────────────

def extract_text_from_file(filepath):
    """Extrait le texte d'un fichier uploadé."""
    ext = Path(filepath).suffix.lower()

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
    system_prompt = "Tu es un assistant professionnel. Tu t'exprimes en français."
    for p in prompts:
        if p["id"] == prompt_id:
            system_prompt = p["prompt"]
            break

    # Appel Bedrock
    try:
        result, usage = call_claude(conv["messages"], system_prompt)
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
                      ".py", ".js", ".yml", ".yaml", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

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

    # Extraire le texte
    text = extract_text_from_file(str(filepath))

    return jsonify({
        "filename": f.filename,
        "saved_as": safe_name,
        "text": text,
        "size": os.path.getsize(str(filepath)),
    })


# ── Coûts ──

@app.route("/api/costs", methods=["GET"])
def api_costs():
    costs = load_costs()
    today = date.today().isoformat()
    month = today[:7]  # "2026-03"

    daily_today = costs["daily"].get(today, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0})

    # Calculer le total du mois
    monthly = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
    for day_key, day_val in costs["daily"].items():
        if day_key.startswith(month):
            monthly["input_tokens"] += day_val["input_tokens"]
            monthly["output_tokens"] += day_val["output_tokens"]
            monthly["cost_usd"] = round(monthly["cost_usd"] + day_val["cost_usd"], 6)

    return jsonify({
        "today": daily_today,
        "month": monthly,
        "total": costs["total"],
    })


# ── Prompts ──

@app.route("/api/prompts", methods=["GET"])
def api_get_prompts():
    return jsonify(load_prompts())


@app.route("/api/prompts", methods=["POST"])
def api_save_prompt():
    data = request.get_json(silent=True) or {}
    prompts = load_prompts()

    prompt_id = data.get("id") or str(uuid.uuid4())[:8]
    name = data.get("name", "Sans nom")
    prompt_text = data.get("prompt", "")

    # Mettre à jour si existe, sinon ajouter
    found = False
    for p in prompts:
        if p["id"] == prompt_id:
            p["name"] = name
            p["prompt"] = prompt_text
            found = True
            break

    if not found:
        prompts.append({"id": prompt_id, "name": name, "prompt": prompt_text})

    save_prompts(prompts)
    return jsonify({"ok": True, "id": prompt_id})


@app.route("/api/prompts/<prompt_id>", methods=["DELETE"])
def api_delete_prompt(prompt_id):
    prompts = load_prompts()
    prompts = [p for p in prompts if p["id"] != prompt_id]
    save_prompts(prompts)
    return jsonify({"ok": True})


# ── Projets ──

@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    projects = load_projects()
    result = []
    for pid, proj in sorted(projects.items(), key=lambda x: x[1].get("created_at", ""), reverse=True):
        result.append({"id": pid, **proj})
    return jsonify(result)


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.get_json(silent=True) or {}
    project_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    project = {
        "name": data.get("name", "Nouveau projet"),
        "description": data.get("description", ""),
        "files": [],
        "created_at": now,
        "updated_at": now,
    }
    save_project(project_id, project)
    return jsonify({"id": project_id, **project}), 201


@app.route("/api/projects/<project_id>", methods=["GET"])
def api_get_project(project_id):
    proj = get_project(project_id)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    return jsonify({"id": project_id, **proj})


@app.route("/api/projects/<project_id>", methods=["PUT"])
def api_update_project(project_id):
    proj = get_project(project_id)
    if not proj:
        return jsonify({"error": "Projet introuvable"}), 404
    data = request.get_json(silent=True) or {}
    if "name" in data:
        proj["name"] = data["name"]
    if "description" in data:
        proj["description"] = data["description"]
    proj["updated_at"] = datetime.now().isoformat()
    save_project(project_id, proj)
    return jsonify({"id": project_id, **proj})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    # Détacher les conversations du projet (ne pas les supprimer)
    convs = load_conversations()
    for cid, conv in convs.items():
        if conv.get("project_id") == project_id:
            conv["project_id"] = None
    save_conversations(convs)
    delete_project(project_id)
    return jsonify({"ok": True})


@app.route("/api/projects/<project_id>/upload", methods=["POST"])
def api_project_upload(project_id):
    proj = get_project(project_id)
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
    filepath = UPLOADS_DIR / safe_name
    f.save(str(filepath))

    text = extract_text_from_file(str(filepath))

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

    # Supprimer le fichier physique
    filepath = UPLOADS_DIR / saved_as
    if filepath.exists():
        filepath.unlink()

    return jsonify({"ok": True})


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

if __name__ == "__main__":
    app.run(debug=True, port=8009)
