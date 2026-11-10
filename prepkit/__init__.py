"""
Prep Kit - turns a job description into an interview preparation kit.

Give it a JD (and optionally your resume) and it produces:
    skills.md             every skill the JD asks for, grouped and ranked
    notes/<skill>.md      in-depth study notes, one file per skill
    mock_interview.md     interview questions with model answers
    README.md             index of the kit with a suggested study order

Package layout:
    config.py      settings from env / .env
    llm.py         the local Ollama chat model
    extraction.py  structured skill extraction (pydantic + with_structured_output)
    tools.py       analyse_jd, confirm_skill_list, ask_candidate, coverage_report
    prompts.py     prompts for the main agent and subagents
    agent.py       wires it all into a deep agent
    graph.py       entry point for `langgraph dev`
    console.py     terminal output + human-in-the-loop prompts
    cli.py         python -m prepkit.cli
"""

__version__ = "0.1.0"
