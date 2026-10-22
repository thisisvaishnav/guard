import { useState } from "react"
import { InstallTabs } from "@/components/install/InstallTabs"
import { TerminalDemo } from "@/components/TerminalDemo"
import { EyeTracker } from "@/components/EyeTracker"
import { AgentIcon } from "@/components/install/AgentIcon"
import { Check, Copy, Network, GitBranch, ShieldCheck } from "lucide-react"

const GithubIcon = ({ size = 16 }: { size?: number }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="currentColor"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
    />
  </svg>
)

const Arrow = ({ dark = false }: { dark?: boolean }) => (
  <span className={`arrow-box ${dark ? "arrow-dark" : ""}`} aria-hidden="true">
    ↗
  </span>
)

const SignalIcon = () => (
  <svg viewBox="0 0 120 120" aria-hidden="true">
    <circle cx="60" cy="60" r="46" />
    <circle cx="60" cy="60" r="28" />
    <circle cx="60" cy="60" r="8" className="fill" />
    <path d="M60 60 98 27M60 14v10M106 60H96" />
  </svg>
)

const ProspectStack = () => (
  <div className="prospect-stack" aria-hidden="true">
    {[
      ["TC", "test_config.py", "test_config_from_file"],
      ["TA", "test_app.py", "test_route_dispatch"],
      ["TL", "test_cli.py", "test_custom_command"],
    ].map(([initials, name, role], index) => (
      <div
        className="prospect"
        key={name}
        style={{ "--index": index } as React.CSSProperties}
      >
        <span>{initials}</span>
        <div>
          <b>{name}</b>
          <small>{role}</small>
        </div>
        <strong>{92 - index * 4}%</strong>
      </div>
    ))}
  </div>
)

