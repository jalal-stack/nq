"""Tests for the MVP import tooling (scripts/mvp_audit.py and scripts/import_mvp.ps1)."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "fake_mvp"

spec = importlib.util.spec_from_file_location("mvp_audit", REPO / "scripts" / "mvp_audit.py")
mvp_audit = importlib.util.module_from_spec(spec)
sys.modules["mvp_audit"] = mvp_audit  # dataclasses resolve their module via sys.modules
spec.loader.exec_module(mvp_audit)


@pytest.fixture(scope="module")
def result():
    findings, ctx = mvp_audit.audit(FIXTURE)
    return findings, ctx


def messages(findings, severity, area=None):
    return [f.message for f in findings if f.severity == severity and (area is None or f.area == area)]


def test_route_collision_and_mvp_only_routes(result):
    findings, ctx = result
    assert any("GET /api/v1/health" in m for m in messages(findings, "CONFLICT", "api"))
    statuses = {(r.method, r.path): s for r, _, s in ctx["routes"]}
    assert statuses[("GET", "/api/v1/health")] == "COLLISION"
    assert statuses[("POST", "/api/v1/proposals/{proposal_id}/approve")].startswith("MVP only")


def test_duplicate_engines_are_flagged_not_imported(result):
    dup = messages(result[0], "CONFLICT", "duplicate")
    for module in ("risk.py", "paper.py", "strategy.py"):
        assert any(module in m and "do not import" in m for m in dup)
    assert any("indicators ['ema', 'rsi']" in m for m in dup)


def test_schema_drift_and_type_findings(result):
    findings, ctx = result
    assert set(ctx["sql_tables"]) == {"proposals", "paper_orders", "equity_snapshots"}
    schema = messages(findings, "CONFLICT", "schema")
    assert any("equity_snapshots` is in SQL migrations but has no SQLAlchemy model" in m for m in schema)
    assert any("paper_orders.status` values" in m and "'open'" in m for m in schema)
    warns = messages(findings, "WARN", "schema")
    assert any("proposals.entry_price` is `double precision`" in m for m in warns)
    assert any("proposals.created_at` is timezone-naive" in m for m in warns)
    assert any("upper-case values" in m for m in warns)
    # TIMESTAMPTZ and DateTime(timezone=True) are fine
    assert not any("filled_at" in m for m in warns)


def test_live_order_code_is_a_blocker(result):
    blockers = messages(result[0], "BLOCKER")
    assert blockers == ["`backend/app/paper.py:10` exchange order submission"]


def test_canonical_code_has_no_live_trading_paths():
    # Same scanner as the MVP audit, applied to everything that ships. Ported MVP code must pass it too.
    shipped = REPO / "backend" / "trademind"
    files = [p for p in shipped.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    blockers = [f.message for f in mvp_audit.scan(files, shipped) if f.severity == "BLOCKER"]
    assert blockers == []


def test_report_and_exit_code(tmp_path):
    out = tmp_path / "report.md"
    assert mvp_audit.main([str(FIXTURE), "--out", str(out)]) == 1
    text = out.read_text(encoding="utf-8")
    assert "1 blocker(s)" in text and "| `DATABASE_URL` | none" in text
    assert "| `STARTING_EQUITY` | `TRADEMIND_STARTING_EQUITY` |" in text
    assert "| sqlalchemy | `==2.0.35` | not a dependency yet |" in text


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell not installed")
def test_import_script_quarantines_and_excludes(tmp_path):
    src = tmp_path / "TradeMind_AI_MVP_v2" / "trademind-ai-mvp"
    shutil.copytree(FIXTURE, src)
    (src / ".env").write_text("DATABASE_URL=postgresql://u:p@h/db\n")
    (src / "backend" / "Dockerfile").write_text("FROM python:3.12\n")
    (src / ".venv").mkdir()
    (src / ".venv" / "x.py").write_text("")
    dest = tmp_path / "legacy" / "mvp"
    cmd = ["pwsh", "-NoProfile", "-File", str(REPO / "scripts" / "import_mvp.ps1"),
           "-Source", str(src.parent), "-Destination", str(dest), "-SkipBranchCheck"]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=REPO)
    report = REPO / "docs" / "MVP_INTEGRATION_REPORT.md"
    try:
        assert run.returncode == 0, run.stdout + run.stderr
        assert (dest / "backend" / "app" / "risk.py").exists()
        assert not (dest / ".env").exists() and not (dest / "backend" / "Dockerfile").exists()
        assert not (dest / ".venv").exists()
        manifest = (dest / "IMPORT_MANIFEST.txt").read_text()
        assert ".env (secrets file)" in manifest and str(tmp_path) not in manifest
        # Second run refuses to overwrite.
        again = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=REPO)
        assert again.returncode == 1 and "-Force" in again.stdout
    finally:
        report.unlink(missing_ok=True)


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell not installed")
def test_import_script_blocks_secrets(tmp_path):
    src = tmp_path / "mvp"
    shutil.copytree(FIXTURE, src)
    cfg = src / "backend" / "app" / "config.py"
    cfg.write_text(cfg.read_text() + '\nANTHROPIC_API_KEY = "sk-ant-abcdefghijklmnop1234567890"\n')
    dest = tmp_path / "out"
    run = subprocess.run(["pwsh", "-NoProfile", "-File", str(REPO / "scripts" / "import_mvp.ps1"),
                          "-Source", str(src), "-Destination", str(dest), "-SkipBranchCheck"],
                         capture_output=True, text=True, timeout=120, cwd=REPO)
    assert run.returncode == 1 and "backend/app/config.py" in run.stdout.replace("\\", "/")
    assert not dest.exists()
