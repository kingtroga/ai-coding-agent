"""
tools.py

The concrete capabilities available to the coding agent. Each tool is a
plain Python function that operates on a target repository directory.
Every tool is sandboxed to the repo root: paths are resolved and checked
so the agent cannot read or write outside the project it was pointed at.

These are exposed to the LLM as "tool" definitions (see agent.py), but
they are ordinary, testable, dependency-free functions -- you can call
them directly without an LLM at all, which is how they're unit tested.
"""

import os
import subprocess
import fnmatch

# Directories we never want to walk into or let the agent touch.
IGNORE_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv"}


class ToolError(Exception):
    """Raised when a tool call is invalid or unsafe (e.g. path escape)."""


def _resolve(repo_root: str, rel_path: str) -> str:
    """Resolve rel_path against repo_root and refuse to leave the sandbox."""
    repo_root = os.path.abspath(repo_root)
    full = os.path.abspath(os.path.join(repo_root, rel_path))
    if not (full == repo_root or full.startswith(repo_root + os.sep)):
        raise ToolError(f"Path '{rel_path}' escapes the repository root.")
    return full


def list_directory(repo_root: str, rel_path: str = ".", max_depth: int = 4) -> str:
    """Recursively list files/folders under rel_path, skipping noise dirs."""
    start = _resolve(repo_root, rel_path)
    if not os.path.exists(start):
        raise ToolError(f"Path does not exist: {rel_path}")

    lines = []
    base_depth = start.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(start):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
        depth = root.rstrip(os.sep).count(os.sep) - base_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        rel_root = os.path.relpath(root, os.path.abspath(repo_root))
        indent = "  " * depth
        label = "." if rel_root == "." else rel_root
        lines.append(f"{indent}{label}/")
        for f in sorted(files):
            lines.append(f"{indent}  {f}")
    return "\n".join(lines) if lines else "(empty)"


def read_file(repo_root: str, rel_path: str) -> str:
    """Return file content with 1-indexed line numbers, like `cat -n`."""
    full = _resolve(repo_root, rel_path)
    if not os.path.isfile(full):
        raise ToolError(f"File does not exist: {rel_path}")
    with open(full, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    numbered = [f"{i+1:>5}\t{line.rstrip(chr(10))}" for i, line in enumerate(lines)]
    return "\n".join(numbered) if numbered else "(empty file)"


def write_file(repo_root: str, rel_path: str, content: str) -> str:
    """Create or fully overwrite a file, creating parent dirs as needed."""
    full = _resolve(repo_root, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    existed = os.path.isfile(full)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    action = "Updated" if existed else "Created"
    return f"{action} {rel_path} ({len(content.splitlines())} lines)."


def search_code(repo_root: str, pattern: str, glob: str = "*") -> str:
    """Simple recursive text search (grep -n substitute, no external dep)."""
    root = os.path.abspath(repo_root)
    hits = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for fname in files:
            if not fnmatch.fnmatch(fname, glob):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if pattern in line:
                            rel = os.path.relpath(fpath, root)
                            hits.append(f"{rel}:{lineno}: {line.strip()}")
            except (IsADirectoryError, PermissionError):
                continue
    if not hits:
        return f"No matches for '{pattern}'."
    return "\n".join(hits[:200])


def run_command(repo_root: str, command: str, timeout: int = 60) -> str:
    """
    Run a shell command with cwd pinned to repo_root, for validation steps
    like `node --check file.js`, `npm install`, or `node -e "..."` smoke
    tests. Not used for arbitrary system access -- cwd is fixed and output
    is truncated.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=os.path.abspath(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s."
    out = (result.stdout or "") + (result.stderr or "")
    out = out[-4000:]  # keep the tool loop's context small
    return f"exit_code={result.returncode}\n{out}"
