"""
Evaluate Prep Kit's skill extraction.

Extraction is the step everything else depends on: a skill that's missed
here never gets notes. So this eval runs the same `extract_skills()` the
agent's `analyse_jd` tool uses and checks it against hand-written answers.

Usage:
    python evals/run_evals.py --local      # no LangSmith, prints a table
    python evals/run_evals.py              # dataset + experiment in LangSmith

Takes:  evals/jd_cases.jsonl, one line per JD:
          {"jd_file": "samples/...md", "expected_skills": ["...", ...]}
Gives:  per JD
          skill_recall   share of expected skills that were extracted
          skills_found   how many skills came back (watch for wild jumps)
          missed         (local mode) which expected skills were not found

Matching is fuzzy on purpose: "A/B tests" counts for "A/B testing" and
"dimensional modeling" for "Dimensional modelling".

Add your own real JDs to jd_cases.jsonl - five or six cases from roles you
actually care about are worth more than the samples.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT))

from prepkit.config import load_settings  # noqa: E402
from prepkit.extraction import extract_skills  # noqa: E402
from prepkit.llm import get_chat_model  # noqa: E402

DATASET_NAME = "prepkit-skill-extraction"


def _stems(text: str) -> set[str]:
    # crude but effective: 4-char prefixes of each word
    return {w[:4] for w in re.findall(r"[a-z0-9+#]+", text.lower())}


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", text.lower())


def skill_matches(expected: str, found: list[str]) -> bool:
    want = _stems(expected)
    squashed = _squash(expected)
    for name in found:
        have = _stems(name)
        if want <= have or (have and have <= want):
            return True
        # "Spark" should match "PySpark"; too short a name ("Git") would over-match
        if len(squashed) >= 4 and squashed in _squash(name):
            return True
    return False


def load_cases() -> list[dict]:
    with (HERE / "jd_cases.jsonl").open(encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]
    for case in cases:
        case["jd_text"] = (PROJECT / case["jd_file"]).read_text(encoding="utf-8")
    return cases


def make_target():
    model = get_chat_model(load_settings())

    def target(inputs: dict) -> dict:
        analysis = extract_skills(model, inputs["jd_text"])
        return {"skills": [s.name for s in analysis.skills], "role": analysis.role_title}

    return target


def skill_recall(outputs: dict, reference_outputs: dict) -> dict:
    expected = reference_outputs["expected_skills"]
    found = outputs.get("skills", [])
    missed = [e for e in expected if not skill_matches(e, found)]
    score = 1 - len(missed) / len(expected) if expected else 1.0
    return {"key": "skill_recall", "score": score, "comment": f"missed: {missed}"}


def skills_found(outputs: dict) -> dict:
    return {"key": "skills_found", "score": len(outputs.get("skills", []))}


def run_local(cases: list[dict]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    target = make_target()
    table = Table(title="Prep Kit - skill extraction")
    for col in ("JD", "recall", "found", "missed"):
        table.add_column(col)

    total = 0.0
    for case in cases:
        console.print(f"[dim]extracting {case['jd_file']} ...[/]")
        outputs = target({"jd_text": case["jd_text"]})
        result = skill_recall(outputs, case)
        total += result["score"]
        table.add_row(case["jd_file"], f"{result['score']:.2f}", str(len(outputs["skills"])),
                      result["comment"].removeprefix("missed: "))
    table.add_row("[bold]average[/]", f"[bold]{total / len(cases):.2f}[/]", "", "")
    console.print(table)


def run_langsmith(cases: list[dict]) -> None:
    from langsmith import Client, evaluate

    if not os.getenv("LANGSMITH_API_KEY"):
        print("LANGSMITH_API_KEY is not set. Add it to .env or use --local.")
        raise SystemExit(1)

    client = Client()
    if not client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.create_dataset(DATASET_NAME, description="JDs with the skills a human expects")
        client.create_examples(
            dataset_id=ds.id,
            examples=[
                {
                    "inputs": {"jd_text": c["jd_text"]},
                    "outputs": {"expected_skills": c["expected_skills"]},
                    "metadata": {"jd_file": c["jd_file"]},
                }
                for c in cases
            ],
        )
        print(f"created dataset '{DATASET_NAME}'")

    model_name = load_settings().ollama_model
    evaluate(
        make_target(),
        data=DATASET_NAME,
        evaluators=[skill_recall, skills_found],
        experiment_prefix=f"extract-{model_name.replace(':', '-')}",
        metadata={"model": model_name},
        max_concurrency=1,
        client=client,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate skill extraction")
    parser.add_argument("--local", action="store_true", help="run without LangSmith")
    args = parser.parse_args()

    cases = load_cases()
    if args.local:
        run_local(cases)
    else:
        run_langsmith(cases)


if __name__ == "__main__":
    main()
