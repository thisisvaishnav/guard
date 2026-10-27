import { useState } from "react"
import { Check, Copy, Shield, Terminal, Zap, Lock } from "lucide-react"

export function FinalCta() {
  const [copied, setCopied] = useState(false)
  const installCmd = "uv tool install guard-cli && guard init --yes"

  const handleCopy = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(installCmd)
      } else {
        const ta = document.createElement("textarea")
        ta.value = installCmd
        ta.style.position = "fixed"
        ta.style.opacity = "0"
        document.body.appendChild(ta)
        ta.select()
        document.execCommand("copy")
        document.body.removeChild(ta)
      }
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }

  return (
    <section className="final-cta-section" id="get-started">
      <div className="shell">
        <div className="final-cta-card">
          <div className="final-cta-glow" aria-hidden="true" />
          <div className="final-cta-content">
            <div className="final-cta-badge">
              <Zap size={14} className="icon-pulse" />
              <span>START IN 10 SECONDS</span>
            </div>

            <h2 className="final-cta-title">
              Stop broken code before it lands in your branch.
            </h2>

            <p className="final-cta-desc">
              Connect Guard directly to Claude Code or Antigravity. Run only what matters in milliseconds with zero Docker overhead.
            </p>

            <div className="final-cta-cmd-wrap">
              <div className="final-cta-cmd-box">
                <span className="final-cta-prompt" aria-hidden="true">$ </span>
                <code className="final-cta-code">{installCmd}</code>
                <button
                  type="button"
                  className="final-cta-copy-btn"
                  onClick={handleCopy}
                  aria-label={copied ? "Copied command" : "Copy install command"}
                >
                  {copied ? (
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
            </div>

            {/* Risk Reversals */}
            <div className="final-cta-reversals">
              <div className="reversal-pill">
                <Shield size={14} className="reversal-icon" />
                <span>Zero Background Daemons (0 MB RAM)</span>
              </div>
              <div className="reversal-pill">
                <Lock size={14} className="reversal-icon" />
                <span>100% Offline &amp; Local</span>
              </div>
              <div className="reversal-pill">
                <Terminal size={14} className="reversal-icon" />
                <span>0.0% Escape Rate on Held-Out Split</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
