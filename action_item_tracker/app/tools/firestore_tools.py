# Copyright 2026 Google LLC
# Firestore tools for Action Item Tracker

import datetime
import uuid
from google.cloud import firestore

import os

# IMPORTANT: Hardcoded Project ID string as explicitly instructed by user
PROJECT_ID = "qwiklabs-gcp-03-ffdf266e9f9f"
COLLECTION_NAME = "action_items"


def get_firestore_client():
    return firestore.Client(project=PROJECT_ID)


def read_meeting_loop_file(file_name: str = "meeting_summary.loop") -> str:
    """Reads a .loop meeting summary file containing meeting notes and action items.

    Args:
        file_name: The name of the .loop file to read.

    Returns:
        The text content of the .loop file.
    """
    possible_paths = [
        os.path.join(os.getcwd(), "data", file_name),
        os.path.join(os.getcwd(), file_name),
        os.path.join("/config/Desktop/BuildWithGemini/action_item_tracker/data", file_name),
        os.path.join("/config/Desktop/BuildWithGemini", file_name),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return f"Error: Could not find .loop file '{file_name}'."



def list_action_items(status: str = "", owner: str = "", category: str = "", priority: str = "") -> str:
    """Lists action items from Firestore, with optional filters for status, owner/assignee, category, or priority.

    Args:
        status: Optional status string to filter by (e.g., 'pending', 'in_progress', 'completed').
        owner: Optional owner or assignee name to filter by (e.g., 'Alice', 'Bob', 'Sarah').
        category: Optional category name to filter by (e.g., 'Engineering', 'Finance', 'Operations', 'General').
        priority: Optional priority level to filter by (e.g., 'High', 'Medium', 'Low').

    Returns:
        Formatted string listing all matching action items.
    """
    db = get_firestore_client()
    collection_ref = db.collection(COLLECTION_NAME)

    docs = collection_ref.stream()
    items = []

    owner_filter = owner.strip().lower() if owner else ""
    cat_filter = category.strip().lower() if category else ""
    status_filter = status.strip().lower() if status else ""
    prio_filter = priority.strip().lower() if priority else ""

    for doc in docs:
        data = doc.to_dict()

        if status_filter and str(data.get("status", "")).lower() != status_filter:
            continue

        if cat_filter and str(data.get("category", "")).lower() != cat_filter:
            continue

        if prio_filter and str(data.get("priority", "")).lower() != prio_filter:
            continue

        if owner_filter:
            doc_owner = str(data.get("owner", "")).lower()
            if owner_filter not in doc_owner:
                continue

        vis = data.get("visibility", "company_wide")
        vis_str = f" [{vis.upper()}]" if vis != "company_wide" else ""
        items.append(
            f"ID: {data.get('id', doc.id)} | Title: {data.get('title')}{vis_str} | Category: {data.get('category', 'General')} | Status: {data.get('status')} | "
            f"Owner: {data.get('owner')} | Due Date: {data.get('due_date')} | Priority: {data.get('priority', 'Medium')} | Source: {data.get('source')} | Visibility: {vis}\n"
            f"  Description: {data.get('description')}"
        )

    if not items:
        filter_parts = []
        if status: filter_parts.append(f"status='{status}'")
        if owner: filter_parts.append(f"owner='{owner}'")
        if category: filter_parts.append(f"category='{category}'")
        if priority: filter_parts.append(f"priority='{priority}'")
        filter_str = f" with {', '.join(filter_parts)}" if filter_parts else ""
        return f"No action items found{filter_str}."

    return "Found Action Items:\n" + "\n\n".join(items)


def add_action_item(
    title: str,
    description: str,
    owner: str = "Unassigned",
    source: str = "User request",
    due_date: str = "TBD",
    category: str = "General",
    priority: str = "Medium",
    visibility: str = "company_wide",
) -> str:
    """Adds a new action item to the Firestore database.

    Args:
        title: Title/summary of the action item.
        description: Detailed description of what needs to be done.
        owner: Assignee or comma-separated list of tagged people (e.g., 'Sarah, Bob, Alice').
        source: Source of the action item (e.g., 'Facilitator email', 'Meeting notes').
        due_date: Due date for completion (e.g., 'YYYY-MM-DD').
        category: Functional category (e.g., 'Engineering', 'Finance', 'Operations', 'General').
        priority: Priority level ('High', 'Medium', 'Low').
        visibility: Access scope ('company_wide', 'restricted_assignee', 'restricted_user').

    Returns:
        Confirmation message with the created item ID.
    """
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
    return f"Successfully created action item '{title}' (Visibility: {valid_vis}) in Category '{category}' with ID '{item_id}'."


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
    """Updates an existing action item in Firestore (e.g. status, due date, description, owner, category, priority, visibility).

    Args:
        item_id: The ID of the action item to update (e.g., 'item-001').
        status: New status ('pending', 'in_progress', 'completed').
        due_date: New due date string (e.g., 'YYYY-MM-DD').
        description: Updated description text.
        owner: Updated owner/assignee.
        category: Updated category string (e.g. 'Engineering', 'Finance').
        priority: Updated priority string ('High', 'Medium', 'Low').
        visibility: Updated access scope ('company_wide', 'restricted_assignee', 'restricted_user').

    Returns:
        Confirmation message describing updated fields.
    """
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(item_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"Error: Action item with ID '{item_id}' not found."

    updates = {}
    if status:
        updates["status"] = status
        if status == "completed":
            updates["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        else:
            updates["completed_at"] = None
    if due_date:
        updates["due_date"] = due_date
    if description:
        updates["description"] = description
    if owner:
        updates["owner"] = owner
    if category:
        updates["category"] = category
    if priority:
        updates["priority"] = priority
    if visibility in ["company_wide", "restricted_assignee", "restricted_user"]:
        updates["visibility"] = visibility

    if not updates:
        return f"No update fields provided for item '{item_id}'."

    doc_ref.update(updates)
    fields_updated = ", ".join(f"{k}='{v}'" for k, v in updates.items())
    return f"Successfully updated action item '{item_id}': {fields_updated}."


def delete_action_item(item_id: str) -> str:
    """Deletes an action item from the Firestore database by its ID.

    Args:
        item_id: The ID of the action item to delete (e.g. 'item-101').

    Returns:
        Confirmation message.
    """
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(item_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"Error: Action item with ID '{item_id}' not found."

    doc_ref.delete()
    return f"Successfully deleted action item '{item_id}' from database."


def parse_and_import_email(email_text: str, source_label: str = "Facilitator Email") -> str:
    """Parses raw email text or facilitator notes to extract action items and save them into Firestore.

    Args:
        email_text: The raw text of the email or meeting notes containing action items.
        source_label: Optional label for the source (e.g. 'Sync Email', 'Facilitator Update').

    Returns:
        Confirmation message detailing how many action items were extracted and saved.
    """
    import re
    db = get_firestore_client()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
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

            clean_title = re.sub(r'^[\s\-\*\d\.\>\#]+', '', l).strip()
            title = clean_title[:77] + "..." if len(clean_title) > 80 else clean_title
            priority = "High" if "urgent" in l.lower() or "high" in l.lower() or "asap" in l.lower() else "Medium"

            buffer_items.append({
                "title": title,
                "description": clean_title,
                "owner": owner,
                "due_date": due_date,
                "priority": priority,
                "category": "Email Action Item",
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

    count = 0
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
        db.collection(COLLECTION_NAME).document(item_id).set(item_data)
        count += 1

    return f"Successfully extracted and saved {count} action items from email text into Firestore database!"


def summarize_file_and_create_action_items(file_content: str, filename: str = "new_meeting_file.loop") -> str:
    """Summarizes a meeting file/transcript and automatically creates extracted action items in Cloud Firestore.

    Args:
        file_content: Text content of the file or email notes.
        filename: Name of the file being processed.

    Returns:
        Summary report detailing extracted action items added to the tracker.
    """
    import datetime
    import re
    import uuid

    db = get_firestore_client()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    count = 0

    if "|" in file_content:
        lines = file_content.splitlines()
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
                        "source": f"File: {filename}",
                        "category": "Meeting Summary",
                        "status": status,
                        "due_date": due_date,
                        "priority": priority,
                        "created_at": now,
                        "completed_at": now if status == "completed" else None,
                    }
                    db.collection(COLLECTION_NAME).document(item_id).set(item_data, merge=True)
                    count += 1
    else:
        lines = file_content.splitlines()
        for line in lines:
            l = line.strip()
            if not l or len(l) < 5 or l.startswith("#") or l.startswith("---"):
                continue
            if any(kw in l.lower() for kw in ["will", "should", "needs to", "to finish", "to review", "action item", "due", "assignee", "own", "handling", "responsible"]):
                owner = "Unassigned"
                owner_match = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:will|is|to|should|needs to|responsible)', l)
                if owner_match:
                    owner = owner_match.group(1)

                due_date = "TBD"
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', l)
                if date_match:
                    due_date = date_match.group(1)

                clean_title = re.sub(r'^[\s\-\*\d\.\>\#]+', '', l).strip()
                title = clean_title[:77] + "..." if len(clean_title) > 80 else clean_title

                item_id = f"item-{uuid.uuid4().hex[:6]}"
                item_data = {
                    "id": item_id,
                    "title": title,
                    "description": clean_title,
                    "owner": owner,
                    "source": f"File: {filename}",
                    "category": "Meeting Action Item",
                    "status": "pending",
                    "due_date": due_date,
                    "priority": "Medium",
                    "created_at": now,
                    "completed_at": None,
                }
                db.collection(COLLECTION_NAME).document(item_id).set(item_data)
                count += 1

    return f"Summarizer Agent processed '{filename}': extracted and created {count} new action items in the tracker!"


AUDIT_COLLECTION_NAME = "audit_logs"


def log_audit_event(user: str, event_type: str, details: str, item_id: str = "") -> dict:
    """Logs website access, session times, or data modifications in a separate Firestore collection.

    Args:
        user: The user performing the action or accessing the site.
        event_type: Category of event (e.g., WEBSITE_ACCESS, SESSION_START, ITEM_CREATED, ITEM_UPDATED, ITEM_DELETED, DATA_IMPORTED).
        details: Explanation of the event or specific data modified.
        item_id: Optional ID of the action item changed.

    Returns:
        The created audit log entry dictionary.
    """
    db = get_firestore_client()
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
    """Retrieves audit logs stored separately from the tracker. Accessible ONLY to admin users.

    Args:
        requester_user: The user requesting access.
        limit: Maximum number of audit records to return.

    Returns:
        List of audit log dictionaries if authorized, or raises PermissionError.
    """
    clean_user = (requester_user or "").strip().lower()
    if clean_user not in ["admin", "administrator", "system_admin"]:
        raise PermissionError(f"Access Denied: User '{requester_user}' is not authorized to view system audit logs.")

    db = get_firestore_client()
    docs = db.collection(AUDIT_COLLECTION_NAME).stream()
    logs = []
    for doc in docs:
        d = doc.to_dict()
        logs.append(d)

    logs.sort(key=lambda x: x.get("timestamp_iso", ""), reverse=True)
    return logs[:limit]


def check_user_scanning_preference(user_id: str = "global_default", scan_type: str = "emails") -> str:
    """Checks whether a user has opted in or opted out of automatic scanning for emails or meeting notes.

    Args:
        user_id: The username or user identifier to check (e.g. 'Alice', 'Bob', 'global_default').
        scan_type: The scanning type to check: 'emails' or 'meeting_notes'.

    Returns:
        Formatted string stating whether auto-scanning is ENABLED (Opted-in) or DISABLED (Opted-out) for the user.
    """
    db = get_firestore_client()
    clean_user = (user_id or "global_default").strip().lower()
    doc_ref = db.collection("user_preferences").document(clean_user)
    doc = doc_ref.get()

    if not doc.exists:
        return f"User '{user_id}' currently has default scanning preferences: Automatic email scanning is DISABLED (Opted-Out by default), Automatic meeting notes scanning is DISABLED (Opted-Out by default)."

    prefs = doc.to_dict()
    emails_enabled = prefs.get("auto_scan_emails", False)
    notes_enabled = prefs.get("auto_scan_meeting_notes", False)

    if scan_type == "meeting_notes":
        state = "ENABLED (Opted-In)" if notes_enabled else "DISABLED (Opted-Out)"
        return f"Automatic meeting notes scanning for user '{user_id}' is {state}."
    else:
        state = "ENABLED (Opted-In)" if emails_enabled else "DISABLED (Opted-Out)"
        return f"Automatic email scanning for user '{user_id}' is {state}."


def update_user_scanning_preference(user_id: str = "global_default", auto_scan_emails: bool = False, auto_scan_meeting_notes: bool = False) -> str:
    """Updates a user's opt-in / opt-out preferences for automatic email and meeting notes scanning.

    Args:
        user_id: The username to update (e.g. 'Alice', 'Bob', 'global_default').
        auto_scan_emails: Set True to opt in to automatic email scanning, False to opt out.
        auto_scan_meeting_notes: Set True to opt in to automatic meeting notes (.loop) scanning, False to opt out.

    Returns:
        Confirmation message detailing the updated preference settings.
    """
    db = get_firestore_client()
    clean_user = (user_id or "global_default").strip().lower()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    prefs_data = {
        "user_id": clean_user,
        "auto_scan_emails": auto_scan_emails,
        "auto_scan_meeting_notes": auto_scan_meeting_notes,
        "updated_at": now_iso,
        "updated_by": "AI Assistant Chat",
    }
    db.collection("user_preferences").document(clean_user).set(prefs_data)

    email_status = "ENABLED (Opted-In)" if auto_scan_emails else "DISABLED (Opted-Out)"
    notes_status = "ENABLED (Opted-In)" if auto_scan_meeting_notes else "DISABLED (Opted-Out)"

    log_audit_event(
        user=user_id,
        event_type="USER_PREFERENCES_UPDATED",
        details=f"Updated preferences via AI Agent: Emails {email_status}, Notes {notes_status}"
    )

    return f"Successfully updated scanning preferences for user '{user_id}':\n- Automatic Email Scanning: {email_status}\n- Automatic Meeting Notes Scanning: {notes_status}"
