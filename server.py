#!/usr/bin/env python3
"""
Servicing Agent MCP Server — Harborstone Mutual Insurance

Built for the "Servicing Agent" scenario: an agentic customer servicing
solution combining CRM customer records, Snowflake operational data,
policy documents, call transcripts, and prior case notes.

This server deliberately exposes CRM and Snowflake as two SEPARATE systems,
not one merged view — get_crm_account stands in for a native Salesforce
read (identity/relationship), while get_policies_held and get_ticket_status
stand in for native Snowflake reads (operational/transactional data). The
agent has to call both and reconcile them itself, the same way it would
against the real systems. Policy documents, product guidance, and case
history form a third, unstructured knowledge layer underneath both.
"""

import json
from pathlib import Path
from datetime import date
from mcp.server import MCPServer

DATA_PATH = Path(__file__).parent / "data" / "servicing.json"
with open(DATA_PATH) as f:
    DATA = json.load(f)

mcp = MCPServer("servicing-agent")


# ---------------------------------------------------------------------------
# CRM layer (stands in for Salesforce)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_crm_account(customer_id: str = "", name_contains: str = "") -> str:
    """
    THE authoritative CRM record for a customer — identity, contact info,
    agent of record, named insureds, and account status. This stands in for
    a native Salesforce/CRM read, NOT Snowflake. Call this FIRST for any
    question naming a specific person, to establish who they are, before
    pulling their policies or tickets. Do NOT use this for what the
    customer owns or what's in flight — that's get_policies_held and
    get_ticket_status. Filter by customer_id (e.g. 'CUST-101') or a
    partial name match.
    """
    customers = DATA["customers"]
    if customer_id:
        customers = [c for c in customers if c["id"] == customer_id]
    if name_contains:
        needle = name_contains.lower()
        customers = [c for c in customers if needle in c["name"].lower()]
    return json.dumps(customers, indent=2)


# ---------------------------------------------------------------------------
# Snowflake layer (structured, operational)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_policies_held(customer_id: str = "", product_id: str = "") -> str:
    """
    THE authoritative source for what insurance products a customer actually
    holds — policy IDs, effective/renewal dates, premium status, coverage
    limits. Stands in for a native Snowflake read against the policies-held
    table, a DIFFERENT system from get_crm_account. Call this for any
    question about coverage limits, whether a policy is current, or whether
    premium payment is up to date — do not guess from general insurance
    knowledge. Filter by customer_id and/or product_id (e.g. 'PROD-AUTO',
    'PROD-UMBRELLA').
    """
    policies = DATA["policies_held"]
    if customer_id:
        policies = [p for p in policies if p["customer_id"] == customer_id]
    if product_id:
        policies = [p for p in policies if p["product_id"] == product_id]
    return json.dumps(policies, indent=2)


@mcp.tool()
def get_ticket_status(ticket_id: str = "", customer_id: str = "", status: str = "", type: str = "") -> str:
    """
    THE authoritative source for request/ticket status — claims, policy
    change requests, cancellation requests, and billing disputes. Stands in
    for a native Snowflake read, the SAME system as get_policies_held but a
    different table. Call this for any question about whether something has
    been submitted, is pending, or is complete; do not guess based on
    typical processing times. Filter by ticket_id (e.g. 'TKT-2201'),
    customer_id, status ('Submitted', 'Under Review', 'Approved', 'Denied',
    'Paid', 'Escalated'), and/or type ('Claim', 'Policy Change Request',
    'Cancellation Request', 'Billing Dispute').
    """
    tickets = DATA["tickets"]
    if ticket_id:
        tickets = [t for t in tickets if t["id"] == ticket_id]
    if customer_id:
        tickets = [t for t in tickets if t["customer_id"] == customer_id]
    if status:
        tickets = [t for t in tickets if t["status"] == status]
    if type:
        tickets = [t for t in tickets if t["type"] == type]
    return json.dumps(tickets, indent=2)


