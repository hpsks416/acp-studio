---
name: acp-studio
description: Unified local panel for GitHub commit, Gitee commit, and GitHub-to-Gitee sync, replacing git-acp, gitee-acp, and gh-gitee-sync. Use when the user asks to commit, submit, push, or sync their work to GitHub and/or Gitee.
---

# ACP Studio (GitHub · Gitee · 双向同步)

One local panel that merges the previous `git-acp` / `gitee-acp` / `gh-gitee-sync` skills: commit and push to GitHub or Gitee, and run the bidirectional sync script once.

## Preferred path: local acp-studio

Start the bundled panel headless and use its compact JSON API to reduce token usage.

- Studio directory: `C:\Users\Razer\Documents\Codex\2026-09-20\y\acp-studio` (override with `ACP_STUDIO_DIR`).
- Start it headless: `python "<ACP_STUDIO_DIR>\server.py" --no-browser`.
- Base URL: `http://127.0.0.1:8790` (port override: `ACP_STUDIO_PORT`).
- Verify with `GET /api/health`.

Endpoints:

1. Inspect: `GET /api/repo?repo=<absolute repo path>` returns branch, GitHub/Gitee remotes, ahead/behind, staged/unstaged/untracked files, and recent commits. If there is nothing to commit, stop and say so.
2. Commit + optional push: `POST /api/commit` with `{"repo_path":"<absolute path>","message":"<emoji> <type>(<scope>): <subject>","push":true|false,"target":"github|gitee"}`.
3. Push only: `POST /api/push` with `{"repo_path":"<absolute path>","target":"github|gitee"}`.
4. Sync once: `POST /api/sync` with `{"repos":[],"dry_run":false,"direction":"github-to-gitee"}` runs `scripts/sync_github_gitee.py` once in the chosen direction and returns its output. Directions: `github-to-gitee`, `gitee-to-github`, `both`.

Still build the commit message yourself with the table below. If acp-studio is missing or `/api/health` fails, fall back to direct git.

## Fallback: direct git

1. Inspect with `git status --porcelain=v1 -b` and `git branch --show-current`.
2. Build the message with the table below.
3. `git add -A` (unless specific paths are named).
4. `git commit -m "<emoji> <type>(<scope>): <subject>"`.
5. Push to `origin` (GitHub) or `gitee` (Gitee); for Gitee use `-c http.sslBackend=openssl` and `GITEE_USERNAME`/`GITEE_TOKEN`.

## Types and emoji

| type | emoji | use when |
| --- | --- | --- |
| feat | ✨ | new feature |
| fix | 🐛 | bug fix |
| docs | 📝 | documentation only |
| style | 💄 | formatting, no logic change |
| refactor | ♻️ | code restructure, no behavior change |
| perf | ⚡ | performance improvement |
| test | ✅ | tests |
| build | 📦 | build system or dependencies |
| ci | 👷 | CI configuration |
| chore | 🔧 | maintenance, no production code |
| revert | ⏪ | reverting a commit |

## License Default

When creating or initializing a repository without a specified license, default to MIT:

- Add a `LICENSE` file with the current year and the owner's name (and email if provided).
- Reference MIT in `README.md`.
- Do not change an existing license without being asked.

## Safety

- Only push when the user asked to push; a bare "提交" means commit only.
- Never force-push (`--force`, `-f`) unless the user explicitly asked.
- Never commit secrets, `.env`, credentials, or large binaries; report them instead.
- Credentials come from `GITEE_USERNAME`/`GITEE_TOKEN` and `GITHUB_TOKEN` (or `gh auth token`); never write them into repo config, and redact them from output.
- New Gitee repositories default to public + MIT; after creating, verify visibility and PATCH `private=false` if Gitee returned private.
- The sync script is fast-forward only and never force-pushes; diverged branches are reported and skipped.
- Sync is one-way by default (`github-to-gitee`); choose `gitee-to-github` for the reverse direction, or `both` to run the two one-way directions in one pass.

## References

- `scripts/sync_github_gitee.py`: the bundled bidirectional sync script.
