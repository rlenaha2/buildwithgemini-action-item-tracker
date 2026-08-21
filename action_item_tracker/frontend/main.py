"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TextPart,
    TransportProtocol,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ["AGENT_ENGINE_RESOURCE_NAME"]
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI."""
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        if isinstance(root, TextPart) and getattr(root, "text", None):
            out.append({"kind": "text", "text": root.text})
        elif getattr(root, "text", None):
            out.append({"kind": "text", "text": getattr(root, "text")})
        elif getattr(root, "data", None) is not None:
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": root.data})
        elif isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            if isinstance(event, tuple):
                task, update = event
                if task is not None:
                    last_task = task
                    if getattr(task, "context_id", None):
                        _contexts[user_id] = task.context_id
                if isinstance(update, TaskArtifactUpdateEvent):
                    got_artifact_update = True
                    parts.extend(_extract_parts(update.artifact.parts))
            elif isinstance(event, Message):
                parts.extend(_extract_parts(event.parts))
            elif getattr(event, "parts", None):
                parts.extend(_extract_parts(event.parts))

        # Non-streaming fallback: pull parts from the final task's artifacts.
        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))

    if not parts:
        # The turn produced no text or UI (e.g. the agent only ran tools, or a
        # tool stalled). Be honest rather than silent.
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


# Direct Firestore REST endpoints for the Interactive Dashboard
FIRESTORE_PROJECT = "qwiklabs-gcp-03-ffdf266e9f9f"


def parse_and_ingest_loop_content(content: str, filename: str = "dropped_file.loop") -> int:
    """Parses a .loop markdown file for Action Items and ingests them into Firestore."""
    import datetime
    import uuid
    from google.cloud import firestore

    db = firestore.Client(project=FIRESTORE_PROJECT)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    count = 0

    lines = content.splitlines()
    for line in lines:
        line_str = line.strip()
        if line_str.startswith("|") and not line_str.startswith("|---|") and "Item ID" not in line_str:
            cols = [c.strip() for c in line_str.split("|")[1:-1]]
            if len(cols) >= 4:
                item_id = cols[0] if cols[0].startswith("item-") else f"item-{uuid.uuid4().hex[:6]}"
                title = cols[1] if len(cols) > 1 else "Action Item"
                desc = cols[2] if len(cols) > 2 else ""
                owner = cols[3] if len(cols) > 3 else "Unassigned"
                due_date = cols[4] if len(cols) > 4 else "TBD"
                priority = cols[5] if len(cols) > 5 else "Medium"
                status = cols[6].lower().replace(" ", "_") if len(cols) > 6 else "pending"
                if status not in ["pending", "in_progress", "completed"]:
                    status = "pending"

                item_data = {
                    "id": item_id,
                    "title": title,
                    "description": desc,
                    "owner": owner,
                    "source": f".loop file ({filename})",
                    "category": "Meeting Action Item",
                    "status": status,
                    "due_date": due_date,
                    "priority": priority,
                    "created_at": now,
                    "completed_at": now if status == "completed" else None,
                }
                db.collection("action_items").document(item_id).set(item_data, merge=True)
                count += 1

    return count


def parse_and_ingest_email_content(email_text: str, source_label: str = "Facilitator Email") -> int:
    """Parses plain text emails or facilitator notes for action items and saves them to Firestore."""
    import datetime
    import re
    import uuid
    from google.cloud import firestore

    db = firestore.Client(project=FIRESTORE_PROJECT)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    count = 0

    # 1. Try parsing markdown table format if present in email/note
    if "|" in email_text:
        table_count = parse_and_ingest_loop_content(email_text, filename=source_label)
        if table_count > 0:
            return table_count

    # 2. Heuristic line parser for freeform emails
    lines = email_text.splitlines()
    buffer_items = []

    for line in lines:
        l = line.strip()
        if not l or len(l) < 5 or l.startswith("#") or l.startswith("---") or l.startswith("Date:"):
            continue

        if any(kw in l.lower() for kw in ["will", "should", "needs to", "to finish", "to review", "action item", "due", "assignee", "own", "handling", "responsible"]):
            owner = "Unassigned"
            owner_match = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:will|is|to|should|needs to|responsible)', l)
            if owner_match:
                owner = owner_match.group(1)
            else:
                assign_match = re.search(r'(?:Assignee|Owner|Assigned to):\s*([A-Za-z\s]+)', l, re.I)
                if assign_match:
                    owner = assign_match.group(1).strip()

            due_date = "TBD"
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', l)
            if date_match:
                due_date = date_match.group(1)
            else:
                month_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?', l, re.I)
                if month_match:
                    due_date = month_match.group(0)

            clean_title = re.sub(r'^[\s\-\*\d\.\>\#]+', '', l).strip()
            if len(clean_title) > 80:
                title = clean_title[:77] + "..."
                desc = clean_title
            else:
                title = clean_title
                desc = f"Extracted from email: '{clean_title}'"

            priority = "High" if "urgent" in l.lower() or "high" in l.lower() or "asap" in l.lower() else "Medium"
            category = "Email Action Item"

            buffer_items.append({
                "title": title,
                "description": desc,
                "owner": owner,
                "due_date": due_date,
                "priority": priority,
                "category": category,
            })

    if not buffer_items and len(email_text.strip()) > 10:
        first_line = email_text.strip().splitlines()[0]
        title = first_line[:75] if len(first_line) > 75 else first_line
        buffer_items.append({
            "title": title,
            "description": email_text.strip(),
            "owner": "Unassigned",
            "due_date": "TBD",
            "priority": "Medium",
            "category": "Facilitator Email",
        })

    for item in buffer_items:
        item_id = f"item-{uuid.uuid4().hex[:6]}"
        item_data = {
            "id": item_id,
            "title": item["title"],
            "description": item["description"],
            "owner": item["owner"],
            "source": source_label,
            "category": item["category"],
            "status": "pending",
            "due_date": item["due_date"],
            "priority": item["priority"],
            "created_at": now,
            "completed_at": None,
        }
        db.collection("action_items").document(item_id).set(item_data)
        count += 1

    return count


@app.post("/api/email/import")
async def import_email_api(req: Request):
    body = await req.json()
    email_text = body.get("text", "").strip()
    source = body.get("source", "Facilitator Email").strip()
    if not email_text:
        return JSONResponse({"status": "error", "message": "Email text required"}, status_code=400)

    count = parse_and_ingest_email_content(email_text, source_label=source)
    return JSONResponse({
        "status": "success",
        "imported_count": count,
        "message": f"Successfully extracted and saved {count} action items from email!"
    })


_processed_loop_files = set()


async def loop_folder_watcher():
    """Background task watching data/ folder for new or updated .loop files."""
    import asyncio
    import os

    watch_dirs = [
        os.path.join(os.getcwd(), "data"),
        os.path.join(os.getcwd()),
        "/config/Desktop/BuildWithGemini/action_item_tracker/data",
    ]
    while True:
        try:
            for d in watch_dirs:
                if os.path.exists(d):
                    for fname in os.listdir(d):
                        if fname.endswith(".loop"):
                            fpath = os.path.join(d, fname)
                            try:
                                mtime = os.path.getmtime(fpath)
                                key = f"{fpath}:{mtime}"
                                if key not in _processed_loop_files:
                                    _processed_loop_files.add(key)
                                    with open(fpath, "r", encoding="utf-8") as f:
                                        content = f.read()
                                    parse_and_ingest_loop_content(content, filename=fname)
                            except Exception as fe:
                                pass
        except Exception:
            pass
        await asyncio.sleep(5)


@app.on_event("startup")
async def start_watcher():
    import asyncio
    asyncio.create_task(loop_folder_watcher())


AUDIT_COLLECTION_NAME = "audit_logs"


def log_audit_event(user: str, event_type: str, details: str, item_id: str = "") -> dict:
    import datetime
    import uuid
    from google.cloud import firestore
    db = firestore.Client(project=FIRESTORE_PROJECT)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    log_id = f"log-{uuid.uuid4().hex[:8]}"
    log_entry = {
        "id": log_id,
        "timestamp_str": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_iso": now_utc.isoformat(),
        "user": user or "Anonymous",
        "event_type": event_type,
        "details": details,
        "item_id": item_id or "",
    }
    try:
        db.collection(AUDIT_COLLECTION_NAME).document(log_id).set(log_entry)
    except Exception as e:
        print(f"Audit log write failed: {e}")
    return log_entry


def get_audit_logs(requester_user: str, limit: int = 100) -> list:
    from google.cloud import firestore
    clean_user = (requester_user or "").strip().lower()
    if clean_user not in ["admin", "administrator", "system_admin"]:
        raise PermissionError(f"Access Denied: User '{requester_user}' is not authorized to view system audit logs.")

    db = firestore.Client(project=FIRESTORE_PROJECT)
    docs = db.collection(AUDIT_COLLECTION_NAME).stream()
    logs = []
    for doc in docs:
        logs.append(doc.to_dict())

    logs.sort(key=lambda x: x.get("timestamp_iso", ""), reverse=True)
    return logs[:limit]


@app.post("/api/loop/upload")
async def upload_loop_file(req: Request):
    form = await req.form()
    file_obj = form.get("file")
    if not file_obj:
        return JSONResponse({"status": "error", "message": "No file uploaded"}, status_code=400)

    contents = (await file_obj.read()).decode("utf-8", errors="ignore")
    filename = getattr(file_obj, "filename", "uploaded.loop")
    count = parse_and_ingest_loop_content(contents, filename=filename)
    log_audit_event(user="User", event_type="DATA_IMPORTED", details=f"Imported {count} action items from file '{filename}'")
    return JSONResponse({
        "status": "success",
        "imported_count": count,
        "message": f"Successfully imported {count} action items from '{filename}'!"
    })


@app.get("/api/action_items")
async def get_action_items_api(user: str = None, scoped: str = None):
    from google.cloud import firestore

    db = firestore.Client(project=FIRESTORE_PROJECT)
    docs = db.collection("action_items").stream()
    items = []

    is_scoped = str(scoped).lower() in ["true", "1", "yes"]
    target_user = (user or "").strip().lower()

    for doc in docs:
        d = doc.to_dict()
        if "id" not in d:
            d["id"] = doc.id

        item_owners = [u.strip().lower() for u in str(d.get("owner", "")).split(",")]
        
        # Calculate visibility scope
        visibility = d.get("visibility", "company_wide")
        d["visibility"] = visibility

        # VISIBILITY PERMISSION ENFORCEMENT
        # Admins can bypass restrictions if requested
        if target_user != "admin":
            if visibility in ["restricted_assignee", "restricted_user"]:
                if not target_user or target_user == "all" or not any(target_user in u for u in item_owners):
                    continue

        # Enforce user permission scoping: assigned to user AND pending only
        if is_scoped and target_user and target_user != "all":
            item_status = str(d.get("status", "")).strip().lower()
            if not any(target_user in u for u in item_owners) or item_status != "pending":
                continue

        items.append(d)
    return JSONResponse({"items": items})


@app.post("/api/action_items/update")
async def update_action_item_api(req: Request):
    import datetime
    from google.cloud import firestore

    body = await req.json()
    item_id = body.get("id")
    if not item_id:
        return JSONResponse({"status": "error", "message": "Missing item id"}, status_code=400)

    db = firestore.Client(project=FIRESTORE_PROJECT)
    doc_ref = db.collection("action_items").document(item_id)
    updates = {}
    for key in ["title", "description", "owner", "due_date", "status", "priority", "source", "category", "visibility"]:
        if key in body and body[key] is not None:
            updates[key] = body[key]

    if "status" in updates:
        if updates["status"] == "completed":
            updates["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        else:
            updates["completed_at"] = None

    if updates:
        doc_ref.update(updates)
        user_performing = body.get("user") or body.get("current_user") or "User"
        changed_keys = ", ".join(updates.keys())
        log_audit_event(
            user=user_performing,
            event_type="ACTION_ITEM_UPDATED",
            details=f"Updated item '{item_id}' fields: {changed_keys}",
            item_id=item_id
        )
    return JSONResponse({"status": "success", "updated": updates})


@app.post("/api/action_items/add")
async def add_action_item_api(req: Request):
    import datetime
    import uuid
    from google.cloud import firestore

    body = await req.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"status": "error", "message": "Title required"}, status_code=400)

    item_id = body.get("id") or f"item-{uuid.uuid4().hex[:6]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    status = body.get("status", "pending")
    completed_at = now if status == "completed" else None
    visibility = body.get("visibility", "company_wide")

    item_data = {
        "id": item_id,
        "title": title,
        "description": body.get("description", ""),
        "owner": body.get("owner", "Unassigned"),
        "source": body.get("source", "Dashboard UI"),
        "category": body.get("category", "General"),
        "status": status,
        "due_date": body.get("due_date", "TBD"),
        "priority": body.get("priority", "Medium"),
        "visibility": visibility,
        "created_at": now,
        "completed_at": completed_at,
    }

    db = firestore.Client(project=FIRESTORE_PROJECT)
    db.collection("action_items").document(item_data["id"]).set(item_data)
    user_performing = body.get("user") or body.get("current_user") or "User"
    log_audit_event(
        user=user_performing,
        event_type="ACTION_ITEM_CREATED",
        details=f"Created new action item '{title}' (ID: {item_id}, Assignees: {item_data['owner']})",
        item_id=item_id
    )
    return JSONResponse({"status": "success", "item": item_data})


@app.post("/api/action_items/delete")
async def delete_action_item_api(req: Request):
    from google.cloud import firestore

    body = await req.json()
    item_id = body.get("id")
    if not item_id:
        return JSONResponse({"status": "error", "message": "Missing item id"}, status_code=400)

    db = firestore.Client(project=FIRESTORE_PROJECT)
    doc_ref = db.collection("action_items").document(item_id)
    if doc_ref.get().exists:
        doc_ref.delete()
        user_performing = body.get("user") or body.get("current_user") or "User"
        log_audit_event(
            user=user_performing,
            event_type="ACTION_ITEM_DELETED",
            details=f"Deleted action item '{item_id}'",
            item_id=item_id
        )
        return JSONResponse({"status": "success", "deleted_id": item_id})
    else:
        return JSONResponse({"status": "error", "message": f"Item '{item_id}' not found"}, status_code=404)


PREFERENCES_COLLECTION_NAME = "user_preferences"


def get_user_preferences_from_db(user_id: str) -> dict:
    from google.cloud import firestore

    clean_user = (user_id or "global_default").strip().lower()
    if not clean_user:
        clean_user = "global_default"

    db = firestore.Client(project=FIRESTORE_PROJECT)
    doc_ref = db.collection(PREFERENCES_COLLECTION_NAME).document(clean_user)
    doc = doc_ref.get()

    if doc.exists:
        return doc.to_dict()

    return {
        "user_id": clean_user,
        "auto_scan_emails": True,
        "auto_scan_meeting_notes": True,
        "updated_at": None,
        "updated_by": "system",
    }


@app.get("/api/user_preferences")
async def get_user_preferences_api(user: str = "global_default"):
    try:
        prefs = get_user_preferences_from_db(user)
        return JSONResponse({"status": "success", "preferences": prefs})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/user_preferences/update")
async def update_user_preferences_api(req: Request):
    import datetime
    from google.cloud import firestore

    body = await req.json()
    user_id = (body.get("user_id") or "global_default").strip().lower()
    auto_scan_emails = bool(body.get("auto_scan_emails", True))
    auto_scan_meeting_notes = bool(body.get("auto_scan_meeting_notes", True))
    updated_by = body.get("updated_by") or body.get("user") or "User"

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    prefs_data = {
        "user_id": user_id,
        "auto_scan_emails": auto_scan_emails,
        "auto_scan_meeting_notes": auto_scan_meeting_notes,
        "updated_at": now_iso,
        "updated_by": updated_by,
    }

    db = firestore.Client(project=FIRESTORE_PROJECT)
    db.collection(PREFERENCES_COLLECTION_NAME).document(user_id).set(prefs_data)

    status_str = f"Emails: {'ON' if auto_scan_emails else 'OFF'}, Notes: {'ON' if auto_scan_meeting_notes else 'OFF'}"
    log_audit_event(
        user=updated_by,
        event_type="USER_PREFERENCES_UPDATED",
        details=f"Updated scanning preferences for '{user_id}': {status_str}",
    )

    return JSONResponse({"status": "success", "preferences": prefs_data})


@app.post("/api/audit_logs/log_access")
async def log_access_api(req: Request):
    body = await req.json()
    user = body.get("user", "Anonymous")
    event_type = body.get("event_type", "WEBSITE_ACCESS")
    details = body.get("details", "Session active / website accessed")
    entry = log_audit_event(user=user, event_type=event_type, details=details)
    return JSONResponse({"status": "success", "log": entry})


@app.get("/api/audit_logs")
async def get_audit_logs_api(user: str = None):
    try:
        logs = get_audit_logs(requester_user=user)
        return JSONResponse({"status": "success", "logs": logs})
    except PermissionError as pe:
        return JSONResponse({"status": "error", "message": str(pe)}, status_code=403)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# Serve the chat UI (keep this mount last so /chat and /api win).
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
