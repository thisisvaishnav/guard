# Graph Report - guard  (2026-10-22)

## Corpus Check
- 130 files · ~107,763 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 54 file(s) not represented in the graph (top: .diff 40, (none) 6, .patch 4)

## Summary
- 1048 nodes · 2376 edges · 90 communities (49 shown, 41 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 144 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f08f989b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- guard_cli/doctor_cmd.py
- decide
- test_doctor_cmd.py
- guard_cli/hook.py
- antigravity.py
- pytest
- build_safety_figure.mjs
- guard_cli/ingest/coverage.py
- _Collector
- compilerOptions
- package.json
- T3: Static graph
- vite.config.ts
- devDependencies
- EyeTracker.tsx
- App.tsx
- guard_cli/thin_slice.py
- harness.py
- guard_cli/agent_integration.py
- subprocess
- scripts
- GraphBackend
- verify_s1.py
- dependencies
- json
- sys
- FalkorDB Service
- DockerBackend
- test_commit_bypass_fresh_session.py
- verify_prep.sh
- Formal Eval Report: Task T2
- Nokia Logo
- Mindflow Logo
- Freepik Logo
- Noota Logo
- Salesforce Logo
- MariaDB Logo
- Coral Glow Graphic
- G2 Logo
- Gojiberry Logo
- Hero Glow Background
- Louis Portrait
- Warrant Logo
- Verification Reports README
- Changelog
- ServerBackend
- os
- time
- verify_t1.py
- guard_cli/ingest/static.py
- test_static.py
- guard_cli/api.py
- figma-make-app
- guard_cli/cli.py
- guard-cli
- guard
- vercel.json
- verify_t4.py
- test_api_and_hook.py
- InstallTabs.tsx
- components.json
- check_idle_turn
- CodeBlock.tsx
- guard
- verify_t3.py
- guard_cli/events.py
- guard_cli/db.py
- get_graph
- check
- test_coverage.py
- temp_repo
- run_session_start_hook
- StaticResult
- eval_t2.py
- isolated_git_repo

## God Nodes (most connected - your core abstractions)
1. `run_stop_hook()` - 48 edges
2. `resolve_backend()` - 22 edges
3. `load_state()` - 22 edges
4. `run()` - 21 edges
5. `GraphBackend` - 21 edges
6. `decide()` - 21 edges
7. `check_idle_turn()` - 20 edges
8. `DockerBackend` - 19 edges
9. `EmbeddedBackend` - 19 edges
10. `main()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `1. Scope & Acceptance Criteria Checked` --references--> `GraphBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py
- `1. Scope & Acceptance Criteria Checked` --references--> `DockerBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py
- `1. Scope & Acceptance Criteria Checked` --references--> `EmbeddedBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py
- `test_repo_graph_name()` --calls--> `get_repo_graph_name()`  [INFERRED]
  tests/test_backend.py → guard_cli/backend.py
- `1. Scope & Acceptance Criteria Checked` --references--> `ServerBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py

## Import Cycles
- None detected.

## Communities (90 total, 41 thin omitted)

### Community 1 - "decide"
Cohesion: 0.08
Nodes (28): Change, compute_trust(), CoveringTest, decide(), Decision, EvidenceEdge, _fresh(), FunctionEvidence (+20 more)

### Community 2 - "test_doctor_cmd.py"
Cohesion: 0.10
Nodes (21): cmd_doctor(), apply_fixes(), check_backend(), check_environment(), check_freshness(), check_hook_timeout(), check_integrations(), check_target_repo() (+13 more)

### Community 3 - "guard_cli/hook.py"
Cohesion: 0.13
Nodes (16): resolve_diff_ref(), clear_last_passed_fingerprint(), clear_last_verified_sha(), get_baseline_sha(), get_ingest_sha(), get_last_verified_sha(), get_repo_baseline_sha(), get_repo_last_verified_sha() (+8 more)

### Community 4 - "antigravity.py"
Cohesion: 0.20
Nodes (10): _contains_guard_hook(), _find_guard_hook(), get_guard_executable(), get_hooks_file_path(), install(), status(), uninstall(), test_antigravity_install_and_status() (+2 more)

### Community 5 - "pytest"
Cohesion: 0.08
Nodes (16): check_embedded_platform_support(), EmbeddedBackend, test_api_check_strict_mode_raises(), test_docker_backend_describe(), test_embedded_backend_live(), test_embedded_backend_platform_check(), test_embedded_backend_version_gate(), test_repo_graph_name() (+8 more)

### Community 6 - "build_safety_figure.mjs"
Cohesion: 0.13
Nodes (25): at(), body, byDepth(), CARRIAGE, D(), DIAL, L(), MATRIX (+17 more)

### Community 7 - "guard_cli/ingest/coverage.py"
Cohesion: 0.14
Nodes (10): compute_flakiness(), CoverageResult, ingest_coverage(), normalize_test_id(), read_coverage_contexts(), run_pytest_once(), RunResult, _write_to_falkordb() (+2 more)

### Community 9 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, baseUrl, isolatedModules, jsx, lib, module, moduleResolution (+10 more)

### Community 10 - "package.json"
Cohesion: 0.12
Nodes (14): name, private, type, version, cn, @fontsource-variable/geist, oxfmt, shadcn (+6 more)

### Community 11 - "T3: Static graph"
Cohesion: 0.23
Nodes (12): S1: SPIKE: per-test coverage, T0: Evaluation harness, T1: Target repo and environment, T2: Schema, T3: Static graph, T4: Coverage evidence, T5: Decision engine, T5a: Thin slice (+4 more)

### Community 12 - "vite.config.ts"
Cohesion: 0.15
Nodes (5): figmaReactRefreshBoundaryFallback(), FigmaSiteConfiguration, @tailwindcss/vite, vite, @vitejs/plugin-react

### Community 13 - "devDependencies"
Cohesion: 0.20
Nodes (10): devDependencies, oxfmt, tailwindcss, @tailwindcss/vite, @types/node, @types/react, @types/react-dom, typescript (+2 more)

### Community 14 - "EyeTracker.tsx"
Cohesion: 0.23
Nodes (11): clamp(), Eye, LINES, measure(), outline(), radii, SHAPES, stillness() (+3 more)

### Community 15 - "App.tsx"
Cohesion: 0.17
Nodes (14): App(), Arrow(), GithubIcon(), ProspectStack(), SectionTitle(), SignalIcon(), AgentIcon(), AgentIconProps (+6 more)

### Community 16 - "guard_cli/thin_slice.py"
Cohesion: 0.15
Nodes (10): ChangedFunction, CheckResult, guard_check(), parse_unified_diff(), resolve_changed_functions(), thin_slice_decision(), test_parse_unified_diff(), test_thin_slice_decision_fallback_on_no_evidence() (+2 more)

### Community 17 - "harness.py"
Cohesion: 0.18
Nodes (9): apply_mutant(), evaluate_diff(), evaluate_mutant(), main(), reset_repo(), resolve_strategy_tests(), run_evaluation(), run_pytest() (+1 more)

### Community 18 - "guard_cli/agent_integration.py"
Cohesion: 0.26
Nodes (4): apply_patch(), count_collected_tests(), reset_repo(), run_agent_guard()

### Community 19 - "subprocess"
Cohesion: 0.27
Nodes (3): extract_guard_commands(), main(), temp_git_repo()

### Community 20 - "scripts"
Cohesion: 0.40
Nodes (5): scripts, build, dev, format, preview

### Community 21 - "GraphBackend"
Cohesion: 0.12
Nodes (4): GraphBackend, check_graph(), test_check_graph_empty(), test_check_graph_populated()

### Community 22 - "verify_s1.py"
Cohesion: 0.27
Nodes (5): build_function_line_map(), inspect_coverage_mapping(), main(), run_coverage_suite(), run_plain_suite()

### Community 23 - "dependencies"
Cohesion: 0.20
Nodes (10): dependencies, @base-ui/react, class-variance-authority, cn, @fontsource-variable/geist, lucide-react, react, react-dom (+2 more)

### Community 24 - "json"
Cohesion: 0.07
Nodes (31): find_mutation_candidates(), generate_diff(), main(), select_diverse_mutants(), cmd_hook_install(), cmd_hook_status(), cmd_hook_uninstall(), check_all_settings() (+23 more)

### Community 25 - "sys"
Cohesion: 0.06
Nodes (17): cmd_init(), check_pytest_cov(), find_repo_root(), record_state(), run_baseline_and_coverage(), run_init(), test_check_pytest_cov(), test_find_repo_root_invalid() (+9 more)

### Community 30 - "test_commit_bypass_fresh_session.py"
Cohesion: 0.14
Nodes (5): _git(), repo_with_ingest(), test_committed_mutant_fresh_session_is_not_idle(), test_repo_last_verified_sha_wins_over_fresh_session_head(), test_session_start_records_repo_baseline_once()

### Community 56 - "Verification Reports README"
Cohesion: 0.29
Nodes (8): FalkorDB Logo, Verification Reports README, Task T4 Verification Report, Task T5 Verification Report, Task T5a Verification Report, Task T6 Verification Report, Task T7 Verification Report, Task T8 Verification Report

### Community 57 - "Changelog"
Cohesion: 0.13
Nodes (14): [0.1.0] - 2026-10-17, [0.1.1] - 2026-10-17, [0.1.2] - 2026-10-18, [0.1.3] - 2026-10-18, [0.1.4] - 2026-10-18, Added, Added, Added (+6 more)

### Community 58 - "ServerBackend"
Cohesion: 0.15
Nodes (7): ServerBackend, 1. Scope & Acceptance Criteria Checked, 2. Raw Test Suite Output, 3. Clean-Machine & CLI Verification, 4. Adversarial Fault Injection & Falsification (Rule 5), 5. Protected Files & Git Integrity (Rule 3), Independent Verification Report: Packaging, Backend Layer, `guard init`, and `guard doctor`

### Community 59 - "os"
Cohesion: 0.15
Nodes (8): get_repo_graph_name(), load_config(), _parse_simple_toml(), resolve_backend(), save_config(), setup_backend(), test_config_save_and_load(), test_resolve_backend_with_config()

### Community 60 - "time"
Cohesion: 0.24
Nodes (5): record_miss(), check_fixtures_exist(), check_guard_check_cli(), check_t0_integration(), main()

### Community 61 - "verify_t1.py"
Cohesion: 0.53
Nodes (3): check_falkordb(), main(), run_flask_suite()

### Community 62 - "guard_cli/ingest/static.py"
Cohesion: 0.23
Nodes (5): analyze_repo(), is_test_file(), is_test_function(), module_name(), _resolve_module()

### Community 63 - "test_static.py"
Cohesion: 0.46
Nodes (7): make(), test_custom_decorator_flags_dynamic(), test_dynamic_dispatch_is_flagged_not_guessed(), test_same_module_and_cross_module_calls(), test_self_method_calls(), test_syntax_errors_are_reported_not_fatal(), test_test_files_excluded_by_default()

### Community 64 - "guard_cli/api.py"
Cohesion: 0.16
Nodes (8): _extract_failures(), normalize_test_target_for_pytest(), run(), get_hook_timeout(), find_test_environment(), test_api_run_fail_open_returns_exit_code_zero(), test_hook_timeout_resolution_precedence(), test_timeout_event_logged()

### Community 65 - "figma-make-app"
Cohesion: 0.33
Nodes (5): Dependencies, Development Server, figma-make-app, Project Structure, Styling

### Community 66 - "guard_cli/cli.py"
Cohesion: 0.27
Nodes (10): cmd_callers(), cmd_covering_tests(), cmd_feedback(), cmd_hook_session_start(), cmd_hook_stop(), cmd_ingest_coverage(), cmd_ingest_static(), cmd_run() (+2 more)

### Community 72 - "verify_t4.py"
Cohesion: 0.53
Nodes (4): check_functions_evidence_or_flag(), check_known_covered_functions(), check_suite_runs_and_flakes(), main()

### Community 73 - "test_api_and_hook.py"
Cohesion: 0.07
Nodes (19): format_failure_summary(), run_stop_hook(), get_session_blocks(), test_antigravity_hook_decision_protocol_continue_on_failure(), test_antigravity_hook_decision_protocol_pass(), _git(), test_item1_baseline_new_conversation_blocks_on_committed_change(), test_item2_stdout_purity_pipe_json_tool() (+11 more)

### Community 74 - "InstallTabs.tsx"
Cohesion: 0.19
Nodes (15): Badge(), LABELS, Agent, initialValue(), InstallSteps(), InstallTabs(), Step(), Tabs() (+7 more)

### Community 75 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 76 - "check_idle_turn"
Cohesion: 0.16
Nodes (13): check_idle_turn(), compute_turn_fingerprint(), is_working_tree_clean(), get_last_passed_fingerprint(), set_baseline_sha(), set_last_passed_fingerprint(), set_last_verified_sha(), test_committed_flask_mutant_hook_exits_2() (+5 more)

### Community 79 - "verify_t3.py"
Cohesion: 0.53
Nodes (4): check_callers_for_sample_functions(), check_graph_counts_and_dynamic(), check_parser_tests(), main()

### Community 80 - "guard_cli/events.py"
Cohesion: 0.18
Nodes (5): get_guard_dir(), log_event(), read_events(), test_item5_database_down_allows_stop_and_logs_fail_open(), test_event_logging()

### Community 81 - "guard_cli/db.py"
Cohesion: 0.11
Nodes (15): _batches(), ensure_schema(), get_backend(), get_callers(), get_covering_tests(), get_graph_state(), get_schema_counts(), reset_graph() (+7 more)

### Community 82 - "get_graph"
Cohesion: 0.24
Nodes (5): callers(), covering_tests(), report_miss(), get_graph(), test_cli_default_graph_resolution()

### Community 83 - "check"
Cohesion: 0.22
Nodes (5): check(), _format_reasons(), cmd_check(), test_api_check_fail_open_by_default(), test_api_check_schema_version_and_keys()

### Community 86 - "run_session_start_hook"
Cohesion: 0.24
Nodes (6): _capture_payload(), _git_head_sha(), read_hook_input(), resolve_hook_context(), run_session_start_hook(), test_item3_payload_capture_with_fixture()

### Community 88 - "StaticResult"
Cohesion: 0.19
Nodes (9): FuncDef, StaticResult, test_get_callers_multi_hop(), test_graph(), test_write_coverage_and_query_covering_tests(), test_write_run_and_failed_in(), test_write_static_creates_nodes_and_edges(), test_record_miss_creates_repair_edge() (+1 more)

### Community 92 - "eval_t2.py"
Cohesion: 0.20
Nodes (5): main(), run_capability_evals(), run_regression_evals(), check_feedback_loop(), main()

## Knowledge Gaps
- **139 isolated node(s):** `PLATE`, `MATRIX`, `NODES`, `CARRIAGE`, `POST` (+134 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 456 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **41 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GraphBackend` connect `GraphBackend` to `guard_cli/doctor_cmd.py`, `test_doctor_cmd.py`, `pytest`, `os`, `guard_cli/db.py`, `sys`, `ServerBackend`, `DockerBackend`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **What connects `PLATE`, `MATRIX`, `NODES` to the rest of the system?**
  _139 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `decide` be split into smaller, more focused modules?**
  _Cohesion score 0.08220211161387632 - nodes in this community are weakly interconnected._
- **Why does `run_stop_hook()` connect `test_api_and_hook.py` to `guard_cli/api.py`, `guard_cli/cli.py`, `guard_cli/hook.py`, `check_idle_turn`, `guard_cli/events.py`, `subprocess`, `run_session_start_hook`, `json`, `os`, `test_commit_bypass_fresh_session.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Should `test_doctor_cmd.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10037878787878787 - nodes in this community are weakly interconnected._
- **Why does `DockerBackend` connect `DockerBackend` to `guard_cli/doctor_cmd.py`, `test_doctor_cmd.py`, `pytest`, `GraphBackend`, `ServerBackend`, `os`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Should `guard_cli/hook.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13213213213213212 - nodes in this community are weakly interconnected._