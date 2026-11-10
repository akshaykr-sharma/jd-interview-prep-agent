"""
Custom tools for Prep Kit.

Takes:  Settings (where the JD, resume and kit folder are) and the chat model
Gives:  `make_tools()` -> a list of LangChain tools:

    analyse_jd          runs structured extraction on the JD, returns the skill table
    confirm_skill_list  saves the final skill list - PAUSES for your approval first
    ask_candidate       asks you a question - you type the answer, the tool never runs
    read_my_profile     returns your resume/profile text if you gave one
    coverage_report     checks every approved skill has a notes file of decent length

Two kinds of human-in-the-loop live here (configured in agent.py):
    confirm_skill_list -> approve / reject. Rejecting with "drop X, add Y"
                          makes the agent call it again with a fixed list.
    ask_candidate      -> respond. Your typed answer becomes the tool result,
                          the Python body below is never executed.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool

from .config import Settings, slugify
from .extraction import JDAnalysis, Skill, extract_skills, to_markdown

KIT_MOUNT = "/kit/"


def note_path(skill_name: str) -> str:
    return f"{KIT_MOUNT}notes/{slugify(skill_name)}.md"


def _word_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").split())
    except OSError:
        return 0


def make_tools(settings: Settings, model: BaseChatModel) -> list:
    kit_dir = settings.kit_dir
    kit_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, JDAnalysis] = {}

    @tool
    def analyse_jd() -> str:
        """Read the job description and extract every skill it asks for.

        Returns the role, seniority, a summary and a table of skills with
        category and priority (must / nice). Call this once at the start,
        then show the list to the human with confirm_skill_list.
        """
        if not settings.jd_path.is_file():
            return f"Error: JD file not found at {settings.jd_path}"
        jd_text = settings.jd_path.read_text(encoding="utf-8", errors="replace")
        try:
            analysis = extract_skills(model, jd_text)
        except Exception as exc:  # small models occasionally return broken JSON
            return f"Error: extraction failed ({exc}). Try calling analyse_jd again."
        state["analysis"] = analysis
        (kit_dir / "jd.md").write_text(jd_text, encoding="utf-8")
        return to_markdown(analysis) + f"\n{len(analysis.skills)} skills found."

    @tool
    def confirm_skill_list(skills: list[str], reason: str = "") -> str:
        """Save the final list of skills the kit will cover. A human reviews it first.

        Args:
            skills: skill names, most important first. Usually the names from
                analyse_jd, adjusted by any feedback from the human.
            reason: one line on what you changed compared to the analysis, if anything.
        """
        known = {s.name.lower(): s for s in state["analysis"].skills} if "analysis" in state else {}
        final: list[Skill] = []
        for name in skills:
            name = name.strip()
            if not name:
                continue
            final.append(known.get(name.lower()) or Skill(
                name=name, category="concept", priority="must", evidence="added by reviewer"
            ))

        payload = [s.model_dump() | {"note": note_path(s.name)} for s in final]
        (kit_dir / "skills.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

        if "analysis" in state:
            md = to_markdown(state["analysis"].model_copy(update={"skills": final}))
            (kit_dir / "skills.md").write_text(md, encoding="utf-8")

        lines = [f"Saved {len(final)} skills. Write one notes file per skill at these paths:"]
        lines += [f"- {s.name} -> {note_path(s.name)}" for s in final]
        return "\n".join(lines)

    @tool
    def ask_candidate(question: str) -> str:
        """Ask the candidate (the human) a question and get their answer.

        Use it for things only they know: years of experience with something,
        interview date, which areas they feel weak in, how deep the notes
        should go. Ask one clear question at a time.

        Args:
            question: the question to ask.
        """
        # Never actually runs - the human's reply is returned in its place.
        return "The candidate did not answer."

    @tool
    def read_my_profile() -> str:
        """Return the candidate's resume / profile text, if one was provided.

        Use it to spot gaps between the JD and the candidate's experience so
        the notes spend more time on weak areas.
        """
        path = settings.resume_path
        if not path:
            return "No profile was provided. Ask the candidate with ask_candidate if you need to know something."
        if not path.is_file():
            return f"Error: profile file not found at {path}"
        if path.suffix.lower() not in {".md", ".txt"}:
            return "Error: profile must be a .md or .txt file - export your resume to text first."
        return path.read_text(encoding="utf-8", errors="replace")[:12000]

    @tool
    def coverage_report(min_words: int = 600) -> str:
        """Check the kit for gaps.

        Lists approved skills that have no notes file yet, notes that look too
        thin (fewer than min_words words), and whether mock_interview.md and
        README.md exist. Call it after writing notes and keep fixing until it
        reports no gaps.

        Args:
            min_words: word count below which a note counts as too thin.
        """
        skills_file = kit_dir / "skills.json"
        if not skills_file.exists():
            return "No approved skill list yet - call confirm_skill_list first."

        skills = json.loads(skills_file.read_text(encoding="utf-8"))
        missing, thin, ok = [], [], []
        for s in skills:
            rel = s["note"].removeprefix(KIT_MOUNT)
            words = _word_count(kit_dir / rel)
            if words == 0:
                missing.append(f"{s['name']} -> {s['note']}")
            elif words < min_words:
                thin.append(f"{s['name']} ({words} words) -> {s['note']}")
            else:
                ok.append(s["name"])

        report = [f"{len(ok)}/{len(skills)} skills fully covered."]
        if missing:
            report.append("MISSING notes:\n" + "\n".join(f"- {m}" for m in missing))
        if thin:
            report.append("TOO THIN, expand these:\n" + "\n".join(f"- {t}" for t in thin))
        for extra in ("mock_interview.md", "README.md"):
            report.append(f"{extra}: {'present' if (kit_dir / extra).exists() else 'MISSING'}")
        if not missing and not thin:
            report.append("No gaps in the notes.")
        return "\n".join(report)

    return [analyse_jd, confirm_skill_list, ask_candidate, read_my_profile, coverage_report]
