"""CLI entry point.

Interactive:  python -m agent.main
Headless:    python -m agent.main -p "health check: CPU, RAM, disk, services"
             (--yes auto-approves tier 2 actions — scripted runs only, use with care)
"""

from __future__ import annotations

import argparse
import sys

from agent import audit, permissions
from agent.config import get_settings
from agent.model import make_model
from agent.prompts import SYSTEM_PROMPT


def build_agent():
    from pydantic_ai import Agent

    import tools

    settings = get_settings()
    audit.configure(settings.audit_dir)
    agent = Agent(make_model(settings), instructions=SYSTEM_PROMPT)
    registered = tools.register_all(agent)
    return agent, settings, registered


def _output(result) -> str:
    return getattr(result, "output", None) or getattr(result, "data", "")


def _fmt_usage(result) -> str:
    usage = result.usage()
    input_tokens = getattr(usage, "input_tokens", None) or getattr(usage, "request_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", None) or getattr(usage, "response_tokens", 0)
    return f"[tokens in={input_tokens} out={output_tokens}]"


def run_headless(agent, prompt: str, auto_approve: bool) -> int:
    permissions.set_auto_approve(auto_approve)
    try:
        result = agent.run_sync(prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    print(_output(result))
    return 0


def run_interactive(agent) -> int:
    history = None
    print(
        "Windows Ops Agent — interactive mode\n"
        "Ask things like:\n"
        "  - what's eating RAM right now?\n"
        "  - why is the bot down? check the logs from the last hour\n"
        "  - is postgres running? is port 5432 listening?\n"
        "  - pull the latest code and restart the service\n"
        "Type 'quit' to exit. Tier 2 actions require your approval before they run."
    )
    while True:
        try:
            question = input("\nyou> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if not question:
            continue
        if question.lower() in {"quit", "exit", "q"}:
            return 0
        try:
            result = agent.run_sync(question, message_history=history)
            history = result.all_messages()
            print(f"\n{_output(result)}\n{_fmt_usage(result)}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[error] {exc}\n(check OPENROUTER_API_KEY / MODEL_NAME / network)")


def main() -> int:
    # Windows consoles default to a legacy code page (cp1252); model output
    # can contain any unicode. Force UTF-8 with replacement so printing can
    # never crash the REPL or headless output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="windows-agent",
        description="Operations agent for this host (PydanticAI + OpenRouter).",
    )
    parser.add_argument("-p", "--print", metavar="PROMPT",
                        help="run a single prompt headlessly and print the result")
    parser.add_argument("--yes", action="store_true",
                        help="auto-approve tier 2 actions (headless automation only!)")
    args = parser.parse_args()

    if args.yes and not args.print:
        parser.error("--yes only makes sense together with --print (headless mode)")

    try:
        agent, settings, registered = build_agent()
    except RuntimeError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    print(
        f"[agent] model: {settings.model_name} | tools: {len(registered)} "
        f"| APP_DIR: {settings.app_dir} | platform: {sys.platform}",
        file=sys.stderr,
    )
    if sys.platform != "win32":
        print(
            "[agent] note: non-Windows dev machine — Windows-only tools "
            "(services, event log) are not registered.",
            file=sys.stderr,
        )
    if args.print:
        if args.yes:
            print("[agent] WARNING: tier 2 auto-approve enabled (--yes)", file=sys.stderr)
        return run_headless(agent, args.print, auto_approve=args.yes)
    return run_interactive(agent)


if __name__ == "__main__":
    raise SystemExit(main())