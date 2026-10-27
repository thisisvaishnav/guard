import { useState } from "react"
import { ChevronDown, HelpCircle } from "lucide-react"

interface FaqItem {
  q: string
  a: string
  tag?: string
}

const FAQS: FaqItem[] = [
  {
    q: "Does Guard require Docker or any background daemon?",
    tag: "Architecture",
    a: "No. Guard runs on an embedded SQLite engine with Write-Ahead Logging (WAL) stored in your repository at .guard/graph.db. It requires zero external containers, zero background processes, and uses 0 MB of idle RAM. An optional FalkorDB server backend is also supported if you prefer a dedicated graph database.",
  },
  {
    q: "What happens if a function is untested or has no coverage evidence?",
    tag: "Safety Invariant",
    a: "Guard immediately triggers safe-mode fallback (no_evidence=True) and runs your full test suite. Guard never gambles: it only subsets tests when mathematical confidence and AST coverage evidence exist. In held-out benchmark evaluations on Flask, Guard maintained a 0.0% escape rate.",
  },
  {
    q: "Does my repository code or telemetry ever leave my machine?",
    tag: "Privacy",
    a: "Never. Guard is 100% local, offline, and self-contained. There is zero network egress, no external telemetry, and no third-party API dependencies. All graph indices and test run histories reside in your local .guard directory.",
  },
  {
    q: "How does Guard hook into Claude Code and Antigravity?",
    tag: "Integrations",
    a: "Guard connects using standard agent hook protocols. Running 'guard init' registers a stop hook and session-start hook in ~/.claude/settings.json or your agent configuration. When your coding agent attempts to finish a turn, Guard intercepts the exit, runs only the affected tests, and feeds back concise diagnostics if a regression occurred.",
  },
  {
    q: "Why not just run pytest on the file the agent edited?",
    tag: "Accuracy",
    a: "Same-file heuristics miss bugs that cross module boundaries. When an agent edits a helper, utility, or database method, the tests that break are often in completely different packages. Guard traverses multi-hop call graphs and coverage mappings, catching cross-module regressions in milliseconds that naive heuristics miss.",
  },
  {
    q: "How much time does Guard save during agent coding loops?",
    tag: "Performance",
    a: "On real-world repositories like pallets/flask and bottle, Guard achieves between 67.3% and 94.8% reduction in test execution time. Instead of waiting 10 to 60 seconds for an entire suite on every turn, your agent gets feedback in 200 to 500 milliseconds.",
  },
]

export function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  const toggle = (idx: number) => {
    setOpenIndex((cur) => (cur === idx ? null : idx))
  }

  return (
    <section className="faq-section" id="faq">
      <div className="shell">
        <div className="eyebrow">
          <span>FREQUENT QUESTIONS</span> ARCHITECTURE &amp; GUARANTEES
        </div>
        <h2 className="faq-headline">
          Everything you need to know.
          <span>No hidden servers. No magic heuristics.</span>
        </h2>
        <p className="section-lead">
          Straightforward answers on privacy, background processes, safety invariants, and agent hooks.
        </p>

        <div className="faq-list">
          {FAQS.map((item, idx) => {
            const isOpen = openIndex === idx
            return (
              <div
                key={idx}
                className={`faq-item ${isOpen ? "open" : ""}`}
              >
                <button
                  type="button"
                  className="faq-question-btn"
                  onClick={() => toggle(idx)}
                  aria-expanded={isOpen}
                  aria-controls={`faq-answer-${idx}`}
                >
                  <div className="faq-q-text-wrap">
                    <span className="faq-badge">{item.tag}</span>
                    <span className="faq-question-text">{item.q}</span>
                  </div>
                  <ChevronDown
                    size={18}
                    className={`faq-chevron ${isOpen ? "rotated" : ""}`}
                    aria-hidden="true"
                  />
                </button>
                <div
                  id={`faq-answer-${idx}`}
                  className="faq-answer-collapse"
                  hidden={!isOpen}
                >
                  <p className="faq-answer-text">{item.a}</p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
