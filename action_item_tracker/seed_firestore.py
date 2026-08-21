# Copyright 2026 Google LLC
# Seed script for Firestore action items collection

from google.cloud import firestore

# IMPORTANT: Hardcoded Project ID string as requested
PROJECT_ID = "qwiklabs-gcp-03-ffdf266e9f9f"
COLLECTION_NAME = "action_items"

def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    sample_items = [
        {
            "id": "item-001",
            "title": "Review quarterly budget proposal",
            "description": "Check financial projections and provide feedback to team lead.",
            "owner": "Alice",
            "source": "Facilitator summary email",
            "status": "pending",
            "due_date": "2026-08-25",
            "created_at": "2026-08-20T20:00:00Z",
        },
        {
            "id": "item-002",
            "title": "Prepare presentation slides",
            "description": "Draft outline and graphics for upcoming product roadmap showcase.",
            "owner": "Bob",
            "source": "Weekly alignment meeting",
            "status": "in_progress",
            "due_date": "2026-08-28",
            "created_at": "2026-08-20T20:30:00Z",
        },
        {
            "id": "item-003",
            "title": "Update system documentation",
            "description": "Ensure API specs and deployment guides reflect recent ADK v1.4 changes.",
            "owner": "Charlie",
            "source": "Engineering sync email",
            "status": "completed",
            "due_date": "2026-08-20",
            "created_at": "2026-08-20T19:00:00Z",
        },
    ]

    for item in sample_items:
        doc_ref = collection_ref.document(item["id"])
        doc_ref.set(item)
        print(f"Seeded action item: {item['id']} - '{item['title']}'")

    print("Firestore database seeded successfully!")

if __name__ == "__main__":
    seed_database()
