<div align="center">

# 🛡️ Guard

**Zero-daemon predictive test engine and safety layer for AI coding agents.**

*Run only the tests a change can break in milliseconds — mechanically blocking your agent until they pass. Zero Docker, 100% local, 0 MB background RAM.*

[![Python](https://img.shields.io/badge/python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Storage](https://img.shields.io/badge/storage-embedded%20SQLite-003B57.svg?style=flat&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status](https://img.shields.io/badge/daemon-zero%20background%20processes-success.svg)](#architecture)
[![Agents](https://img.shields.io/badge/agents-Claude%20Code%20%7C%20Antigravity%20%7C%20Cursor-purple.svg)](#agent-integration)

[Quickstart](#quickstart) • [How It Works](#how-it-works) • [Architecture](#architecture) • [Trust Engine](#trust--decision-engine) • [Benchmarks](#empirical-benchmarks) • [CLI Reference](#cli-reference)

</div>

---

## ⚡ The Problem

AI coding agents (like Claude Code, Antigravity, and Cursor) write and refactor code at superhuman speed. However:
1. **Running the full test suite on every turn kills momentum** — large suites take minutes, breaking agent flow and burning tokens.
2. **Skipping tests is catastrophic** — agents hallucinate that subtle regressions are fine and commit broken code.
3. **Naive file-based diffing is blind** — changing a helper function in `utils.py` can break an endpoint in `api.py` that no file-level heuristic catches.
4. **Existing solutions demand heavy infrastructure** — Docker daemons, remote graph servers, or memory-hungry background services.

---

## 💡 What is Guard?

Guard connects **embedded graph intelligence** directly to your AI agent's test loop. 

Whenever an agent finishes a turn or attempts to commit, Guard intercepts the turn via native agent hooks, computes the exact **blast radius** of the diff using recursive graph traversal in embedded SQLite, and runs **only the tests that can catch a regression** in milliseconds.

```
Agent edits code
       │
       ▼
Guard Stop Hook Intercepts (<20ms)
       │
       ├─► Extract Git diff & AST modified functions
       ├─► Query embedded SQLite graph (.guard/graph.db) via Recursive CTEs
       ├─► Calculate composite Trust Score [0.0 - 1.0]
       │
       ▼
Targeted Test Execution
       │
       ├─► PASS  ──► Exit 0 (Agent proceeds smoothly)
       └─► FAIL  ──► Exit 2 (Agent mechanically blocked with failure diagnostics)
```

If coverage evidence is missing, uncertain, or a test file itself was touched, Guard **fails closed** and runs the full suite. It never silently passes.

---

## 🚀 Quickstart

### 1. Installation

Install Guard globally via `uv` or `pip`:

```bash
# Using uv (recommended)
uv tool install guard-cli

# Using pip
pip install guard-cli
```

### 2. Initialize your Repository

Run `guard init` inside your project root:

```bash
guard init --yes
```

`guard init` runs non-interactively to:
1. Detect your git root and python virtual environment (`pytest` + `pytest-cov`).
2. Statically parse Python source files via AST to build the function and call hierarchy.
3. Collect per-test coverage mapping.
4. Write the knowledge graph into `.guard/graph.db` (pure embedded SQLite).
5. Automatically install stop hooks into Claude Code (`.claude/settings.local.json`) and Antigravity (`.agents/hooks.json`).

### 3. Verify Health

```bash
guard doctor
```

Inspects backend health, graph node/edge counts, hook registrations, and test environment sanity. Run `guard doctor --fix` to auto-repair any drift.

---

## 🏗️ Architecture

Guard operates **100% locally with zero background daemons and zero external dependencies**.

```
┌────────────────────────────────────────────────────────┐
│                   AI Coding Agent                      │
│             (Claude Code / Antigravity)                │
└──────────────────────────┬─────────────────────────────┘
                           │ (Native Stop / PreStop Hook)
                           ▼
┌────────────────────────────────────────────────────────┐
│                   Guard Engine                         │
│  ┌────────────────────┐      ┌──────────────────────┐  │
│  │ AST Diff Analyzer  │      │  Trust Score Engine  │  │
│  └─────────┬──────────┘      └──────────▲───────────┘  │
│            │                            │              │
│            ▼                            │              │
│  ┌──────────────────────────────────────┴───────────┐  │
│  │           SQLite Graph Store (.guard/graph.db)   │  │
│  │                                                  │  │
│  │  • functions (AST qualnames, line spans, dyn)    │  │
│  │  • calls     (multi-hop caller/callee links)     │  │
│  │  • covered_by (per-test coverage evidence)       │  │
│  │  • queries   (Recursive CTEs, WAL mode, <20ms)   │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────┬─────────────────────────────┘
                           │
                 [Exit 0 / Exit 2]
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
  Tests Pass                              Tests Fail
(Agent proceeds)                     (Agent blocked with
                                      targeted stack trace)
```

### Backend Options

While embedded SQLite is the zero-configuration default, Guard provides a flexible backend abstraction:

| Backend | Flag | Description | Overhead |
|---|---|---|---|
| **SQLite** *(Default)* | `--backend sqlite` | Embedded `.guard/graph.db` with WAL mode & recursive CTEs | **0 MB RAM**, Zero Daemons |
| **Server** | `--backend server` | Remote or local FalkorDB instance on port 6379 | Network Redis/FalkorDB |
| **Docker** | `--backend docker` | Dedicated auto-managed container on port 6390 | Docker VM / Container |
| **Embedded FalkorDB** | `--backend embedded` | In-process FalkorDBLite (Python 3.12+ on supported OS) | Native C shared library |

Configure backends persistently in `.guard/config.toml`:

```toml
[backend]
type = "sqlite"
```

---

## 🎯 Trust & Decision Engine

Guard does not guess. Every test selection decision produces a deterministic **Trust Score** between `0.0` and `1.0`:

$$\text{Trust} = 0.5 \times \text{EvidenceRatio} + 0.3 \times \text{Freshness} + 0.2 \times (1 - \text{UncertainRatio})$$

- **Evidence Ratio**: The coverage depth and confidence of tests mapped to changed functions.
- **Freshness**: Ratio of coverage edges verified against the current commit SHA.
- **Uncertain Ratio**: Penalty for dynamic Python dispatch (`getattr`, `eval`, `exec`, `__import__`).

### Policy Thresholds

| Trust Score | Policy | Execution Plan |
|---|---|---|
| **$\ge 0.8$** | `subset` | Run **only** the directly and transitively covering tests |
| **$0.5 \le \text{Trust} < 0.8$** | `medium` | Run covering tests **plus** all tests in affected modules |
| **$< 0.5$** | `run_all` | Run the **entire test suite** |

### Safety Invariants (Fail-Closed)

Guard enforces strict fail-closed overrides that immediately escalate to `run_all`:
1. `no_evidence`: Any modified function has zero coverage records in the graph.
2. `test_file_touched`: A test file itself was edited or deleted.
3. `dynamic_dispatch`: High uncertainty due to runtime reflection expands to full module tests.
4. `untracked_files`: New files without graph representations trigger comprehensive validation.

---

## 🤖 Agent Integration

Guard integrates seamlessly with major AI developer tools:

### Claude Code
Guard registers a Stop hook in `.claude/settings.local.json` (or `.claude/settings.json`):
```json
{
  "hooks": {
    "Stop": [
      {
        "command": "guard hook stop"
      }
    ]
  }
}
```

### Antigravity
Guard registers a `PreStop` hook in `.agents/hooks.json`:
```json
{
  "hooks": {
    "PreStop": [
      {
        "command": "guard hook stop"
      }
    ]
  }
}
```

### Cursor, Codex, and Custom LLM Harnesses
Guard hooks into standard shell execution or pre-commit hooks:
```bash
guard hook stop --repo /path/to/repo
```
* **Exit 0**: All targeted tests passed (or working tree is clean).
* **Exit 2**: Tests failed — stdout/stderr pipes targeted failure diagnostics back into the agent's context to guide immediate self-repair.

---

## 🔄 Self-Healing Feedback Loop

If a regression ever slips past Guard's predictive selection, repair the graph permanently with a single command:

```bash
guard feedback \
  --function "myapp/payments.py::process_refund" \
  --test "tests/test_payments.py::test_refund_edge_case"
```

This inserts a `COVERED_BY` edge with `source="miss_repair"` and `confidence=1.0`. Guard will never miss that relationship again.

---

## 📊 Empirical Benchmarks

Guard was benchmarked against prominent real-world Python repositories under realistic AI refactoring scenarios:

| Repository | Full Suite | Guard Selected | Test Reduction | Regressions Caught | Decision Latency |
|---|---|---|---|---|---|
| **Pallets / Flask** | 450+ tests | 12 tests | **~97.3%** | **100%** (0 missed) | **<18 ms** |
| **Bottle** | 363 tests | 19 tests | **94.8%** | **100%** (0 missed) | **<12 ms** |

---

## 🛠️ CLI Reference

```text
guard init [repo] [--backend sqlite|server|docker|embedded] [--skip-coverage] [-y] [--agents ...]
guard doctor [repo] [--json] [--fix]
guard run [--diff <file>] [--repo <path>] [--json] [--strict]
guard check [--diff <file>] [--repo <path>] [--json] [--strict]
guard callers <function-id> [--hops N] [--min-confidence F]
guard covering-tests <function-id> [--min-confidence F]
guard feedback --function <id> --test <id> [--confidence F]
guard stats
guard hook install [--repo <path>] [--shared] [--antigravity]
guard hook uninstall [--repo <path>] [--shared] [--antigravity]
guard hook status [--repo <path>] [--antigravity]
guard hook stop [--repo <path>] [--strict]
guard hook session-start [--repo <path>]
```

---

## 💻 Development & Contributing

```bash
# Clone repository
git clone https://github.com/thisisvaishnav/guard.git
cd guard

# Set up development virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run test suite
pytest

# Test SQLite store specifically
pytest tests/test_store_sqlite.py
```

---

## 📄 License

Guard is open-source software licensed under the [MIT License](LICENSE).
