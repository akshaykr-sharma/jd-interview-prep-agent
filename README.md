# Prep Kit (JD → interview prep kit)

Give it a job description (and optionally your resume) and it builds a complete preparation kit:

```
output/kits/<jd-name>/
├── jd.md                 the JD it worked from
├── skills.md             every skill in the JD: category, must/nice, where it's mentioned
├── skills.json           same list, machine readable
├── notes/
│   ├── pyspark.md        in-depth notes, one file per skill
│   ├── mlflow.md
│   └── ...
├── mock_interview.md     4 rounds of questions with model answers
└── README.md             study order + links to every note
```

The agent is built to leave no gaps. It keeps checking coverage with a deterministic tool and keeps writing until every skill on the list has a proper notes file.

It stops twice to involve you:

1. **It asks you a question** (your experience level, interview date, weak areas). You type the answer, and the answer goes straight back to the agent.
2. **It shows you the skill list.** You approve it, or reject it with something like "drop Terraform, add system design". It fixes the list and asks you again.

Everything runs locally on Ollama. LangSmith is optional.

---

## What this project teaches (beyond RepoScout)

| Concept | Where to look |
|---|---|
| Structured output with pydantic (`with_structured_output`) | `extraction.py` |
| A tool that wraps an LLM call | `analyse_jd` in `tools.py` |
| HITL on a **custom tool** instead of a file write | `INTERRUPTS` in `agent.py` |
| The **respond** decision: the human is the tool | `ask_candidate` + `RESPOND_TOOLS` |
| A deterministic checker driving an agent loop | `coverage_report` + step 6 of `MAIN_PROMPT` |
| Memory of *you* across sessions | `/memories/AGENTS.md` (experience, weak areas) |
| Evaluating one step of an agent in isolation | `evals/run_evals.py` (extraction recall) |

---



## Project layout

```
prep-kit/
├── prepkit/
│   ├── __init__.py     package overview
│   ├── config.py       settings + kit folder naming
│   ├── llm.py          ChatOllama
│   ├── extraction.py   JDAnalysis schema + extract_skills()
│   ├── tools.py        analyse_jd, confirm_skill_list, ask_candidate, read_my_profile, coverage_report
│   ├── prompts.py      main + subagent prompts
│   ├── agent.py        backend, interrupts, subagents -> create_deep_agent
│   ├── graph.py        entry for `langgraph dev`
│   ├── console.py      terminal output + HITL prompts
│   └── cli.py          python -m prepkit.cli
├── samples/            three example JDs to play with
├── evals/
│   ├── jd_cases.jsonl  JDs + the skills a human expects
│   └── run_evals.py    extraction recall, local or LangSmith
├── langgraph.json
├── requirements.txt
└── .env.example
```

---

## Setup

Prerequisites: **Python 3.11+**, **Ollama** with `qwen2.5:7b` pulled (`ollama pull qwen2.5:7b`).

### macOS

```bash
cd prep-kit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Windows (PowerShell)

```powershell
cd prep-kit
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

(If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then reopen PowerShell.)

### Run

Try a sample first:

```bash
python -m prepkit.cli --jd samples/jd_genai_engineer.md
```

With your own JD and resume:

```bash
# macOS
python -m prepkit.cli --jd ~/Downloads/jd.md --resume ~/Documents/resume.md

# Windows
python -m prepkit.cli --jd C:\Users\you\Downloads\jd.md --resume C:\Users\you\Documents\resume.md
```

Copied a JD from a website? Paste it:

```bash
python -m prepkit.cli --paste
# paste, then type END on its own line
```

Your resume has to be text (`.md` or `.txt`). From a PDF, copy-paste into a text file. Converting it is out of scope here.

After the kit is built you're still in a chat, so you can ask for things like:

```
you: the Kafka notes are too shallow, expand the consumer groups section
you: add 5 more system design questions
you: /memory
```

The kit for a 15-skill JD takes a while on a laptop - roughly one model call chain per skill. Leave it running.

---

## LangGraph Studio (optional)

```bash
pip install "langgraph-cli[inmem]"
langgraph dev
```

Set `PREPKIT_JD_PATH` (and `PREPKIT_RESUME_PATH`) in `.env` first. In Studio you'll see the `ask_candidate` and `confirm_skill_list` interrupts as pause points. Resume them with a JSON payload like:

```json
{"decisions": [{"type": "respond", "message": "5 years, weak in Kubernetes"}]}
```

```json
{"decisions": [{"type": "reject", "message": "add system design, drop Terraform"}]}
```

---

## LangSmith (optional, free)

Same as the other projects. Free Developer plan, **no credit card** (hard cap of 5,000 traces/month without one). Set in `.env`:

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=prepkit
```

One full kit is one long trace. It's a good way to see how much context the main agent saves by handing each skill to a fresh note-writer.

---

## Evals

The eval checks the step everything depends on - did extraction find every skill in the JD?

```bash
python evals/run_evals.py --local     # prints recall per JD + which skills were missed
python evals/run_evals.py             # same, as a LangSmith experiment
```

To make it useful for you, add real JDs to `samples/` and a line for each in `evals/jd_cases.jsonl` with the skills *you* think matter. Then try:

- changing `EXTRACTION_PROMPT` in `extraction.py`
- a different model (`OLLAMA_MODEL=llama3.1:8b`)
- `temperature` 0 vs 0.2

and compare runs in LangSmith.

---

## Things to try

1. Answer `ask_candidate` with "I'm weak in Kubernetes" and check whether that note ends up longer and earlier in the study order.
2. Start a new session with a different JD and see if it still remembers your experience (`/memory`).
3. Raise `min_words` in the coverage check by asking: *"run coverage_report with min_words 1200 and fix everything it flags"*.
4. Swap the `confirm_skill_list` decisions to `["approve", "edit", "reject"]` and build an edit flow in `console.py`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `extraction failed` | The model returned broken JSON. It usually works on retry; `qwen2.5:7b` is more reliable here than most 7-8B models. |
| Notes are shallow | Small model limits. Run `gap-reviewer` on a note, or try a bigger model. |
| The agent stops before every note is written | Ask it to "run coverage_report and fix every gap". Raising `recursion_limit` in `cli.py` helps for long JDs. |
| Ollama connection errors | `ollama serve`, then check `ollama list` |
| Resume ignored | Must be `.md` or `.txt`, passed with `--resume` |
