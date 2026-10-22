import { useCallback, useRef, useState } from "react"
import { Tabs, TabsContent, TabsIndicator, TabsList, TabsTrigger } from "@/components/ui/tabs"
import agents from "@/data/agents.json"
import { Badge } from "./Badge"
import { CodeBlock } from "./CodeBlock"
import { Step } from "./Step"
import { AgentIcon } from "./AgentIcon"
import { CheckCircle2, ChevronDown, ChevronUp, ExternalLink, FileCode, RotateCcw, ShieldCheck, Undo2 } from "lucide-react"

type Agent = (typeof agents)[number]

const GITHUB_URL = "https://github.com/thisisvaishnav/guard"
const STORAGE_KEY = "guard-install-agent"

function initialValue(): string {
  if (typeof window === "undefined") return agents[0].id
  const requested = new URLSearchParams(window.location.search).get("agent")
  if (requested && agents.some((a) => a.id === requested)) return requested
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved && agents.some((a) => a.id === saved)) return saved
  } catch {
    // private mode blocks localStorage
  }
  return agents[0].id
}

function InstallSteps({ agent }: { agent: Agent }) {
  const [disclosureOpen, setDisclosureOpen] = useState(false)

  return (
    <div className="install-steps-wrapper" role="tabpanel" id={`panel-${agent.id}`} aria-labelledby={`tab-${agent.id}`}>
      {/* Before you start prerequisite callout */}
      <div className="install-prereq-banner">
        <span className="install-prereq-label">Prerequisites:</span>
        <span className="install-prereq-text">
          Python project with pytest, git, and{" "}
          <a
            href={agent.prereqUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="install-prereq-link"
          >
            uv <ExternalLink size={11} className="inline-icon" aria-hidden="true" />
          </a>
          .
        </span>
      </div>

      {/* Step 1: Install tool */}
      <Step n={1} title="Install Guard" tag="Global Tool">
        <p>Install the Guard CLI tool on your system PATH:</p>
        <CodeBlock value={agent.installCmd} label="bash" isCommand />
        {agent.alternative && (
          <p className="install-alt-row">
            <strong>Optional:</strong> Install Guard with pipx (<code>pipx install guard-cli</code>).
          </p>
        )}
      </Step>

      {/* Step 2: Set up repository */}
      <Step n={2} title="Initialize your project" tag="Repository Init">
        <p>
          Run the initialization command in your project root directory:
        </p>
        <CodeBlock value={agent.initCmd} label="bash" isCommand />
        <p className="install-runnote">{agent.initNote}</p>
      </Step>

      {/* Step 3: Restart agent */}
      <Step n={3} title="Restart your agent" tag="Reload Hook">
        <div className="install-restart-box">
          <div className="install-restart-icon-wrap" aria-hidden="true">
            <RotateCcw size={15} className="install-restart-icon" />
          </div>
          <p className="install-restart-text">{agent.restart}</p>
        </div>
      </Step>

      {/* Step 4: Verify integration */}
      <Step n={4} title="Verify the installation" tag="Doctor check" isLast>
        <p>Run the diagnostic tool in your terminal. Confirm that all checks pass.</p>
        <CodeBlock value={agent.verify} label="verify" compact isCommand />
        <div className="install-verify-expected">
          <div className="install-verify-header">
            <CheckCircle2 size={13} className="install-verify-icon" aria-hidden="true" />
            <span>Expected health report:</span>
          </div>
          <CodeBlock
            value={agent.expected}
            label="guard doctor"
            compact
            isCommand={false}
          />
        </div>
      </Step>

      {/* Expandable "What does this change?" disclosure */}
      <div className="install-disclosure-box">
        <button
          type="button"
          className="install-disclosure-toggle"
          onClick={() => setDisclosureOpen((prev) => !prev)}
          aria-expanded={disclosureOpen}
        >
          <div className="install-disclosure-toggle-title">
            <FileCode size={14} className="install-disclosure-icon" aria-hidden="true" />
            <span>Files created or modified</span>
          </div>
          {disclosureOpen ? <ChevronUp size={15} aria-hidden="true" /> : <ChevronDown size={15} aria-hidden="true" />}
        </button>

        {disclosureOpen && (
          <div className="install-disclosure-content">
            <p className="install-disclosure-desc">
              Guard writes configuration files to your repository. Guard does not change your source code:
            </p>
            <ul className="install-disclosure-list">
              {agent.writes.map((item) => (
                <li key={item.file}>
                  <code className="install-code-inline">{item.file}</code> — {item.description}
                </li>
              ))}
            </ul>
            {agent.coverageNote && (
              <p className="install-disclosure-note">
                <strong>Note:</strong> {agent.coverageNote}
              </p>
            )}
            <div className="install-undo-row">
              <Undo2 size={13} className="install-undo-icon" aria-hidden="true" />
              <span>To remove the hooks at any time, run: </span>
              <code className="install-code-inline">{agent.undo}</code>
            </div>
          </div>
        )}
      </div>

      {/* Platform limits callout */}
      <div className="install-platform-limits">
        <ShieldCheck size={14} className="install-platform-icon" aria-hidden="true" />
        <p>{agent.platformLimit}</p>
      </div>
    </div>
  )
}

export function InstallTabs() {
  const [value, setValue] = useState(initialValue)
  const navRef = useRef<HTMLDivElement>(null)

  const handleValueChange = useCallback((next: string) => {
    setValue(next)
    try {
      const url = new URL(window.location.href)
      url.searchParams.set("agent", next)
      window.history.replaceState(null, "", url)
    } catch {
      // history unavailable (sandboxed iframe)
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // private mode blocks localStorage
    }
  }, [])

  return (
    <div className="install-tabs-container">
      <div className="install-scope-bar">
        <span className="install-scope-badge">Scope: Python projects that use pytest</span>
      </div>

      <div className="install-scope-cutoff" aria-hidden="true" />

      <Tabs
        value={value}
        onValueChange={handleValueChange}
        className="install-tabs"
      >
        <div className="install-tabs-nav-outer" ref={navRef}>
          <TabsList
            variant="line"
            aria-label="Choose your agent"
            className="install-tabs-list"
            role="tablist"
          >
            {agents.map((a) => (
              <TabsTrigger
                key={a.id}
                value={a.id}
                id={`tab-${a.id}`}
                aria-controls={`panel-${a.id}`}
                role="tab"
                className="install-tab-trigger"
                title={a.label}
              >
                <div className="install-tab-icon-wrap" aria-hidden="true">
                  <AgentIcon id={a.id} size={18} />
                </div>
                <span className="install-tab-name">{a.label}</span>
                {"badge" in a && a.badge ? <Badge status={String(a.badge)} /> : null}
              </TabsTrigger>
            ))}
            <TabsIndicator className="install-tab-indicator" />
          </TabsList>
        </div>

        <div className="install-tabs-panels">
          {agents.map((a) => (
            <TabsContent key={a.id} value={a.id} className="install-tab-content">
              <InstallSteps agent={a} />
            </TabsContent>
          ))}
        </div>
      </Tabs>

      {/* Coming next row */}
      <div className="install-coming-next-row">
        <span>Planned agent support: <strong>Cursor</strong>, <strong>VS Code</strong>, <strong>Codex</strong>, and <strong>OpenCode</strong> (requires the MCP server).</span>
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="install-coming-link"
        >
          Follow progress on GitHub <ExternalLink size={12} className="inline-icon" aria-hidden="true" />
        </a>
      </div>
    </div>
  )
}
