"""
Builds the Prep Kit deep agent.

Takes:  Settings, plus an optional checkpointer and store
Gives:  a compiled LangGraph graph

Layout of the virtual filesystem:
    /kit/       -> FilesystemBackend on output/kits/<jd-name>/ (real files)
    /memories/  -> StoreBackend, the candidate profile survives restarts
    /scratch/ and anything else -> StateBackend (in graph state only)

Human in the loop:
    confirm_skill_list  approve / reject      (you sign off the skill list)
    ask_candidate       respond               (you answer the agent's question)

Unlike RepoScout, file writes are NOT gated here. A kit has 15-30 notes
files and approving each one gets old fast. The skill list is the decision
that matters, so that's where the approval sits.
"""

from __future__ import annotations

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from langchain.agents.middleware import TodoListMiddleware

from .config import Settings
from .llm import get_chat_model
from .prompts import (
    GAP_REVIEWER_PROMPT,
    INTERVIEWER_PROMPT,
    MAIN_PROMPT,
    NOTE_WRITER_PROMPT,
)
from .tools import make_tools

MEMORY_FILE = "/memories/AGENTS.md"
MEMORY_NAMESPACE = ("prepkit", "memories")

# tools that pause the graph, and what the human is allowed to answer
INTERRUPTS = {
    "confirm_skill_list": {
        "allowed_decisions": ["approve", "reject"],
        "description": "Review the skills this kit will cover.",
    },
    "ask_candidate": {
        "allowed_decisions": ["respond"],
        "description": "The coach has a question for you.",
    },
}

RESPOND_TOOLS = {"ask_candidate"}


def build_agent(settings: Settings, checkpointer=None, store=None):
    model = get_chat_model(settings)
    analyse_jd, confirm_skill_list, ask_candidate, read_my_profile, coverage_report = make_tools(
        settings, model
    )

    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/kit/": FilesystemBackend(root_dir=settings.kit_dir, virtual_mode=True),
            "/memories/": StoreBackend(namespace=lambda _rt: MEMORY_NAMESPACE),
        },
    )

    subagents = [
        {
            "name": "note-writer",
            "description": (
                "Writes (or expands) in-depth study notes for ONE skill into the given "
                "/kit/notes/<skill>.md path. Give it the skill, the path, the role and "
                "what you know about the candidate."
            ),
            "system_prompt": NOTE_WRITER_PROMPT,
            "tools": [],
        },
        {
            "name": "interviewer",
            "description": "Writes /kit/mock_interview.md once all notes exist.",
            "system_prompt": INTERVIEWER_PROMPT,
            "tools": [],
        },
        {
            "name": "gap-reviewer",
            "description": "Reviews one notes file against the JD and fixes gaps in place. Give it the path.",
            "system_prompt": GAP_REVIEWER_PROMPT,
            "tools": [],
        },
    ]

    return create_deep_agent(
        model=model,
        tools=[analyse_jd, confirm_skill_list, ask_candidate, read_my_profile, coverage_report],
        system_prompt=MAIN_PROMPT,
        subagents=subagents,
        middleware=[TodoListMiddleware()],
        backend=backend,
        interrupt_on=INTERRUPTS,
        memory=[MEMORY_FILE],
        checkpointer=checkpointer,
        store=store,
        name="prepkit",
    )
