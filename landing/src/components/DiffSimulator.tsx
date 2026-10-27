import { useState } from "react"
import { GitCommit, ShieldCheck, Zap, AlertTriangle, CheckCircle2, ChevronRight } from "lucide-react"

interface Scenario {
  id: string
  title: string
  file: string
  func: string
  diffLines: { type: "add" | "del" | "context"; text: string }[]
  decision: "SUBSET" | "RUN_ALL"
  trustScore: string
  selectedTests: string[]
  skippedCount: number
  latency: string
  explanation: string
  policyReason: string
}

const SCENARIOS: Scenario[] = [
  {
    id: "pricing",
    title: "Edit Core Pricing",
    file: "shop/orders.py",
    func: "calculate_discount(subtotal, tier)",
    diffLines: [
      { type: "context", text: "def calculate_discount(subtotal: float, tier: str) -> float:" },
      { type: "del", text: "-    if tier == 'vip': return subtotal * 0.15" },
      { type: "add", text: "+    if tier == 'vip': return subtotal * 0.20" },
      { type: "context", text: "     return subtotal * 0.05" },
    ],
    decision: "SUBSET",
    trustScore: "0.94 (High Trust)",
    selectedTests: [
      "tests/test_orders.py::test_vip_discount_rate",
      "tests/test_orders.py::test_checkout_order_total",
      "tests/test_invoices.py::test_invoice_tiered_pricing",
    ],
    skippedCount: 360,
    latency: "14.2ms",
    explanation: "Guard traversed 2-hop AST callers and verified per-test coverage edges in .guard/graph.db.",
    policyReason: "Targeted 3 covering tests. Safe to skip 360 unrelated unit tests.",
  },
  {
    id: "inventory",
    title: "Stock Concurrency",
    file: "shop/inventory.py",
    func: "reserve_stock(sku, qty)",
    diffLines: [
      { type: "context", text: "def reserve_stock(sku: str, qty: int) -> bool:" },
      { type: "del", text: "-    item = db.find(sku)" },
      { type: "add", text: "+    item = db.find_with_lock(sku)" },
      { type: "context", text: "     return item.decrement(qty)" },
    ],
    decision: "SUBSET",
    trustScore: "0.91 (High Trust)",
    selectedTests: [
      "tests/test_inventory.py::test_atomic_reserve_stock",
      "tests/test_inventory.py::test_insufficient_stock_error",
    ],
    skippedCount: 361,
    latency: "16.8ms",
    explanation: "Identified direct callers across 2 modules. Inbound coverage confidence > 0.90.",
    policyReason: "Targeted 2 covering tests. Agent feedback loop finishes in 0.24s instead of 12.8s.",
  },
  {
    id: "test-touched",
    title: "Test File Modified",
    file: "tests/test_auth.py",
    func: "test_token_refresh()",
    diffLines: [
      { type: "context", text: "def test_token_refresh(client):" },
      { type: "del", text: "-    assert token.is_valid is True" },
      { type: "add", text: "+    assert token.is_valid and token.claims['exp'] > now()" },
    ],
    decision: "RUN_ALL",
    trustScore: "Fallback Override",
    selectedTests: [
      "tests/test_auth.py (all tests)",
      "Full repository test suite (363 tests)",
    ],
    skippedCount: 0,
    latency: "18.1ms",
    explanation: "Hard safety rule triggered: when test files are touched or added, Guard falls back to run-all.",
    policyReason: "Safety override: zero-escape guarantee prevents agent hallucinating test escapes.",
  },
]

export function DiffSimulator() {
  const [activeScenario, setActiveScenario] = useState<Scenario>(SCENARIOS[0])

  return (
    <div className="diff-simulator-container">
      <div className="diff-simulator-header">
        <div className="diff-simulator-title-group">
          <div className="diff-simulator-badge">
            <Zap size={14} className="icon-pulse" />
            <span>INTERACTIVE GRAPH SIMULATOR</span>
          </div>
          <h3>See how Guard decides which tests to run</h3>
          <p>Click a scenario below to watch how Guard isolates the blast radius in real time.</p>
        </div>

        <div className="diff-scenario-pills" role="tablist" aria-label="Simulator Scenarios">
          {SCENARIOS.map((s) => {
            const isActive = s.id === activeScenario.id
            return (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`diff-scenario-pill ${isActive ? "active" : ""}`}
                onClick={() => setActiveScenario(s)}
              >
                <span>{s.title}</span>
                {isActive && <ChevronRight size={14} className="pill-arrow" />}
              </button>
            )
          })}
        </div>
      </div>

      <div className="diff-simulator-grid">
        {/* Left column: Git Diff Viewer */}
        <div className="diff-card-pane">
          <div className="diff-card-topbar">
            <div className="diff-card-file">
              <GitCommit size={14} className="diff-git-icon" />
              <span>{activeScenario.file}</span>
            </div>
            <span className="diff-fn-badge">{activeScenario.func}</span>
          </div>
          <div className="diff-code-body">
            {activeScenario.diffLines.map((line, idx) => (
              <div
                key={idx}
                className={`diff-code-line diff-line-${line.type}`}
              >
                <span className="diff-line-num">{idx + 1}</span>
                <span className="diff-line-content">{line.text}</span>
              </div>
            ))}
          </div>
          <div className="diff-card-footer">
            <span className="diff-engine-tag">Engine: Embedded SQLite WAL</span>
            <span className="diff-timing">Graph Query: <strong>{activeScenario.latency}</strong></span>
          </div>
        </div>

        {/* Right column: Guard Decision Pane */}
        <div className="diff-decision-pane">
          <div className="decision-header">
            <div className="decision-status-wrap">
              {activeScenario.decision === "SUBSET" ? (
                <div className="decision-badge subset">
                  <ShieldCheck size={16} />
                  <span>POLICY: HIGH-TRUST SUBSET</span>
                </div>
              ) : (
                <div className="decision-badge fallback">
                  <AlertTriangle size={16} />
                  <span>POLICY: SAFE-MODE FALLBACK</span>
                </div>
              )}
              <span className="decision-trust">Score: <strong>{activeScenario.trustScore}</strong></span>
            </div>
          </div>

          <div className="decision-stats-row">
            <div className="decision-stat-box highlight">
              <span className="stat-label">Tests Selected</span>
              <strong className="stat-val text-coral">{activeScenario.selectedTests.length}</strong>
            </div>
            <div className="decision-stat-box">
              <span className="stat-label">Tests Skipped</span>
              <strong className="stat-val text-ink">{activeScenario.skippedCount}</strong>
            </div>
            <div className="decision-stat-box">
              <span className="stat-label">Execution Time</span>
              <strong className="stat-val text-green">{activeScenario.decision === "SUBSET" ? "0.28s" : "2.1s"}</strong>
            </div>
          </div>

          <div className="decision-target-list">
            <div className="target-list-title">
              <CheckCircle2 size={13} className="text-coral" />
              <span>Covering Test Targets (Auto-Selected)</span>
            </div>
            <ul>
              {activeScenario.selectedTests.map((t, idx) => (
                <li key={idx} className="target-item">
                  <code>{t}</code>
                </li>
              ))}
            </ul>
          </div>

          <div className="decision-explainer-box">
            <p className="decision-policy-note">{activeScenario.policyReason}</p>
            <small className="decision-infra-note">{activeScenario.explanation}</small>
          </div>
        </div>
      </div>
    </div>
  )
}
