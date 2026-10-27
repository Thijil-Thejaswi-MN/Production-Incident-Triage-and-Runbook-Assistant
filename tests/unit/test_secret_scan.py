"""Tests for the D4 repository scanner.

Fake secrets are assembled at runtime so that this file itself never contains a
string the scanner would flag.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from triage.security.secret_scan import (
    candidate_files,
    is_code_path,
    main,
    scan_paths,
    scan_text,
)

FAKE = {
    "openai_style_key": "sk-" + "A1b2C3d4" * 4,
    "google_api_key": "AIza" + "x" * 35,
    "groq_api_key": "gsk_" + "Z9" * 15,
    "github_token": "ghp_" + "a" * 36,
    "aws_access_key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "private_key_block": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "bearer_token": "Authorization: " + "Bearer " + "q" * 32,
    "hardcoded_credential": 'api_key = "' + "r" * 16 + '"',
}


@pytest.mark.parametrize(("rule", "text"), sorted(FAKE.items()))
def test_each_credential_rule_detects_its_pattern_everywhere(rule: str, text: str) -> None:
    for path in ("docs/notes.md", "src/triage/x.py"):
        assert [f.rule for f in scan_text(text, path)] == [rule]


@pytest.mark.parametrize(
    "text",
    [
        'model = "' + "gpt-" + '4o-mini"',
        "LLM_MODEL=" + "claude-" + "sonnet-x",
        "name: " + "gemini-" + "2.0-flash",
        "Llama-" + "3.1-8b",
        "all-" + "MiniLM-L6-v2",
    ],
)
def test_model_identifiers_flagged_in_code_but_not_docs(text: str) -> None:
    assert [f.rule for f in scan_text(text, "src/triage/llm.py")] == ["model_identifier"]
    assert scan_text(text, "docs/architecture.md") == []


def test_endpoints_flagged_in_code_except_loopback() -> None:
    url = "https://" + "api.example-provider.com/v1"
    assert [f.rule for f in scan_text(f'BASE = "{url}"', "src/x.py")] == ["hardcoded_endpoint"]
    assert [f.rule for f in scan_text(url, "docker-compose.yml")] == ["hardcoded_endpoint"]
    assert scan_text(url, "README.md") == []
    assert scan_text('probe = "http://' + 'localhost:8000/health"', "docker/api.Dockerfile") == []


@pytest.mark.parametrize(
    "text",
    [
        "LLM_API_KEY=not-a-real-key-replace-me",
        "prompt_tokens = 1200",
        "api_key = settings.llm_api_key.get_secret_value()",
        'password = ""',
        "Use a bearer token from the environment.",
    ],
)
def test_benign_lines_are_not_flagged(text: str) -> None:
    assert scan_text(text, "src/triage/x.py") == []


def test_finding_reports_location_but_never_the_secret() -> None:
    (finding,) = scan_text("ok\n" + FAKE["openai_style_key"], "src/a.py")
    assert finding.line == 2
    assert FAKE["openai_style_key"] not in str(finding)
    assert str(finding) == "src/a.py:2: openai_style_key"


def test_code_path_classification() -> None:
    assert is_code_path("src/triage/config.py")
    assert is_code_path("docker-compose.yml")
    assert not is_code_path("docs/architecture.md")
    assert not is_code_path(".env.example")


def test_scan_paths_reads_files_and_skips_binaries(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leak.py").write_text("KEY = '" + FAKE["groq_api_key"] + "'\n")
    (tmp_path / "doc.pdf").write_bytes(b"%PDF " + FAKE["groq_api_key"].encode())
    (tmp_path / "clean.md").write_text("nothing here\n")
    findings = scan_paths(tmp_path, sorted(tmp_path.rglob("*")))
    assert {(f.path, f.rule) for f in findings} == {("src/leak.py", "groq_api_key")}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607


def test_cli_fails_on_planted_secret_and_tracked_env_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "app.py").write_text("TOKEN = '" + FAKE["github_token"] + "'\n")
    (tmp_path / ".env").write_text("LLM_API_KEY=whatever\n")
    _git(tmp_path, "add", "-f", ".env", "app.py")
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "app.py:1: github_token" in out
    assert ".env: tracked_env_file" in out
    assert FAKE["github_token"] not in out


def test_ignored_env_file_is_not_scanned(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text(".env\n")
    (tmp_path / ".env").write_text("LLM_API_KEY=" + FAKE["openai_style_key"] + "\n")
    names = {p.name for p in candidate_files(tmp_path)}
    assert ".env" not in names
    assert main([str(tmp_path)]) == 0


def test_repository_is_clean() -> None:
    findings = scan_paths(REPO_ROOT, candidate_files(REPO_ROOT))
    assert [str(f) for f in findings] == []
