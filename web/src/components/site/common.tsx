import * as React from "react"
import { Moon, Sun } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { Decision } from "@/types"

export const CLASS_COLOR: Record<string, string> = {
  D1: "var(--d1)", D2: "var(--d2)", D3: "var(--d3)", D4: "var(--d4)",
  D5: "var(--d5)", D6: "var(--d6)", D7: "var(--d7)",
}

export const f3 = (v: number) => v.toFixed(3)
export const pct = (v: number) => `${(v * 100).toFixed(1)}%`

export function Section({
  id, eyebrow, title, description, children, className,
}: {
  id: string
  eyebrow: string
  title: string
  description?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section id={id} className={cn("border-t py-16 md:py-24", className)}>
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mb-10 max-w-3xl space-y-3">
          <p className="font-mono text-xs font-medium uppercase tracking-widest text-muted-foreground">{eyebrow}</p>
          <h2 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">{title}</h2>
          {description && <p className="text-muted-foreground text-pretty">{description}</p>}
        </div>
        {children}
      </div>
    </section>
  )
}

const DECISION_STYLE: Record<Decision, string> = {
  GO: "border-success/30 bg-success/10 text-success",
  NO_GO: "border-destructive/30 bg-destructive/10 text-destructive",
  NOT_EVALUABLE: "border-warning/30 bg-warning/10 text-warning",
}

export function DecisionBadge({ decision, className }: { decision: Decision; className?: string }) {
  const label = decision === "NOT_EVALUABLE" ? "Pending" : decision.replace("_", "-")
  return (
    <Badge variant="outline" className={cn("font-mono", DECISION_STYLE[decision], className)}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {label}
    </Badge>
  )
}

export function PassBadge({ pass }: { pass: boolean }) {
  return (
    <Badge variant="outline" className={DECISION_STYLE[pass ? "GO" : "NO_GO"]}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {pass ? "Pass" : "Fail"}
    </Badge>
  )
}

export function ThemeToggle() {
  const [dark, setDark] = React.useState(() => document.documentElement.classList.contains("dark"))
  const toggle = () => {
    const next = !dark
    document.documentElement.classList.toggle("dark", next)
    try { localStorage.setItem("theme", next ? "dark" : "light") } catch { /* private mode */ }
    setDark(next)
  }
  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label={dark ? "Use light theme" : "Use dark theme"}>
      {dark ? <Sun /> : <Moon />}
    </Button>
  )
}
