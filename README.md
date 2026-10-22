# Guard

**Graph-powered safety layer for AI coding agents built on [FalkorDB](https://falkordb.com)**

Guard builds a live knowledge graph of your codebase—functions, tests, call paths, and coverage evidence—and intercepts every agent stop-turn to run only the tests that can actually catch a regression in what just changed. When coverage evidence is missing or stale, Guard falls back to the full suite. It never silently passes.

```
Agent edits code → Guard Stop Hook fires → graph query → targeted test run → block or pass
```

---

## Table of Contents

- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Setup](#setup)
- [Configuration](#configuration)
- [CLI Reference](#cli-reference)
- [Agent Integration](#agent-integration)
- [Graph Data Model](#graph-data-model)
- [Trust & Decision Engine](#trust--decision-engine)
- [Feedback Loop](#feedback-loop)
- [Development](#development)

---

## How It Works

1. **`guard init`** — Parses your repo statically (AST), runs the test suite once to collect per-test coverage, and writes the knowledge graph into FalkorDB.
2. **Stop hook** — When an AI agent finishes a turn, Guard diffs the working tree, resolves which functions changed, queries the graph for covering tests, and either runs a targeted subset or the full suite.
3. **Trust score** — Every decision carries a `trust` score (0–1) composed of evidence ratio, edge freshness, and dynamic-dispatch uncertainty. Low trust = full suite.
4. **Feedback loop** — When a regression slips through, `guard feedback` inserts a high-confidence repair edge so the miss cannot repeat.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | ≥ 3.10 (≥ 3.12 for embedded backend) |
| pytest + pytest-cov | any recent version |
| FalkorDB | one of: Docker, existing server, or embedded (see below) |

### FalkorDB backend options

| Backend | When to use |
|---|---|
| **Docker** (default) | Local dev — Guard starts a container automatically |
| **Server** | Existing FalkorDB/Redis instance on your network |
| **Embedded** | Python 3.12+, macOS 15+ or Linux glibc ≥ 2.39; no Docker needed |

---

## Installation

```bash
pip install guard-cli
```

With the embedded (no-Docker) backend:

```bash
pip install "guard-cli[embedded]"   # requires Python 3.12+
```

For development:

```bash
git clone https://github.com/thisisvaishnav/guard
cd guard
pip install -e ".[dev]"
```

---

## Setup

### 1. Initialize Guard in your repo

Run this once from your project root (or pass a path):

```bash
guard init
```

`guard init` will:

1. Locate your git root and test configuration.
2. Resolve or start a FalkorDB backend.
3. Parse all Python source files (AST static analysis).
4. Run the test suite and collect per-test coverage.
5. Write the knowledge graph (functions → tests → files).
6. Install the Stop hook into your agent's settings file.
7. Add a `guard run` instruction to `AGENTS.md` / `CLAUDE.md`.

**Non-interactive / CI:**

```bash
guard init --yes --backend docker --skip-coverage
```

**Choose backend explicitly:**

```bash
guard init --backend server    # existing FalkorDB on localhost:6379
guard init --backend docker    # Docker (auto-start)
guard init --backend embedded  # in-process FalkorDBLite (Python 3.12+)
```

**Choose which agents to configure:**

```bash
guard init --agents claude,antigravity,cursor,codex
```

### 2. Verify the installation

```bash
guard doctor
```

`guard doctor` checks:
- Backend connectivity and graph freshness
- Hook installation in agent settings
- pytest-cov availability
- Environment sanity

Auto-fix common issues:

```bash
guard doctor --fix
```

JSON output for CI:

```bash
guard doctor --json
```

### 3. (Optional) Re-ingest after large refactors

```bash
guard ingest-static .           # re-parse source → graph
guard ingest-coverage .         # re-run coverage → COVERED_BY edges
```

---

## Configuration

Guard stores per-repo config in `.guard/config.toml`:

```toml
[backend]
type = "docker"           # server | docker | embedded
host = "localhost"        # server backend only
port = 6390               # docker default; server uses 6379
graph_name = "my_repo"   # defaults to repo directory name
```

Environment variable overrides:

```bash
FALKORDB_HOST=my-server FALKORDB_PORT=6379 guard run
GUARD_GRAPH=my_graph guard run
GUARD_DEBUG_PAYLOAD=1 guard hook stop   # dumps raw hook payload to .guard/last_payload.json
```

---

## CLI Reference

```
guard init [repo] [--backend server|docker|embedded] [--skip-coverage] [-y] [--agents ...]
guard doctor [repo] [--json] [--fix]
guard run [--diff path] [--repo path] [--json] [--strict]
guard check [--diff path] [--repo path] [--json] [--strict]
guard ingest-static <repo> [--dry-run] [--include-tests] [--commit-sha SHA]
guard ingest-coverage <repo> [--runs N] [--commit-sha SHA]
guard callers <function-id> [--hops N] [--min-confidence F]
guard covering-tests <function-id> [--min-confidence F]
guard feedback --function <id> --test <id> [--confidence F]
guard stats
guard hook install [--repo path] [--shared] [--antigravity]
guard hook uninstall [--repo path] [--shared] [--antigravity]
guard hook status [--repo path] [--antigravity]
guard hook stop [--repo path] [--strict]
guard hook session-start [--repo path]
```

### Key flags

| Flag | Effect |
|---|---|
| `--strict` | Fail closed if Guard itself errors (default: fail open) |
| `--json` | Machine-readable output on stdout |
| `--dry-run` | Parse without touching the database |
| `--shared` | Write to `settings.json` instead of `settings.local.json` |

### Function ID format

Guard uses qualified names as function IDs:

```
guard_cli/api.py::run
guard_cli/decision.py::decide
guard_cli/db.py::write_static
tests/test_decision.py::test_decide_no_evidence
```

---

## Agent Integration

### Claude Code

```bash
guard hook install
```

Writes a Stop hook entry into `.claude/settings.local.json`. When Claude tries to stop a turn, the hook calls `guard hook stop`, which blocks if tests fail.

```bash
guard hook install --shared   # → .claude/settings.json (shared across users)
```

### Antigravity

```bash
guard hook install --antigravity
```

Writes a `PreStop` hook entry into `.agents/hooks.json`.

### Manual hook invocation

```bash
guard hook stop --repo /path/to/repo
```

Exit codes: `0` = pass (or fail-open), `2` = tests failed (agent blocked).

---

## Graph Data Model

Guard's knowledge graph is stored in [FalkorDB](https://falkordb.com) (a property graph database). Each repository gets its own named graph (default: the repository directory name).

### Node types

| Label | Key property | Description |
|---|---|---|
| `File` | `path` (string) | A Python source file, repo-relative path |
| `Function` | `id` (string) | A callable — function or method, identified by `file::qualname` |
| `Test` | `id` (string) | A pytest-discoverable test function |
| `Run` | `id` (string) | A recorded test-suite execution |
| `GuardMeta` | `id = "meta"` | Singleton: graph generation counter and last-updated timestamp |

#### `Function` properties

| Property | Type | Description |
|---|---|---|
| `id` | string | `file.py::ClassName.method` — globally unique within the graph |
| `name` | string | Simple function name |
| `qualname` | string | Dotted qualified name within the module |
| `file` | string | Relative path of the containing file |
| `start` | int | First line number |
| `end` | int | Last line number |
| `has_dynamic_dispatch` | bool | `true` if the function uses `getattr`, `eval`, `exec`, `__import__`, etc. |

#### `Test` properties

| Property | Type | Description |
|---|---|---|
| `id` | string | `tests/test_foo.py::TestClass.test_method` |
| `name` | string | Simple test name |
| `qualname` | string | Dotted qualified name |
| `file` | string | Relative path |
| `start` / `end` | int | Line range |

#### `Run` properties

| Property | Type | Description |
|---|---|---|
| `id` | string | UUID for the run |
| `timestamp` | string | ISO-8601 timestamp |
| `commit_sha` | string | HEAD SHA at run time |
| `duration_ms` | float | Wall time in milliseconds |
| `total_tests` | int | Number of tests collected |
| `passed` / `failed` | int | Pass / fail counts |

---

### Edge types

| Type | Source → Target | Populated by | Default confidence |
|---|---|---|---|
| `DEFINED_IN` | `Function` → `File` | static ingest | — |
| `DEFINED_IN` | `Test` → `File` | static ingest | — |
| `CALLS` | `Function` → `Function` | static ingest | 0.6 |
| `IMPORTS` | `File` → `File` | static ingest | 0.6 |
| `COVERED_BY` | `Function` → `Test` | coverage / feedback | 0.9 / 1.0 |
| `FAILED_IN` | `Test` → `Run` | test run | — |

#### Edge properties

**`CALLS`**

| Property | Type | Description |
|---|---|---|
| `source` | string | Always `"static"` |
| `confidence` | float | `0.6` — static edges are capped; only dynamic execution evidence can raise confidence |
| `evidence_count` | int | Number of times this edge has been confirmed |
| `last_verified_sha` | string | Commit SHA when last confirmed — used to compute freshness |

**`COVERED_BY`**

| Property | Type | Description |
|---|---|---|
| `source` | string | `"coverage"` (dynamic run) or `"miss_repair"` (feedback loop) |
| `confidence` | float | `0.9` for coverage runs; `1.0` for repair edges |
| `evidence_count` | int | Incremented on each coverage run that confirms the edge |
| `last_verified_sha` | string | Commit SHA when last confirmed — drives edge freshness score |

**`IMPORTS`**

| Property | Type | Description |
|---|---|---|
| `source` | string | `"static"` |
| `confidence` | float | `0.6` |
| `last_verified_sha` | string | Commit SHA |

**`FAILED_IN`**

| Property | Type | Description |
|---|---|---|
| `source` | string | `"test_run"` |
| `error_message` | string | Truncated failure output |
| `commit_sha` | string | Commit SHA at run time |

---

### Graph schema diagram

```
┌──────────┐   DEFINED_IN   ┌──────┐   IMPORTS   ┌──────┐
│ Function │ ─────────────► │ File │ ───────────► │ File │
└──────────┘                └──────┘              └──────┘
     │  ▲
     │  │ CALLS (multi-hop, up to N hops)
     ▼  │
┌──────────┐
│ Function │
└──────────┘
     │
     │ COVERED_BY  (confidence 0.9 dynamic / 1.0 repair)
     ▼
┌──────┐   DEFINED_IN   ┌──────┐
│ Test │ ─────────────► │ File │
└──────┘                └──────┘
     │
     │ FAILED_IN
     ▼
┌─────┐
│ Run │
└─────┘
```

### Indexes

Guard automatically creates these FalkorDB indexes on `guard init`:

```cypher
CREATE INDEX FOR (f:Function) ON (f.id)
CREATE INDEX FOR (t:Test)     ON (t.id)
CREATE INDEX FOR (x:File)     ON (x.path)
CREATE INDEX FOR (r:Run)      ON (r.id)
CREATE INDEX FOR (m:GuardMeta) ON (m.id)
```

### Useful graph queries

```cypher
-- Tests covering a specific function
MATCH (f:Function {id: "guard_cli/api.py::run"})-[e:COVERED_BY]->(t:Test)
RETURN t.id, e.confidence, e.source
ORDER BY e.confidence DESC

-- Multi-hop callers (up to 4 hops)
MATCH p=(caller:Function)-[:CALLS*1..4]->(target:Function {id: "guard_cli/db.py::write_static"})
RETURN caller.id, min(length(p)) AS hops
ORDER BY hops

-- Functions with no test coverage
MATCH (f:Function)
WHERE NOT (f)-[:COVERED_BY]->()
RETURN f.id, f.file

-- Stale coverage edges (confirmed at a different SHA)
MATCH (f:Function)-[e:COVERED_BY]->(t:Test)
WHERE e.last_verified_sha <> "HEAD_SHA_HERE"
RETURN f.id, t.id, e.last_verified_sha
```

Or via the CLI:

```bash
guard callers guard_cli/db.py::write_static --hops 4
guard covering-tests guard_cli/api.py::run --min-confidence 0.8
guard stats
```

---

## Trust & Decision Engine

Every Guard decision outputs a `trust` score in `[0, 1]`:

```
trust = 0.5 × evidence_ratio
      + 0.3 × freshness
      + 0.2 × (1 − uncertain_ratio)
```

| Component | Description |
|---|---|
| `evidence_ratio` | Average `best_confidence` across all changed functions |
| `freshness` | Fraction of `COVERED_BY` edges whose `last_verified_sha` matches HEAD |
| `uncertain_ratio` | Fraction of changed functions flagged `has_dynamic_dispatch = true` |

### Policy levels

| Trust | Policy | Action |
|---|---|---|
| ≥ 0.8 | `subset` | Run only the directly covering tests |
| 0.5 – 0.8 | `medium` | Covering tests + all tests in the same module |
| < 0.5 | `run_all` | Full suite |

### Hard overrides (always trigger `run_all`)

| Override key | Trigger condition |
|---|---|
| `no_evidence` | Any changed function has zero `COVERED_BY` edges |
| `test_file_touched` | A test file itself was modified |
| `dynamic_dispatch` | A changed function uses `getattr` / `eval` (widens to module tests) |

---

## Feedback Loop

When Guard misses a regression, repair the graph immediately:

```bash
guard feedback \
  --function "myapp/payments.py::charge" \
  --test "tests/test_payments.py::test_charge_declined"
```

This inserts or upgrades a `COVERED_BY` edge with `source="miss_repair"` and `confidence=1.0`. From then on, every Guard decision that touches `charge` will include `test_charge_declined`.

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run the full test suite
pytest

# Run with coverage
pytest --cov=guard_cli --cov-report=term-missing

# Run Guard on itself
guard run
```

### Verification scripts

Standalone integration checks in `tests/verify_*.py`:

```bash
python tests/verify_t3.py   # static graph integrity
python tests/verify_t4.py   # coverage evidence
python tests/verify_t5.py   # decision engine
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

## Links

- [GitHub](https://github.com/thisisvaishnav/guard)
- [Issue tracker](https://github.com/thisisvaishnav/guard/issues)
- [Changelog](CHANGELOG.md)
- [FalkorDB](https://falkordb.com)
