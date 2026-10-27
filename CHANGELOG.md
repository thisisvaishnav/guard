# Changelog

All notable changes to Guard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.5] - 2026-10-27

### Added
- **Zero-Daemon Embedded SQLite Architecture (`.guard/graph.db`)**:
  - Replaced the hard requirement for Docker containers and external FalkorDB servers with standard library `sqlite3`.
  - Embedded storage operates with **0 MB background RAM** and **zero background daemons**.
  - Multi-hop blast-radius traversal implemented using SQLite Recursive Common Table Expressions (`WITH RECURSIVE`).
  - Sub-20ms query latency with WAL mode (`PRAGMA journal_mode = WAL`) and optimized indexes on functions, calls, and coverage mappings.
- **Modern Landing Page & Interactive Diff Simulator**:
  - Full interactive Blast-Radius simulator demonstrating AST static analysis -> SQLite CTE traversal -> Targeted test execution.
  - Scroll-illuminated Tagline Reveal component (`landing/src/components/TaglineReveal.tsx`).
  - Developer FAQ accordion covering zero daemons, offline privacy, and fail-closed safety invariants.
  - Upgraded typography to Geist Variable with balanced headers and responsive mobile layout adhering to core design principles.
- **Multi-Backend Abstraction**:
  - Added `GraphStore` and `GraphBackend` abstraction layers supporting `sqlite` (default), `server` (remote FalkorDB), `docker`, and `embedded` (FalkorDBLite).
- **Bottle & Flask Empirical Benchmarks**:
  - Demonstrated 94.8% test reduction on Bottle (363 tests) with 100% regression capture.
  - Zero missed failures on Pallets Flask benchmark suite.

### Fixed
- **Tagline Word Spacing**: Fixed inter-word whitespace collapse in animated tagline text.
- **Header Navigation Glitch**: Eliminated stray character in navigation bar preceding "Workflow".
- **Pre-Hydration Reload Flash**: Removed static fallback `#root` header block in `index.html` preventing momentary text flash on page refresh.
- **Hook Robustness & Stdin Deadlock**: Hardened non-blocking stdin ingestion and loop guard mechanisms.

## [0.1.4] - 2026-10-18

### Fixed
- **Single-Stream Stdout Purity**: Routed JSON decision output strictly to the dedicated stdout stream, eliminating dual-writes that previously leaked the decision payload into stderr when stdout was redirected to fd 2.

## [0.1.3] - 2026-10-18

### Fixed
- **CLI Hook Subcommands**: Fixed missing `set_defaults(fn=...)` handlers for `guard hook status`, `guard hook install`, and `guard hook uninstall` which caused `AttributeError: 'Namespace' object has no attribute 'fn'`. Added safety fallback in `main()` to gracefully display help if a subcommand lacks a handler.
- **Coverage Ingest Target**: Automatically resolve virtualenv Python binary and detect `src/flask` coverage source targets when ingesting target repositories.

## [0.1.2] - 2026-10-18

### Added
- **PyPI Project Links**: `[project.urls]` block added so the PyPI page links to the repository, issue tracker, and changelog.
- **Antigravity Hook Subcommand Support**: `guard hook install|uninstall|status --antigravity` now manages stop hooks in Antigravity's `.agents/hooks.json` directly from the CLI.
- **Payload Capture**: `GUARD_DEBUG_PAYLOAD=1` writes raw stdin payloads to `.guard/last_payload.json` for live debugging and testing.

### Changed
- **Antigravity Hook Hardening**:
  - Writes absolute executable path into `.agents/hooks.json` to prevent PATH truncation failures inside subshells.
  - Guaranteed pure stdout JSON stream (`{"decision":"continue"|"stop","reason":"..."}`) with all logs, warnings, and diagnostic output isolated to stderr, always exiting 0.
  - Verified hook format and field names against official Antigravity documentation (`hooks.md`), configuring `SessionStart`, `PreInvocation`, and `Stop` with execution timeouts in seconds.
- **Actionable Block Message**: Hook block summary lists failing tests, changed functions, and instructs: "Fix the source code. Do not edit, skip, or delete tests."
- **Claude Code Hook Format Cleanup**: `guard hook install` now writes the canonical Claude Code shape (`{"matcher": "", "hooks": [{type, command, timeout}]}`) under `hooks.Stop`, dropping the stray non-standard top-level `command` key. Status/uninstall still detect the legacy shape written by 0.1.x releases.

### Fixed
- **Commit Bypass via Fresh Session ID (High)**: A new agent session ID no longer resets the diff baseline to the current HEAD, which let a broken commit look like a clean tree and pass the Stop hook. The baseline is now repo-level — `repo.last_verified_sha` (updated on every successful run), falling back to the SHA recorded at ingest in `.guard/state.json` — and is therefore independent of session IDs.
- **Loop Guard Off-by-One**: Corrected block cap calculation to ensure the agent receives exactly 3 consecutive blocks before handing control back to the human.
- **Database Down Fail-Open**: When FalkorDB is unreachable, allows stop with `{"decision": "stop", "reason": "Guard skipped: database unreachable"}` and logs a `fail_open` event (never a `blocked` event).
- **Executable Validation in Doctor**: `guard doctor` verifies the absolute binary path configured in `.agents/hooks.json` actually exists on the filesystem.

## [0.1.1] - 2026-10-17

### Changed
- **BREAKING (Library imports)**: Migrated core implementation from top-level `guard` namespace to `guard_cli`. Top-level `guard/` is excluded from published wheels to resolve PyPI namespace collision with the unrelated `guard` package. CLI entry points (`guard` and `guard-cli`) remain unchanged and fully backward compatible. Local shims retained in source repo for legacy test suites.

### Added
- **Commit Bypass Defense**: Track `baseline_sha` and `last_verified_sha` in session state. When an agent commits changes to git, Guard diffs against the last verified commit rather than relying solely on `git status --porcelain`, preventing unverified commits from escaping.
- **Comprehensive Turn Fingerprint**: Turn cache key now binds modified files, staged changes (`git diff --cached`), untracked files, Guard version, and FalkorDB graph generation state to prevent stale cache passes.
- **Multi-Agent Stop Hook Architecture**: Support for Antigravity CLI (`.agents/hooks.json` returning JSON decision protocol `{"decision": "continue"|"stop"}`) alongside Claude Code (`.claude/settings.local.json` exit code 2 / 0).
- **Distinct Event Reasons**: Idle turn events in `.guard/events.jsonl` explicitly record specific reason strings: `clean_tree`, `non_python_only`, and `cached_pass`.
- **Configurable Hook Timeout & Doctor Warning**:
  - Hook timeout configurable via `GUARD_HOOK_TIMEOUT` environment variable or `.guard/config.toml` (`[hook] timeout = ...`).
  - Timeout occurrences log a dedicated `timeout` event in `.guard/events.jsonl`.
  - `guard doctor` warns when baseline test suite duration is near the timeout threshold ($\ge 70\%$).
- **Embedded Platform Compatibility Guard**: Clear, actionable error message (`no embedded build for this platform, use Docker or a server`) when FalkorDBLite embedded backend is used on Linux with glibc < 2.39 or macOS < 15.

## [0.1.0] - 2026-10-17

### Added
- Initial public release of Guard: graph-powered test selection and safety layer for AI coding agents.
- FalkorDB graph backend support: Server (`localhost:6379`), Docker (`guard-falkordb`), and Embedded (`falkordblite`).
