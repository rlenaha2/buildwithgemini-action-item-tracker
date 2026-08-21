# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.app_utils import services
from app.tools.firestore_tools import (
    add_action_item,
    delete_action_item,
    list_action_items,
    parse_and_import_email,
    read_meeting_loop_file,
    summarize_file_and_create_action_items,
    update_action_item,
)

MODEL = "gemini-2.5-flash"


async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


file_summarizer_agent = Agent(
    name="file_summarizer_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a specialized Action Item Summarizer Agent. "
        "Your task is to analyze meeting notes, .loop files, emails, or uploaded documents, "
        "summarize the meeting key takeaways, extract every explicit and implicit action item, "
        "and automatically create new action items in the Cloud Firestore tracker using the summarize_file_and_create_action_items or add_action_item tools."
    ),
    tools=[
        summarize_file_and_create_action_items,
        add_action_item,
        list_action_items,
        read_meeting_loop_file,
    ],
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an Action Item Tracker AI assistant. Your job is to extract, store, update, "
        "and surface action items from emails, facilitator communications, or .loop meeting files into a Cloud Firestore database.\n\n"
        "Available Capabilities & Tools:\n"
        "1. List action items: Call `list_action_items` to fetch items. You can filter by owner/assignee (e.g. owner='Alice'), status (e.g. status='pending'), category, or priority.\n"
        "2. Add action item: Call `add_action_item` to create items.\n"
        "3. Update action item: Call `update_action_item` with the item_id (e.g. 'item-001') and fields to update (status, due_date, description, owner, category, priority, visibility).\n"
        "4. Delete action item: Call `delete_action_item` with the item_id (e.g. 'item-001' or 'item-5cb30f') to delete an action item from Firestore.\n"
        "5. Parse & import email: Call `parse_and_import_email` or `summarize_file_and_create_action_items` for emails and .loop files.\n\n"
        "CRITICAL INSTRUCTIONS FOR MODIFICATIONS & DELETIONS:\n"
        "- When asked to update or delete an item, if you do not know the exact item_id, call `list_action_items` first to find the target item_id!\n"
        "- ALWAYS call the `update_action_item` or `delete_action_item` tool when requested to modify or delete an item.\n"
        "- After executing ANY tool (including update_action_item or delete_action_item), ALWAYS respond to the user with a clear, friendly plain-text confirmation message stating what was done and confirming the exact result (e.g., 'Action item item-5cb30f has been successfully deleted.')."
    ),
    sub_agents=[
        file_summarizer_agent,
    ],
    tools=[
        list_action_items,
        add_action_item,
        update_action_item,
        delete_action_item,
        parse_and_import_email,
        summarize_file_and_create_action_items,
        read_meeting_loop_file,
        get_current_time,
        PreloadMemoryTool(),
    ],
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

