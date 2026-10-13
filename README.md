# Request-to-Action

A full-stack workflow application that turns customer service messages
into reviewed calendar bookings.

An operator can inspect extracted details, request clarification,
review policy excerpts and an exact appointment proposal, and approve
execution through Google Calendar. Failed actions remain visible with
an execution history and retry support.

## Business problem

Service requests arrive as unstructured messages. Staff must identify
the requested service, collect missing details, check scheduling rules,
and transfer the information into a calendar.

This project demonstrates that workflow using HVAC, plumbing, and
electrical requests. It is a portfolio demonstration, not a live
customer deployment.

## Technology

- Backend: Python, FastAPI, Pydantic
- Frontend: React, TypeScript, Vite
- Storage: SQLite
- Integration: Google Calendar API with OAuth authorization
- Extraction: deterministic rules with optional OpenAI extraction
- Policy retrieval: keyword matching over Markdown documents
- Testing: pytest and FastAPI TestClient

## Workflow

1. Submit a customer message.
2. Extract service type, requested time window, and contact information.
3. Reject unsupported requests or flag missing information.
4. Add customer clarification while preserving previously collected fields.
5. Display relevant policy excerpts and a proposed appointment.
6. Approve the specific saved proposal.
7. Check calendar availability and create the event.
8. Record success or failure in the execution history.

A preview does not create an event or reserve a slot.

## Example

Customer message:

> Need a plumber Wednesday morning. Call 312-555-0100.

The application extracts:

- Service: plumbing
- Requested window: Wednesday morning
- Contact: 312-555-0100

It resolves the request into a dated proposal in America/Chicago.
The demo assigns morning appointments to 9–10 AM and afternoon
appointments to 1–2 PM.

Only approval triggers the calendar integration.

## Architecture

- `frontend/src/App.tsx`: operator dashboard and review workflow
- `frontend/src/api.ts`: typed backend API client
- `app/main.py`: request endpoints and workflow transitions
- `app/extract.py`: extraction, validation, and optional LLM fallback
- `app/policies.py`: policy retrieval and scheduling checks
- `app/calendar_api.py`: saved proposals and Google Calendar integration
- `app/db.py`: requests, execution history, and database access
- `policies/`: business policy documents
- `tests/test_flow.py`: isolated API workflow tests
- `evals/`: labeled extraction evaluation cases and runner

SQLite stores request details, policy excerpts, statuses, execution
history, and calendar proposal payloads.

## Local setup

Requires Python 3.11+ and Node.js with npm.

Run these commands from the repository folder containing `app/`,
`frontend/`, and `requirements.txt`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib tzdata pytest httpx
```

### Google Calendar configuration

1. Create a separate private calendar for demonstration bookings.
2. Enable the Google Calendar API in a Google Cloud project.
3. Configure the OAuth consent screen and permitted test users.
4. Create a Desktop OAuth client.
5. Save its downloaded credentials as `credentials.json` in the
   repository folder.
6. Run:

```powershell
.\.venv\Scripts\python.exe authorize_calendar.py
```

Authorization creates `token.json`.

Create `calendar_config.json` beside `authorize_calendar.py`:

```json
{
  "calendar_id": "YOUR_DEMO_CALENDAR_ID",
  "timezone": "America/Chicago"
}
```

Use the separate demo calendar's ID. The connector rejects `primary`.

Keep OAuth credentials, tokens, API keys, local databases, and actual
calendar configuration out of version control.

### Start the backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/health
- API documentation: http://127.0.0.1:8000/docs

The backend root `/` has no page and returns 404.

### Start the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Local URL printed by Vite, usually http://localhost:5173.
Vite proxies `/api` requests to the backend.

### Optional LLM extraction

Set `OPENAI_API_KEY` in the backend terminal before starting the server.
`OPENAI_MODEL` optionally selects the extraction model.

Without a key, the application uses rule-based extraction. Invalid
or failed LLM responses fall back to the rules.

Live LLM extraction has not yet been verified as part of the recorded
demo checks. Policy retrieval currently uses keyword matching, not
vector retrieval or a RAG answer-generation pipeline.

## Validation

Backend workflow tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_flow.py -q
```

Frontend type checking and build:

```powershell
cd frontend
npm run build
```

Recorded local results:

- 9 backend workflow tests passed.
- TypeScript checking and Vite production build passed.
- Real Google Calendar event creation was exercised manually.
- An occupied appointment slot was blocked during manual testing.
- Preview and approval were exercised through the updated dashboard.

The automated workflow tests use temporary databases and a mocked
calendar connector. They do not independently validate Google's API,
calendar availability logic, or connector concurrency behavior.

The extraction evaluation can be run separately:

```powershell
python -m evals.run_eval
```

Evaluation results should be regenerated after extraction changes.

## Reliability mechanisms

- Missing fields block approval.
- Scheduling checks are repeated before execution.
- Approval must reference the saved proposal ID.
- The event ID and dated payload are persisted before calendar execution.
- Retries reuse the saved event ID.
- The connector looks for an existing event before inserting another.
- Repeated approval of a booked request returns its recorded result.
- Calendar failures are recorded and can be retried.
- Availability checks ignore cancelled events and events marked free.

A process-local lock serializes connector calls in one server process.
Availability checking and event insertion are separate API operations;
this does not guarantee conflict prevention across other calendar
writers or multiple server processes.

## Demo scenarios

- Complete service request → preview → approval → booked.
- Missing contact or time → clarification → ready for review.
- Sunday request → scheduling clarification required.
- Account billing question → rejected as unsupported.
- Occupied appointment slot → action blocked.
- Simulated connector failure → retry → completed.

Use the dashboard's demo controls to simulate a connector failure.
This control is intended for local development.

## Bugs investigated

### Incorrect service classification

A broad match for `ac` could classify an account-related question as
an HVAC request. Service matching was tightened to avoid that case.

### Clarification did not update scheduling

A reply such as “Monday morning instead” may omit the service type.
Clarification handling now captures scheduling corrections separately
and preserves the existing service and contact fields.

### Calendar files were not found

Nested project folders caused configuration and authorization files
to be placed in the wrong location. The connector resolves these files
relative to its repository folder.

### Backend URL appeared broken

Opening port 8000 at `/` returned 404 because it is an API server.
The operator dashboard runs through Vite, usually on port 5173.

## Current limitations

- No operator authentication or role-based access control.
- The demo failure endpoint is not protected.
- Local Desktop OAuth setup is not a hosted multi-user OAuth flow.
- Service-area and cancellation rules are displayed but not enforced.
- Emergency scheduling exceptions are not implemented.
- Appointment times use fixed demo defaults.
- Complex dates and phrases such as “this” versus “next” need further work.
- Saved proposals require a new request when their appointment time expires.
- No multi-tenant isolation, load testing, or production SLA claims.
- Deployment and live LLM verification remain outstanding.

## FDE relevance

The project demonstrates translating a business workflow into software,
building a Python backend and TypeScript interface, integrating an
external API, investigating configuration failures, adding validation,
and documenting implementation behavior and limitations.

The service-business scenario is one example of the workflow pattern.
Applying it to another sector would require adapting its data model,
policies, integrations, and evaluation cases.