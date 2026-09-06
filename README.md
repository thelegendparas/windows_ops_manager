# Windows Ops Agent

An AI **operations assistant that lives on your Windows production host**.
You SSH in, ask it questions — it inspects the machine, explains what's
happening, and performs approved actions. It also runs headlessly for
scheduled health checks.

## Capabilities at a glance

| Capability | What it means in practice |
|---|---|
| 🔍 Diagnose problems | "Why is my bot down?" → walks process → service → logs → ports → dependencies before touching anything |
| 📊 System stats | CPU (per-core), RAM/swap, disk per drive, uptime, top processes by CPU/RAM |
| 🪟 Windows services | List any service, get detailed status, start/stop/restart **your allowlisted** ones |
| 📜 Event log | Recent ERROR/WARNING events from the Windows Application log |
| 📂 Files & logs | List dirs, read files, tail logs, regex-search logs — with secrets (.env, keys, `.ssh`) always blocked |
| 🌐 Networking | Every listening port with pid + process name |
| 🧮 Processes | Find by name, top consumers, kill **allowlisted** processes only |
| 🔀 Git & deploy | Branch status, recent commits, diff, `git pull --ff-only` (gated) |
| ⏰ Scheduled health checks | Headless `-p` mode for Task Scheduler: "report only anomalies" |
| 🧾 Full audit trail | Every tool call logged to JSONL — including rejections and approvals |
| 🔁 Model-agnostic | OpenRouter behind the model layer: GLM today, any model tomorrow via `.env` |
| 🍎 Mac-dev friendly | Runs on the Mac for development; Windows-only tools auto-register only on Windows |

**What it can never do (by design):** delete files, drop databases, edit
firewall/users, disable security software, or run arbitrary shell. Those
aren't prompt-level rules — **the tools simply don't exist**, so there is
nothing to bypass.

## Tool inventory (what the agent actually has access to)

### Tier 1 — autonomous, read-only (runs immediately)

| Tool | Platform | Does |
|---|---|---|
| `get_system_info` | all | Hostname, OS, CPU cores, total RAM, boot time, uptime |
| `get_cpu_usage` | all | CPU % overall + per-core (1s sample) |
| `get_memory_usage` | all | RAM used/total/available %, swap usage |
| `get_disk_usage` | all | Used/total/free per local drive + which drive holds APP_DIR |
| `get_top_processes` | all | Top processes by CPU (RAM tiebreak), ~0.7s sample |
| `find_processes` | all | Find processes by name substring: pid, RAM, cmdline |
| `get_open_ports` | all | All listening TCP/UDP ports with pid + process name |
| `list_dir` | all | Directory listing (dirs marked `/`, sizes shown) |
| `read_file` | all | Read first N bytes of a text file (secrets blocked, truncated) |
| `tail_log` | all | Last N lines of a log (reads max final 4MB of huge files) |
| `search_log` | all | Regex search over the last N lines, returns matches + line numbers |
| `get_git_status` | all | Branch + working-tree status of APP_DIR |
| `get_recent_commits` | all | Commit log, one line per commit |
| `get_git_diff` | all | Diffstat + diff of uncommitted changes |
| `list_services` | Windows | List services (filterable): name, display name, status, start type |
| `get_service_status` | Windows | One service in detail: status, pid, start type, binary path |
| `get_recent_event_log_errors` | Windows | Application event log ERROR/WARNING entries (last N hours) |

### Tier 2 — gated, mutating (proposal → your approval → execution)

| Tool | Platform | Does | Allowlist |
|---|---|---|---|
| `restart_service` | Windows | Stop, wait, start a service | `ALLOWED_SERVICES` |
| `start_service` | Windows | Start a service | `ALLOWED_SERVICES` |
| `stop_service` | Windows | Stop a service | `ALLOWED_SERVICES` |
| `kill_process` | all | Terminate by pid (never system pids, never itself) | `ALLOWED_KILL_NAMES` |
| `git_pull` | all | `git pull --ff-only` on APP_DIR, reports new HEAD | — |
| `confirm_action` | all | **The gate itself**: executes a proposed tier 2 action by token | — |

### Tier 3 — no tools exist for these

Deleting files, dropping DBs, firewall/user/SSH changes, disabling security
software, arbitrary shell access. Not registered, not implemented, not reachable.

```
        YOUR MACHINE (Mac / SSH / future: chat bot / VS Code)
                            │
                            ▼
                 ┌─────────────────────┐
                 │   Windows Ops Agent │
                 │  (PydanticAI loop)  │
                 │      OpenRouter     │  ← GLM today, any model tomorrow
                 └──────────┬──────────┘
                            │  typed tools, tiered permissions, audited
     ┌──────────┬───────────┼───────────┬──────────┐
     ▼          ▼           ▼           ▼          ▼
  CPU/RAM    processes   services    logs/ports  git
  disk      (kill=T2)   (restart=T2) files      (pull=T2)
```

## Security model (the most important part)

| Tier | Examples | Behaviour |
|------|----------|-----------|
| 1 — autonomous | CPU/RAM/disk, processes, ports, services list, log tail/search, git status | Runs immediately, audited |
| 2 — ask first | restart/start/stop service, `git pull`, kill process | Returns a **proposal + token**; only executes when you approve and it calls `confirm_action(token)` |
| 3 — never | delete files, drop DBs, firewall/user changes, arbitrary shell | **Not implemented as tools at all** |

