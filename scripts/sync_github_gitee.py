#!/usr/bin/env python3
"""One-way or two-way sync between GitHub and Gitee mirrors.

For each repo it fetches all branches and tags from both remotes, then pushes
missing commits along the selected direction. Diverged branches are reported
and skipped (never force-pushed). Use --direction to choose the direction and
--watch for continuous sync.

Environment:
  GITEE_USERNAME / GITEE_TOKEN   Gitee login and personal access token (push)
  GITHUB_TOKEN                   GitHub token (optional; falls back to `gh auth token`)
  GH_USER                        GitHub owner name (default hpsks416)
  GITEE_USER                     Gitee owner name (defaults to GITEE_USERNAME)
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_REPOS = [
    "cad-viewer",
    "gitee-acp",
    "web-3d-asset-pipeline",
    "open-source-scout",
    "rust-refactor-local-projects",
    "browser-viz-local-scripts",
    "git-acp",
    "github-ready-packager",
    "stem2synthv-studio",
    "gacp-studio",
]


def gh_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def run(args: list[str], redact: tuple[str, ...] = (), timeout: int = 180) -> tuple[int, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=timeout)
    out = (proc.stdout or "") + (proc.stderr or "")
    for token in redact:
        if token:
            out = out.replace(token, "***")
    return proc.returncode, out


def rev_parse(mirror: Path, ref: str) -> str:
    code, out = run(["git", "-C", str(mirror), "rev-parse", "--verify", ref], timeout=30)
    return out.strip() if code == 0 else ""


def is_ancestor(mirror: Path, a: str, b: str) -> bool:
    code, _ = run(["git", "-C", str(mirror), "merge-base", "--is-ancestor", a, b], timeout=30)
    return code == 0


class Syncer:
    def __init__(self, args) -> None:
        self.args = args
        self.gh_user = os.environ.get("GH_USER", "hpsks416").strip()
        self.gitee_user = os.environ.get("GITEE_USER", "").strip() or os.environ.get("GITEE_USERNAME", "").strip()
        self.gitee_token = os.environ.get("GITEE_TOKEN", "").strip()
        self.git_token = gh_token()
        self.gh_b64 = base64.b64encode(f"{self.gh_user}:{self.git_token}".encode()).decode() if self.git_token else ""
        self.gitee_b64 = base64.b64encode(f"{self.gitee_user}:{self.gitee_token}".encode()).decode() if self.gitee_token else ""
        self.cache = Path(args.cache).resolve()

    def _git(self, mirror: Path, *parts: str, b64: str = "", redact: tuple = ()) -> tuple[int, str]:
        cmd = ["git", "-C", str(mirror), "-c", "http.sslBackend=openssl"]
        if b64:
            cmd += ["-c", f"http.extraheader=Authorization: Basic {b64}"]
        cmd += list(parts)
        return run(cmd, redact=redact)

    def ensure_remote(self, mirror: Path, remote: str, url: str) -> bool:
        code, out = run(["git", "-C", str(mirror), "remote"])
        if remote in out.splitlines():
            code, out = run(["git", "-C", str(mirror), "remote", "set-url", remote, url])
        else:
            code, out = run(["git", "-C", str(mirror), "remote", "add", remote, url])
        return code == 0

    def fetch(self, mirror: Path, remote: str, url: str, b64: str, redact: tuple) -> bool:
        if not self.ensure_remote(mirror, remote, url):
            print("  remote add failed")
            return False
        code, out = self._git(
            mirror, "fetch", "--prune", remote,
            f"+refs/heads/*:refs/remotes/{remote}/*",
            "+refs/tags/*:refs/tags/*",
            b64=b64, redact=redact)
        if code != 0:
            print("  fetch %s failed: %s" % (remote, out.strip()[-160:]))
            return False
        return True

    def push_ref(self, mirror: Path, remote: str, sha: str, dst_ref: str, b64: str, redact: tuple) -> bool:
        if self.args.dry_run:
            print("  [dry-run] push %s -> %s %s" % (sha[:8], remote, dst_ref))
            return True
        code, out = self._git(mirror, "push", remote, f"{sha}:{dst_ref}", b64=b64, redact=redact)
        if code != 0:
            print("  push %s %s failed: %s" % (remote, dst_ref, out.strip()[-160:]))
            return False
        print("  pushed %s -> %s" % (sha[:8], f"{remote}/{dst_ref}"))
        return True

    def _push_tags(self, mirror, remote, b64, redact):
        if self.args.dry_run:
            print(f"  [dry-run] push --tags {remote}")
        else:
            self._git(mirror, "push", remote, "--tags", b64=b64, redact=redact)

    def _sync_branch(self, mirror, src_sha, dst_sha, dst_remote, dst_ref, b64, redact):
        """Push src_sha to dst_remote only when it fast-forwards dst_sha."""
        if not src_sha:
            return "same"
        if dst_sha is None:
            self.push_ref(mirror, dst_remote, src_sha, dst_ref, b64, redact)
            return "pushed"
        if src_sha == dst_sha:
            return "same"
        if is_ancestor(mirror, dst_sha, src_sha):
            self.push_ref(mirror, dst_remote, src_sha, dst_ref, b64, redact)
            return "pushed"
        return "diverged"

    def sync_repo(self, repo: str) -> str:
        mirror = self.cache / (repo + ".git")
        mirror.mkdir(parents=True, exist_ok=True)
        if not (mirror / "HEAD").exists():
            code, _ = run(["git", "init", "--bare", str(mirror)])
            if code != 0:
                return "init-failed"

        gh_url = f"https://github.com/{self.gh_user}/{repo}.git"
        gitee_url = f"https://gitee.com/{self.gitee_user}/{repo}.git"
        redact = tuple(t for t in (self.git_token, self.gitee_token) if t)

        if not self.fetch(mirror, "gh", gh_url, self.gh_b64, redact):
            return "fetch-gh-failed"
        if not self.fetch(mirror, "gitee", gitee_url, self.gitee_b64, redact):
            return "fetch-gitee-failed"

        code, out = run(["git", "-C", str(mirror), "for-each-ref", "--format=%(refname:short)", "refs/remotes"])
        branches = set()
        for line in out.splitlines():
            remote, _, b = line.partition("/")
            if remote in ("gh", "gitee") and b:
                branches.add(b)

        direction = self.args.direction
        changed = 0
        diverged = 0
        for b in sorted(branches):
            gh_sha = rev_parse(mirror, f"refs/remotes/gh/{b}")
            gitee_sha = rev_parse(mirror, f"refs/remotes/gitee/{b}")
            if direction in ("both", "github-to-gitee"):
                result = self._sync_branch(mirror, gh_sha, gitee_sha, "gitee", f"refs/heads/{b}", self.gitee_b64, redact)
                if result == "pushed":
                    changed += 1
                elif result == "diverged":
                    print(f"  diverged branch '{b}' (gh={gh_sha[:8]} gitee={gitee_sha[:8]}): skipped, needs manual merge")
                    diverged += 1
            if direction in ("both", "gitee-to-github"):
                result = self._sync_branch(mirror, gitee_sha, gh_sha, "gh", f"refs/heads/{b}", self.gh_b64, redact)
                if result == "pushed":
                    changed += 1
                elif result == "diverged":
                    print(f"  diverged branch '{b}' (gitee={gitee_sha[:8]} gh={gh_sha[:8]}): skipped, needs manual merge")
                    diverged += 1

        if direction in ("both", "github-to-gitee"):
            self._push_tags(mirror, "gitee", self.gitee_b64, redact)
        if direction in ("both", "gitee-to-github"):
            self._push_tags(mirror, "gh", self.gh_b64, redact)

        return f"synced(direction={direction}, changes={changed}, diverged={diverged})"


    def run(self) -> int:
        repos = self.args.repos if self.args.repos else DEFAULT_REPOS
        failures = 0
        for repo in repos:
            print("%s:" % repo)
            try:
                status = self.sync_repo(repo)
                print("  ->", status)
                if "failed" in status:
                    failures += 1
            except subprocess.TimeoutExpired:
                print("  -> timeout")
                failures += 1
            except Exception as exc:
                print("  -> error:", exc)
                failures += 1
        print("done: %d repos, %d failures" % (len(repos), failures))
        return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub <-> Gitee sync (one-way or two-way)")
    parser.add_argument("--repos", nargs="*", help="repo names to sync (default: built-in list)")
    parser.add_argument("--cache", default=str(Path.home() / ".cache" / "gh-gitee-sync"), help="bare mirror cache dir")
    parser.add_argument("--direction", choices=["both", "github-to-gitee", "gitee-to-github"], default="both",
                        help="sync direction: both (two-way), github-to-gitee, or gitee-to-github")
    parser.add_argument("--watch", action="store_true", help="run continuously")
    parser.add_argument("--interval", type=int, default=300, help="seconds between runs in --watch mode")
    parser.add_argument("--dry-run", action="store_true", help="print actions without pushing")
    args = parser.parse_args()

    if not os.environ.get("GITEE_TOKEN"):
        print("GITEE_TOKEN is required", file=sys.stderr)
        return 2

    syncer = Syncer(args)
    while True:
        code = syncer.run()
        if not args.watch:
            return code
        print("sleeping %ds..." % args.interval, flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())