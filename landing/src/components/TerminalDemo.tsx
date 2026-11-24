import { useEffect, useRef, useState } from "react"
import { CheckCircle2, ShieldAlert, ShieldCheck } from "lucide-react"

interface Frame {
  time: number // in seconds
  phase: "break" | "block" | "fix" | "pass"
  phaseLabel: string
  lines: Array<{
    type: "prompt" | "agent" | "guard" | "test-fail" | "test-pass" | "error" | "success" | "dim"
    text: string
  }>
}

const FRAMES: Frame[] = [
  {
    time: 2,
    phase: "break",
    phaseLabel: "Agent refactors code",
    lines: [
      { type: "prompt", text: "claude" },
      { type: "dim", text: "Claude Code v1.0.8 (project: pallets/flask)" },
      { type: "agent", text: "→ Refactoring helper dispatch logic in src/flask/helpers.py..." },
      { type: "agent", text: "✓ Modified 2 functions: url_for, stream_with_context" },
      { type: "dim", text: "Task finished. Invoking agent stop hook..." },
    ],
  },
  {
    time: 6,
    phase: "block",
    phaseLabel: "Guard intercepts diff & runs tests",
    lines: [
      { type: "prompt", text: "claude" },
      { type: "agent", text: "✓ Modified 2 functions in src/flask/helpers.py" },
      { type: "guard", text: "⚡ Guard stop hook intercepted completion (session: sess_8a2f)" },
      { type: "guard", text: "  Traversing SQLite test graph: 26 covering tests found across 4 suites" },
      { type: "guard", text: "  Skipped 405 unrelated tests with queryable reasons" },
      { type: "dim", text: "  pytest -q tests/test_helpers.py tests/test_basic.py tests/test_blueprints.py" },
      { type: "test-pass", text: "  ✓ tests/test_helpers.py::test_url_for PASSED" },
      { type: "test-fail", text: "  ✗ tests/test_blueprints.py::test_endpoint_dispatch FAILED" },
      { type: "error", text: "⛔ GUARD BLOCKED (exit code 2): Stop rejected." },
      { type: "error", text: "   1 regression detected in blueprint caller. Agent cannot finish." },
    ],
  },
  {
    time: 11,
    phase: "fix",
    phaseLabel: "Agent receives feedback & fixes bug",
    lines: [
      { type: "error", text: "⛔ GUARD BLOCKED (exit code 2): 1 regression detected." },
      { type: "agent", text: "→ Agent inspected failure: blueprint endpoint prefix lost in helpers.py" },
      { type: "agent", text: "  Patching src/flask/helpers.py: preserving endpoint scope..." },
      { type: "dim", text: "  Saved changes. Agent attempting to finish again..." },
      { type: "guard", text: "⚡ Guard stop hook re-evaluating working tree..." },
    ],
  },
  {
    time: 16,
    phase: "pass",
    phaseLabel: "Guard verifies fix & passes",
    lines: [
      { type: "guard", text: "⚡ Guard stop hook re-evaluating working tree..." },
      { type: "guard", text: "  FalkorDB trust score: 0.94 (high evidence confidence)" },
      { type: "guard", text: "  Running 26 covering tests..." },
      { type: "test-pass", text: "  ✓ tests/test_helpers.py::test_url_for PASSED" },
      { type: "test-pass", text: "  ✓ tests/test_blueprints.py::test_endpoint_dispatch PASSED" },
      { type: "test-pass", text: "  ✓ 26 passed in 0.13s (67.3% test-time saved)" },
      { type: "success", text: "✓ GUARD PASSED (exit code 0): All covering tests green." },
      { type: "agent", text: "Claude Code: Task completed safely without escapes." },
    ],
  },
]

const TOTAL_DURATION = 18

export function TerminalDemo() {
  const [currentTime, setCurrentTime] = useState<number>(0)
  const animRef = useRef<number>(0)
  const lastTimeRef = useRef<number>(0)

  useEffect(() => {
    lastTimeRef.current = performance.now()

    const tick = (now: number) => {
      const delta = (now - lastTimeRef.current) / 1000
      lastTimeRef.current = now

      setCurrentTime((prev) => {
        const next = prev + delta
        if (next >= TOTAL_DURATION) {
          return 0
        }
        return next
      })

      animRef.current = requestAnimationFrame(tick)
    }

    animRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animRef.current)
  }, [])

  // Determine current active frame
  const currentFrame =
    [...FRAMES].reverse().find((f) => currentTime >= f.time) ?? FRAMES[0]

  return (
    <div className="terminal-demo-container" aria-label="Terminal demonstration of Guard intercepting and blocking broken code">
      <div className="terminal-demo-window">
        {/* Title bar */}
        <div className="terminal-demo-bar">
          <div className="terminal-dots" aria-hidden="true">
            <span className="dot dot-close" />
            <span className="dot dot-min" />
            <span className="dot dot-max" />
          </div>
          <div className="terminal-title">
            <span>guard — claude-code hook session</span>
          </div>
          <div className="terminal-phase-pill" data-phase={currentFrame.phase}>
            {currentFrame.phase === "block" && <ShieldAlert size={12} className="inline-icon" aria-hidden="true" />}
            {currentFrame.phase === "pass" && <ShieldCheck size={12} className="inline-icon" aria-hidden="true" />}
            {currentFrame.phaseLabel}
          </div>
        </div>

        {/* Console display */}
        <div className="terminal-demo-body" role="region" aria-live="polite">
          <pre className="terminal-pre">
            <code>
              {currentFrame.lines.map((line, idx) => (
                <div key={idx} className={`term-line term-${line.type}`}>
                  {line.type === "prompt" && <span className="term-prompt">$ </span>}
                  {line.text}
                </div>
              ))}
              <span className="term-cursor" aria-hidden="true">█</span>
            </code>
          </pre>
        </div>
      </div>
      <p className="terminal-caption">
        <CheckCircle2 size={13} className="inline-icon success-text" aria-hidden="true" />
        Live simulation: Agent breaks code → Guard blocks stop (exit 2) → Agent fixes regression → Guard passes.
      </p>
    </div>
  )
}
