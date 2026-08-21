# Copyright 2026 Google LLC
# Seed script to store .loop meeting action items into Firestore

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-ffdf266e9f9f"
COLLECTION_NAME = "action_items"

def seed_loop_items():
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    loop_items = [
        {
            "id": "item-101",
            "title": "Finalize A2UI Component Cards",
            "description": "Design and test interactive task cards for the chat UI frontend",
            "owner": "Sarah Miller",
            "source": "Facilitator Meeting Sync (meeting_summary.loop)",
            "status": "pending",
            "due_date": "2026-08-25",
            "priority": "High",
            "created_at": "2026-08-20T21:00:00Z",
        },
        {
            "id": "item-102",
            "title": "Configure BigQuery Agent Analytics",
            "description": "Set up telemetry export and Cloud Trace monitoring for production traffic",
            "owner": "Bob Smith",
            "source": "Facilitator Meeting Sync (meeting_summary.loop)",
            "status": "pending",
            "due_date": "2026-08-27",
            "priority": "Medium",
            "created_at": "2026-08-20T21:00:00Z",
        },
        {
            "id": "item-103",
            "title": "Prepare Facilitator Onboarding Brief",
            "description": "Draft quickstart guide for external facilitators to submit daily email summaries",
            "owner": "Alice Johnson",
            "source": "Facilitator Meeting Sync (meeting_summary.loop)",
            "status": "in_progress",
            "due_date": "2026-08-29",
            "priority": "Medium",
            "created_at": "2026-08-20T21:00:00Z",
        },
    ]

    for item in loop_items:
        doc_ref = collection_ref.document(item["id"])
        doc_ref.set(item)
        print(f"Stored action item from .loop: {item['id']} - '{item['title']}'")

    print("All .loop file action items successfully stored in Firestore!")

if __name__ == "__main__":
    seed_loop_items()
