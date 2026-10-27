"""Repository scanner for committed secrets, endpoints and model identifiers (requirement D4).

Two rule scopes:

* Credential rules apply to every text file in the repository.
* Endpoint and model-identifier rules apply to code and configuration
  (`src/`, `services/`, `scripts/`, `docker/`, compose files). Documentation may
  name the technologies it describes; code must take them from the environment.

Usage: ``python -m triage.security.secret_scan [ROOT]`` — exits 1 on any finding.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

CODE_DIRS = ("src", "services", "scripts", "docker")
CODE_FILES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
BINARY_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".gz", ".whl", ".pyc"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
# Loopback addresses (e.g. in-container health checks) are not environment endpoints.
ALLOWED_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")  # noqa: S104 - a pattern, not a bind


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    code_only: bool


RULES: tuple[Rule, ...] = (
    Rule("openai_style_key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"), False),
    Rule("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), False),
    Rule("groq_api_key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), False),
    Rule("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), False),
    Rule("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), False),
    Rule("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), False),
    Rule("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-.=]{20,}"), False),
    Rule(
        "hardcoded_credential",
        re.compile(
            r"(?i)\b[\w]*(?:api_?key|secret|password|passwd|token)\b\s*[:=]\s*"
            r"[\"'][^\"'\s]{12,}[\"']"
        ),
        False,
    ),
    Rule(
        "model_identifier",
        re.compile(
            r"(?i)\b(?:gpt-(?:3\.5|4|4o|5)[\w.\-]*|claude-[a-z0-9][\w.\-]*|gemini-\d[\w.\-]*"
            r"|llama-?\d[\w.\-]*|mixtral-[\w.\-]+|mistral-(?:small|medium|large|tiny)[\w.\-]*"
            r"|all-minilm-l\d+-v\d)\b"
        ),
        True,
    ),
    Rule("hardcoded_endpoint", re.compile(r"https?://[^\s\"'<>)]+"), True),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str

    def __str__(self) -> str:  # never print the matched text: it may be a real secret
        return f"{self.path}:{self.line}: {self.rule}"


def is_code_path(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    return bool(parts) and (parts[0] in CODE_DIRS or rel_path in CODE_FILES)


def _endpoint_allowed(match: str) -> bool:
    host = re.sub(r"^https?://", "", match).split("/", 1)[0].split(":", 1)[0]
    return host in ALLOWED_HOSTS


def scan_text(text: str, rel_path: str) -> list[Finding]:
    code = is_code_path(rel_path)
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule in RULES:
            if rule.code_only and not code:
                continue
            for m in rule.pattern.finditer(line):
                if rule.name == "hardcoded_endpoint" and _endpoint_allowed(m.group(0)):
                    continue
                findings.append(Finding(rel_path, lineno, rule.name))
                break
    return findings


def candidate_files(root: Path) -> list[Path]:
    """Tracked plus untracked-but-not-ignored files; falls back to a directory walk."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],  # noqa: S607
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        return [root / p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return [
            p
            for p in root.rglob("*")
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(root).parts)
        ]


def scan_paths(root: Path, paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(text, path.relative_to(root).as_posix()))
    return findings


def tracked_env_files(root: Path) -> list[str]:
    """Real `.env` files must never be committed (only `.env.example`)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],  # noqa: S607
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        return []
    return [
        p
        for p in out.split("\0")
        if p and Path(p).name.startswith(".env") and not p.endswith(".example")
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0] if args else ".").resolve()
    findings = scan_paths(root, candidate_files(root))
    env_files = tracked_env_files(root)
    for f in findings:
        print(f)
    for p in env_files:
        print(f"{p}: tracked_env_file")
    total = len(findings) + len(env_files)
    print(f"secret scan: {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