const SectionTitle = ({
  children,
  light = false,
}: {
  children: React.ReactNode
  light?: boolean
}) => <h2 className={light ? "light" : ""}>{children}</h2>

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [heroCopied, setHeroCopied] = useState(false)

  const heroCommand = "uv tool install guard-cli && guard init --yes"

  const handleHeroCopy = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(heroCommand)
      } else {
        const ta = document.createElement("textarea")
        ta.value = heroCommand
        ta.style.position = "fixed"
        ta.style.opacity = "0"
        document.body.appendChild(ta)
        ta.select()
        document.execCommand("copy")
        document.body.removeChild(ta)
      }
      setHeroCopied(true)
      setTimeout(() => setHeroCopied(false), 2000)
    } catch {
      // ignore clipboard error
    }
  }

  return (
    <main>
      <section className="hero" id="top">
        <nav className="nav shell">
          <a className="brand" href="#top" aria-label="Guard home">
            <EyeTracker size={30} shape="Cube" />
            <span>guard</span>
          </a>
          <button
            className="menu-button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="Toggle navigation"
            aria-expanded={menuOpen}
          >
            <span />
            <span />
          </button>
          <div className={`nav-links ${menuOpen ? "open" : ""}`}>
            <a href="#workflow" onClick={() => setMenuOpen(false)}>
              Workflow
            </a>
            <a href="#install" onClick={() => setMenuOpen(false)}>
              Install
            </a>
            <a href="#features" onClick={() => setMenuOpen(false)}>
              Features
            </a>
            <a href="#stories" onClick={() => setMenuOpen(false)}>
              Benchmarks
            </a>
            <a
              href="https://github.com/thisisvaishnav/guard"
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setMenuOpen(false)}
            >
              GitHub
            </a>
          </div>
          <div className="nav-actions">
            <a
              className="solid-github-btn"
              href="https://github.com/thisisvaishnav/guard"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="View Guard repository on GitHub"
            >
              <GithubIcon size={14} aria-hidden="true" />
              <span>GitHub</span>
            </a>
          </div>
        </nav>

        <svg
          className="hero-orange-line"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "none",
            zIndex: 1,
          }}
          viewBox="0 0 1440 900"
          fill="none"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            d="M -40 220 C 220 80 440 340 760 180 C 1060 40 1260 280 1480 190"
            stroke="#f46722"
            strokeWidth="1.2"
            strokeOpacity="0.55"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d="M -20 460 C 280 540 520 280 820 440 C 1120 600 1300 360 1480 480"
            stroke="#ff5c51"
            strokeWidth="1"
            strokeOpacity="0.4"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d="M 60 20 C 180 340 400 640 720 720 C 1040 800 1280 620 1460 920"
            stroke="#f46722"
            strokeWidth="1"
            strokeOpacity="0.25"
            vectorEffect="non-scaling-stroke"
          />
        </svg>

        <div className="hero-lines" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>

        <div className="hero-content shell">
          <a
            className="yc-badge"
            href="https://falkordb.com"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Powered by FalkorDB"
          >
            <img
              src="/assets/falkordb.svg"
              alt="FalkorDB"
              style={{
                width: 22,
                height: 22,
                borderRadius: 0,
                display: "block",
              }}
            />
            <span>Powered by</span>
            <em>FalkorDB</em>
          </a>

          <h1 className="hero-headline">
            Stop AI agents from finishing
            <span>with broken code.</span>
          </h1>

          <p className="hero-subhead">
            Guard runs only the tests a change can break, and blocks your coding agent until they pass.
          </p>

          {/* Bash Command Box with Copy button (White theme) */}
          <div className="hero-cmd-container">
            <div className="hero-cmd-box">
              <div className="hero-cmd-dots" aria-hidden="true">
                <span className="dot dot-close" />
                <span className="dot dot-min" />
                <span className="dot dot-max" />
              </div>
              <span className="hero-prompt-symbol" aria-hidden="true">$ </span>
              <code className="hero-cmd-code">{heroCommand}</code>
              <button
                type="button"
                className="hero-copy-btn"
                onClick={handleHeroCopy}
                aria-label={heroCopied ? "Copied command" : "Copy command to clipboard"}
              >
                {heroCopied ? (
                  <>
                    <Check size={14} className="icon-copied" aria-hidden="true" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy size={14} aria-hidden="true" />
                    <span>Copy</span>
                  </>
                )}
              </button>
            </div>
            <p className="hero-privacy-line">
              Runs locally. Your code never leaves your machine.
            </p>
          </div>

          {/* Factual Proof Line */}
          <div className="hero-proof-strip">
            <a href="#stories" className="hero-proof-link">
              <span className="proof-highlight">0 missed failures</span> across 17 killable mutants on Flask, with <strong>67% less test time</strong> ↗
            </a>
          </div>

          {/* Works with strip */}
          <div className="hero-works-with-strip">
            <span className="works-with-tag">Works with:</span>
            <div className="works-with-list">
              <div className="works-agent-pill">
                <AgentIcon id="claude-code" size={17} />
                <span>Claude Code</span>
              </div>
              <div className="works-agent-pill">
                <AgentIcon id="antigravity" size={17} />
                <span>Antigravity</span>
              </div>
            </div>
          </div>

          {/* Terminal Demonstration */}
          <div className="hero-demo-section">
            <TerminalDemo />
          </div>
        </div>
      </section>

      {/* 3-Step Workflow Section */}
      <section className="workflow-section" id="workflow">
        <div className="shell">
          <div className="eyebrow">
            <span>HOW IT WORKS</span> THREE-STEP VERIFICATION
          </div>
          <SectionTitle>
            Explain the workflow in three steps.
            <span>From code change to verified safety.</span>
          </SectionTitle>
          <p className="section-lead">
            Guard connects FalkorDB graph intelligence directly to your agent's test loop. Run only what matters in milliseconds.
          </p>

          <div className="workflow-grid">
            <article className="workflow-card">
              <div className="workflow-card-header">
                <div className="workflow-step-badge">
                  <Network size={18} className="workflow-step-icon" aria-hidden="true" />
                  <span>STEP 01</span>
                </div>
                <span className="workflow-capability-tag">guard ingest</span>
              </div>
              <h3>1. Analyze</h3>
              <p className="workflow-desc">
                Understand the relevant code relationships.
              </p>
              <div className="workflow-capability-box">
                <span className="workflow-capability-label">Product Capability</span>
                <p>AST static analysis and per-test coverage mapping persisted in a local FalkorDB graph.</p>
              </div>
            </article>

            <article className="workflow-card">
              <div className="workflow-card-header">
                <div className="workflow-step-badge">
                  <GitBranch size={18} className="workflow-step-icon" aria-hidden="true" />
                  <span>STEP 02</span>
                </div>
                <span className="workflow-capability-tag">guard run</span>
              </div>
              <h3>2. Trace</h3>
              <p className="workflow-desc">
                Identify what a change could affect.
              </p>
              <div className="workflow-capability-box">
                <span className="workflow-capability-label">Product Capability</span>
                <p>Blast-radius graph traversal and trust scoring across git diffs to isolate impacted tests.</p>
              </div>
            </article>

            <article className="workflow-card">
              <div className="workflow-card-header">
                <div className="workflow-step-badge">
                  <ShieldCheck size={18} className="workflow-step-icon" aria-hidden="true" />
                  <span>STEP 03</span>
                </div>
                <span className="workflow-capability-tag">guard hook</span>
              </div>
              <h3>3. Validate</h3>
              <p className="workflow-desc">
                Run targeted tests and surface regressions.
              </p>
              <div className="workflow-capability-box">
                <span className="workflow-capability-label">Product Capability</span>
                <p>Sub-second targeted test execution with agent-blocking stop hooks and self-repair feedback.</p>
              </div>
            </article>
          </div>
        </div>
      </section>

      {/* Page 1: Install Section */}
      <section className="install-section" id="install">
        <div className="shell">
          <div className="eyebrow"><span>01</span> INSTALL &amp; CONNECT</div>
          <SectionTitle>
            Install Guard for your AI coding agent.
            <span>Automatic repository configuration.</span>
          </SectionTitle>
          <p className="section-lead">
            Select your agent. Run the command in your project root directory.
            Restart the agent and verify the installation. All code stays on your local system.
          </p>
          <InstallTabs />
        </div>
      </section>

      {/* Features: Graph Safety Layer */}
      <section className="agent-section" id="features">
        <div className="shell">
          <div className="eyebrow">
            <span>02</span> GRAPH SAFETY LAYER
          </div>
          <SectionTitle light>
            Trust-scored test selection
            <span>That learns from every run.</span>
          </SectionTitle>
          <p className="section-lead light">
            From mapping AST call graphs to per-test coverage evidence, Guard
            protects your test suite automatically.
          </p>
          <p className="trust-score-explainer">
            Trust score measures evidence confidence (0.9 for per-test coverage, 0.6 for static call graph), git commit freshness, and dynamic dispatch risk before every run.
          </p>
          <div className="agent-grid">
            <article className="agent-card wide coral">
              <div className="card-copy">
                <small>1/4</small>
                <h3>Evaluates &amp; scores test trust first</h3>
                <p>
                  Guard evaluates evidence confidence, freshness against
                  current commit, and dynamic dispatch risk to score trust
                  before running tests.
                </p>
                <div className="pills">
                  <span>Coverage Evidence (0.9)</span>
                  <span>Static Call Graph (0.6)</span>
                  <span>Dynamic Widening</span>
                </div>
              </div>
              <div className="signal-art">
                <SignalIcon />
                <b>HIGH TRUST</b>
              </div>
            </article>
            <article className="agent-card pale">
              <small>2/4</small>
              <h3>Only tests covering your diff. Nothing else.</h3>
              <p>
                Every test is mapped to modified functions via live FalkorDB
                graph traversals.
              </p>
              <ProspectStack />
            </article>
            <article className="agent-card ink">
              <small>3/4</small>
              <h3>Three-tier policy with hard safety overrides</h3>
              <p>
                Subset (≥0.8), module widening (0.5–0.8), or run-all (&lt;0.5).
                Test edits force full suite immediately.
              </p>
              <div className="message-card">
                <div>
                  <span>GD</span>
                  <b>Guard Decision</b>
                  <small>just now</small>
                </div>
                <p>
                  Selected 14 covering tests for 2 changed functions. Skipped
                  405 unrelated tests with queryable reasons.
                </p>
              </div>
            </article>
            <article className="agent-card chart-card">
              <small>4/4</small>
              <h3>Self-repairing feedback loop</h3>
              <p>
                If an escape occurs, Guard inserts a miss_repair edge
                (confidence 1.0) so the test is never missed again.
              </p>
              <div className="chart">
                <div className="chart-line" />
                <span>Run 1</span>
                <span>Miss Logged</span>
                <span>Repaired</span>
              </div>
            </article>
          </div>
          <div className="section-cta-wrap">
            <a className="button coral-button" href="#install">
              <Arrow />
              <span>Run Guard on your repo</span>
            </a>
          </div>
        </div>
      </section>

      {/* Benchmark & Evals */}
      <section className="stories" id="stories">
        <div className="shell">
          <div className="eyebrow">
            <span>03</span> BENCHMARK &amp; EVALS
          </div>
          <SectionTitle light>
            Frozen benchmark on held-out mutants
            <span>Proves safety &amp; speed.</span>
          </SectionTitle>
          <div className="metrics">
            <div>
              <b>0.0%</b>
              <span>Escape rate on held-out mutants (0/17 killable)</span>
            </div>
            <div>
              <b>67.3%</b>
              <span>Test-time saved vs run-all on pallets/flask</span>
            </div>
            <div>
              <b>&lt;10ms</b>
              <span>Graph decision latency</span>
            </div>
          </div>
          <div className="quotes">
            <article>
              <div className="quote-mark">“</div>
              <blockquote>
                On the held-out split of Flask mutants, Guard achieved a 0.0%
                escape rate and 67.3% test-time savings, beating both the run-all
                baseline and same-file heuristics.
              </blockquote>
              <footer>
                <img src="/assets/louis.png" alt="" />
                <span>
                  <b>Evaluation Report</b>
                  <small>Held-out Test Split · pallets/flask</small>
                </span>
              </footer>
            </article>
            <article>
              <div className="quote-mark">“</div>
              <blockquote>
                Mutant m08 escaped under the same-file heuristic because the
                fault crossed module boundaries. Guard traversed the FalkorDB
                graph and caught it immediately in 0.13s.
              </blockquote>
              <footer>
                <span className="avatar-letter">MG</span>
                <span>
                  <b>Failure Case Analysis</b>
                  <small>Mutant m08 Audit</small>
                </span>
              </footer>
            </article>
            <article>
              <div className="quote-mark">“</div>
              <blockquote>
                Engineering Rule R9 strictly enforced: tasks verified only by
                independent verifier sessions with fresh context. Zero
                self-graded claims.
              </blockquote>
              <footer>
                <span className="avatar-letter">KS</span>
                <span>
                  <b>Verification Gate</b>
                  <small>reports/verify_t8.md</small>
                </span>
              </footer>
            </article>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="shell footer-grid">
          <div className="footer-brand">
            <a className="brand" href="#top" aria-label="Guard home">
              <EyeTracker size={30} shape="Cube" />
              <span>guard</span>
            </a>
            <p>Graph-powered safety layer for AI coding agents.</p>
            <div className="footer-falkor-credit">
              <span>Built on </span>
              <a
                href="https://falkordb.com"
                target="_blank"
                rel="noopener noreferrer"
                className="falkor-link"
              >
                <img
                  src="/assets/falkordb.svg"
                  alt="FalkorDB"
                  width="14"
                  height="14"
                  style={{ display: "inline-block", verticalAlign: "middle", marginRight: 4 }}
                />
                <strong>FalkorDB</strong>
              </a>
            </div>
          </div>
          <div>
            <b>Navigation</b>
            <a href="#workflow">Workflow</a>
            <a href="#install">Install</a>
            <a href="#features">Features</a>
            <a href="#stories">Benchmarks</a>
            <a href="https://github.com/thisisvaishnav/guard" target="_blank" rel="noopener noreferrer">
              GitHub
            </a>
          </div>
          <div>
            <b>Product</b>
            <a href="#features">Graph Safety Layer</a>
            <a href="#features">Trust Scoring</a>
            <a href="#stories">Evaluation Report</a>
            <a href="#install">Agent Integration</a>
          </div>
          <div>
            <b>Project</b>
            <a href="https://github.com/thisisvaishnav/guard" target="_blank" rel="noopener noreferrer">
              GitHub Repository
            </a>
            <a href="https://github.com/thisisvaishnav/guard/blob/main/PLAN.md" target="_blank" rel="noopener noreferrer">
              PLAN.md
            </a>
            <a href="https://github.com/thisisvaishnav/guard/blob/main/reports/verify_t8.md" target="_blank" rel="noopener noreferrer">
              T8 Evaluation Report
            </a>
            <a href="https://github.com/thisisvaishnav/guard/blob/main/DEVIATIONS.md" target="_blank" rel="noopener noreferrer">
              Rules R1–R9
            </a>
          </div>
        </div>
        <div className="shell footer-bottom">
          <span>© 2026 Guard. Open-source software.</span>
          <span>Tested on pallets/flask · Built on FalkorDB</span>
        </div>
      </footer>
    </main>
  )
}
