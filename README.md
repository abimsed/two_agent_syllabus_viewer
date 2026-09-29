# Two-Agent Syllabus Lens

Prototype frontend + anchoring layer for the modified Generative Agents syllabus-reading experiment.

## What this keeps from the current research backend

Each detected syllabus concept is sent to **Abi** and **Tim** in document reading order. The agent response remains exactly four structured fields:

- `internal_monologue`
- `perceived_concerns`
- `confidence_to_succeed`
- `immediate_next_step`

Agent working memory is maintained independently for Abi and Tim so earlier syllabus reactions can influence later sections.

## What this adds

1. Upload any text-based PDF syllabus.
2. Extract text blocks and bounding boxes with PyMuPDF.
3. Locate six canonical syllabus concepts using content-based matching, not page numbers.
4. Run Abi and Tim on the matched passage plus nearby context.
5. Render the original PDF as page images.
6. Overlay clickable annotations at the matched source text.
7. Switch between **Abi**, **Tim**, and **Compare**.

The page number and bounding box are UI metadata only; they are not added to the agent output.

## Project structure

```text
app.py                 FastAPI server
pdf_pipeline.py        PDF extraction, concept matching, page rendering
agent_backend.py       Adapter to the existing Persona + Ollama backend
templates/index.html   Main UI
static/app.js          Viewer behavior and anchored reactions
static/style.css       UI styling
```

## 1. Frontend-only test

This lets you test upload, PDF matching, markers, and Compare mode without the Generative Agents repo.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
MOCK_AGENTS=1 uvicorn app:app --reload
```

Open `http://127.0.0.1:8000`.

## 2. Connect your existing Ollama / Generative Agents backend

The adapter intentionally uses the same imports as `test_syllabus_onboarding.py`:

```python
from persona.persona import Persona
from persona.prompt_template.gpt_structure import GPT_request
```

Before starting the app, set:

```bash

export GENERATIVE_AGENTS_ROOT="/Users/{user}/{user}/practice/generative_agents_ollama/reverie/backend_server"
export PERSONA_STORAGE_BASE="/Users/{user}/{user}/practice/generative_agents_ollama/environment/frontend_server/storage/base_gen_students/personas"

python3 uvicorn app:app --reload
```

If your project root is the directory *above* `environment/frontend_server`, change `GENERATIVE_AGENTS_ROOT` accordingly so `import persona...` works exactly as it does in your current script.

## Current concept matcher

The prototype recognizes:

- Course Overview & Prerequisites
- Required Toolchain & Software
- Grading Scheme & Project Weights
- Late Submission & Deadlines
- Academic Dishonesty & Collaboration Rules
- Attendance & Participation Policy

Matching uses keyword/phrase scoring against **all PDF text blocks**, then chooses the strongest block. This is deliberately simple and transparent for the MVP.

### Why not page numbers?

A topic stores an anchor like:

```json
{
  "topic_id": "late_submission",
  "page": 4,
  "bbox": [72.3, 318.1, 497.0, 366.4],
  "anchor_text": "Assignments submitted after the deadline ...",
  "confidence": 0.87
}
```

If another syllabus places that policy on page 7, the extracted text is matched again and a new anchor is produced automatically.

## Recommended next improvements

- Merge adjacent blocks into full semantic sections before agent inference.
- Add a minimum-confidence threshold and an "unanchored reactions" tray.
- Add fuzzy / embedding-based fallback matching for unusual wording.
- Store processed documents and reactions in SQLite instead of memory.
- Add scanned-PDF OCR only when text extraction returns too little text.
- Add an audit/debug view showing exactly what passage was sent to each agent.

## Important research note

The UI labels the model responses as **simulated student reactions**. The matcher confidence refers only to where the syllabus concept was anchored in the PDF; it does not measure the validity of the simulated behavior.


## Python 3.9 / PyMuPDF note

This prototype supports Python 3.9 by pinning `PyMuPDF==1.26.5`. Newer PyMuPDF releases require Python 3.10+.

If `ModuleNotFoundError: No module named 'fitz'` or `No module named 'pymupdf'` appears, install dependencies with the same Python interpreter that launches Uvicorn:

```bash
python3 -m pip install -r requirements.txt
python3 -c "import pymupdf; print(pymupdf.__doc__[:80])"
python3 -m uvicorn app:app --reload
```

Using `python3 -m uvicorn` instead of the bare `uvicorn` command helps ensure Uvicorn and the installed packages use the same Python environment.

## Expanded syllabus concept coverage

The matcher now uses generic syllabus concepts rather than CS201-specific wording. It can anchor reactions for:

- Course Overview & Prerequisites
- Learning Objectives & Outcomes
- Textbooks & Course Materials
- Technology, Programming Languages & Software
- Grading Scheme & Assessment Weights
- Late Work, Deadlines & Submission Rules
- Academic Integrity & Collaboration Rules
- Attendance & Participation Policy
- Course Schedule & Important Dates
- Student Support & Accommodations

Programming-language detection is no longer Java-specific. The technology matcher recognizes generic phrases such as `programming language`, `IDE`, `compiler`, `runtime`, `software requirements`, and a broad set of common languages/tools. The matcher also recognizes common learning-outcome wording such as `students will be able to...` and course-material wording such as `required text`, `ISBN`, and `course materials`.

This remains a transparent rule-based MVP. A later version can add embeddings or local-model classification as a fallback for sections whose wording does not match the rules confidently.

## Table-aware syllabus extraction

The PDF ingestion layer now extracts both ordinary text blocks and tables. It uses PyMuPDF's line-based table detection for bordered tables and a text-alignment fallback for borderless tables. Tables are converted to a row/column-preserving text representation such as `Week | Topic | Reading | Assignment`, so the same concept matcher and two-agent backend can analyze them.

For `Course Schedule & Important Dates`, schedule-like tables that span multiple PDF pages are combined into one conceptual section before the Abi/Tim simulation runs. The UI still anchors the reaction to the strongest matching table location in the PDF.
