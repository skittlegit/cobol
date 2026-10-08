import { Clock, ShieldCheck } from "lucide-react"

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PassBadge, Section, f3 } from "@/components/site/common"
import { cn } from "@/lib/utils"
import { gate, isEvaluated, type Evaluated, type Gate, type SiteData } from "@/types"

function Meter({ gate }: { gate: Gate }) {
  if (gate.value === null || gate.threshold === null || gate.key === "interprocedural_advantage") return null
  const clamp = (v: number) => Math.max(0, Math.min(1, v)) * 100
  return (
    <div
      className="relative h-2 w-full min-w-24 rounded-full bg-muted"
      role="img"
      aria-label={`${f3(gate.value)}, required ${gate.threshold}`}
    >
      <div
        className={cn("h-full rounded-full", gate.pass ? "bg-success" : "bg-destructive")}
        style={{ width: `${clamp(gate.value)}%` }}
      />
      <div className="absolute -top-1 -bottom-1 w-0.5 rounded bg-foreground" style={{ left: `${clamp(gate.threshold)}%` }} />
    </div>
  )
}

function Margin({ comparison, pass }: { comparison: Evaluated["comparison"]; pass: boolean }) {
  const lo = -0.2
  const hi = 0.8
  const x = (v: number) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`
  const [ciLo, ciHi] = comparison.ci
  const ticks = [-0.2, 0, 0.2, 0.4, 0.6, 0.8]
  return (
    <Card>
      <CardHeader>
        <CardDescription>Cross-program F1 advantage over the RAG baseline</CardDescription>
        <CardTitle className="flex flex-wrap items-baseline gap-x-3 text-4xl font-semibold tabular-nums tracking-tight">
          {comparison.delta >= 0 ? "+" : ""}{f3(comparison.delta)}
          <span className="text-sm font-normal text-muted-foreground">
            95% CI {f3(ciLo)}–{f3(ciHi)} · {comparison.p === null ? "p = –" : comparison.p < 0.001 ? "p < 0.001" : `p = ${comparison.p.toFixed(4)}`} · n = {comparison.n}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className="relative mx-3 mt-6 h-16"
          role="img"
          aria-label={`difference ${f3(comparison.delta)}, 95% interval ${f3(ciLo)} to ${f3(ciHi)}, required ${comparison.need}`}
        >
          <div className="absolute inset-x-0 top-6 h-px bg-border" />
          {ticks.map((t) => (
            <div key={t} className="absolute top-11 -translate-x-1/2 font-mono text-[11px] text-muted-foreground" style={{ left: x(t) }}>
              {t === 0 ? "0" : `${t > 0 ? "+" : ""}${t.toFixed(1)}`}
            </div>
          ))}
          <div className="absolute top-2 h-8 w-px bg-muted-foreground/50" style={{ left: x(0) }} />
          <div className="absolute top-2 h-8 w-0.5 bg-foreground" style={{ left: x(comparison.need) }}>
            <span className="absolute -top-5 -translate-x-1/2 whitespace-nowrap font-mono text-[11px] text-muted-foreground">
              +{comparison.need} needed
            </span>
          </div>
          <div
            className={cn("absolute top-5 h-2 rounded-full", pass ? "bg-success/30" : "bg-destructive/30")}
            style={{ left: x(ciLo), width: `calc(${x(ciHi)} - ${x(ciLo)})` }}
          />
          <div
            className={cn("absolute top-4 size-4 -translate-x-1/2 rounded-full border-2 border-card", pass ? "bg-success" : "bg-destructive")}
            style={{ left: x(comparison.delta) }}
          />
        </div>
      </CardContent>
      <CardFooter className="grid grid-cols-2 gap-4 border-t [.border-t]:pt-6">
        {[
          ["Detector", comparison.detector_f1, "bg-primary"],
          ["RAG reranker baseline", comparison.baseline_f1, "bg-muted-foreground/40"],
        ].map(([label, value, color]) => (
          <div key={label as string} className="space-y-2">
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-muted-foreground">{label}</span>
              <span className="font-mono tabular-nums">{f3(value as number)}</span>
            </div>
            <div className="h-2 rounded-full bg-muted">
              <div className={cn("h-full rounded-full", color as string)} style={{ width: `${(value as number) * 100}%` }} />
            </div>
          </div>
        ))}
      </CardFooter>
    </Card>
  )
}

function Evaluation({ results, current }: { results: Evaluated; current: string }) {
  const margin = gate(results, "interprocedural_advantage")
  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <Card className="lg:row-span-2">
        <CardHeader>
          <CardDescription>{current} · official result</CardDescription>
          <CardTitle
            className={cn(
              "text-5xl font-semibold tracking-tighter",
              results.decision === "GO" ? "text-success" : "text-destructive",
            )}
          >
            {results.decision.replace("_", "-")}
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            {results.passed} of {results.gates.length} gates pass. A GO needs all of them.
          </p>
        </CardHeader>
        <CardContent className="px-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Gate</TableHead>
                  <TableHead>Measured</TableHead>
                  <TableHead className="hidden sm:table-cell">Required</TableHead>
                  <TableHead className="pr-6 text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.gates.map((g) => (
                  <TableRow key={g.name}>
                    <TableCell className="pl-6 align-top">
                      <div className="font-medium whitespace-normal">{g.label}</div>
                      <div className="mt-2 max-w-56"><Meter gate={g} /></div>
                      <div className="mt-1 text-xs text-muted-foreground sm:hidden">{g.required}</div>
                    </TableCell>
                    <TableCell className="align-top font-mono text-xs whitespace-normal tabular-nums">{g.measured}</TableCell>
                    <TableCell className="hidden align-top font-mono text-xs whitespace-normal text-muted-foreground sm:table-cell">{g.required}</TableCell>
                    <TableCell className="pr-6 text-right align-top"><PassBadge pass={g.pass} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
      <Margin comparison={results.comparison} pass={margin.pass} />
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-muted-foreground" />
            <CardDescription>Verification</CardDescription>
          </div>
          <CardTitle className="text-xl">
            {gate(results, "zero_unverified_findings").pass ? "Every finding was verified" : "An unverified finding was emitted"}
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Each finding is checked by executing it under GnuCOBOL or proving it statically, and the clause must entail
          it according to an NLI model from a different family. A finding that fails becomes an abstention, never a guess.
        </CardContent>
      </Card>
    </div>
  )
}

export function Results({ data }: { data: SiteData }) {
  const results = data.results
  return (
    <Section
      id="result"
      eyebrow="Official evaluation"
      title="Gates fixed in advance, test data unseen before the run"
      description="The detector, the gates and the test data were all frozen before the run. The test programs were written for it and appear in no other split."
    >
      {isEvaluated(results) ? (
        <Evaluation results={results} current={data.current} />
      ) : (
        <Card>
          <CardHeader>
            <CardDescription>{data.current} · official result</CardDescription>
            <CardTitle className="flex items-center gap-3 text-3xl">
              <Clock className="size-6 text-warning" /> Pending
            </CardTitle>
          </CardHeader>
          <CardContent className="text-muted-foreground">{results.status} The gates are fixed in advance.</CardContent>
        </Card>
      )}
    </Section>
  )
}
