# ShopBot — LangChain 1.x / LangGraph E-commerce Support Agent

A single LangGraph agent that powers two Streamlit apps: a customer support
chat and an admin review dashboard, built against `ecommerce.db`.

## Architecture at a glance

```
                      ┌─────────────────────────┐
 app_customer.py ───▶ │   ONE agent (agent.py)   │ ◀─── app_admin.py
 (Streamlit, 8501)    │  create_react_agent +    │      (Streamlit, 8502)
                       │  SqliteSaver checkpointer│
                       └────────────┬─────────────┘
                                     │ tools
        ┌────────────────┬──────────┼───────────────┬──────────────────┐
        ▼                ▼          ▼               ▼                  ▼
  SQLDatabaseToolkit  rag_policy_search      send_gmail_notification   cancel_order_action /
  (orders, returns,   (Chroma over the 3     (Gmail API, or           request_return_action
   payments, tickets,  policy .txt files)     simulated + logged)     (HITL: interrupt() pauses,
   email_logs...)                                                      admin resumes via
                                                                        Command(resume=...))
```

- **One agent, not several** — `src/agent.py` builds a single
  `langgraph.prebuilt.create_react_agent` per session; all business logic is
  in its tools, per the spec's "agent-centric" requirement.
- **Conversation state** lives only in a `SqliteSaver` checkpointer
  (`checkpoints.sqlite`), threaded by `user_email:conversation_id` — never
  in the business database.
- **Human-in-the-loop** — `cancel_order_action` and `request_return_action`
  write a `pending_actions` row, then call LangGraph's `interrupt()`. That
  *pauses and returns immediately* (non-blocking for the customer's chat
  request). The admin dashboard later calls `resume_thread(...)`, which
  resumes that exact paused run with `Command(resume=decision)`, finishing
  the DB update and notification. The chatbot never auto-approves a
  cancellation or return.
- **Logging/observability** — `src/logging_middleware.py` is a LangChain
  `BaseCallbackHandler` attached via `config={"callbacks": [...]}` on every
  agent invocation, so it fires for the agent run and every tool call
  automatically. Logs go to `logs/app.log`.

## Project structure

```
ecommerce.db              # provided business DB (+ pending_actions, added by db_init)
policies/                 # returns_policy.txt, shipping_policy.txt, faq_returns_and_cancellations.txt
requirements.txt
.env.example
src/
  config.py               # env loading, paths, business-rule constants
  db_init.py               # idempotent: adds pending_actions table
  auth.py                 # plain-text login against users table (lab simplification)
  logging_middleware.py    # LangChain callback handler -> logs/app.log
  rag_tool.py              # rag_policy_search tool (Chroma over policies/)
  gmail_tool.py             # send_gmail_notification tool (+ email_logs writes)
  action_tools.py          # cancel_order_action / request_return_action (HITL)
  agent.py                 # builds the single agent, checkpointer, resume_thread()
  app_customer.py           # Streamlit customer chat (port 8501)
  app_admin.py               # Streamlit admin dashboard (port 8502)
logs/app.log               # created on first run
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in OPENAI_API_KEY
python -m src.db_init        # idempotent — adds pending_actions if missing
```

## Run

Two separate Streamlit processes, as the spec suggests:

```bash
streamlit run src/app_customer.py --server.port 8501
streamlit run src/app_admin.py --server.port 8502
```

Demo accounts (already in `ecommerce.db`):
- Customers: `alice@example.com` / `alice123`, `bob@example.com` / `bob123`, `charlie@example.com` / `charlie123`
- Admin: `admin@example.com` / `admin123`

## End-to-end flow to try

1. Log in as Alice in the customer app, ask *"What's the status of my order #2?"* (SQL tool).
2. Ask *"How long do I have to return something?"* (RAG tool — grounded in `returns_policy.txt`).
3. Ask *"I want to return order #1, the keyboard, the keys are sticking"* — the agent creates a pending return + ticket and tells Alice it's under human review. Her chat request returns immediately; nothing is approved yet.
4. Log in as admin in the admin app (port 8502). The request appears in the **PENDING** queue. Approve or reject it, optionally with a note.
5. Back in Alice's chat, send any new message (or just reopen the same conversation) — the resolution message that the agent produced on resume is now part of the conversation history.

## Simplifications documented (per spec's non-functional requirements)

- **Passwords are plain-text** in `users.password` and compared directly — acceptable for this lab only, never for production.
- **Gmail is optional.** With `GMAIL_ENABLED=false` (default), `send_gmail_notification` simulates the send and still writes to `email_logs`, so the rest of the app (including the audit trail) behaves identically without requiring Google Cloud OAuth setup. Set `GMAIL_ENABLED=true` and provide `credentials.json`/`token.json` (see `google-auth-oauthlib`'s installed-app flow) for real sends.
- **Chroma index** is built once from `policies/*.txt` into `chroma_db/` on first run and reused after that; delete `chroma_db/` to force a rebuild if you edit the policy files.
- The admin dashboard's queue is backed by a dedicated `pending_actions` table (added by `db_init.py`) rather than introspecting the checkpointer directly — this keeps the dashboard simple and fast while `thread_id` on each row is exactly what's used to resume the paused agent run.

## Notes on this environment

This was built and syntax-checked in a sandboxed container without outbound
network access, so the LangGraph/LangChain packages could not be installed
or exercised against a live OpenAI key here. The code follows the
documented, stable APIs for `create_react_agent`, `SqliteSaver`,
`interrupt()`/`Command(resume=...)`, and `SQLDatabaseToolkit`. Run
`pip install -r requirements.txt` and a real `OPENAI_API_KEY` locally to
exercise it end-to-end — and if any package's API has shifted since this
was written, the fix is almost always a one-line import change in
`src/agent.py` or `src/action_tools.py`.
