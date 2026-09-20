#!/usr/bin/env python3
"""acp-studio: one local panel for GitHub commit, Gitee commit, and GitHub <-> Gitee sync.

Merges the previous git-acp / gitee-acp / gh-gitee-sync workflows into a single
zero-dependency local web UI + JSON API (Python 3.9+ standard library only).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"

VERSION = "1.0.0"

DEFAULT_CONFIG = {
    "git_path": "",        # optional absolute path to git; empty means auto-detect
    "host": "127.0.0.1",   # bind to localhost only
    "port": 8790,
    "state_file": "state.json",
    "github_remote": "origin",  # preferred GitHub remote name
    "gitee_remote": "gitee",    # preferred Gitee remote name
    "github_user": "hpsks416",  # used only with GITHUB_TOKEN for inline auth
    "gitee_user": "",           # falls back to GITEE_USERNAME
    "gitee_token": "",          # falls back to GITEE_TOKEN
    "use_openssl": True,        # force git http.sslBackend=openssl
}

DEFAULT_STATE = {
    "repo_path": str(ROOT),
    "commit_type": "feat",
    "scope": "",
    "breaking": False,
    "subject": "",
    "body": "",
    "emoji": "✨",
    "push": True,
    "target": "github",
}

CONVENTIONAL_TYPES = [
    {"key": "feat", "emoji": "✨", "label": "feat 新功能"},
    {"key": "fix", "emoji": "🐛", "label": "fix 修复"},
    {"key": "docs", "emoji": "📝", "label": "docs 文档"},
    {"key": "style", "emoji": "💄", "label": "style 样式"},
    {"key": "refactor", "emoji": "♻️", "label": "refactor 重构"},
    {"key": "perf", "emoji": "⚡", "label": "perf 性能"},
    {"key": "test", "emoji": "✅", "label": "test 测试"},
    {"key": "build", "emoji": "📦", "label": "build 构建"},
    {"key": "ci", "emoji": "👷", "label": "ci 持续集成"},
    {"key": "chore", "emoji": "🔧", "label": "chore 杂项"},
    {"key": "revert", "emoji": "⏪", "label": "revert 回滚"},
]

STATUS_INDEX_CHARS = set("MADRC")
STATUS_WORKTREE_CHARS = set("MD")


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        except Exception:
            pass
    return cfg


def state_file_path(cfg: dict) -> Path:
    name = cfg.get("state_file") or "state.json"
    p = Path(name)
    return p if p.is_absolute() else ROOT / p


def load_state(cfg: dict) -> dict:
    state = dict(DEFAULT_STATE)
    sp = state_file_path(cfg)
    if sp.exists():
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state.update({k: v for k, v in data.items() if k in DEFAULT_STATE})
        except Exception:
            pass
    return state


def save_state(cfg: dict, state: dict) -> None:
    sp = state_file_path(cfg)
    sp.parent.mkdir(parents=True, exist_ok=True)
    tmp = sp.with_suffix(sp.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, sp)


def find_git(cfg: dict) -> str:
    configured = (cfg.get("git_path") or "").strip()
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return str(p)
    found = shutil.which("git")
    if found:
        return found
    return "git"


def run(cmd: list[str], cwd, timeout: int = 30):
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
    except FileNotFoundError:
        return 127, "", "git executable not found"
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
    except OSError as exc:
        return 1, "", str(exc)


def resolve_repo(raw) -> Path:
    if not raw:
        raw = load_state(load_config()).get("repo_path") or str(ROOT)
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def github_token() -> str:
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


def gitee_credentials(cfg: dict) -> tuple[str, str]:
    user = (cfg.get("gitee_user") or "").strip() or os.environ.get("GITEE_USERNAME", "").strip()
    token = (cfg.get("gitee_token") or "").strip() or os.environ.get("GITEE_TOKEN", "").strip()
    return user, token


def redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def remote_url(git: str, repo: Path, name: str) -> str:
    code, url, _ = run([git, "remote", "get-url", name], repo)
    return url.strip() if code == 0 else ""


def remote_urls(cfg: dict, git: str, repo: Path) -> tuple[str, str]:
    gh_pref = (cfg.get("github_remote") or "origin").strip()
    gitee_pref = (cfg.get("gitee_remote") or "gitee").strip()
    gh_url = gitee_url = ""
    for name in (gh_pref, "origin", "gitee", gitee_pref):
        url = remote_url(git, repo, name)
        if not url:
            continue
        if not gh_url and "github.com" in url:
            gh_url = url
        if not gitee_url and "gitee.com" in url:
            gitee_url = url
    return gh_url, gitee_url


def resolve_target_remote(cfg: dict, git: str, repo: Path, target: str) -> tuple[str, str]:
    if target == "gitee":
        pref = (cfg.get("gitee_remote") or "gitee").strip()
        for name in (pref, "origin"):
            url = remote_url(git, repo, name)
            if "gitee.com" in url:
                return name, url
        return pref, remote_url(git, repo, pref)
    pref = (cfg.get("github_remote") or "origin").strip()
    for name in (pref, "gitee"):
        url = remote_url(git, repo, name)
        if url and "github.com" in url:
            return name, url
    return pref, remote_url(git, repo, pref)


def parse_status_branch(line: str) -> tuple[str, int, int]:
    m = re.match(r"^## (?:No commits yet on )?([^\[]+?)\s*(?:\[(.*)\])?$", line)
    if not m:
        return "", 0, 0
    branch = m.group(1).strip().rstrip(".")
    ahead = behind = 0
    detail = m.group(2) or ""
    am = re.search(r"ahead (\d+)", detail)
    bm = re.search(r"behind (\d+)", detail)
    if am:
        ahead = int(am.group(1))
    if bm:
        behind = int(bm.group(1))
    return branch, ahead, behind


def git_status(cfg: dict, repo: Path) -> dict:
    git = find_git(cfg)
    result = {
        "ok": False, "repo_path": str(repo), "is_repo": False, "git": git,
        "branch": "", "upstream": "", "ahead": 0, "behind": 0,
        "github_url": "", "gitee_url": "", "staged": [], "unstaged": [],
        "untracked": [], "log": [], "error": "",
    }
    code, _out, _err = run([git, "rev-parse", "--is-inside-work-tree"], repo)
    if code != 0:
        result["error"] = "该路径不是有效的 git 仓库"
        return result
    result["is_repo"] = True

    code, branch, _ = run([git, "rev-parse", "--abbrev-ref", "HEAD"], repo)
    result["branch"] = branch.strip() if code == 0 else "(detached)"

    code, up, _ = run([git, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo)
    if code == 0:
        result["upstream"] = up.strip()

    result["github_url"], result["gitee_url"] = remote_urls(cfg, git, repo)

    code, status, _ = run([git, "status", "--porcelain=v1", "-b"], repo)
    if code == 0:
        for line in status.splitlines():
            if line.startswith("## "):
                result["branch"], result["ahead"], result["behind"] = parse_status_branch(line)
                continue
            if len(line) < 4:
                continue
            xy = line[:2]
            path = line[3:]
            if xy == "??":
                result["untracked"].append(path)
            else:
                if xy[0] in STATUS_INDEX_CHARS:
                    result["staged"].append(path)
                if xy[1] in STATUS_WORKTREE_CHARS:
                    result["unstaged"].append(path)
        for key in ("staged", "unstaged", "untracked"):
            result[key] = result[key][:200]

    code, log, _ = run([git, "log", "--pretty=format:%h%x1f%an%x1f%ar%x1f%s", "-n", "20"], repo)
    if code == 0 and log.strip():
        result["log"] = [
            {"hash": p[0], "author": p[1], "when": p[2], "subject": p[3]}
            for p in (line.split("\x1f") for line in log.splitlines())
            if len(p) == 4
        ]

    result["ok"] = True
    return result


def do_push(cfg: dict, repo: Path, target: str) -> dict:
    git = find_git(cfg)
    remote, url = resolve_target_remote(cfg, git, repo, target)
    label = "Gitee" if target == "gitee" else "GitHub"
    if not url:
        return {"ok": False, "out": f"未找到 {label} 远程（请先 `git remote add {'gitee' if target=='gitee' else 'origin'} <url>`）"}

    code, branch, _ = run([git, "rev-parse", "--abbrev-ref", "HEAD"], repo)
    branch = branch.strip()
    if not branch or branch == "HEAD":
        return {"ok": False, "out": "无法确定当前分支，无法推送"}

    cmd = [git]
    if cfg.get("use_openssl", True):
        cmd += ["-c", "http.sslBackend=openssl"]
    token = ""
    if target == "gitee":
        user, token = gitee_credentials(cfg)
        if user and token:
            b64 = base64.b64encode(f"{user}:{token}".encode()).decode()
            cmd += ["-c", f"http.extraheader=Authorization: Basic {b64}"]
    else:
        gh_user = (cfg.get("github_user") or os.environ.get("GH_USER", "hpsks416")).strip()
        token = github_token()
        if gh_user and token:
            b64 = base64.b64encode(f"{gh_user}:{token}".encode()).decode()
            cmd += ["-c", f"http.extraheader=Authorization: Basic {b64}"]

    code, up, _ = run([git, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo)
    if code == 0:
        cmd += ["push", remote]
    else:
        cmd += ["push", "-u", remote, branch]
    code, out, err = run(cmd, repo, timeout=180)
    return {"ok": code == 0, "out": redact((out + err).strip(), token)}


def do_commit(cfg: dict, repo: Path, message: str, push: bool, target: str) -> dict:
    git = find_git(cfg)
    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "提交信息不能为空"}

    code, out, err = run([git, "add", "-A"], repo)
    if code != 0:
        return {"ok": False, "error": "git add 失败", "detail": (out + err).strip()}

    code, staged, _ = run([git, "diff", "--cached", "--name-only"], repo)
    if code != 0 or not staged.strip():
        return {"ok": False, "error": "没有可提交的更改"}

    code, out, err = run([git, "commit", "-m", message], repo, timeout=120)
    if code != 0:
        return {"ok": False, "error": "git commit 失败", "detail": (out + err).strip()}

    result = {"ok": True, "commit_out": (out + err).strip()}
    if push:
        pushed = do_push(cfg, repo, target)
        result["push_ok"] = pushed["ok"]
        result["push_out"] = pushed["out"]
        if not pushed["ok"]:
            result["error"] = "提交成功，但推送失败"
    return result


def do_sync(cfg: dict, repos: list[str], dry_run: bool) -> dict:
    script = ROOT / "scripts" / "sync_github_gitee.py"
    if not script.exists():
        return {"ok": False, "out": "scripts/sync_github_gitee.py 不存在"}
    cmd = [sys.executable, str(script)]
    if dry_run:
        cmd += ["--dry-run"]
    repos = [r for r in (repos or []) if str(r).strip()]
    if repos:
        cmd += ["--repos"] + repos
    code, out, err = run(cmd, ROOT, timeout=600)
    text = (out + err)
    for token in (os.environ.get("GITEE_TOKEN", ""), os.environ.get("GITHUB_TOKEN", ""), github_token()):
        if token:
            text = text.replace(token, "***")
    return {"ok": code == 0, "out": text.strip()}


def merge_state(body: dict) -> dict:
    state = load_state(load_config())
    for key in DEFAULT_STATE:
        if key in body:
            state[key] = body[key]
    return state


class Handler(BaseHTTPRequestHandler):
    server_version = "acp-studio/" + VERSION

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _query(self) -> dict:
        return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self._api_get(path)
        else:
            self._static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._read_json()
        cfg = load_config()
        if path == "/api/state":
            state = merge_state(body)
            save_state(cfg, state)
            self._send_json({"ok": True, "state": state})
        elif path == "/api/commit":
            repo = resolve_repo(body.get("repo_path"))
            target = body.get("target") or "github"
            self._send_json(do_commit(cfg, repo, body.get("message", ""), bool(body.get("push")), target))
        elif path == "/api/push":
            repo = resolve_repo(body.get("repo_path"))
            target = body.get("target") or "github"
            self._send_json(do_push(cfg, repo, target))
        elif path == "/api/sync":
            self._send_json(do_sync(cfg, body.get("repos", []), bool(body.get("dry_run"))))
        else:
            self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    def _api_get(self, path: str):
        cfg = load_config()
        if path == "/api/health":
            self._send_json({"ok": True, "version": VERSION, "git": find_git(cfg),
                             "host": cfg.get("host"), "port": cfg.get("port")})
        elif path == "/api/state":
            self._send_json({"ok": True, "state": load_state(cfg)})
        elif path == "/api/repo":
            repo = resolve_repo(self._query().get("repo"))
            self._send_json(git_status(cfg, repo))
        elif path == "/api/types":
            self._send_json({"ok": True, "types": CONVENTIONAL_TYPES})
        else:
            self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    def _static(self, path: str):
        if path == "/":
            path = "/index.html"
        rel = urllib.parse.unquote(path.lstrip("/"))
        safe = (WEB_DIR / rel).resolve()
        if safe != WEB_DIR and WEB_DIR not in safe.parents:
            self.send_error(404)
            return
        if safe.is_dir():
            safe = safe / "index.html"
        if not safe.is_file():
            self.send_error(404)
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(safe.suffix.lower(), "application/octet-stream")
        data = safe.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description="acp-studio local server")
    parser.add_argument("--host", help="bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, help="bind port (default: 8790)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    cfg = load_config()
    host = args.host or cfg.get("host", "127.0.0.1")
    port = args.port or int(os.environ.get("ACP_STUDIO_PORT", cfg.get("port", 8790)))

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = "http://%s:%d/" % (host, port)
    print("acp-studio %s running at %s (Ctrl+C to stop)" % (VERSION, url))
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
