# Servicing Agent MCP Server — Harborstone Mutual Insurance

A Model Context Protocol (MCP) server that shows how a customer-servicing agent can combine CRM customer records, Snowflake operational data, policy documents, call transcripts and prior case notes. All data is synthetic.

**This version deliberately exposes CRM and Snowflake as two separate systems, not one merged view.** `get_crm_account` stands in for a native Salesforce/CRM read — identity, contact info, agent of record. `get_policies_held` and `get_ticket_status` stand in for native Snowflake reads — what the customer owns and what's in flight. The agent has to call across both and reconcile them itself, the same way it would against the real systems, rather than reading from one flattened record.

**Dataset**: 10 customers across 5 products (Auto, Homeowners, Renters, Term Life, Umbrella), 14 policies held, 18 service tickets spanning 4 request types (Claim, Policy Change Request, Cancellation Request, Billing Dispute) and every status from Submitted through Denied, 6 policy documents, and 13 case history entries — 8 of them full call transcripts with real dialogue, not one-line summaries.

## Architecture

```
Claude Desktop (MCP Client)
        │  MCP Protocol over stdio
        ▼
servicing-agent-mcp-server/server.py  ←── This repo
        │
        ├──────────────┬──────────────────┬─────────────────────
        ▼               ▼                  ▼
   CRM layer      Snowflake layer     Knowledge layer
  (get_crm_account) (get_policies_held,  (search_policy,
   identity/         get_ticket_status)   get_product_guidance,
   relationship       operational data     get_case_history)
        │               │                  │
        └───────────────┴──────────────────┘
                        │
                        ▼
        Claude reconciles across systems, reasons,
        and returns a grounded, explainable answer
                        │
                        ▼
              Escalates When It Should (get_escalations)
```

## Setup

### 1. Install dependencies
```bash
cd servicing-agent-mcp-server
python3 -m pip install -r requirements.txt
```

### 2. Configure Claude Desktop
Open your Claude Desktop config file:
```bash
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Add the server config (merge with any existing config), replacing the path with where you cloned this repo:
```json
{
  "mcpServers": {
    "servicing-agent": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/servicing-agent-mcp-server/server.py"],
      "env": {}
    }
  }
}
```

### 3. Restart Claude Desktop
Quit and reopen Claude Desktop. You should see a 🔌 icon or tool count increase in the chat interface.

---

## MCP Tools Exposed

| Tool | System | Servicing use case |
|---|---|---|
| `get_crm_account` | CRM (Salesforce stand-in) | Customer identity, contact info, agent of record, named insureds |
| `get_policies_held` | Snowflake | What products/policies the customer holds, coverage limits, premium status |
| `get_ticket_status` | Snowflake | "Request/ticket status" — claims, policy changes, cancellations, billing disputes |
| `search_policy` | Knowledge | Policy documents — grounds a "why" answer in actual written policy |
| `get_product_guidance` | Knowledge | "Product guidance" — what a product covers and how it works |
| `get_case_history` | Knowledge | Call transcripts + case notes, with sentiment |
| `get_escalations` | Computed | Proactive scan of open tickets that need a human, and why |

---

## Demo Prompts

Use these in Claude Desktop after connecting the server:

**Account question + ticket status, combined (CRM + Snowflake reconciliation):**
> "Pull up Renee Castellano's account and her open tickets — give me a complete picture of where things stand with her water damage claim."

**The cross-product policy gotcha (the strongest one to run live):**
> "Tom Bregman's request to add his daughter as a driver on his auto policy was denied. His driving record and hers are both clean — why would this get denied, and what does he need to do to get it approved?"
> This one is worth running live. The obvious read is a driver-eligibility problem. The actual answer is on a different policy entirely — his umbrella coverage requires higher underlying auto liability limits once a driver under 25 is added, and his auto policy is below that threshold. The agent has to pull his CRM record, his policies held (both auto and umbrella), the ticket, and the Umbrella Underlying Coverage Requirements document, and reconcile all four to get the real answer.

**The billing/coverage-lapse gotcha:**
> "Ray Whitfield says he's been a loyal customer for eleven years and can't understand why his claim was denied. Walk me through why, using the actual policy, not a general explanation."
> Second grounded, non-obvious moment — the claim was filed during a premium grace-period lapse, and reinstatement isn't retroactive. A good test of whether the agent will state the policy-grounded reason plainly rather than soften it into something vague.

**Product guidance, not tied to one customer:**
> "A prospect is asking what umbrella insurance actually covers and whether they need anything else in place first. Ground it in the actual product and policy requirements."

**Proactive escalation scan:**
> "Scan all open tickets and tell me which ones should go to a human instead of being handled by the agent, and why."
> The scan checks SLA dates against the date you run it, so the count changes over time. When this dataset was built it flagged 4 of the 8 open tickets, and it flags more as SLA dates pass. It flags an SLA breach, a ticket already escalated, a high-value claim in manual underwriting review, or negative sentiment in case history. Closed and resolved tickets are excluded on purpose; a Denied or Paid ticket doesn't need escalation, it needs a policy-grounded explanation if asked about.

**Full servicing walkthrough:**
> "James O'Connell is worried his theft claim being marked Escalated means it's going to be denied. Pull his account, the claim, and his case history, and tell me what's actually going on and what I should tell him."

Watch Claude decide which of the seven tools it needs per question, and which system — CRM or Snowflake — actually holds the answer, rather than guessing from one merged mental model.

---

## Why CRM and Snowflake Are Two Separate Tools

This is the deliberate architectural choice in this version: identity data and operational data are exposed as genuinely separate systems the agent must call independently and reconcile, rather than one flattened "customer 360" object. That's closer to how most enterprises are actually wired — Salesforce or another CRM as the system of record for the relationship, Snowflake as the operational/data-warehouse layer for high-volume transactional data — and it forces a design discipline worth having anyway: every fact the agent states should be traceable to which system it came from, which is a trust and auditability feature, not just a technical constraint.

## About

A small reference implementation of a customer-servicing agent over synthetic insurance data. It shows how an agent can reconcile identity data, operational data and written policy, and route risky tickets to a person.
