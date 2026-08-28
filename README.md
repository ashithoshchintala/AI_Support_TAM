# AI Support & TAM Copilot

An AI-assisted customer-support and Technical Account Management system that performs structured support-ticket triage and generates grounded account briefs from customer and ticket data.

The application uses Gemini for structured generation, deterministic local retrieval and validation for grounding, Pydantic for output enforcement, and Streamlit for the user interface.

## Features

### Task 1: Support-ticket triage

* Accepts raw ticket text or structured `subject` and `body` input
* Classifies product area, issue category, and urgency
* Recommends the appropriate support team
* Searches the local knowledge base for known issues
* Produces a customer-facing draft response
* Redacts common forms of PII before external model processing
* Treats instructions inside ticket text as untrusted input

### Task 2: TAM account brief

* Retrieves account information and tickets from the latest 90-day window
* Produces an executive summary
* Identifies supported risks and flagged issues
* Requires recent ticket quotes for churn and escalation risks
* Validates every supplied quote against its source ticket
* Returns three to five recommended talking points
* Handles missing accounts with a controlled error
* Uses stable ordering and deterministic preprocessing

## Project structure

```text
.
├── app/
│   ├── prompts/              # Versioned Task 1 and Task 2 prompts
│   ├── utils/                # PII-redaction utilities
│   ├── config.py             # Environment and path configuration
│   ├── data_loader.py        # JSON loading and validation
│   ├── data_repository.py    # Account and ticket access
│   ├── llm_client.py         # Gemini structured-output client
│   ├── retrieval.py          # Knowledge-base retrieval
│   ├── schemas.py            # Pydantic input/output models
│   ├── tam_context.py        # Grounded TAM context construction
│   ├── tam_summarizer.py     # Task 2 pipeline
│   └── triage_agent.py       # Task 1 pipeline
├── data/
│   ├── accounts.json
│   └── tickets.json
├── evals/
│   ├── run_evals.py
│   ├── scoring.py
│   └── test_cases.py
├── knowledge-base/           # Local support documentation
├── tests/
│   └── test_core.py
├── DESIGN.md                 # Architecture and trade-off analysis
├── eval_report.json          # Machine-readable evaluation results
├── eval_report.md            # Human-readable evaluation results
├── requirements.txt
└── streamlit_app.py          # Streamlit interface
```

## Requirements

* Python 3.11 or newer
* A Gemini API key
* Internet access when running model-backed workflows

## Installation

Clone the repository and enter the project directory:

```bash
git clone <repository-url>
cd AI_Suppot_TAM
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

For macOS or Linux:

```bash
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

Copy the environment template.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS or Linux:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
LLM_API_KEY=your_gemini_api_key
LLM_MODEL=gemini-3.6-flash
LLM_TEMPERATURE=0.0
```

Never commit the real `.env` file or an API key.

## Run the application

From the project root:

```bash
streamlit run streamlit_app.py
```

Streamlit will display a local address, normally:

```text
http://localhost:8501
```

The interface contains two tabs:

1. **Ticket Triage** for Task 1
2. **TAM Account Brief** for Task 2

## Example inputs

### Ticket-triage example

```text
Subject: SecureVault production authentication outage

Body: All production authentication requests are failing with
AUTH_TOKEN_EXPIRED. No users can access SecureVault.
```

Expected classification includes P1 urgency, Authentication product area, Bug category, Incident Response routing, and a grounded SecureVault knowledge-base match.

The same workflow also accepts raw text:

```text
A user cannot reset their password and needs instructions to regain access.
```

### Account-brief example

```text
ACC-1256
```

The generated output contains exactly:

1. Executive summary
2. Open risks and flagged issues
3. Recommended talking points

## Programmatic usage

Task 1:

```python
from app.triage_agent import triage_ticket

result = triage_ticket(
    {
        "subject": "Production authentication outage",
        "body": (
            "All authentication requests fail with "
            "AUTH_TOKEN_EXPIRED."
        ),
    }
)

print(result.model_dump_json(indent=2))
```

Task 2:

```python
from app.tam_summarizer import summarize_account

brief = summarize_account("ACC-1256")

print(brief.model_dump_json(indent=2))
```

## Automated tests

Run the deterministic test suite:

```bash
pytest -q
```

Current result:

```text
8 passed
```

These tests do not call Gemini. They cover dataset loading, account matching, 90-day filtering, ticket ordering, knowledge-base confidence, missing-account handling, and PII redaction.

## Evaluation harness

Run all ten end-to-end evaluation cases:

```bash
python -m evals.run_evals
```

The runner writes:

```text
eval_report.json
eval_report.md
```

Current evaluation results:

| Evaluation group | Passed | Total | Average quality |
| ---------------- | -----: | ----: | --------------: |
| Task 1           |      5 |     5 |             1.0 |
| Task 2           |      5 |     5 |             1.0 |
| Overall          |     10 |    10 |             1.0 |

Each task includes an adversarial case. The evaluation uses deterministic acceptance checks and records strict pass/fail status, named check scores, and an overall quality score between zero and one.

## Grounding and safety

The application includes several safeguards:

* Pydantic validation for inputs and structured outputs
* PII redaction before external model requests
* Local knowledge-base grounding
* Confidence requirements for known-issue claims
* Exact source-ticket validation for direct quotes
* Controlled errors for unknown accounts
* Prompt-injection resistance
* Versioned prompts
* Stable ticket ordering
* No API keys or internal matching metadata in UI output

The account repository supports a documented exact company-name fallback because the supplied dataset contains inconsistent account identifiers. This fallback produces an internal warning and does not silently fabricate a match.

## Design decisions and limitations

See [DESIGN.md](DESIGN.md) for the full architecture, security approach, evaluation strategy, and trade-off analysis.

The rule-based evaluation system is reproducible and inexpensive, but it cannot assess every aspect of natural-language quality. Strict quote validation can omit a genuine risk when no qualifying recent ticket quote exists; this conservative behaviour is intentional because unsupported risk claims are more harmful than incomplete ones.

## Video demonstration

Loom walkthrough: https://drive.google.com/file/d/1PiUvI9Jg0Ss-wCGiLYceR4Ou3wyMtBL-/view?usp=sharing