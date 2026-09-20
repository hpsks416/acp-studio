---
name: acp-studio
description: Unified local panel for GitHub commit, Gitee commit, and GitHub-to-Gitee sync, replacing git-acp, gitee-acp, and gh-gitee-sync. Use when the user asks to commit, submit, push, or sync their work to GitHub and/or Gitee.
---

# ACP Studio (GitHub · Gitee · 双向同步)

One local panel that merges the previous `git-acp` / `gitee-acp` / `gh-gitee-sync` skills: commit and push to GitHub or Gitee, and run the bidirectional sync script once.

## Preferred path: local acp-studio

Start the bundled panel headless and use its compact JSON API to reduce token usage.

- Studio directory: `C:\Users\Razer\Documents\Codex\2026-09-20\y\acp-studio` (override with `ACP_STUDIO_DIR`).
- Base URL: `http://127.0.0.1:8790` (port override: `ACP_STUDIO_PORT`).
- Verify with `GET /api/health`.

### Launching inside the Codex sandbox

Do **not** use `Start-Process` / `Start-Job` to run the panel in the background. Those detach a
process outside the tracked sandbox tree, so the `sandbox_approval` policy rejects the call.

Start the panel as a **foreground process in an exec PTY session** instead:

    python "<ACP_STUDIO_DIR>\server.py" --no-browser

- Run that command with `tty: true`; the server keeps running and the exec tool returns a session id.
- Poll `GET /api/health` until it returns `ok`.
- Keep the session open while calling the JSON API below.
- If `/api/health` already answers, do not start a second instance (avoids a port conflict).
- Stop it with Ctrl+C via `write_stdin` (`\u0003`) when finished, or leave it running.

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

## GitHub push: sandbox specifics

When the panel is not running or cannot authenticate, push directly with git. On this machine the sandbox has a few
quirks worth handling in the push command:

- Clear stale proxy env vars first: `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` are often set to `http://127.0.0.1:9`.
- Use `-c http.sslBackend=openssl`; the default schannel backend can fail with `SEC_E_NO_CREDENTIALS`.
- Prefer inline auth `https://<github_user>:<GITHUB_TOKEN>@github.com/<owner>/<repo>.git`, plus
  `-c credential.helper=` so git never opens an interactive prompt.
- Never write the token into repo config; read it from `secrets.cmd` / `GITHUB_TOKEN` and redact it from output.
- Error meanings:
  - `remote: Invalid username or token` = token is wrong/expired.
  - `remote: Permission to <repo> denied` = token is valid but lacks write access; use a classic PAT with `repo`
    scope, or a fine-grained PAT with `Contents: Read and write` for that repository.

`secrets.cmd` notes:

- It is a batch config file, not a double-clickable app; double-clicking flashes and exits. Edit it in a text editor.
- The panel reads `GITHUB_TOKEN` from the environment; its `start.cmd` sources `secrets.cmd`, so run the panel via
  `start.cmd` (or export the variable) to make newly added tokens take effect.

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
