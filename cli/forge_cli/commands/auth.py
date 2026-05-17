from __future__ import annotations
import json

import click

from forge_cli.api import ForgeClient, APIError, CONFIG_PATH, _load_config


def _save_api_key(api_url: str, api_key: str) -> None:
    cfg = _load_config()
    cfg["api_url"] = api_url
    cfg["api_key"] = api_key
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _auth_and_save(api_url: str, token: str) -> str:
    """Use a JWT to create a persistent CLI API key, save it, return the key."""
    tmp = ForgeClient(api_url, api_key=token)
    key_data = tmp.create_api_key("cli")
    key = key_data["key"]
    _save_api_key(api_url, key)
    return key


@click.command()
@click.option("--email", prompt=True)
@click.option("--password", prompt=True, hide_input=True)
@click.option("--org-name", prompt="Organisation name")
@click.option("--api-url", default=None)
def register(email: str, password: str, org_name: str, api_url: str | None) -> None:
    """Create a new account and organisation."""
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    client = ForgeClient(url)
    try:
        data = client.register(email, password, org_name)
        token = data["access_token"]
        _auth_and_save(url, token)
        role = data.get("role", "")
        click.echo(f"✓ Registered as {email}  [{role}]  org: {org_name}")
        click.echo(f"  API key saved to {CONFIG_PATH}")
    except APIError as e:
        raise click.ClickException(str(e))


@click.command()
@click.option("--email", prompt=True)
@click.option("--password", prompt=True, hide_input=True)
@click.option("--api-url", default=None)
def login(email: str, password: str, api_url: str | None) -> None:
    """Sign in and save an API key to ~/.forge/config.json."""
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    client = ForgeClient(url)
    try:
        data = client.login(email, password)
        token = data["access_token"]
        tmp = ForgeClient(url, api_key=token)
        me = tmp.me()
        _auth_and_save(url, token)
        role = me.get("role", "")
        org = me.get("org_name", me.get("org_id", "—"))
        click.echo(f"✓ Signed in as {email}  [{role}]  org: {org}")
        click.echo(f"  API key saved to {CONFIG_PATH}")
    except APIError as e:
        raise click.ClickException(str(e))


@click.command()
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def whoami(api_url: str | None, api_key: str | None) -> None:
    """Show the currently authenticated user."""
    from forge_cli.display import render_whoami
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    key = api_key or cfg.get("api_key")
    client = ForgeClient(url, api_key=key)
    try:
        me = client.me()
        render_whoami(me)
    except APIError as e:
        raise click.ClickException(str(e))


@click.command()
def logout() -> None:
    """Remove the saved API key from ~/.forge/config.json."""
    cfg = _load_config()
    if "api_key" not in cfg:
        click.echo("Not logged in.")
        return
    del cfg["api_key"]
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    click.echo("✓ Signed out — API key removed from config.")


@click.group("api-keys")
def api_keys_group() -> None:
    """Manage API keys for the current user."""


@api_keys_group.command("list")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def api_keys_list(api_url: str | None, api_key: str | None) -> None:
    """List your API keys."""
    from forge_cli.display import render_api_keys
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    key = api_key or cfg.get("api_key")
    client = ForgeClient(url, api_key=key)
    try:
        keys = client.list_api_keys()
        render_api_keys(keys)
    except APIError as e:
        raise click.ClickException(str(e))


@api_keys_group.command("create")
@click.argument("name")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def api_keys_create(name: str, api_url: str | None, api_key: str | None) -> None:
    """Create a new API key."""
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    key = api_key or cfg.get("api_key")
    client = ForgeClient(url, api_key=key)
    try:
        data = client.create_api_key(name)
        click.echo(f"Key: {data['key']}")
        click.echo("Save this — it won't be shown again.")
    except APIError as e:
        raise click.ClickException(str(e))


@api_keys_group.command("revoke")
@click.argument("key_id")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def api_keys_revoke(key_id: str, api_url: str | None, api_key: str | None) -> None:
    """Revoke an API key by its ID."""
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    key = api_key or cfg.get("api_key")
    client = ForgeClient(url, api_key=key)
    try:
        client.revoke_api_key(key_id)
        click.echo(f"✓ Key …{key_id[-8:]} revoked.")
    except APIError as e:
        raise click.ClickException(str(e))