# ---------------------------------------------------------------------------
# Knowledge layer (unstructured — policy, product guidance, case history)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_policy(topic: str = "") -> str:
    """
    Retrieve policy document text to ground an answer about WHY something
    happened — a denial, a hold, a coverage limit — in the actual written
    policy rather than a general-knowledge guess about how insurance
    "usually" works. Many servicing questions look like a CRM or ticket
    data question on the surface but actually require this tool to explain
    correctly (e.g. "why was my policy change denied" is rarely answered by
    the ticket record alone). Filter by topic ('Auto Coverage', 'Homeowners
    Coverage', 'Claims Filing', 'Cancellation', 'Umbrella Coverage',
    'Billing'). Leave blank to return all policy documents.
    """
    policies = DATA["policy_documents"]
    if topic:
        needle = topic.lower()
        policies = [p for p in policies if needle in p["topic"].lower() or needle in p["title"].lower()]
    return json.dumps(policies, indent=2)


@mcp.tool()
def get_product_guidance(product: str = "") -> str:
    """
    Retrieve product guidance content — what a product covers, how it
    works, and how it interacts with other products the customer holds.
    Use this for general "what does X cover" or "how does X work" questions
    that are not about a specific customer's account. Filter by product
    name or category ('Auto', 'Homeowners', 'Renters', 'Life', 'Umbrella').
    Leave blank to return all products.
    """
    products = DATA["products"]
    if product:
        needle = product.lower()
        products = [
            p for p in products
            if needle in p["name"].lower() or needle in p["category"].lower() or needle in p["id"].lower()
        ]
    return json.dumps(products, indent=2)


@mcp.tool()
def get_case_history(customer_id: str = "", sentiment: str = "") -> str:
    """
    Retrieve prior call transcripts and case notes for a customer — the
    conversational/interaction layer. Every interaction has a transcript
    field (full dialogue) when the channel was a call, or null with just a
    case_note when it was email/chat; a case_note is always an addition to
    the interaction, never a parallel record. Use this to see what a
    customer has already been told, and to check sentiment before deciding
    whether something needs a human. Filter by customer_id and/or sentiment
    ('Positive', 'Neutral', 'Negative').
    """
    history = DATA["case_history"]
    if customer_id:
        history = [h for h in history if h["customer_id"] == customer_id]
    if sentiment:
        history = [h for h in history if h["sentiment"] == sentiment]
    return json.dumps(history, indent=2)


# ---------------------------------------------------------------------------
# Proactive layer (computed from Snowflake + Knowledge, not stored)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_escalations() -> str:
    """
    Return OPEN tickets that should route to a human rather than be closed
    out by the agent: SLA breaches, tickets already marked Escalated,
    high-value claims requiring manual underwriting review, or customers
    with negative-sentiment case history. Closed/resolved tickets (Approved,
    Denied, Paid) are intentionally excluded — they don't need escalation,
    they need a policy-grounded explanation if the customer asks about one.
    Use this as the proactive "what needs a person" scan.
    """
    today = date.today()
    candidates = []

    open_statuses = {"Submitted", "Under Review", "Escalated"}

    for ticket in DATA["tickets"]:
        if ticket["status"] not in open_statuses:
            continue

        flags = []
        due = date.fromisoformat(ticket["sla_due_date"])
        days_past_due = (today - due).days

        if days_past_due > 0:
            flags.append(f"Past SLA due date by {days_past_due} day(s)")
        if ticket["status"] == "Escalated":
            flags.append("Already flagged escalated in system")
        if ticket["type"] == "Claim" and ticket.get("estimated_value", 0) > 10000:
            flags.append(f"High-value claim (${ticket['estimated_value']:,}) requires manual underwriting review")

        customer_notes = [
            h for h in DATA["case_history"]
            if h["customer_id"] == ticket["customer_id"] and h["sentiment"] == "Negative"
        ]
        if customer_notes:
            flags.append("Negative sentiment in recent case history")

        if flags:
            customer = next((c for c in DATA["customers"] if c["id"] == ticket["customer_id"]), None)
            candidates.append({
                "ticket_id": ticket["id"],
                "customer_id": ticket["customer_id"],
                "customer_name": customer["name"] if customer else "Unknown",
                "type": ticket["type"],
                "status": ticket["status"],
                "sla_due_date": ticket["sla_due_date"],
                "escalation_flags": flags,
            })

    return json.dumps(candidates, indent=2)


if __name__ == "__main__":
    mcp.run()
