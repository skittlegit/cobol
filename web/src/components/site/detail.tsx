import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig,
} from "@/components/ui/chart"
import { Progress } from "@/components/ui/progress"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Section, pct } from "@/components/site/common"
import { cn } from "@/lib/utils"
import type { Evaluated } from "@/types"

const chartConfig = {
  detector: { label: "Detector", color: "var(--primary)" },
  baseline: { label: "RAG reranker baseline", color: "var(--muted-foreground)" },
} satisfies ChartConfig

function PerClass({ results }: { results: Evaluated }) {
  const rows = results.per_class.map((c) => ({ ...c, label: `${c.code} ${c.name}` }))
  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>F1 per drift class</CardTitle>
        <CardDescription>Test split, detector against the retrieval baseline</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="aspect-auto h-[340px] w-full">
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }} barGap={2}>
            <CartesianGrid horizontal={false} />
            <XAxis type="number" domain={[0, 1]} tickLine={false} axisLine={false} tickMargin={8} />
            <YAxis
              type="category"
              dataKey="label"
              width={150}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 12 }}
            />
            <ChartTooltip
              cursor={false}
              content={<ChartTooltipContent indicator="line" formatter={(value, name) => (
                <div className="flex w-full justify-between gap-4">
                  <span className="text-muted-foreground">{chartConfig[name as keyof typeof chartConfig]?.label}</span>
                  <span className="font-mono tabular-nums">{Number(value).toFixed(3)}</span>
                </div>
              )} />}
            />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar dataKey="detector" fill="var(--color-detector)" radius={4} barSize={12} />
            <Bar dataKey="baseline" fill="var(--color-baseline)" radius={4} barSize={12} fillOpacity={0.5} />
          </BarChart>
        </ChartContainer>
      </CardContent>
      <CardFooter className="flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {results.per_class.map((c) => (
          <span key={c.code} className="font-mono">{c.code} n = {c.support}</span>
        ))}
      </CardFooter>
    </Card>
  )
}

function Confusion({ results }: { results: Evaluated }) {
  const { cols, rows } = results.confusion
  return (
    <Card>
      <CardHeader>
        <CardTitle>Confusion matrix</CardTitle>
        <CardDescription>True class (rows) by predicted class (columns). The diagonal is correct.</CardDescription>
      </CardHeader>
      <CardContent>
        <table className="w-full table-fixed border-separate border-spacing-[3px] font-mono text-[11px]">
          <thead>
            <tr>
              <th className="w-6" />
              {cols.map((c) => <th key={c} className="pb-1 font-medium text-muted-foreground">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.gold}>
                <th className="pr-0.5 text-right font-medium text-muted-foreground">{r.gold}</th>
                {r.cells.map((cell, i) => (
                  <td
                    key={cols[i]}
                    title={`${r.gold} predicted ${cols[i]}: ${cell.n}`}
                    className={cn("aspect-square rounded-[5px] text-center tabular-nums", cell.diagonal && "font-semibold")}
                    style={{
                      background: cell.n
                        ? `color-mix(in oklch, ${cell.diagonal ? "var(--success)" : "var(--destructive)"} ${Math.round(15 + cell.share * 70)}%, transparent)`
                        : "var(--muted)",
                    }}
                  >
                    {cell.n || ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

function Bars({ title, description, items }: {
  title: string
  description: string
  items: { name: string; value: number; note: string }[]
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {items.map((i) => (
          <div key={i.name} className="space-y-2">
            <div className="flex items-baseline justify-between text-sm">
              <span>{i.name}</span>
              <span className="font-mono text-xs text-muted-foreground tabular-nums">{i.note}</span>
            </div>
            <Progress value={i.value * 100} />
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function Temporal({ results }: { results: Evaluated }) {
  const t = results.temporal
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold tabular-nums">{t.successes}/{t.pairs}</span>
          <span className="text-sm font-normal text-muted-foreground">pairs right on both sides</span>
        </CardTitle>
        <CardDescription>
          A pair counts only if the old side is called conformant and the new side drifted. Exact 95% interval{" "}
          {pct(t.ci[0])}–{pct(t.ci[1])}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(2.75rem,1fr))] gap-2">
          {t.per_pair.map((p) => (
            <Tooltip key={p.name}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "aspect-square rounded-md border font-mono text-xs font-medium transition-colors",
                    p.ok
                      ? "border-success/30 bg-success/10 text-success hover:bg-success/20"
                      : "border-dashed border-destructive/50 bg-destructive/10 text-destructive hover:bg-destructive/20",
                  )}
                >
                  {p.name.slice(-2)}
                </button>
              </TooltipTrigger>
              <TooltipContent>
                {p.name} · {p.target} · {p.ok ? "both sides right" : "missed"}
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function Detail({ results }: { results: Evaluated }) {
  return (
    <Section
      id="per-class"
      eyebrow="Breakdown"
      title="Where it is strong, and where it is not"
      description="Dead compliance code (D6) needs evidence from another program: the detector has to show that the guarded step can never run."
    >
      <div className="grid gap-6 lg:grid-cols-3">
        <PerClass results={results} />
        <Confusion results={results} />
        <Bars
          title="Localisation"
          description="Top-1 accuracy of the cited location."
          items={results.localisation.map((l) => ({ name: l.name, value: l.value, note: pct(l.value) }))}
        />
        <Bars
          title="Verification tier"
          description="Faithfulness of emitted findings, by the strongest evidence that verified them."
          items={results.tiers.map((t) => ({ name: t.name, value: t.faithfulness, note: `${pct(t.faithfulness)} · n = ${t.n}` }))}
        />
        <div id="temporal"><Temporal results={results} /></div>
      </div>
    </Section>
  )
}
