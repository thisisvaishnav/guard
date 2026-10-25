# Graph Report - guard  (2026-10-25)

## Corpus Check
- 134 files · ~111,648 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 54 file(s) not represented in the graph (top: .diff 40, (none) 6, .patch 4)

## Summary
- 1116 nodes · 2520 edges · 103 communities (61 shown, 42 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 148 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e8ec1a1e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- guard_cli/init_cmd.py
- decide
- guard_cli/doctor_cmd.py
- guard_cli/hook.py
- json
- resolve_backend
- build_safety_figure.mjs
- test_diagnostics_extraction.py
- StaticResult
- compilerOptions
- package.json
- T3: Static graph
- vite.config.ts
- devDependencies
- EyeTracker.tsx
- App.tsx
- pathlib
- harness.py
- run
- subprocess
- scripts
- GraphBackend
- verify_s1.py
- dependencies
- guard_cli/integrations/claude.py
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
- guard_cli/backend.py
- time
- verify_t1.py
- guard_check
- find_test_environment
- get_hook_timeout
- figma-make-app
- Independent Verification Report: Packaging, Backend Layer, `guard init`, and `guard doctor`
- guard-cli
- guard
- vercel.json
- verify_t4.py
- run_stop_hook
- InstallTabs.tsx
- components.json
- check_idle_turn
- verify_t9.py
- guard
- verify_t3.py
- test_api_and_hook.py
- guard_cli/db.py
- guard_cli/ingest/coverage.py
- check
- guard_cli/cli.py
- verify_t8.py
- run_session_start_hook
- get_graph
- pytest
- covering_tests
- mutator.py
- guard_cli/ingest/static.py
- verify_t6.py
- verify_t0.py
- guard_cli/api.py
- _Collector
- get_repo_graph_name
- callers
- test_static.py
- _write_to_falkordb
- test_coverage.py
- test_integration_init_doctor.py
- test_graph

## God Nodes (most connected - your core abstractions)
1. `run_stop_hook()` - 50 edges
2. `run()` - 25 edges
3. `resolve_backend()` - 22 edges
4. `load_state()` - 22 edges
5. `GraphBackend` - 21 edges
6. `decide()` - 21 edges
7. `check_idle_turn()` - 20 edges
8. `DockerBackend` - 19 edges
9. `EmbeddedBackend` - 19 edges
10. `main()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `1. Scope & Acceptance Criteria Checked` --references--> `GraphBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py
- `1. Scope & Acceptance Criteria Checked` --references--> `ServerBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py
- `1. Scope & Acceptance Criteria Checked` --references--> `DockerBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py
- `1. Scope & Acceptance Criteria Checked` --references--> `EmbeddedBackend`  [INFERRED]
  reports/verify_packaging_and_init.md → guard_cli/backend.py
- `test_repo_graph_name()` --calls--> `get_repo_graph_name()`  [INFERRED]
  tests/test_backend.py → guard_cli/backend.py

## Import Cycles
- None detected.

## Communities (103 total, 42 thin omitted)

### Community 0 - "guard_cli/init_cmd.py"
Cohesion: 0.10
Nodes (13): check_pytest_cov(), find_repo_root(), record_state(), run_baseline_and_coverage(), run_init(), run_static_ingest(), setup_backend(), write_integrations() (+5 more)

### Community 1 - "decide"
Cohesion: 0.08
Nodes (28): Change, compute_trust(), CoveringTest, decide(), Decision, EvidenceEdge, _fresh(), FunctionEvidence (+20 more)

### Community 2 - "guard_cli/doctor_cmd.py"
Cohesion: 0.11
Nodes (20): apply_fixes(), check_backend(), check_environment(), check_freshness(), check_graph(), check_integrations(), check_target_repo(), CheckResult (+12 more)

### Community 3 - "guard_cli/hook.py"
Cohesion: 0.13
Nodes (16): resolve_diff_ref(), clear_last_passed_fingerprint(), clear_last_verified_sha(), get_baseline_sha(), get_ingest_sha(), get_last_verified_sha(), get_repo_baseline_sha(), get_repo_last_verified_sha() (+8 more)

### Community 4 - "json"
Cohesion: 0.15
Nodes (14): _contains_guard_hook(), _find_guard_hook(), get_guard_executable(), get_hooks_file_path(), install(), status(), uninstall(), test_antigravity_hook_decision_protocol_continue_on_failure() (+6 more)

### Community 5 - "resolve_backend"
Cohesion: 0.12
Nodes (7): check_embedded_platform_support(), EmbeddedBackend, resolve_backend(), test_embedded_import_error_catches_glibc_link_failure(), test_embedded_platform_glibc_below_2_39(), test_embedded_platform_macos_below_15(), test_embedded_platform_non_posix()

### Community 6 - "build_safety_figure.mjs"
Cohesion: 0.13
Nodes (25): at(), body, byDepth(), CARRIAGE, D(), DIAL, L(), MATRIX (+17 more)

### Community 7 - "test_diagnostics_extraction.py"
Cohesion: 0.11
Nodes (11): _extract_failure_summary(), _extract_failures(), test_extract_failure_summary_captures_actionable_lines(), test_extract_failures_captures_collection_errors(), test_extract_failures_captures_error_lines(), test_extract_failures_fallback_on_errors_section(), test_extract_failures_preserves_standard_failed(), test_format_failure_summary_includes_actionable_details() (+3 more)

### Community 8 - "StaticResult"
Cohesion: 0.20
Nodes (9): record_miss(), FuncDef, StaticResult, test_get_callers_multi_hop(), test_write_coverage_and_query_covering_tests(), test_write_run_and_failed_in(), test_write_static_creates_nodes_and_edges(), test_record_miss_creates_repair_edge() (+1 more)

### Community 9 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, baseUrl, isolatedModules, jsx, lib, module, moduleResolution (+10 more)

### Community 10 - "package.json"
Cohesion: 0.11
Nodes (16): name, private, type, version, @base-ui/react, class-variance-authority, cn, @fontsource-variable/geist (+8 more)

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

### Community 16 - "pathlib"
Cohesion: 0.19
Nodes (7): ChangedFunction, CheckResult, resolve_changed_functions(), thin_slice_decision(), test_thin_slice_decision_fallback_on_no_evidence(), test_thin_slice_decision_fallback_on_test_files_touched(), test_thin_slice_selects_covering_tests()

### Community 17 - "harness.py"
Cohesion: 0.18
Nodes (9): apply_mutant(), evaluate_diff(), evaluate_mutant(), main(), reset_repo(), resolve_strategy_tests(), run_evaluation(), run_pytest() (+1 more)

### Community 18 - "run"
Cohesion: 0.19
Nodes (6): apply_patch(), count_collected_tests(), reset_repo(), run_agent_guard(), run(), test_api_run_fail_open_returns_exit_code_zero()

### Community 19 - "subprocess"
Cohesion: 0.20
Nodes (3): temp_git_repo(), isolated_git_repo(), throwaway_repo()

### Community 20 - "scripts"
Cohesion: 0.40
Nodes (5): scripts, build, dev, format, preview

### Community 22 - "verify_s1.py"
Cohesion: 0.29
Nodes (5): build_function_line_map(), inspect_coverage_mapping(), main(), run_coverage_suite(), run_plain_suite()

### Community 23 - "dependencies"
Cohesion: 0.20
Nodes (10): dependencies, @base-ui/react, class-variance-authority, cn, @fontsource-variable/geist, lucide-react, react, react-dom (+2 more)

### Community 24 - "guard_cli/integrations/claude.py"
Cohesion: 0.13
Nodes (14): check_all_settings(), _contains_guard_hook(), get_guard_executable(), get_settings_path(), install(), _matches_command(), status(), uninstall() (+6 more)

### Community 25 - "sys"
Cohesion: 0.13
Nodes (3): main(), run_capability_evals(), run_regression_evals()

### Community 30 - "test_commit_bypass_fresh_session.py"
Cohesion: 0.14
Nodes (5): _git(), repo_with_ingest(), test_committed_mutant_fresh_session_is_not_idle(), test_repo_last_verified_sha_wins_over_fresh_session_head(), test_session_start_records_repo_baseline_once()

### Community 56 - "Verification Reports README"
Cohesion: 0.29
Nodes (8): FalkorDB Logo, Verification Reports README, Task T4 Verification Report, Task T5 Verification Report, Task T5a Verification Report, Task T6 Verification Report, Task T7 Verification Report, Task T8 Verification Report

### Community 57 - "Changelog"
Cohesion: 0.13
Nodes (14): [0.1.0] - 2026-10-17, [0.1.1] - 2026-10-17, [0.1.2] - 2026-10-18, [0.1.3] - 2026-10-18, [0.1.4] - 2026-10-18, Added, Added, Added (+6 more)

### Community 59 - "guard_cli/backend.py"
Cohesion: 0.20
Nodes (5): load_config(), _parse_simple_toml(), save_config(), test_config_save_and_load(), test_resolve_backend_with_config()

### Community 60 - "time"
Cohesion: 0.31
Nodes (8): check_fixtures_exist(), check_guard_check_cli(), check_t0_integration(), main(), check_agent_runner_blocks_on_failure(), check_agent_runner_high_trust(), check_agent_runner_low_trust_forces_full(), main()

### Community 61 - "verify_t1.py"
Cohesion: 0.53
Nodes (3): check_falkordb(), main(), run_flask_suite()

### Community 62 - "guard_check"
Cohesion: 0.12
Nodes (8): guard_check(), is_test_file(), test_is_test_file_negative_cases(), test_is_test_file_positive_cases(), test_thin_slice_test_files_touched_not_triggered_by_attestation(), test_thin_slice_test_files_touched_not_triggered_by_contest(), test_thin_slice_test_files_touched_triggered_by_calc_test(), test_thin_slice_test_files_touched_triggered_by_test_file()

### Community 63 - "find_test_environment"
Cohesion: 0.20
Nodes (6): find_test_environment(), test_find_test_environment(), test_find_test_environment_respects_conda_prefix(), test_find_test_environment_respects_sys_prefix(), test_find_test_environment_respects_virtual_env(), fake_subprocess_run()

### Community 64 - "get_hook_timeout"
Cohesion: 0.31
Nodes (5): check_hook_timeout(), get_hook_timeout(), test_doctor_warns_on_slow_suite(), test_hook_timeout_resolution_precedence(), test_timeout_event_logged()

### Community 65 - "figma-make-app"
Cohesion: 0.33
Nodes (5): Dependencies, Development Server, figma-make-app, Project Structure, Styling

### Community 66 - "Independent Verification Report: Packaging, Backend Layer, `guard init`, and `guard doctor`"
Cohesion: 0.29
Nodes (6): 1. Scope & Acceptance Criteria Checked, 2. Raw Test Suite Output, 3. Clean-Machine & CLI Verification, 4. Adversarial Fault Injection & Falsification (Rule 5), 5. Protected Files & Git Integrity (Rule 3), Independent Verification Report: Packaging, Backend Layer, `guard init`, and `guard doctor`

### Community 71 - "vercel.json"
Cohesion: 0.50
Nodes (3): cleanUrls, headers, $schema

### Community 72 - "verify_t4.py"
Cohesion: 0.53
Nodes (4): check_functions_evidence_or_flag(), check_known_covered_functions(), check_suite_runs_and_flakes(), main()

### Community 73 - "run_stop_hook"
Cohesion: 0.09
Nodes (15): format_failure_summary(), run_stop_hook(), get_session_blocks(), _git(), test_item1_baseline_new_conversation_blocks_on_committed_change(), test_item2_stdout_purity_pipe_json_tool(), test_item4_block_message_content(), test_item6_block_cap_gives_three_blocks_then_handback() (+7 more)

### Community 74 - "InstallTabs.tsx"
Cohesion: 0.19
Nodes (15): Badge(), LABELS, CodeBlock(), copyText(), Agent, initialValue(), InstallSteps(), InstallTabs() (+7 more)

### Community 75 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 76 - "check_idle_turn"
Cohesion: 0.16
Nodes (13): check_idle_turn(), compute_turn_fingerprint(), is_working_tree_clean(), get_last_passed_fingerprint(), set_baseline_sha(), set_last_passed_fingerprint(), set_last_verified_sha(), test_committed_flask_mutant_hook_exits_2() (+5 more)

### Community 77 - "verify_t9.py"
Cohesion: 0.53
Nodes (4): check_demo_execution(), check_readme_content(), check_report(), main()

### Community 79 - "verify_t3.py"
Cohesion: 0.53
Nodes (4): check_callers_for_sample_functions(), check_graph_counts_and_dynamic(), check_parser_tests(), main()

### Community 80 - "test_api_and_hook.py"
Cohesion: 0.10
Nodes (10): get_guard_dir(), log_event(), read_events(), test_item5_database_down_allows_stop_and_logs_fail_open(), test_api_run_fail_open_check_skips_full_suite(), test_event_logging(), test_session_state_and_loop_guard(), test_stop_hook_clean_working_tree_exits_zero() (+2 more)

### Community 81 - "guard_cli/db.py"
Cohesion: 0.17
Nodes (8): _batches(), get_callers(), get_graph_state(), set_backend(), update_graph_meta(), write_coverage(), write_run(), write_static()

### Community 82 - "guard_cli/ingest/coverage.py"
Cohesion: 0.18
Nodes (8): compute_flakiness(), ingest_coverage(), normalize_test_id(), read_coverage_contexts(), run_pytest_once(), RunResult, test_compute_flakiness(), test_normalize_test_id()

### Community 83 - "check"
Cohesion: 0.25
Nodes (4): check(), _format_reasons(), test_api_check_fail_open_by_default(), test_api_check_schema_version_and_keys()

### Community 84 - "guard_cli/cli.py"
Cohesion: 0.18
Nodes (14): cmd_check(), cmd_doctor(), cmd_hook_install(), cmd_hook_session_start(), cmd_hook_status(), cmd_hook_stop(), cmd_hook_uninstall(), cmd_ingest_coverage() (+6 more)

### Community 85 - "verify_t8.py"
Cohesion: 0.43
Nodes (6): check_evaluation_results(), check_failure_case_and_unkillables(), check_frozen_claim(), check_mutant_counts(), check_report_artifact(), main()

### Community 86 - "run_session_start_hook"
Cohesion: 0.24
Nodes (6): _capture_payload(), _git_head_sha(), read_hook_input(), resolve_hook_context(), run_session_start_hook(), test_item3_payload_capture_with_fixture()

### Community 87 - "get_graph"
Cohesion: 0.21
Nodes (7): cmd_ingest_static(), ensure_schema(), get_backend(), get_graph(), reset_graph(), seeded_guard_graph(), temp_repo()

### Community 88 - "pytest"
Cohesion: 0.14
Nodes (10): test_api_check_strict_mode_raises(), test_docker_backend_describe(), test_embedded_backend_live(), test_embedded_backend_platform_check(), test_embedded_backend_version_gate(), test_repo_graph_name(), test_resolve_backend_preference(), test_server_backend_describe_and_graph() (+2 more)

### Community 89 - "covering_tests"
Cohesion: 0.29
Nodes (4): covering_tests(), cmd_covering_tests(), get_covering_tests(), test_cli_default_graph_resolution()

### Community 90 - "mutator.py"
Cohesion: 0.33
Nodes (4): find_mutation_candidates(), generate_diff(), main(), select_diverse_mutants()

### Community 91 - "guard_cli/ingest/static.py"
Cohesion: 0.20
Nodes (5): analyze_repo(), is_test_file(), is_test_function(), module_name(), _resolve_module()

### Community 93 - "verify_t0.py"
Cohesion: 0.60
Nodes (3): main(), verify_harness_on_run_all(), verify_split_file()

### Community 96 - "get_repo_graph_name"
Cohesion: 0.24
Nodes (5): get_repo_graph_name(), parse_unified_diff(), extract_guard_commands(), main(), test_parse_unified_diff()

### Community 97 - "callers"
Cohesion: 0.29
Nodes (4): callers(), report_miss(), cmd_callers(), cmd_feedback()

### Community 98 - "test_static.py"
Cohesion: 0.46
Nodes (7): make(), test_custom_decorator_flags_dynamic(), test_dynamic_dispatch_is_flagged_not_guessed(), test_same_module_and_cross_module_calls(), test_self_method_calls(), test_syntax_errors_are_reported_not_fatal(), test_test_files_excluded_by_default()

### Community 99 - "_write_to_falkordb"
Cohesion: 0.40
Nodes (3): CoverageResult, _write_to_falkordb(), test_coverage_write_to_graph()

## Knowledge Gaps
- **141 isolated node(s):** `PLATE`, `MATRIX`, `NODES`, `CARRIAGE`, `POST` (+136 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 488 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **42 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GraphBackend` connect `GraphBackend` to `guard_cli/init_cmd.py`, `guard_cli/doctor_cmd.py`, `Independent Verification Report: Packaging, Backend Layer, `guard init`, and `guard doctor``, `resolve_backend`, `guard_cli/backend.py`, `ServerBackend`, `DockerBackend`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **What connects `PLATE`, `MATRIX`, `NODES` to the rest of the system?**
  _141 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `guard_cli/init_cmd.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10037878787878787 - nodes in this community are weakly interconnected._
- **Why does `run_stop_hook()` connect `run_stop_hook` to `guard_cli/hook.py`, `json`, `check_idle_turn`, `test_api_and_hook.py`, `run`, `subprocess`, `guard_cli/cli.py`, `run_session_start_hook`, `test_commit_bypass_fresh_session.py`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Should `decide` be split into smaller, more focused modules?**
  _Cohesion score 0.08220211161387632 - nodes in this community are weakly interconnected._
- **Why does `resolve_backend()` connect `resolve_backend` to `guard_cli/init_cmd.py`, `guard_cli/doctor_cmd.py`, `json`, `guard_cli/backend.py`, `guard_cli/db.py`, `GraphBackend`, `get_graph`, `pytest`, `ServerBackend`, `DockerBackend`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Should `guard_cli/doctor_cmd.py` be split into smaller, more focused modules?**
  _Cohesion score 0.1140819964349376 - nodes in this community are weakly interconnected._