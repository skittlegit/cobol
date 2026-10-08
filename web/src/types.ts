// The shape of site.json, written by scripts/build_site.py. Every number on
// the site comes from this file; the components only lay it out.

export type Decision = "GO" | "NO_GO" | "NOT_EVALUABLE"

export type GateKey =
  | "t1_f1" | "balanced_accuracy" | "answer_rate" | "answered_accuracy"
  | "interprocedural_advantage" | "temporal_paired_accuracy" | "zero_unverified_findings"

export interface Gate {
  key: GateKey
  label: string
  name: string
  measured: string
  required: string
  pass: boolean
  value: number | null
  threshold: number | null
}

export interface Evaluated {
  decision: "GO" | "NO_GO"
  passed: number
  gates: Gate[]
  comparison: {
    delta: number
    ci: [number, number]
    p: number | null
    n: number
    detector_f1: number
    baseline_f1: number
    need: number
  }
  per_class: { code: string; name: string; detector: number; baseline: number; support: number }[]
  confusion: {
    cols: string[]
    rows: { gold: string; cells: { n: number; share: number; diagonal: boolean }[] }[]
  }
  localisation: { name: string; value: number }[]
  tiers: { name: string; n: number; faithfulness: number }[]
  temporal: {
    successes: number
    pairs: number
    accuracy: number
    ci: [number, number]
    per_pair: { name: string; ok: boolean; target: string }[]
  }
}

export interface Pending {
  decision: "NOT_EVALUABLE"
  status: string
}

export interface SiteData {
  repo: string
  current: string
  classes: { code: string; name: string; description: string }[]
  history: { run: string; decision: Decision; text: string; current: boolean }[]
  excavation: {
    program: string
    lines: { n: number; text: string; hit: boolean }[]
    old: { version: string; value: number }
    new: { version: string; value: number }
  }
  benchmark: {
    splits: { name: string; rows: number; cross: number; classes: Record<string, number> }[]
    pairs: number
    versions: string[]
    targets: { name: string; pairs: number }[]
  }
  results: Evaluated | Pending
}

export const gate = (r: Evaluated, key: GateKey) => r.gates.find((g) => g.key === key)!

export const isEvaluated = (r: Evaluated | Pending): r is Evaluated => r.decision !== "NOT_EVALUABLE"
