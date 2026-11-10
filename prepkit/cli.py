"""
Command line app for Prep Kit.

Usage:
    python -m prepkit.cli --jd samples/jd_ml_engineer.md
    python -m prepkit.cli --jd path/to/jd.md --resume path/to/resume.md
    python -m prepkit.cli --paste                      # paste a JD into the terminal
    python -m prepkit.cli --jd jd.md --session kit-1a2b3c4d   # continue later

Takes:  a JD file (or pasted text), optionally a resume in .md/.txt
Gives:  a kit folder under output/kits/<jd-name>/, plus a chat where you can
        ask for changes ("expand the Kafka notes", "add system design questions")

On the way the agent stops twice:
    - to ask you a question (type your answer)
    - to show you the skill list (approve, or reject with what to change)
"""

from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import datetime

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore
from rich.prompt import Prompt

from .agent import MEMORY_NAMESPACE, RESPOND_TOOLS, build_agent
from .config import PROJECT_ROOT, langsmith_enabled, load_settings, slugify
from .console import console, run_turn, show_todos

KICKOFF = "Build my complete interview prep kit for this job description."


def read_pasted_jd() -> str:
    console.print("Paste the job description. Finish with a line containing only [bold]END[/]:")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def save_pasted_jd(text: str):
    folder = PROJECT_ROOT / "output" / "jds"
    folder.mkdir(parents=True, exist_ok=True)
    first_line = next((l for l in text.splitlines() if l.strip()), "pasted-jd")
    name = slugify(first_line, max_len=40)  # safe on Windows too
    path = folder / f"{name}-{datetime.now():%Y%m%d-%H%M}.md"
    path.write_text(text, encoding="utf-8")
    return path

def open_persistence(data_dir):
    """Open the checkpointer and the store on two separate connections.

    They must not share one: SqliteStore runs its own BEGIN/COMMIT and needs
    an autocommit connection (isolation_level=None), while SqliteSaver
    commits on its own schedule. On a shared connection one commits the
    other's transaction and you get "cannot commit - no transaction is active".
    """
    db = data_dir / "prepkit.db"
    saver_conn = sqlite3.connect(db, check_same_thread=False)
    store_conn = sqlite3.connect(db, check_same_thread=False, isolation_level=None)
    store = SqliteStore(store_conn)
    store.setup()
    return SqliteSaver(saver_conn), store, (saver_conn, store_conn)

def main() -> None:
    parser = argparse.ArgumentParser(description="Prep Kit - JD to interview prep kit")
    parser.add_argument("--jd", help="job description file (.md or .txt)")
    parser.add_argument("--paste", action="store_true", help="paste the JD instead of passing a file")
    parser.add_argument("--resume", help="optional resume/profile file (.md or .txt)")
    parser.add_argument("--session", help="session name to continue")
    args = parser.parse_args()

    settings = load_settings()
    if args.paste:
        text = read_pasted_jd()
        if not text:
            console.print("[red]No JD pasted.[/]")
            raise SystemExit(1)
        settings = settings.with_inputs(jd=save_pasted_jd(text))
    settings = settings.with_inputs(jd=args.jd, resume=args.resume)

    if not settings.jd_path.is_file():
        console.print(f"[red]JD not found:[/] {settings.jd_path}")
        raise SystemExit(1)

    checkpointer, store, conns = open_persistence(settings.data_dir)
    agent = build_agent(settings, checkpointer=checkpointer, store=store)

    session = args.session or f"kit-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": session}, "recursion_limit": 300}

    console.rule("[bold]Prep Kit")
    console.print(f"JD       : {settings.jd_path}")
    console.print(f"profile  : {settings.resume_path or '-'}")
    console.print(f"kit      : {settings.kit_dir}")
    console.print(f"model    : {settings.ollama_model} (ctx {settings.num_ctx})")
    console.print(f"session  : {session}")
    console.print(f"langsmith: {'tracing on' if langsmith_enabled() else 'off'}")
    console.print("[dim]/todos plan, /memory what it knows about you, /quit exit[/]\n")

    # a resumed session already has the kit underway, so don't kick off again
    first = None if args.session else KICKOFF

    try:
        while True:
            text = (first or Prompt.ask("[bold]you[/]")).strip()
            first = None
            if not text:
                continue
            if text in ("/quit", "/exit"):
                break
            if text == "/todos":
                state = agent.get_state(config)
                show_todos(state.values.get("todos", []) if state.values else [])
                continue
            if text == "/memory":
                item = store.get(MEMORY_NAMESPACE, "/AGENTS.md")
                console.print(item.value.get("content", "") if item else "[dim]nothing saved yet[/]")
                continue
            run_turn(agent, {"messages": [{"role": "user", "content": text}]}, config,
                     respond_tools=RESPOND_TOOLS)
    except KeyboardInterrupt:
        console.print("\n[dim]bye[/]")
    finally:
        for conn in conns:
            conn.close()


if __name__ == "__main__":
    main()
