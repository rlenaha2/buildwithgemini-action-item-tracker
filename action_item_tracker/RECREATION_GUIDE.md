# 🚀 Complete Recreation Guide: AI-Powered Action Item Tracker

This comprehensive guide provides everything required to build, configure, deploy, and run the **AI-Powered Action Item Tracker** from scratch on Google Cloud Platform using Google's **Agent Development Kit (ADK)**, **Cloud Run**, and **Firestore**.

---

## 📐 1. System Architecture

The application consists of three main tiers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      FastAPI Frontend (Cloud Run)                       │
│  - Interactive Dashboard UI (Vanilla HTML/CSS/JS + Glassmorphism)       │
│  - User Profile Account Switcher & 3-Tier Permission Filter             │
│  - Category Pick List & Filter Pill                                     │
│  - Consolidated "Import New Action" 3-Tab Modal (Form, Email, File)     │
│  - Admin System Audit & Access Log Modal                                │
└───────────────────┬───────────────────────────┬─────────────────────────┘
                    │                           │
                    ▼                           ▼
┌───────────────────────────────┐   ┌─────────────────────────────────────┐
│    Cloud Firestore Native     │   │ Vertex AI Agent Runtime / Reasoning │
│  - `action_items` collection  │   │  - ADK `root_agent`                 │
│  - `audit_logs` collection    │   │  - `file_summarizer_agent` subagent │
│  - Real-time CRUD operations  │   │  - A2A Proxy endpoint               │
└───────────────────────────────┘   └─────────────────────────────────────┘
```

---

## 🛠️ 2. Prerequisites & GCP Setup

### 2.1 Enable Required APIs
Ensure the following Google Cloud APIs are enabled on your GCP project:

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com
```

### 2.2 Create Firestore Database (Native Mode)
```bash
gcloud firestore databases create --location=us-east1 --type=firestore-native
```

### 2.3 Create Cloud Storage Bucket
```bash
gsutil mb -l us-east1 gs://qwiklabs-gcp-03-ffdf266e9f9f-action-items
```

---

## 📂 3. Directory & File Structure

Create the project directory structure:

```
action_item_tracker/
├── app/
│   ├── __init__.py
│   ├── agent.py               # ADK Root Agent and File Summarizer Sub-agent
│   └── tools/
│       ├── __init__.py
│       └── firestore_tools.py # Firestore CRUD, Email Import, File Summarizer Tools
├── frontend/
│   ├── main.py                # FastAPI proxy server & REST API
│   ├── Dockerfile             # Container build file
│   └── static/
│       └── index.html         # Frontend Dashboard UI
├── data/
│   └── meeting_summary.loop   # Sample meeting transcript file
├── deployment_metadata.json   # Deployment tracking file
└── requirements.txt           # Python dependencies
```

---

## 📦 4. Installation & Dependencies

Create `requirements.txt`:

```text
google-adk>=0.1.0
google-cloud-firestore>=2.11.0
google-cloud-storage>=2.10.0
fastapi>=0.100.0
uvicorn>=0.22.0
pydantic>=2.0.0
jinja2>=3.1.0
python-multipart>=0.0.6
```

---

## 🐍 5. Backend Code Implementation

### 5.1 Firestore Tools (`app/tools/firestore_tools.py`)

