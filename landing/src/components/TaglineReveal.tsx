import { useEffect, useRef, useState, Fragment } from "react"

const WORDS = [
  { text: "Every", highlight: false },
  { text: "code", highlight: false },
  { text: "change", highlight: false },
  { text: "has", highlight: false },
  { text: "an", highlight: false },
  { text: "exact", highlight: false },
  { text: "blast", highlight: true },
  { text: "radius.", highlight: true },
  { text: "Guard", highlight: false },
  { text: "traverses", highlight: false },
  { text: "the", highlight: false },
  { text: "graph", highlight: false },
  { text: "in", highlight: false },
  { text: "milliseconds,", highlight: false },
  { text: "testing", highlight: false },
  { text: "what", highlight: false },
  { text: "matters", highlight: false },
  { text: "before", highlight: false },
  { text: "your", highlight: false },
  { text: "agent", highlight: false },
  { text: "can", highlight: false },
  { text: "commit.", highlight: true },
]

export function TaglineReveal() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [activeRatio, setActiveRatio] = useState(0)

  useEffect(() => {
    const handleScroll = () => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const windowHeight = window.innerHeight
      // Trigger when the element enters between 85% and 25% of viewport
      const start = windowHeight * 0.85
      const end = windowHeight * 0.25
      const progress = (start - rect.top) / (start - end)
      const clamped = Math.max(0, Math.min(1, progress))
      setActiveRatio(clamped)
    }

    window.addEventListener("scroll", handleScroll, { passive: true })
    handleScroll()

    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  const activeCount = Math.floor(activeRatio * (WORDS.length + 1))

  return (
    <section className="tagline-reveal-section" ref={containerRef}>
      <div className="shell">
        <div className="tagline-reveal-badge" aria-hidden="true">
          <span>PREDICTIVE VERIFICATION</span>
        </div>
        <p className="tagline-reveal-text">
          {WORDS.map((word, idx) => {
            const isLit = idx < activeCount
            return (
              <Fragment key={`${word.text}-${idx}`}>
                <span
                  className={`tagline-word ${isLit ? "lit" : ""} ${
                    word.highlight && isLit ? "highlight" : ""
                  }`}
                  style={{
                    transitionDelay: `${idx * 15}ms`,
                  }}
                >
                  {word.text}
                </span>
                {idx < WORDS.length - 1 ? " " : ""}
              </Fragment>
            )
          })}
        </p>
        <p className="tagline-subtext">
          Powered by embedded SQLite with recursive call-graph queries. Zero external daemons, zero Docker overhead.
        </p>
      </div>
    </section>
  )
}
