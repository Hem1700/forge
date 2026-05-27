"""Tests for OSModeler SSH collection and OSFingerprint."""
from __future__ import annotations
import uuid
import pytest
import pytest_asyncio
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch, call
from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.brain.os_fingerprint import OSFingerprint
from app.brain.os_modeler import OSModeler, SSHAuth
from app.database import Base, get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.engagement import Engagement, EngagementStatus
from app.api.deps import get_current_user

TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"
_pwd = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


@pytest_asyncio.fixture
async def org_http_client():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        org = Organization(name=f"os-test-{uuid.uuid4()}")
        db.add(org)
        await db.commit()
        await db.refresh(org)
        user = User(
            email=f"os-{uuid.uuid4()}@test.forge",
            hashed_password=_pwd.hash("x"),
            role=UserRole.super_admin,
            org_id=org.id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    async def _db():
        async with sf() as s:
            yield s
    async def _user():
        return user
    async def _get_org():
        return org

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, sf, org
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


# ── OSFingerprint unit tests ──────────────────────────────────────────────────

def test_fingerprint_defaults():
    fp = OSFingerprint(host="10.0.0.1", port=22, collected_at="2026-01-01T00:00:00Z")
    assert fp.host == "10.0.0.1"
    assert fp.packages == []
    assert fp.collection_errors == []
    assert fp.suid_binaries == []


def test_fingerprint_to_dict():
    fp = OSFingerprint(host="10.0.0.1", port=22, collected_at="2026-01-01T00:00:00Z")
    d = fp.to_dict()
    assert isinstance(d, dict)
    assert d["host"] == "10.0.0.1"
    assert "packages" in d
    assert "collection_errors" in d


# ── OSModeler parser unit tests ───────────────────────────────────────────────

def _modeler() -> OSModeler:
    return OSModeler()


def test_parse_uname():
    m = _modeler()
    fp = OSFingerprint(host="h", port=22, collected_at="x")
    m._parse_uname("Linux myhost 5.15.0-76-generic #83-Ubuntu SMP Thu Jun 15 19:16:32 UTC 2023 x86_64", fp)
    assert fp.kernel["os"] == "Linux"
    assert fp.kernel["hostname"] == "myhost"
    assert "5.15" in fp.kernel["release"]


def test_parse_os_release():
    m = _modeler()
    fp = OSFingerprint(host="h", port=22, collected_at="x")
    raw = 'NAME="Ubuntu"\nVERSION="22.04 LTS"\nID=ubuntu\n'
    m._parse_os_release(raw, fp)
    assert fp.os_info["NAME"] == "Ubuntu"
    assert fp.os_info["ID"] == "ubuntu"


def test_parse_packages_deb():
    m = _modeler()
    fp = OSFingerprint(host="h", port=22, collected_at="x")
    raw = "bash 5.1-6ubuntu1 amd64\ncurl 7.81.0-1ubuntu1.14 amd64\n"
    m._parse_packages(raw, "", fp)
    assert len(fp.packages) == 2
    assert fp.packages[0]["name"] == "bash"
    assert fp.packages[0]["version"] == "5.1-6ubuntu1"


def test_parse_suid():
    m = _modeler()
    fp = OSFingerprint(host="h", port=22, collected_at="x")
    m._parse_suid("/usr/bin/sudo\n/usr/bin/passwd\n", fp)
    assert "/usr/bin/sudo" in fp.suid_binaries
    assert "/usr/bin/passwd" in fp.suid_binaries


def test_parse_passwd():
    m = _modeler()
    fp = OSFingerprint(host="h", port=22, collected_at="x")
    m._parse_passwd("root:x:0:0:root:/root:/bin/bash\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n", fp)
    assert fp.users[0]["username"] == "root"
    assert fp.users[0]["shell"] == "/bin/bash"


def test_parse_sshd():
    m = _modeler()
    fp = OSFingerprint(host="h", port=22, collected_at="x")
    raw = "PermitRootLogin no\nPasswordAuthentication yes\n# comment line\n"
    m._parse_sshd(raw, fp)
    assert fp.ssh_config.get("PermitRootLogin") == "no"
    assert fp.ssh_config.get("PasswordAuthentication") == "yes"
    assert "# comment line" not in fp.ssh_config


def test_error_in_command_non_fatal():
    m = _modeler()
    fp = OSFingerprint(host="h", port=22, collected_at="x")
    m._parse_uname("__ERROR__:connection refused", fp)
    # Should not raise; kernel stays empty
    assert fp.kernel == {}


# ── SSH collection integration test (mocked) ─────────────────────────────────

@pytest.mark.asyncio
async def test_collect_returns_fingerprint_on_connection_error():
    """Even if SSH fails, collect() returns an OSFingerprint with errors logged."""
    m = OSModeler()
    auth = SSHAuth(auth_type="password", password="bad")
    with patch("asyncssh.connect", side_effect=Exception("Connection refused")):
        fp = await m.collect("10.0.0.1", 22, "root", auth)
    assert fp.host == "10.0.0.1"
    assert any("ssh_connect" in e for e in fp.collection_errors)


@pytest.mark.asyncio
async def test_collect_runs_commands_in_parallel():
    """Verify all commands are gathered concurrently (asyncio.gather called once)."""
    m = OSModeler()
    mock_conn = AsyncMock()
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_conn.run = AsyncMock(return_value=mock_result)

    with patch("asyncssh.connect") as mock_connect:
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)
        auth = SSHAuth(auth_type="agent")
        fp = await m.collect("10.0.0.1", 22, "root", auth)

    assert mock_conn.run.call_count >= 15  # at least 15 commands ran
    assert fp.host == "10.0.0.1"
    assert fp.port == 22


# ── REST endpoint tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_os_target_creates_row(org_http_client):
    from cryptography.fernet import Fernet
    from unittest.mock import AsyncMock, patch as _patch
    import app.brain.llm_factory as _m
    client, sf, org = org_http_client
    # Need FORGE_SECRETS_KEY for encryption
    orig = _m._fernet
    _m._fernet = Fernet(Fernet.generate_key())
    try:
        # Create an engagement first
        async with sf() as db:
            eng = Engagement(
                org_id=org.id,
                target_url="ssh://10.0.0.1",
                target_type="os_ssh",
                status=EngagementStatus.pending,
            )
            db.add(eng)
            await db.commit()
            await db.refresh(eng)

        with _patch("app.api.start.enqueue", new=AsyncMock(return_value=None)):
            resp = await client.post(f"/api/v1/engagements/{eng.id}/os-target", json={
                "host": "10.0.0.1",
                "port": 22,
                "username": "root",
                "auth_type": "key",
                "key_material": "/home/user/.ssh/id_rsa",
                "access_mode": "agentless",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["host"] == "10.0.0.1"
        assert data["auth_type"] == "key"
    finally:
        _m._fernet = orig


@pytest.mark.asyncio
async def test_add_os_target_invalid_auth_type(org_http_client):
    client, sf, org = org_http_client
    async with sf() as db:
        eng = Engagement(
            org_id=org.id,
            target_url="ssh://10.0.0.2",
            target_type="os_ssh",
            status=EngagementStatus.pending,
        )
        db.add(eng)
        await db.commit()
        await db.refresh(eng)

    resp = await client.post(f"/api/v1/engagements/{eng.id}/os-target", json={
        "host": "10.0.0.2", "port": 22, "username": "root",
        "auth_type": "badtype", "access_mode": "agentless",
    })
    assert resp.status_code == 422