```python
import datetime
import os
import uuid
from google.cloud import firestore

# NOTE: Set your GCP Project ID string
PROJECT_ID = "qwiklabs-gcp-03-ffdf266e9f9f"
COLLECTION_NAME = "action_items"

def get_firestore_client():
    return firestore.Client(project=PROJECT_ID)

def list_action_items(status: str = "") -> str:
    """Lists action items from Firestore, optionally filtered by status."""
    db = get_firestore_client()
    query_ref = db.collection(COLLECTION_NAME)
    if status:
        query_ref = query_ref.where("status", "==", status)

    docs = query_ref.stream()
    items = []
    for doc in docs:
        data = doc.to_dict()
        vis = data.get("visibility", "company_wide")
        vis_str = f" [{vis.upper()}]" if vis != "company_wide" else ""
        items.append(
            f"ID: {data.get('id', doc.id)} | Title: {data.get('title')}{vis_str} | "
            f"Category: {data.get('category', 'General')} | Status: {data.get('status')} | "
            f"Owner: {data.get('owner')} | Due Date: {data.get('due_date')} | "
            f"Priority: {data.get('priority', 'Medium')} | Source: {data.get('source')} | Visibility: {vis}\n"
            f"  Description: {data.get('description')}"
        )

    if not items:
        return f"No action items found."
    return "Found Action Items:\n" + "\n\n".join(items)

def add_action_item(
    title: str,
    description: str = "",
    owner: str = "Unassigned",
    source: str = "User request",
    due_date: str = "TBD",
    category: str = "General",
    priority: str = "Medium",
    visibility: str = "company_wide",
) -> str:
    """Adds a new action item to Firestore."""
    db = get_firestore_client()
    item_id = f"item-{uuid.uuid4().hex[:6]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    valid_vis = visibility if visibility in ["company_wide", "restricted_assignee", "restricted_user"] else "company_wide"

    item_data = {
        "id": item_id,
        "title": title,
        "description": description,
        "owner": owner,
        "source": source,
        "category": category,
        "priority": priority,
        "status": "pending",
        "due_date": due_date,
        "visibility": valid_vis,
        "created_at": now,
    }

    db.collection(COLLECTION_NAME).document(item_id).set(item_data)
    return f"Successfully created action item '{title}' (Visibility: {valid_vis}) with ID '{item_id}'."

def update_action_item(
    item_id: str,
    status: str = "",
    due_date: str = "",
    description: str = "",
    owner: str = "",
    category: str = "",
    priority: str = "",
    visibility: str = "",
) -> str:
    """Updates an existing action item in Firestore."""
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(item_id)
    if not doc_ref.get().exists:
        return f"Error: Item '{item_id}' not found."

    updates = {}
    if status:
        updates["status"] = status
        updates["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat() if status == "completed" else None
    if due_date: updates["due_date"] = due_date
    if description: updates["description"] = description
    if owner: updates["owner"] = owner
    if category: updates["category"] = category
    if priority: updates["priority"] = priority
    if visibility: updates["visibility"] = visibility

    if updates:
        doc_ref.update(updates)
    return f"Successfully updated item '{item_id}'."

def delete_action_item(item_id: str) -> str:
    """Deletes an action item from Firestore."""
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(item_id)
    if doc_ref.get().exists:
        doc_ref.delete()
        return f"Successfully deleted item '{item_id}'."
    return f"Error: Item '{item_id}' not found."
```

---

### 5.2 Agent Definitions (`app/agent.py`)

```python
from google.adk import Agent
from app.tools.firestore_tools import (
    list_action_items,
    add_action_item,
    update_action_item,
    delete_action_item,
)

# Sub-agent for File / Email Summarization
file_summarizer_agent = Agent(
    name="file_summarizer_agent",
    model="gemini-2.5-flash",
    description="Sub-agent that analyzes meeting notes, emails, or .loop files to extract action items.",
    instruction="Extract clear action items, assignees, due dates, categories, and priorities from text.",
    tools=[add_action_item]
)

# Root Orchestrator Agent
root_agent = Agent(
    name="action_item_tracker",
    model="gemini-2.5-flash",
    description="Action Item Tracker Root Agent",
    instruction="Manage, track, query, update, and summarize team action items.",
    tools=[
        list_action_items,
        add_action_item,
        update_action_item,
        delete_action_item,
    ],
    sub_agents=[file_summarizer_agent]
)
```

---

## 🌐 6. Frontend Code Implementation

### 6.1 FastAPI Proxy & REST API (`frontend/main.py`)

