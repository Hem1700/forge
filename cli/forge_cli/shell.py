"""Interactive FORGE shell — Metasploit-style REPL."""
from __future__ import annotations
import shlex
from pathlib import Path

from rich.console import Console
from rich.text import Text

console = Console()

_BANNER = """\

  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝\
"""

_COMPLETIONS = {
    "run": None,
    "list": None,
    "status": None,
    "findings": None,
    "exploit": None,
    "poc": None,
    "exploit-script": None,
    "execute": None,
    "report": None,
    "delete": None,
    "stats": None,
    "configure": None,
    "register": None,
    "login": None,
    "logout": None,
    "whoami": None,
    "api-keys": {"list": None, "create": None, "revoke": None},
    "users": {"list": None, "promote": None, "remove": None},
    "ci": {"scan": None, "report": None},
    "gate": {"approve": None, "reject": None},
    "help": None,
    "exit": None,
    "quit": None,
}


def _build_prompt():
    """Return a prompt callable, using prompt_toolkit when available."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.completion import NestedCompleter
        from prompt_toolkit.styles import Style

        hist = Path.home() / ".forge" / "history"
        hist.parent.mkdir(parents=True, exist_ok=True)

        session = PromptSession(
            history=FileHistory(str(hist)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=NestedCompleter.from_nested_dict(_COMPLETIONS),
            style=Style.from_dict({"prompt": "bold ansired"}),
        )

        def _prompt() -> str:
            return session.prompt([("class:prompt", "forge"), ("", "> ")])

        return _prompt

    except ImportError:
        # Fallback: plain input with readline history
        try:
            import readline
            hist = Path.home() / ".forge" / "history"
            hist.parent.mkdir(parents=True, exist_ok=True)
            try:
                readline.read_history_file(str(hist))
            except FileNotFoundError:
                pass
            import atexit
            atexit.register(readline.write_history_file, str(hist))
        except ImportError:
            pass

        def _prompt() -> str:
            return input("forge> ")

        return _prompt


def launch(cli_group) -> None:
    """Start the interactive FORGE shell."""
    import click

    prompt = _build_prompt()

    console.print(Text(_BANNER, style="bold red"))
    console.print()
    console.print("  [bold]Framework for Offensive Reasoning, Generation & Exploitation[/bold]")
    console.print(
        "  [dim]Type [bold white]help[/bold white] for commands  "
        "·  [bold white]help <cmd>[/bold white] for details  "
        "·  [bold white]exit[/bold white] to quit[/dim]"
    )
    console.print()

    while True:
        try:
            line = prompt().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not line:
            continue
        if line in ("exit", "quit"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if line == "help":
            _show_help(cli_group)
            continue
        if line.startswith("help "):
            _show_cmd_help(cli_group, line[5:].strip())
            continue

        try:
            args = shlex.split(line)
        except ValueError as e:
            console.print(f"  [red]Parse error:[/red] {e}")
            continue

        try:
            cli_group.main(args=args, prog_name="forge", standalone_mode=True)
        except SystemExit:
            pass
        except click.exceptions.Exit:
            pass
        except click.exceptions.Abort:
            console.print("[dim]Aborted.[/dim]")
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")


def _show_help(cli_group) -> None:
    import click
    with click.Context(cli_group, info_name="forge") as ctx:
        console.print(cli_group.get_help(ctx))


def _show_cmd_help(cli_group, cmd_name: str) -> None:
    import click
    parts = cmd_name.split()
    if not parts:
        _show_help(cli_group)
        return
    cmd = cli_group.commands.get(parts[0])
    if cmd is None:
        console.print(f"  [red]Unknown command:[/red] {parts[0]}")
        return
    for sub in parts[1:]:
        if hasattr(cmd, "commands"):
            sub_cmd = cmd.commands.get(sub)
            if sub_cmd is None:
                console.print(f"  [red]Unknown subcommand:[/red] {sub}")
                return
            cmd = sub_cmd
        else:
            break
    with click.Context(cmd, info_name=" ".join(parts)) as ctx:
        console.print(cmd.get_help(ctx))
