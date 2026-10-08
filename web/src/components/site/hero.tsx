import { ArrowRight, FileCode2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { DecisionBadge } from "@/components/site/common"
import { cn } from "@/lib/utils"
import { gate, isEvaluated, type SiteData } from "@/types"

function Excavation({ data }: { data: SiteData["excavation"] }) {
  const sides = [
    { key: "old", rule: data.old, verdict: "Conformant", note: "The program matches the rule it was written for.", drift: false },
    { key: "new", rule: data.new, verdict: "D1 · Stale threshold", note: "Same code, newer rule: the marked lines still hold the old value.", drift: true },
  ] as const
  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-lg">
      <Tabs defaultValue="new" className="gap-0">
        <CardHeader className="flex flex-row items-center justify-between gap-3 border-b py-3 [.border-b]:pb-3">
          <div className="flex min-w-0 items-center gap-2">
            <FileCode2 className="size-4 shrink-0 text-muted-foreground" />
            <CardTitle className="truncate font-mono text-sm">{data.program}</CardTitle>
          </div>
          <TabsList className="h-8">
            {sides.map((s) => (
              <TabsTrigger key={s.key} value={s.key} className="px-2.5 text-xs">
                Rule of {s.rule.version.slice(0, 4)}
              </TabsTrigger>
            ))}
          </TabsList>
        </CardHeader>
        {sides.map((s) => (
          <TabsContent key={s.key} value={s.key} className="m-0">
            <CardContent className="px-0">
              <pre className="max-h-80 overflow-auto py-3 font-mono text-[12.5px] leading-6">
                <code className="block min-w-max">
                  {data.lines.map((line) => (
                    <span
                      key={line.n}
                      className={cn(
                        "block pr-4 pl-3 border-l-2 border-transparent",
                        s.drift && line.hit && "border-destructive bg-destructive/10",
                      )}
                    >
                      <span className="mr-4 inline-block w-6 select-none text-right text-muted-foreground/60">{line.n}</span>
                      {line.text}
                    </span>
                  ))}
                </code>
              </pre>
            </CardContent>
            <CardFooter className="flex flex-wrap items-center justify-between gap-2 border-t bg-muted/40 py-3 [.border-t]:pt-3">
              <CardDescription className="text-xs">
                KYC rule as of {s.rule.version}: owner above {s.rule.value}%. {s.note}
              </CardDescription>
              <Badge
                variant="outline"
                className={s.drift ? "border-destructive/30 bg-destructive/10 text-destructive" : "border-success/30 bg-success/10 text-success"}
              >
                {s.verdict}
              </Badge>
            </CardFooter>
          </TabsContent>
        ))}
      </Tabs>
    </Card>
  )
}

export function Hero({ data }: { data: SiteData }) {
  const test = data.benchmark.splits.find((s) => s.name === "test")!
  const decision = data.results.decision
  const stats = [
    { value: test.rows, label: "Held-out test rows" },
    { value: test.cross, label: "Cross-program cases" },
    { value: data.benchmark.pairs, label: "Temporal pairs" },
    { value: data.classes.length, label: "Drift classes" },
  ]
  return (
    <div className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-[linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_40%,transparent_100%)] opacity-60"
      />
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-16 pb-12 sm:px-6 md:pt-24 lg:grid-cols-[1.05fr_1fr]">
        <div className="min-w-0 space-y-6">
          <a href="#result">
            <Badge variant="outline" className="gap-2 rounded-full bg-background px-3 py-1 text-xs">
              <DecisionBadge decision={decision} className="-ml-2 border-0 bg-transparent px-0" />
              <span className="text-muted-foreground">{data.current} official result</span>
              <ArrowRight className="size-3 text-muted-foreground" />
            </Badge>
          </a>
          <h1 className="text-4xl font-semibold tracking-tighter text-balance sm:text-5xl lg:text-6xl">
            The rule changed. <span className="text-muted-foreground">The COBOL didn’t.</span>
          </h1>
          <p className="max-w-xl text-lg text-muted-foreground text-pretty">
            COBOL Archaeologist finds where decades-old banking code has drifted from the regulation it was built
            to satisfy: stale thresholds, missing checks, contradictions, dead compliance code. Every finding is
            pinned to source lines and verified before it counts.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button size="lg" asChild>
              <a href="#result">See the result <ArrowRight /></a>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <a href={data.repo}>Read the code</a>
            </Button>
          </div>
        </div>
        <div className="min-w-0">
          <Excavation data={data.excavation} />
        </div>
      </div>
      <div className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border md:grid-cols-5">
          {stats.map((s) => (
            <div key={s.label} className="bg-card p-5">
              <div className="text-3xl font-semibold tabular-nums tracking-tight">{s.value}</div>
              <div className="mt-1 text-sm text-muted-foreground">{s.label}</div>
            </div>
          ))}
          <div className="col-span-2 bg-card p-5 md:col-span-1">
            <div className="text-3xl font-semibold tabular-nums tracking-tight">
              {isEvaluated(data.results) ? (gate(data.results, "zero_unverified_findings").pass ? "0" : "≥1") : "–"}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">Unverified findings emitted</div>
          </div>
        </div>
      </div>
    </div>
  )
}
