# cli/forge_cli/commands/org_llm.py
"""forge org llm — per-org LLM provider configuration commands."""
from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forge_cli.api import ForgeClient, APIError, _load_config

console = Console()


def _make_client(api_url: str | None, api_key: str | None) -> ForgeClient:
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    key = api_key or cfg.get("api_key")
    return ForgeClient(url, api_key=key)


def _err(msg: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {msg}")
    sys.exit(1)


# ── Top-level group: forge org llm ───────────────────────────────────────────

@click.group("llm")
def org_llm_group() -> None:
    """Configure per-org LLM providers, models, and credentials."""


# ── forge org llm show ────────────────────────────────────────────────────────

@org_llm_group.command("show")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def llm_show(api_url: str | None, api_key: str | None) -> None:
    """Show active credentials and task → model configuration."""
    client = _make_client(api_url, api_key)
    try:
        creds = client._request("GET", "/api/v1/org/llm/credentials")
        task_cfg = client._request("GET", "/api/v1/org/llm/task-config")
    except APIError as e:
        _err(str(e))

    # Credential summary lines
    cred_lines: list[str] = []
    for c in creds:
        prov = c["provider"]
        if c["configured"]:
            if c.get("use_iam_role"):
                region = c.get("region") or "us-east-1"
                cred_lines.append(f"  [green]✓[/green] {prov:<12} IAM role · {region}")
            else:
                tested = c.get("last_tested_at")
                suffix = f" · last tested {tested[:10]}" if tested else ""
                cred_lines.append(f"  [green]✓[/green] {prov:<12} configured{suffix}")
        else:
            cred_lines.append(f"  [dim]✗ {prov:<12} not configured[/dim]")

    preset = task_cfg.get("preset", "custom")

    # Task table
    task_table = Table(show_header=True, header_style="bold orange1", box=None, padding=(0, 1))
    task_table.add_column("Task", style="cyan", no_wrap=True)
    task_table.add_column("Provider")
    task_table.add_column("Model")
    task_table.add_column("Source", style="dim")

    for task_name, spec in sorted(task_cfg.get("tasks", {}).items()):
        source = "default" if spec.get("from_default") else "custom"
        task_table.add_row(task_name, spec["provider"], spec["model"], source)

    cred_block = "\n".join(cred_lines) or "  (none configured)"
    console.print(Panel(
        f"[bold]Active credentials[/bold]\n{cred_block}\n\n"
        f"[bold]Preset:[/bold] {preset}",
        title="[bold]AI Provider Configuration[/bold]",
        border_style="orange1",
    ))
    console.print(task_table)


# ── forge org llm preset ──────────────────────────────────────────────────────

@org_llm_group.command("preset")
@click.argument("preset_name", metavar="PRESET",
                type=click.Choice(["smart", "balanced", "cheap"]))
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def llm_preset(preset_name: str, api_url: str | None, api_key: str | None) -> None:
    """Apply a model preset to all tasks.

    \b
    Presets:
      smart     — best models (Claude Sonnet / GPT-4 Turbo)
      balanced  — Forge defaults (mix of smart + cheap)
      cheap     — cheapest models (Haiku / GPT-4o-mini)
    """
    client = _make_client(api_url, api_key)
    try:
        result = client._request(
            "PUT", "/api/v1/org/llm/task-config",
            body={"preset": preset_name},
        )
    except APIError as e:
        _err(str(e))
    count = result.get("tasks_configured", 0)
    console.print(f"[green]✓[/green] Preset [bold]{preset_name}[/bold] applied ({count} tasks configured).")


# ── forge org llm set ─────────────────────────────────────────────────────────

@org_llm_group.command("set")
@click.argument("task_type")
@click.option("--provider", required=True,
              type=click.Choice(["anthropic", "openai", "bedrock", "azure"]),
              help="LLM provider")
@click.option("--model", required=True, help="Model name (e.g. gpt-4-turbo)")
@click.option("--max-tokens", type=int, default=None, help="Override max output tokens")
@click.option("--temperature", type=float, default=None, help="Override temperature (0.0–1.0)")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def llm_set(task_type: str, provider: str, model: str,
            max_tokens: int | None, temperature: float | None,
            api_url: str | None, api_key: str | None) -> None:
    """Set provider and model for a specific task type.

    \b
    Examples:
      forge org llm set findings_judge --provider openai --model gpt-4-turbo
      forge org llm set agent_brain --provider bedrock --model anthropic.claude-sonnet-4 --max-tokens 4096
    """
    client = _make_client(api_url, api_key)
    entry: dict = {"provider": provider, "model": model}
    if max_tokens is not None:
        entry["max_tokens"] = max_tokens
    if temperature is not None:
        entry["temperature"] = temperature
    try:
        client._request(
            "PUT", "/api/v1/org/llm/task-config",
            body={"custom": {task_type: entry}},
        )
    except APIError as e:
        _err(str(e))
    console.print(
        f"[green]✓[/green] Task [bold]{task_type}[/bold] → "
        f"[cyan]{provider}[/cyan] / [cyan]{model}[/cyan]"
    )


# ── forge org llm tiers ───────────────────────────────────────────────────────

# Mirror of backend/app/brain/llm_factory.py TASK_TIER_MAP and TIER_MODEL_MAP.
# Duplicated here so the CLI does not import the `app` backend package.
# Keep in sync when editing tier assignments in llm_factory.py.
_CLI_TASK_TIER_MAP: dict[str, str] = {
    "codebase_modeling":  "STANDARD",
    "campaign_planning":  "STANDARD",
    "code_analyzer":      "STANDARD",
    "semantic_modeler":   "LIGHT",
    "findings_judge":     "STANDARD",
    "execution_judge":    "HEAVY",
    "exploit_engine":     "HEAVY",
    "exploit_script":     "HEAVY",
    "poc_engine":         "HEAVY",
    "evasion_strategist": "HEAVY",
    "logic_modeler":      "LIGHT",
    "agent_brain":        "STANDARD",
    "challenger":         "STANDARD",
    "severity_assessor":  "LIGHT",
}

_CLI_TIER_MODEL_MAP: dict[str, dict[str, str]] = {
    "anthropic": {
        "LIGHT":    "claude-haiku-4-5-20251001",
        "STANDARD": "claude-sonnet-4-6",
        "HEAVY":    "claude-opus-4-7",
    },
    "openai": {
        "LIGHT":    "gpt-4o-mini",
        "STANDARD": "gpt-4o",
        "HEAVY":    "o1",
    },
    "bedrock": {
        "LIGHT":    "anthropic.claude-haiku-4",
        "STANDARD": "anthropic.claude-sonnet-4",
        "HEAVY":    "anthropic.claude-opus-4",
    },
    "azure": {
        "LIGHT":    "gpt-4o-mini",
        "STANDARD": "gpt-4-turbo",
        "HEAVY":    "gpt-4o",
    },
}

_TIER_STYLES: dict[str, str] = {
    "LIGHT":    "green",
    "STANDARD": "yellow",
    "HEAVY":    "red",
}


@org_llm_group.command("tiers")
def llm_tiers() -> None:
    """Show task → tier mapping and tier → model assignments per provider.

    \b
    Tiers route tasks to appropriately-priced models:
      LIGHT     — small/cheap models for low-complexity work
      STANDARD  — balanced models for typical analysis
      HEAVY     — top-tier models for exploitation and complex reasoning

    When an org has a credential configured for a provider but no explicit
    task-config override, requests automatically use the tier-mapped model.
    """
    table = Table(
        show_header=True,
        header_style="bold orange1",
        box=None,
        padding=(0, 1),
        title="[bold]Task Tier Routing[/bold]",
        title_style="bold",
    )
    table.add_column("Task Type", style="cyan", no_wrap=True)
    table.add_column("Tier", no_wrap=True)
    table.add_column("Anthropic")
    table.add_column("OpenAI")
    table.add_column("Bedrock")
    table.add_column("Azure")

    for task_name in sorted(_CLI_TASK_TIER_MAP):
        tier = _CLI_TASK_TIER_MAP[task_name]
        style = _TIER_STYLES.get(tier, "white")
        table.add_row(
            task_name,
            f"[{style}]{tier}[/{style}]",
            _CLI_TIER_MODEL_MAP["anthropic"][tier],
            _CLI_TIER_MODEL_MAP["openai"][tier],
            _CLI_TIER_MODEL_MAP["bedrock"][tier],
            _CLI_TIER_MODEL_MAP["azure"][tier],
        )

    console.print(table)
    console.print(
        "\n[dim]Tip: override per-task with[/dim] "
        "[cyan]forge org llm set <task> --provider <p> --model <m>[/cyan]"
    )


# ── forge org llm key ─────────────────────────────────────────────────────────

@org_llm_group.group("key")
def llm_key_group() -> None:
    """Manage provider API keys / IAM credentials."""


@llm_key_group.command("set")
@click.argument("provider",
                type=click.Choice(["anthropic", "openai", "bedrock", "azure"]))
@click.option("--iam-role", is_flag=True, help="Use IAM role instead of static key (Bedrock)")
@click.option("--region", default=None, help="AWS region (Bedrock)")
@click.option("--endpoint", default=None, help="Azure OpenAI endpoint URL")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def key_set(provider: str, iam_role: bool, region: str | None, endpoint: str | None,
            api_url: str | None, api_key: str | None) -> None:
    """Store a provider API key (prompts securely; hidden input).

    \b
    Examples:
      forge org llm key set anthropic
      forge org llm key set bedrock --iam-role --region us-east-1
      forge org llm key set azure --endpoint https://mydeployment.openai.azure.com
    """
    client = _make_client(api_url, api_key)

    raw_key: str | None = None
    if not iam_role:
        raw_key = click.prompt(
            f"API key for {provider}", hide_input=True, confirmation_prompt=False
        )
        if not raw_key.strip():
            _err("API key cannot be empty (omit --iam-role to enter a key, or use --iam-role for Bedrock IAM).")

    body: dict = {"use_iam_role": iam_role}
    if raw_key:
        body["api_key"] = raw_key
    if region:
        body["region"] = region
    if endpoint:
        body["endpoint"] = endpoint

    try:
        client._request("PUT", f"/api/v1/org/llm/credentials/{provider}", body=body)
    except APIError as e:
        _err(str(e))
    console.print(f"[green]✓[/green] Credentials for [bold]{provider}[/bold] saved.")


@llm_key_group.command("test")
@click.argument("provider",
                type=click.Choice(["anthropic", "openai", "bedrock", "azure"]))
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def key_test(provider: str, api_url: str | None, api_key: str | None) -> None:
    """Send a 1-token probe to validate stored credentials."""
    client = _make_client(api_url, api_key)
    with console.status(f"[bold]Testing {provider} credentials…[/bold]"):
        try:
            result = client._request("POST", f"/api/v1/org/llm/credentials/{provider}/test")
        except APIError as e:
            _err(str(e))

    if result.get("ok"):
        console.print(f"[green]✓[/green] [bold]{provider}[/bold] credentials are valid.")
    else:
        error_detail = result.get("error", "unknown error")
        console.print(f"[red]✗[/red] [bold]{provider}[/bold] test failed: {error_detail}")
        sys.exit(1)


@llm_key_group.command("revoke")
@click.argument("provider",
                type=click.Choice(["anthropic", "openai", "bedrock", "azure"]))
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def key_revoke(provider: str, yes: bool, api_url: str | None, api_key: str | None) -> None:
    """Delete stored credentials for a provider."""
    if not yes:
        click.confirm(f"Revoke credentials for {provider}?", abort=True)
    client = _make_client(api_url, api_key)
    try:
        client._request("DELETE", f"/api/v1/org/llm/credentials/{provider}")
    except APIError as e:
        _err(str(e))
    console.print(f"[green]✓[/green] Credentials for [bold]{provider}[/bold] revoked.")


# ── forge org llm usage ───────────────────────────────────────────────────────

@org_llm_group.command("usage")
@click.option("--since", default=None, metavar="ISO_DATETIME",
              help="Filter events after this datetime (e.g. 2026-01-01T00:00:00)")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def llm_usage(since: str | None, api_url: str | None, api_key: str | None) -> None:
    """Show LLM usage and cost aggregated by task, provider, and model."""
    client = _make_client(api_url, api_key)
    path = "/api/v1/org/llm/usage"
    if since:
        path += f"?since={since}"
    try:
        data = client._request("GET", path)
    except APIError as e:
        _err(str(e))

    rows = data.get("rows", [])
    total = data.get("total_cost_usd", 0.0)

    if not rows:
        console.print("[dim]No usage data found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold orange1", box=None, padding=(0, 1))
    table.add_column("Task", style="cyan")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Calls", justify="right")
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("Cost (USD)", justify="right")

    for r in sorted(rows, key=lambda x: -x.get("cost_usd", 0)):
        table.add_row(
            r.get("task", ""),
            r.get("provider", ""),
            r.get("model", ""),
            str(r.get("calls", 0)),
            f"{r.get('input_tokens', 0):,}",
            f"{r.get('output_tokens', 0):,}",
            f"${r.get('cost_usd', 0):.4f}",
        )

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] [orange1]${total:.4f}[/orange1]")
