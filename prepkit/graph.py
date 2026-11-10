"""
Graph entry point for `langgraph dev` and LangGraph Studio.

Takes:  .env settings - PREPKIT_JD_PATH picks the job description,
        PREPKIT_RESUME_PATH (optional) your profile
Gives:  the module-level `agent` referenced in langgraph.json

The dev server supplies its own checkpointer and store.
"""

from prepkit.agent import build_agent
from prepkit.config import load_settings

agent = build_agent(load_settings())
