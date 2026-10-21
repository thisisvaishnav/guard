# Guard: Graph-Powered Safety Layer for AI Coding Agents

[![PyPI version](https://img.shields.io/pypi/v/guard-cli.svg)](https://pypi.org/project/guard-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FalkorDB](https://img.shields.io/badge/Graph-FalkorDB-red.svg)](https://falkordb.com/)

> **A high-velocity, graph-native regression prevention engine built on FalkorDB.**  
> Guard selects the exact minimal subset of tests to run after an AI coding agent modifies code, measures a multi-factor **Trust Score**, and deterministically triggers hard fallbacks to full test suites when graph confidence drops.

---

## Quickstart

### 1. Install Guard
```bash
uv tool install guard-cli
# Or with embedded FalkorDB support on Python 3.12+:
# uv tool install "guard-cli[embedded]"
```

### 2. Initialize in your Repository
```bash
cd /path/to/your/repo
guard init
```
`guard init` auto-detects your Python environment, sets up FalkorDB (server, docker, or embedded), ingests static call graphs & dynamic test coverage, and configures agent integrations (Claude Code Stop hook, AGENTS.md, .gitignore).

### 3. Check System Health
```bash
guard doctor
```
Verifies backend connectivity, graph integrity, git freshness, and integration settings.

---

## Verified Benchmark Results (Held-Out Evaluation)

Evaluated against **`pallets/flask`** (494 tests) across 24 held-out mutants under a frozen protocol (`evals/split.json`, `PLAN.md`).

All metrics are evaluated and reported as **Paired Metrics** (Escape Rate $\leftrightarrow$ Fallback Rate $\leftrightarrow$ Savings Ratio):

| Strategy / Engine | Escape Rate (Paired) | Savings Ratio (Paired) | Fallback Rate (Paired) | Killable Evaluated | Escapes |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`run-all`** (Ground Truth) | 0.0% (0/17) | 0.0% | 100.0% (24/24) | 17 | None |
| **`same-file`** (Heuristic) | 17.6% (3/17) | 77.3% | 0.0% (0/24) | 17 | `m08`, `m16`, `m30` |
| **`naive-guess`** (Agent Guess) | 17.6% (3/17) | 77.5% | 0.0% (0/24) | 17 | `m08`, `m16`, `m30` |
| **`guard` (Full System)** | **0.0% (0/17)** | **67.3%** | **25.0% (6/24)** | 17 | **0 (Zero)** |
| *Ablation 1: `guard-no-confidence`* | 0.0% (0/17) | 77.1% | 20.8% (5/24) | 17 | None |
| *Ablation 2: `guard-no-widening`* | 0.0% (0/17) | 73.3% | 25.0% (6/24) | 17 | None |

> **Key Result**: Guard achieved a **0.0% Escape Rate** while delivering **67.3% Test-Time Savings** compared to `run-all`, completely eliminating the 17.6% escape rate of naive heuristics.

### Case Study: Root Cause of `m08` Escape Under `same-file`
- **Mutant `m08`** inverted an `if not` condition in `src/flask/helpers.py:45`.
- `same-file` and `naive-guess` selected only `tests/test_helpers.py` (30 tests) $\to$ **0 failures reported (Escape)**.
- `guard` traversed FalkorDB `COVERED_BY` edges and detected dependent execution paths in `tests/test_basic.py`, `tests/test_blueprints.py`, and `tests/test_templating.py` (26 tests) $\to$ **Caught failure in 0.13s (0.0% escape)**.

---

## Problem Statement & Motivation

When AI coding agents (Claude Code, Cursor, Codex, OpenCode) modify complex codebases, running the entire test suite on every step slows iteration cycles to a crawl. Conversely, naive heuristics introduce catastrophic silent escapes:

- **Same-File Heuristic (`same-file`)**: Only runs tests in the matching test file (e.g., changes in `src/flask/helpers.py` $\to$ run `tests/test_helpers.py`). Foundational helpers, middleware, and lifecycle hooks are heavily exercised across disparate modules (`test_basic.py`, `test_blueprints.py`, `test_templating.py`). On the held-out benchmark, **`same-file` suffered a 17.6% Escape Rate** (3 missed failures).
- **Agent Guessing (`naive-guess`)**: LLMs predicting test paths based on file names or semantic similarity produce identical blind spots and hallucinate coverage.
- **Run-All Suite (`run-all`)**: 100% safe, but destroys developer velocity and agent autonomy on non-trivial suites.

**Guard's Core Thesis**: Code relationships and test executions form a graph topology. By indexing static AST relationships and per-test dynamic coverage contexts inside **FalkorDB**, Guard computes exact dependency subgraphs, measures empirical test confidence, dynamically widens around ambiguous dynamic dispatch, and enforces hard overrides when evidence is absent.

---

## Architecture & System Design

Guard operates as a deterministic, graph-native verification pipeline connecting static code structure, dynamic coverage telemetry, and autonomous agent loops:

1. **AST Diff Analyzer (`guard.thin_slice`)**: Inspects unified git diffs, identifies modified lines, and resolves them to exact function boundaries while flagging test file modifications.
2. **FalkorDB Graph Engine (`guard.db`)**: Maintains structural call/import relationships and empirical per-test coverage contexts (`COVERED_BY`) in FalkorDB for sub-millisecond Cypher graph traversals.
3. **Decision Engine (`guard.decision`)**: Pre-emptively checks hard safety overrides (uncovered functions, dynamic dispatch, touched tests), computes the multi-factor Trust Score, and routes execution to the appropriate policy level.
4. **Self-Healing Feedback Loop (`guard.feedback`)**: Injects high-confidence `miss_repair` edges whenever a missed failure is detected, continuously hardening the graph against future escapes.

```
       +-----------------------+
       |   AI Agent Git Diff   |
       +-----------+-----------+
                   |
                   v
       +-----------------------+
       |   AST Diff Analyzer   | -> Identifies modified functions & test files
       +-----------+-----------+
                   |
                   v
       +-----------------------+
       |  FalkorDB Graph Engine| -> Queries COVERED_BY edges, call paths,
       +-----------+-----------+    and dynamic dispatch topology
                   |
                   v
       +-----------------------+
       |    Decision Engine    | -> Evaluates hard overrides & Trust Score
       +-----------+-----------+
                   |
         +---------+---------+
         |                   |
    Trust >= 0.8        Trust < 0.8 / Override
         |                   |
         v                   v
+-----------------+ +-----------------+
| Targeted Subset | | Full Test Suite |
+-----------------+ +-----------------+
```

### FalkorDB Graph Schema

#### Nodes
- `(:File {path})`: Source files and test files in the repository.
- `(:Function {id, file, name, qualname, start, end, has_dynamic_dispatch, no_evidence})`: Function and method definitions.
- `(:Test {id, file, name, qualname, start, end, flake_rate})`: Pytest test units.
- `(:Run {id, timestamp, commit_sha, duration_ms, total_tests, passed, failed})`: Historical test execution runs.

#### Edges
- `(:Function)-[:DEFINED_IN]->(:File)`: Static structural hierarchy.
- `(:Test)-[:DEFINED_IN]->(:File)`: Static test placement.
- `(:Function)-[:CALLS {source: 'static', confidence: 0.6, last_verified_sha}]->(:Function)`: Multi-hop static call graph.
- `(:File)-[:IMPORTS {source: 'static', confidence: 0.6}]->(:File)`: Module import topology.
- `(:Function)-[:COVERED_BY {source: 'coverage'|'miss_repair', confidence, evidence_count, last_verified_sha}]->(:Test)`: Verified dynamic execution evidence connecting modified functions directly to covering tests.
- `(:Test)-[:FAILED_IN {source: 'test_run', error_message}]->(:Run)`: Historical test failure records.

---

## Decision Engine & Trust Model

Guard evaluates code changes using a strict two-stage process: **Hard Safety Overrides** followed by the **Empirical Trust Score Policy**.

### 1. Hard Safety Overrides (Pre-Emptive Gating)
Before computing continuous scores, Guard enforces three non-bypassable guardrails:
1. **Test Files Touched**: If any test file is modified or added, Guard forces `run-all` with a safety warning.
2. **Missing Evidence (`no_evidence`)**: If any modified function lacks dynamic coverage evidence in FalkorDB, Guard automatically falls back to `run-all` (never guess when unmapped).
3. **Dynamic Dispatch Flagged**: If AST analysis flags dynamic dispatch (`getattr`, `setattr`, `eval`, `**kwargs` dispatch), Guard automatically triggers **Dynamic Widening**, expanding the candidate test set to include all module tests.

### 2. Trust Score Formula
When no hard overrides force `run-all`, Guard computes the composite trust metric:

$$\text{Trust} = 0.5 \cdot \text{EvidenceRatio} + 0.3 \cdot \text{Freshness} + 0.2 \cdot (1 - \text{UncertainRatio})$$

- $\text{EvidenceRatio}$: Mean of the highest covering-edge confidence per modified function ($0.0$ for functions without covering edges).
- $\text{Freshness}$: Proportion of evidence edges whose `last_verified_sha` matches the current commit SHA.
- $\text{UncertainRatio}$: Proportion of modified functions flagged with dynamic dispatch patterns.

### 3. Three-Level Execution Policy
- **$\text{Trust} \ge 0.8$ (`subset`)**: Execute only the directly covering tests mapped via high-confidence `COVERED_BY` edges.
- **$0.5 \le \text{Trust} < 0.8$ (`medium`)**: Execute the covering subset plus all tests associated with the modified modules.
- **$\text{Trust} < 0.5$ (`run-all`)**: Enforce full test suite fallback.

---

## Claude Code & Agent Integration

> Both the Claude Code Stop hook and the Antigravity integration are
> labeled **experimental**. The Antigravity `hooks.json` schema was verified against
> [Antigravity's official hook documentation](https://antigravity.google/docs/hooks), but
> both integrations have only been validated with simulated stdin/stdout input. A real
> live session (Claude Code, Antigravity) has not yet confirmed end-to-end behavior.

Guard integrates into autonomous coding workflows:

- **Claude Code Stop Hook**: Installed via `guard hook install` into `.claude/settings.local.json`. Whenever Claude attempts to conclude a task, the Stop hook evaluates the diff. If tests fail, it blocks completion (Exit 2) and injects a concise $\le$ 30 line failure report.
- **Idle-Turn Optimization**: Caches working-tree SHA-256 fingerprints and skips unchanged turns and non-Python diffs.
- **Loop Guard**: Caps consecutive failures at 3 attempts, handing control back to the user before burning tokens.
- **Audit Log**: Appends all hook executions, test results, and decisions to `.guard/events.jsonl`.

---

## CLI Reference

### `guard init`
Initializes Guard in a repository, detects backends, and configures integrations:
```bash
guard init [--backend server|docker|embedded] [--skip-coverage]
```

#### Backends & Platform Support

Guard supports three FalkorDB backend topologies:
1. **Server (`--backend server`)**: Connects to an existing FalkorDB instance (default: `localhost:6379`). Works across all platforms.
2. **Docker (`--backend docker`)**: Automatically launches and manages a dedicated `guard-falkordb` container on port 6390. Works on any platform with Docker installed.
3. **Embedded (`--backend embedded`)**: Zero-configuration, in-process FalkorDBLite instance.
   - **Supported OS & Platform Requirements**:
     - **Python**: 3.12 or newer
     - **Linux**: `glibc` 2.39 or newer (e.g., Ubuntu 24.04+, Fedora 40+)
     - **macOS**: macOS 15 (Sequoia) or newer
   - **Platform Fallback**: On unsupported platforms (such as Linux with glibc < 2.39 or macOS < 15), Guard prints a clear message:
     ```text
     no embedded build for this platform, use Docker or a server
     ```
     and guides you to use `--backend docker` or `--backend server` instead of failing with a build error.

### `guard doctor`
Verifies system health, backend reachability, graph counts, and settings:
```bash
guard doctor [--fix]
```

### `guard run`
Executes agent pre-completion test verification on the current working tree diff:
```bash
guard run [--repo /path/to/repo]
```

### `guard check`
Computes the test selection decision without executing tests (outputs JSON schema v1.0 or text):
```bash
guard check [--repo /path/to/repo] [--json]
```

### `guard hook`
Manages Claude Code and agent hook configurations (experimental — see note above):
```bash
guard hook install [--shared] [--antigravity]
guard hook status
guard hook uninstall [--antigravity]
```

### `guard feedback`
Repairs the graph after an unexpected failure:
```bash
guard feedback --function "src/flask/helpers.py::url_for" --test "tests/test_helpers.py::test_url_for"
```

---

## Documentation & Visualizations

Additional architectural diagrams, interactive visualizations, and test reports are available in the [`docs/`](docs/) directory:
- [Interactive 3D Flow Architecture](docs/project_flow_3d.html)
- [Safety Layer Overview](docs/falkordb-safety-layer.html)
- [Verification Reports](reports/)

---

## License

MIT License. See [LICENSE](LICENSE) for details.
