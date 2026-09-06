---
name: windows-executor
description: Operate the Windows evidence executor over SSH from this Mac — connect, transfer bundles, unpack and verify offline, clean up. Use when a task requires the Windows machine (D:\AI-Scientist-v2-workspace), when an SSH/scp command to Windows fails, or when the connection parameters are unknown or stale.
---

# Windows Executor over SSH

The Windows machine is the local-ranking bulk evidence executor (see `AGENTS.md` → Local-Ranking Execution Topology). This skill is the operational manual for reaching it. It deliberately carries **no endpoint**: the connection identity is resolved locally on first use, then cached on disk outside the repo so the skill itself stays pushable and the endpoint can change without editing it.

## 1. Resolve the endpoint

The SSH identity is the local key `~/.ssh/mac_win_screen`; the destination is cached in `~/.ssh/mac_win_screen.endpoint` (line 1: `user@host`; optional line 2: port). Read it and test:

```bash
DEST=$(head -1 ~/.ssh/mac_win_screen.endpoint)
PORT=$(sed -n 2p ~/.ssh/mac_win_screen.endpoint)
ssh -i ~/.ssh/mac_win_screen ${PORT:+-p $PORT} -o BatchMode=yes -o ConnectTimeout=5 \
    -o PreferredAuthentications=publickey -o PasswordAuthentication=no \
    "$DEST" "echo CONNECTED"
```

Completion: the reply prints `CONNECTED`. Keep `StrictHostKeyChecking` at default once the host key is in `known_hosts`. The private key never leaves `~/.ssh` and is never printed or copied.

If the endpoint file is missing, or the test fails (network change, reimaged host), recover in this order, then **verify with the live test above before persisting**:

1. Grep local agent session history for past connections made with this key: `grep -rl "mac_win_screen" ~/.codex/sessions/ ~/.kimi-code/sessions/ 2>/dev/null`, then extract the `user@host` destination from the newest match (`grep -o '[A-Za-z0-9_.-]*@[0-9.]*' <file> | sort | uniq -c | sort -rn | head`).
2. Check `~/.ssh/known_hosts` for LAN-address candidates.
3. Ask the user for `user@host` (and port if non-default).

Persist the verified destination so later sessions skip recovery:

```bash
printf '%s\n' "$DEST" > ~/.ssh/mac_win_screen.endpoint && chmod 600 ~/.ssh/mac_win_screen.endpoint
```

The endpoint file is local-only (outside the repo, mode 600): never copy its contents into tracked files, logs, reports, or evidence artifacts. Delete it to force re-resolution.

## 2. Recon once per session

```bash
ssh ... "chcp 65001 >nul & D:\python.exe --version & D:\python.exe -c \"import httpx; print(httpx.__version__)\" & dir /b D:\AI-Scientist-v2-workspace & where tar"
```

Expected: Python 3.13.7, `httpx 0.28.1` system-installed, workspace with `repo/ envs/ model-cache/ artifacts/ tmp/`, `tar.exe` present. If a dependency is missing, build an offline wheel set on Mac (`pip download <pkg>==<locked> --platform win_amd64 --python-version 3.13 --only-binary=:all:`), verify each wheel SHA-256 against `prototypes/local_ranking/environments/requirements.windows-x86_64-py313.txt`, ship the wheels with the bundle, and install with `pip install --no-index --find-links`.

## 3. Operate: cmd.exe rules

The remote shell is cmd.exe on a GBK console.

- Prefix every invocation with `chcp 65001 >nul &` so UTF-8 output decodes; expect mojibake without it.
- Chain with `&`; mind precedence around `if exist ... ( ) else ( )` — put the `if` last or use separate calls.
- cmd builtins reject forward-slash paths: use backslashes inside remote commands (`mkdir D:\path`). scp remote specs are the exception: `scp -q -i ~/.ssh/mac_win_screen <local> "$DEST:D:/AI-Scientist-v2-workspace/..."`.
- Hash check on Windows: `certutil -hashfile <file> SHA256`.
- Run Python as `D:\python.exe -B -X utf8` — `-B` keeps imported trees free of `__pycache__` (mandatory when a ledger re-check must prove the tree pristine), `-X utf8` gives UTF-8 mode.

## 4. Transfer and unpack

1. Create a **new** child directory under `D:\AI-Scientist-v2-workspace`; check absence first (`if exist ... (echo EXISTS) else (echo ABSENT)`). Never overwrite an existing checkout or evidence root.
2. scp the archive once; verify its SHA-256 on Windows before unpacking.
3. **MAX_PATH (260 chars)**: tar.exe *silently skips* files whose full path exceeds it, and this project's artifact paths run 150+ chars deep. Unpack into a short prefix (`D:\AI-Scientist-v2-workspace\tmp\<short-name>\`) and drop the bundle's top-level directory with `--strip-components=1`. Completion criterion: count extracted files and compare against the expected count (`dir /s /b /a:-d | find /c "\"`), not tar's exit code.
4. Run the task (verifier, replay, runner) from the unpacked root, offline unless the task explicitly authorizes otherwise.

## 5. Clean up

`rmdir /s /q` fails on trees containing long-path remnants from a partial extraction. Remove such trees with the robocopy empty-mirror:

```cmd
mkdir _empty & robocopy _empty <target> /MIR >nul & rmdir _empty & rmdir <target>
```

Delete every scratch directory the task created; leave the workspace as `repo/ envs/ model-cache/ artifacts/ tmp/` plus the task's own new evidence directory.

## 6. Discipline

- Reports, session logs, tickets, and freeze summaries refer to the machine only by class ("existing LAN Windows host", "new child under the workspace") — the endpoint lives in `~/.ssh/mac_win_screen.endpoint` and nowhere else.
- No credentials on the Windows side: never read, copy, or persist API keys there; formal evidence runs are offline on Windows.
- Preserve raw verifier output and hashes, and copy them back to the Mac controller as evidence.
