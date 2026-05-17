from __future__ import annotations

import click

from forge_cli.api import ForgeClient, APIError, _load_config

VALID_ROLES = ("viewer", "analyst", "admin", "super_admin")


def _make_client(api_url: str | None, api_key: str | None) -> ForgeClient:
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    key = api_key or cfg.get("api_key")
    return ForgeClient(url, api_key=key)


def _resolve_email(client: ForgeClient, email: str) -> str:
    users = client.list_org_users()
    for u in users:
        if u.get("email") == email:
            return u["id"]
    raise click.ClickException(f"No user with email {email} in your org.")


@click.group("users")
def users_group() -> None:
    """Manage users in your organisation (admin+)."""


@users_group.command("list")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def users_list(api_url: str | None, api_key: str | None) -> None:
    """List all users in your org."""
    from forge_cli.display import render_users
    client = _make_client(api_url, api_key)
    try:
        users = client.list_org_users()
        render_users(users)
    except APIError as e:
        raise click.ClickException(str(e))


@users_group.command("promote")
@click.argument("email")
@click.argument("role", type=click.Choice(VALID_ROLES))
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def users_promote(email: str, role: str, yes: bool,
                  api_url: str | None, api_key: str | None) -> None:
    """Set a user's role (admin+)."""
    client = _make_client(api_url, api_key)
    try:
        users = client.list_org_users()
        user = next((u for u in users if u.get("email") == email), None)
        if not user:
            raise click.ClickException(f"No user with email {email} in your org.")
        current = user.get("role", "?")
        if not yes:
            click.confirm(f"Change {email} from {current} → {role}?", abort=True)
        client.update_user_role(user["id"], role)
        click.echo(f"✓ {email} is now {role}.")
    except APIError as e:
        raise click.ClickException(str(e))


@users_group.command("remove")
@click.argument("email")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def users_remove(email: str, yes: bool,
                 api_url: str | None, api_key: str | None) -> None:
    """Remove a user from your org (admin+)."""
    client = _make_client(api_url, api_key)
    try:
        user_id = _resolve_email(client, email)
        if not yes:
            click.confirm(f"Remove {email} from your org?", abort=True)
        client.remove_user(user_id)
        click.echo(f"✓ {email} removed.")
    except APIError as e:
        raise click.ClickException(str(e))
