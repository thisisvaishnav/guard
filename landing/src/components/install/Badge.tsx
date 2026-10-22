const LABELS: Record<string, string> = {
  enforced: "Enforced",
  beta: "Beta",
  experimental: "Experimental",
  advisory: "Advisory",
  "coming-soon": "Soon",
}

export function Badge({ status }: { status?: string }) {
  if (!status) return null
  const label = LABELS[status] ?? status

  return (
    <span className="install-badge" data-badge={status}>
      {status === "enforced" && <span className="install-badge-pulse" aria-hidden="true" />}
      <span className="install-badge-text">{label}</span>
    </span>
  )
}
