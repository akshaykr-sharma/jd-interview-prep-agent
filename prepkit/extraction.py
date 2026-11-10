"""
Structured skill extraction from a job description.

This is the one place where we ask the model for structured output instead
of free text. The agent calls it through the `analyse_jd` tool, and the eval
script calls it directly, so the two always test the same code path.

Takes:  a chat model and the raw JD text
Gives:  a `JDAnalysis` pydantic object:
            role_title, seniority, summary,
            skills: [Skill(name, category, priority, evidence)]

Small models sometimes return a skill twice with different casing, or an
empty name. `clean()` tidies that up so the rest of the pipeline can trust
the list.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field


class Skill(BaseModel):
    name: str = Field(description="Short skill name, e.g. 'PySpark', 'A/B testing', 'Stakeholder management'")
    category: Literal["language", "framework", "tool", "concept", "domain", "soft"] = Field(
        description="What kind of skill this is"
    )
    priority: Literal["must", "nice"] = Field(
        description="'must' if the JD requires it, 'nice' if it is a plus / preferred"
    )
    evidence: str = Field(description="The phrase from the JD that mentions this skill")


class JDAnalysis(BaseModel):
    role_title: str
    seniority: str = Field(description="e.g. junior, mid, senior, staff, lead, unknown")
    summary: str = Field(description="Two sentences on what the job is really about")
    skills: list[Skill]


EXTRACTION_PROMPT = """\
Read the job description below and list EVERY skill, tool, technology,
concept and soft skill it asks for. Be exhaustive - include items mentioned
only in passing, in the responsibilities, and in the "nice to have" part.
Split combined items ("AWS/GCP" -> two skills). Do not invent skills that
are not in the text.

Job description:
-----
{jd}
-----
"""


def clean(analysis: JDAnalysis) -> JDAnalysis:
    seen: dict[str, Skill] = {}
    for skill in analysis.skills:
        name = skill.name.strip()
        if not name:
            continue
        key = name.lower()
        # if the same skill shows up as both must and nice, keep "must"
        if key in seen and seen[key].priority == "must":
            continue
        seen[key] = skill.model_copy(update={"name": name})
    ordered = sorted(seen.values(), key=lambda s: (s.priority != "must", s.category, s.name.lower()))
    return analysis.model_copy(update={"skills": ordered})


def extract_skills(model: BaseChatModel, jd_text: str) -> JDAnalysis:
    structured = model.with_structured_output(JDAnalysis)
    result = structured.invoke(EXTRACTION_PROMPT.format(jd=jd_text))
    if isinstance(result, dict):  # some providers hand back a dict
        result = JDAnalysis.model_validate(result)
    return clean(result)


def to_markdown(analysis: JDAnalysis) -> str:
    lines = [
        f"# {analysis.role_title}",
        "",
        f"**Seniority:** {analysis.seniority}",
        "",
        analysis.summary,
        "",
        "| # | Skill | Category | Priority | From the JD |",
        "|---|---|---|---|---|",
    ]
    for i, s in enumerate(analysis.skills, 1):
        evidence = s.evidence.replace("|", "/").replace("\n", " ")
        lines.append(f"| {i} | {s.name} | {s.category} | {s.priority} | {evidence} |")
    return "\n".join(lines) + "\n"
