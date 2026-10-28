"""Equal-input discovery cases for a transparent synthetic component comparison.

These are synthetic capability contracts, not model-task success labels. Both
engines receive the same names, descriptions, JSON schemas, and query order.
"""

from __future__ import annotations

import hashlib
import json


_TOOLS = (
    ("github.create_issue", "Create an issue in a GitHub repository.", "title"),
    ("github.list_issues", "List issues in a GitHub repository.", "repository"),
    (
        "github.search_repositories",
        "Search GitHub repositories by name and description.",
        "query",
    ),
    (
        "github.get_pull_request",
        "Read a GitHub pull request and its review status.",
        "number",
    ),
    ("gitlab.create_issue", "Create an issue in a GitLab project.", "title"),
    ("gitlab.list_issues", "List issues in a GitLab project.", "project"),
    ("slack.send_message", "Send a message to a Slack channel.", "text"),
    ("slack.search_messages", "Search messages in Slack channels.", "query"),
    ("gmail.send_email", "Send an email through Gmail.", "recipient"),
    ("gmail.search_emails", "Search Gmail emails by sender or subject.", "query"),
    ("gmail.read_email", "Read a Gmail email and its attachments.", "message_id"),
    ("outlook.send_email", "Send an email through Outlook.", "recipient"),
    ("outlook.search_emails", "Search Outlook emails by sender or subject.", "query"),
    ("calendar.create_event", "Create an event in a calendar.", "title"),
    ("calendar.list_events", "List events in a calendar.", "date"),
    ("drive.search_files", "Search documents and files in Drive.", "query"),
    ("drive.read_file", "Read the contents of a Drive file.", "file_id"),
    ("notion.create_page", "Create a page in a Notion workspace.", "title"),
    ("notion.search_pages", "Search pages in a Notion workspace.", "query"),
    ("browser.list_tabs", "List the open browser tabs.", "window"),
    ("browser.navigate", "Navigate a browser tab to a web address.", "url"),
    ("browser.click", "Click an element in a browser tab.", "selector"),
    ("terminal.run_command", "Run a shell command in a terminal.", "command"),
    ("python.execute_code", "Execute Python code and return its output.", "code"),
    ("billing.create_invoice", "Create an invoice for a billing account.", "customer"),
    ("billing.list_invoices", "List invoices for a billing account.", "customer"),
    ("inventory.list_products", "List products in the inventory.", "category"),
    (
        "inventory.update_stock",
        "Update the stock quantity of an inventory product.",
        "quantity",
    ),
    ("support.create_ticket", "Create a customer support ticket.", "subject"),
    ("support.search_tickets", "Search customer support tickets.", "query"),
    (
        "incident.create_incident",
        "Create an incident with severity and affected service.",
        "severity",
    ),
    (
        "incident.send_email",
        "Send an email notification about an incident.",
        "recipient",
    ),
)


def catalog(size: int = 32) -> list[dict]:
    if size < len(_TOOLS):
        raise ValueError("catalog size must include all 32 base capabilities")
    rows = list(_TOOLS)
    for index in range(size - len(rows)):
        rows.append(
            (
                f"archive_{index:04d}.read_record",
                f"Read an archived record from archive {index:04d}.",
                "record_id",
            )
        )
    return [
        {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {argument: {"type": "string"}},
                "required": [argument],
                "additionalProperties": False,
            },
        }
        for name, description, argument in rows
    ]


def cases() -> list[dict]:
    rows = [
        {
            "id": f"exact_{index:02d}",
            "group": "qualified_name",
            "query": name,
            "acceptable": [name],
            "expect_empty": False,
        }
        for index, (name, _, _) in enumerate(_TOOLS)
    ]
    intents = (
        ("github create issue", "github.create_issue"),
        ("github search repositories", "github.search_repositories"),
        ("slack send message", "slack.send_message"),
        ("slack search messages", "slack.search_messages"),
        ("gmail send email", "gmail.send_email"),
        ("outlook search emails", "outlook.search_emails"),
        ("calendar create event", "calendar.create_event"),
        ("drive read file", "drive.read_file"),
        ("notion create page", "notion.create_page"),
        ("python execute code", "python.execute_code"),
        ("billing create invoice", "billing.create_invoice"),
        ("support search tickets", "support.search_tickets"),
    )
    for index, (query, target) in enumerate(intents):
        for group, text in (
            ("keywords", query),
            ("polite", f"please {query}"),
            ("request", f"can you {query} for me"),
        ):
            rows.append(
                {
                    "id": f"{group}_{index:02d}",
                    "group": group,
                    "query": text,
                    "acceptable": [target],
                    "expect_empty": False,
                }
            )
    inflections = (
        ("github creating issues", "github.create_issue"),
        ("slack sending messages", "slack.send_message"),
        ("gmail sending emails", "gmail.send_email"),
        ("calendar creating events", "calendar.create_event"),
        ("drive reading files", "drive.read_file"),
        ("notion searching pages", "notion.search_pages"),
        ("billing creating invoices", "billing.create_invoice"),
        ("support searching tickets", "support.search_tickets"),
    )
    for index, (query, target) in enumerate(inflections):
        rows.append(
            {
                "id": f"inflected_{index:02d}",
                "group": "inflected",
                "query": query,
                "acceptable": [target],
                "expect_empty": False,
            }
        )
    for index, query in enumerate(
        (
            "salesforce create lead",
            "asana create task",
            "discord send message",
            "dropbox read file",
            "trello create card",
            "zoom create meeting",
            "stripe list payments",
            "gitlab create merge request",
        )
    ):
        rows.append(
            {
                "id": f"unavailable_{index:02d}",
                "group": "unavailable_capability",
                "query": query,
                "acceptable": [],
                "expect_empty": True,
            }
        )
    for index, query in enumerate(
        (
            "please salesforce create lead",
            "can you discord send message for me",
            "please dropbox read file",
            "can you zoom create meeting for me",
        )
    ):
        rows.append(
            {
                "id": f"unavailable_polite_{index:02d}",
                "group": "unavailable_polite",
                "query": query,
                "acceptable": [],
                "expect_empty": True,
            }
        )
    return rows


def fixture_digest(size: int) -> str:
    body = json.dumps(
        {"catalog": catalog(size), "cases": cases(), "additional": additional_cases()},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(body).hexdigest()


def additional_cases() -> list[dict]:
    """Separately reported punctuation and combined request-wrapper cases."""
    keywords = [case for case in cases() if case["group"] == "keywords"]
    rows = []
    for index, case in enumerate(keywords):
        for style, query in (
            ("combined", f"Could you please {case['query']}?"),
            ("kindly", f"Kindly {case['query']}."),
            ("would", f"Would you {case['query']} for me?"),
        ):
            rows.append(
                {
                    **case,
                    "id": f"combined_{style}_{index:02d}",
                    "group": "additional_requests",
                    "query": query,
                }
            )
    for index, query in enumerate(
        (
            "Could you please salesforce create lead?",
            "Kindly discord send message.",
            "Would you dropbox read file for me?",
            "Could you please zoom create meeting?",
        )
    ):
        rows.append(
            {
                "id": f"combined_unavailable_{index:02d}",
                "group": "additional_unavailable",
                "query": query,
                "acceptable": [],
                "expect_empty": True,
            }
        )
    return rows