```python
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore

app = FastAPI(title="Action Item Tracker")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

FIRESTORE_PROJECT = "qwiklabs-gcp-03-ffdf266e9f9f"

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("frontend/static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/action_items")
async def get_action_items_api(user: str = None, scoped: str = None):
    db = firestore.Client(project=FIRESTORE_PROJECT)
    docs = db.collection("action_items").stream()
    items = []

    is_scoped = str(scoped).lower() in ["true", "1", "yes"]
    target_user = (user or "").strip().lower()

    for doc in docs:
        d = doc.to_dict()
        if "id" not in d: d["id"] = doc.id
        
        item_owners = [u.strip().lower() for u in str(d.get("owner", "")).split(",") if u.strip()]
        vis = d.get("visibility", "company_wide")

        # Granular Visibility & Privacy Enforcement
        if vis == "restricted_assignee":
            if not target_user or target_user == "all" or not any(target_user in u for u in item_owners):
                continue
        elif vis == "restricted_user":
            if not target_user or target_user == "all" or not any(target_user in u for u in item_owners):
                continue

        # Scoped Pending Enforcement
        if is_scoped and target_user and target_user != "all":
            if not any(target_user in u for u in item_owners) or str(d.get("status", "")).lower() != "pending":
                continue

        items.append(d)
    return JSONResponse({"items": items})

@app.post("/api/action_items/add")
async def add_item_api(req: Request):
    body = await req.json()
    db = firestore.Client(project=FIRESTORE_PROJECT)
    item_id = body.get("id") or f"item-{uuid.uuid4().hex[:6]}"
    visibility = body.get("visibility", "company_wide")
    item_data = {
        "id": item_id,
        "title": body["title"],
        "description": body.get("description", ""),
        "owner": body.get("owner", "Unassigned"),
        "category": body.get("category", "General"),
        "status": body.get("status", "pending"),
        "due_date": body.get("due_date", "TBD"),
        "priority": body.get("priority", "Medium"),
        "visibility": visibility,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection("action_items").document(item_id).set(item_data)
    return JSONResponse({"status": "success", "item": item_data})

@app.post("/api/action_items/update")
async def update_item_api(req: Request):
    body = await req.json()
    db = firestore.Client(project=FIRESTORE_PROJECT)
    doc_ref = db.collection("action_items").document(body["id"])
    doc_ref.update({k: v for k, v in body.items() if k != "id"})
    return JSONResponse({"status": "success"})

@app.post("/api/action_items/delete")
async def delete_item_api(req: Request):
    body = await req.json()
    db = firestore.Client(project=FIRESTORE_PROJECT)
    db.collection("action_items").document(body["id"]).delete()
    return JSONResponse({"status": "success"})
```

---

## 🚀 7. Deployment Instructions

### 7.1 Deploy Agent Engine to Vertex AI Agent Runtime

Run the deployment command from the root directory:

```bash
agents-cli deploy \
  --project qwiklabs-gcp-03-ffdf266e9f9f \
  --region us-east1
```

*This generates `deployment_metadata.json` containing the Reasoning Engine resource ID.*

---

### 7.2 Deploy Frontend Proxy to Google Cloud Run

Deploy the FastAPI service to Cloud Run:

```bash
cd frontend

gcloud run deploy action-item-tracker-frontend \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="projects/869308136518/locations/us-east1/reasoningEngines/1933117363490652160",AGENT_DIRECTORY="action_item_tracker"
```

---

## ✅ 8. Verification & Testing

1. Open the Cloud Run Service URL:
   `https://action-item-tracker-frontend-869308136518.us-east1.run.app`
2. **Create/Import Action Items:**
   * Click **`Import New Action`** in the top toolbar.
   * **Tab 1 (➕ Structured Form):** Enter Title, Description, Tagged Assignees, Category, Due Date, Priority, and Visibility Permissions.
   * **Tab 2 (📧 Paste Email Text):** Paste email text to automatically extract action items.
   * **Tab 3 (📄 Upload .loop / Text File):** Upload `.loop` files or meeting summary text files.
3. **Test Permission Scoping:** Click **`🔒 Assigned to Me & Pending Only`** and select `Sarah Miller` in the header profile switcher.
4. **Test 3-Tier Permissions:** Create action items with:
   * **🏢 Company Wide:** Visible to everyone across all profiles.
   * **👥 Restricted to Assignee(s):** Visible only to tagged assignees.
   * **🔒 Restricted to User:** Visible only when logged in under the target user profile.
5. **Test Admin Audit Logs:** Switch profile to `🛡️ Admin (System Audit Access)`. Click **`🛡️ Audit Logs`** in the header to view website access, session times, and data modification audit records stored in the separate `audit_logs` Firestore collection.
