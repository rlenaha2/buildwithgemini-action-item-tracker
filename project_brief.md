# My agent: Action Item Tracker Agent

One-liner: An agentic assistant that reads data from emails and facilitator notes, extracts action items requiring tracking, stores them in a database, surfaces them to the user, and enables modifying details, status, and due dates.

## Description
The Action Item Tracker Agent automates the extraction and lifecycle management of tasks derived from daily communications:
1. **Ingest Data**: Reads incoming content from email threads and facilitator summaries.
2. **Action Item Extraction**: Analyzes text to automatically identify actionable tasks, assigned owners, context, and implied deadlines.
3. **Database Persistence**: Stores structured action items into a persistent database.
4. **User Surface & Interaction**: Presents action items to the user via interactive cards and tables.
5. **Item Lifecycle Management**: Allows the user to edit descriptions, adjust due dates, reassign tasks, and mark items as complete.

## Tool Coverage:
- **Memory**: User task preferences, email filtering rules, default due-date lead times, and context history.
- **Tools**: 
  - `read_emails_and_facilitator_data`: Fetches incoming messages and meeting notes.
  - `extract_action_items`: Parses text for actionable deliverables and deadlines.
  - `save_action_item`: Inserts new items into the database.
  - `update_action_item`: Modifies existing action items (status, due date, priority, notes).
  - `list_action_items`: Queries stored action items from the database with status filters.
- **Catalog/UI**: Action Item catalog displaying tasks with status badges, priority levels, and due dates.
- **Image gen**: Task completion badge / progress overview diagram (optional).
- **Sandbox**: Computes deadline SLA urgency, overdue days, and workload distribution metrics.

Core rails (everyone): memory, tools, eval, deploy, frontend
My stretch menu (pick later): A2UI task cards/tables, database storage, code sandbox analytics
First eval question: "Extract all action items from the facilitator summary email below, set their due dates for next Friday, and store them in the database."
