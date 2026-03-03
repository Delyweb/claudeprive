
import json
import uuid
import logging
from datetime import datetime, date
from pathlib import Path

# On importe les fonctions nécessaires depuis app (attention aux imports circulaires, 
# idéalement il faudrait refactoriser, mais ici on va importer au moment de l'exécution ou passer les fonctions)
# Pour simplifier, je vais réimplémenter l'accès aux données ici ou utiliser app comme module.
# Le plus simple est de mettre cette logique DANS app.py ou de faire un module `data_access.py`.
# Mais pour ne pas tout casser, je vais mettre la logique du journal dans un module qui reçoit les fonctions en paramètre
# ou qui importe app si app est structuré pour.

# Vu que app.py est un script monolithique, je vais créer ce fichier journal.py 
# mais il devra être appelé par app.py qui lui passera le contexte.

def build_journal_prompt(project_name, conversations_text):
    today = date.today().isoformat()
    return f"""Tu es l'assistant de synthèse de ClaudePrivé. 

Voici les conversations du jour pour le projet "{project_name}".

Génère un journal quotidien concis au format markdown avec les sections suivantes :

# Journal {project_name} - {today}

## Actions réalisées
Liste des actions concrètes effectuées aujourd'hui (mails rédigés, documents créés, analyses faites, décisions prises). Utilise ✅ pour chaque action.

## Informations clés
Nouvelles informations apprises, réponses reçues, clarifications obtenues. Ce qui change la compréhension du contexte.

## Prochaines étapes
Actions identifiées à faire, en attente de réponse, ou à planifier. Utilise ⏳ pour chaque item.

## Points d'attention
Risques, blocages, sujets sensibles, ou éléments à surveiller.

---

Règles :
- Sois factuel et concis
- Pas de reformulation des conversations, uniquement la synthèse
- Si une section est vide, ne pas l'inclure
- Maximum 30 lignes au total

Conversations du jour :
{conversations_text}
"""

def generate_journal(project_id, app_context):
    """
    Génère le journal pour un projet donné.
    app_context: dictionnaire contenant les fonctions d'accès aux données (passé depuis app.py)
    """
    print(f"[Journal] Début génération pour projet {project_id}")
    
    get_project = app_context['get_project']
    load_conversations = app_context['load_conversations']
    call_claude = app_context['call_claude']
    save_project = app_context['save_project']
    UPLOADS_DIR = app_context['UPLOADS_DIR']
    
    project = get_project(project_id)
    if not project:
        print(f"[Journal] Projet {project_id} introuvable")
        return None

    # 1. Récupérer les conversations du jour
    today_str = date.today().isoformat()
    convs = load_conversations()
    project_convs_text = ""
    count = 0
    
    for cid, conv in convs.items():
        # Vérifier si la conversation appartient au projet
        if conv.get("project_id") != project_id:
            continue
            
        # Vérifier si la conversation a été modifiée aujourd'hui
        # Le champ updated_at est en ISO format (YYYY-MM-DDTHH:MM:SS...)
        updated_at = conv.get("updated_at", "")
        if not updated_at.startswith(today_str):
            continue
            
        count += 1
        project_convs_text += f"\n\n--- Conversation : {conv.get('title', 'Sans titre')} ---\n"
        for msg in conv.get("messages", []):
            role = "Utilisateur" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")
            project_convs_text += f"{role}: {content}\n"

    if count == 0:
        print(f"[Journal] Aucune activité aujourd'hui pour le projet {project['name']}")
        return None

    print(f"[Journal] {count} conversations trouvées pour {project['name']}")

    # 2. Vérifier si un journal existe déjà pour aujourd'hui
    # On regarde dans les fichiers du projet
    journal_filename = f"Journal_{project['name'].replace(' ', '_')}_{today_str}.md"
    for f in project.get("files", []):
        if f.get("filename") == journal_filename:
            print(f"[Journal] Le journal existe déjà : {journal_filename}")
            return None # On ne l'écrase pas automatiquement (règle demandée)

    # 3. Appeler Claude
    prompt = build_journal_prompt(project['name'], project_convs_text)
    
    # On utilise un contexte vide pour l'appel technique, ou on simule
    # call_claude attend ([messages], system_prompt)
    try:
        # On utilise Haiku ou Sonnet pour la synthèse (rapide et pas cher)
        # On force un modèle rapide si possible, sinon on laisse le défaut
        result, usage = call_claude(
            [{"role": "user", "content": prompt}], 
            "Tu es un assistant de synthèse expert."
        )
        
        journal_content = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                journal_content += block["text"]
                
        if not journal_content:
            print("[Journal] Réponse vide de Claude")
            return None

        # 4. Sauvegarder le fichier
        # On crée un fichier physique
        safe_name = f"journal_{uuid.uuid4().hex[:8]}.md"
        filepath = UPLOADS_DIR / safe_name
        filepath.write_text(journal_content, encoding="utf-8")
        
        # On crée le fichier sidecar .txt (pour le RAG futur)
        txt_path = UPLOADS_DIR / (safe_name + ".txt")
        txt_path.write_text(journal_content, encoding="utf-8")
        
        # 5. Ajouter au projet
        file_info = {
            "filename": journal_filename,
            "saved_as": safe_name,
            "size": len(journal_content.encode('utf-8')),
            "uploaded_at": datetime.now().isoformat(),
            "text_preview": journal_content[:200] + "...",
            "type": "journal" # Marqueur spécial
        }
        
        project["files"].append(file_info)
        project["updated_at"] = datetime.now().isoformat()
        save_project(project_id, project)
        
        print(f"[Journal] Journal généré avec succès : {journal_filename}")
        return file_info

    except Exception as e:
        print(f"[Journal] Erreur lors de la génération : {e}")
        return None

def run_daily_journals(app_context):
    """
    Fonction appelée par le Cron à 23h00.
    Parcourt tous les projets et génère les journaux.
    """
    print("[Cron] Lancement de la génération des journaux quotidiens...")
    load_projects = app_context['load_projects']
    projects = load_projects()
    
    count = 0
    for pid, proj in projects.items():
        res = generate_journal(pid, app_context)
        if res:
            count += 1
            
    print(f"[Cron] Terminé. {count} journaux générés.")