Extra hard rules:

- **Allowlists**: tier 2 service/process control is restricted to `ALLOWED_SERVICES` / `ALLOWED_KILL_NAMES` in `.env`. Empty = nothing may be touched.
- **Secrets are unreadable**: even tier 1 "read-only" file tools block `.env`, `*.pem`, `id_rsa*`, `*secret*`, `*credential*`, and anything under `.ssh`, `.aws`, `.gnupg`, `.git`. Set `ALLOWED_ROOTS` to restrict reads to specific directories.
- **Every tool call is audited** to `logs/audit-YYYY-MM-DD.jsonl` (tool, args, status, duration, result summary), including rejections and confirmations.

## Quick start

### On the Mac (development)

```bash
uv sync                     # or: python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/pip install pytest
uv run pytest -q           # sanity check: permission gate + security guard tests
cp env.example .env        # add your OpenRouter key
uv run python -m agent.main
```

Windows-only tools (services, event log) are **not registered** on the Mac —
everything else works, which is exactly why the core logic is testable here.

### On the Windows laptop (production)

1. Install Python 3.10+ and **Git for Windows** (git must be on PATH).
2. Clone this repo, then:

```powershell
cd Windows_assistant
uv sync                     # or: py -m venv .venv; .venv\Scripts\activate; pip install -e .
copy env.example .env        # then edit: key, APP_DIR, ALLOWED_SERVICES, ALLOWED_KILL_NAMES
uv run python -m agent.main
```

3. Run the terminal **as Administrator** for best visibility (pid names on ports, service control).

## Usage

Interactive over SSH:

```
you> why is my bot down?
you> what's eating RAM right now?
you> is postgres running? is port 5432 listening?
you> pull the latest code and restart the DiscordBot service
```

For tier 2 actions the agent proposes first and waits for your yes:

```
agent> PROPOSAL: restart_service('DiscordBot') — stop, wait, start.
       Approve?
you> yes
agent> Done. Service status now 'running'.
```

Headless one-shot (reports anomalies only — good for Task Scheduler):

```powershell
uv run python -m agent.main -p "Health check: CPU, RAM, disk, listening ports, service statuses, recent log errors. Report only anomalies, briefly."
```

Scheduled check (Task Scheduler, hourly):
- Program: `C:\path\to\Windows_assistant\.venv\Scripts\python.exe`
- Arguments: `-m agent.main -p "Health check: report only anomalies, briefly."`

`--yes` (auto-approve tier 2) exists for scripted pipelines — **use with care**;
without it, tier 2 tools in headless mode report that they need interactive
approval and do nothing destructive.

## Configuration

See `env.example`. Key values:

| Variable | Meaning |
|----------|---------|
| `OPENROUTER_API_KEY` | OpenRouter key (agent can never read this file) |
| `MODEL_NAME` | Any OpenRouter model id, e.g. `z-ai/glm-4.6` |
| `APP_DIR` | The app/repo the agent operates on (git pull, relative log paths) |
| `ALLOWED_SERVICES` | Windows services it may start/stop/restart |
| `ALLOWED_KILL_NAMES` | Process names it may kill |
| `ALLOWED_ROOTS` | If set, file reads are restricted to these roots |
| `CONFIRM_TTL_SECONDS` | How long a tier 2 proposal token stays valid |

## Project layout

```
agent/
  config.py       settings from .env (pydantic-settings)
  permissions.py  tier decorators, proposal/confirm gate, allowlists  ← the heart
  audit.py        JSONL audit log of every tool call
  prompts.py      system prompt (inspect-before-intervene, confirmation protocol)
  model.py        OpenRouter/OpenAI-compatible model construction
  main.py         CLI: interactive REPL + headless -p mode
tools/
  system.py       CPU / RAM / disk / host info            (tier 1)
  processes.py    top processes, find, kill               (find=T1, kill=T2)
  networking.py   listening ports                          (tier 1)
  filesystem.py   list/read with secrets guard             (tier 1)
  logs.py         tail_log / search_log                    (tier 1)
  gitops.py       status/log/diff, git pull --ff-only      (pull=T2)
  windows_services.py  query/start/stop/restart services   (control=T2, Windows-only)
  eventlog.py     Windows Application event log errors     (tier 1, Windows-only)
tests/            permission gate + security guard tests (run on the Mac)
```

## Adding a tool

1. Write a typed function returning a string (docstring = the model's tool description).
2. Decorate: `@tier1` for read-only, `@tier2` for mutating (add an
   `allowlist_check` attribute if it needs an allowlist).
3. Append it to that module's `TOOLS` list. Done — registration is automatic.

## Roadmap

- [ ] Wrap the tool layer as a **FastMCP server** so your Mac coding agent can call
      `windows.deploy(...)` directly (week 3)
- [ ] Docker tools (`docker_ps`, `docker_logs`)
- [ ] Deploy tool (git pull → tests → service restart) as a tier 2 composite
- [ ] Optional chat clients (Discord/Telegram) — the headless CLI is already client-ready
- [ ] Consider pydantic-ai's native tool-approval flow once pinned to a version that has it