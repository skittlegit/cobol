import * as React from "react"
import { Check, Copy, Eraser, Network, Search, ShieldCheck, ShieldHalf } from "lucide-react"
import { Bar, BarChart, XAxis, YAxis } from "recharts"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Separator } from "@/components/ui/separator"
import { CLASS_COLOR, DecisionBadge, Section } from "@/components/site/common"
import { cn } from "@/lib/utils"
import type { SiteData } from "@/types"

const STEPS = [
  { icon: Eraser, title: "Clean", text: "Mask EXEC blocks, expand COPY REPLACING, keep every original line number." },
  { icon: Network, title: "Map", text: "tree-sitter AST, paragraphs, copybooks, call graph, and cross-program def-use." },
  { icon: Search, title: "Investigate", text: "gpt-6-luna reads the clause and the code through bounded tools: slices, traces, grep, compile-and-run." },
  { icon: ShieldCheck, title: "Verify", text: "Executed under GnuCOBOL or shown statically, and entailed by the clause (DeBERTa NLI, another model family)." },
  { icon: ShieldHalf, title: "Guard", text: "A class-specific evidence check. Anything that fails becomes an abstention, never a guess." },
]

export function Method() {
  return (
    <Section
      id="method"
      eyebrow="Method"
      title="An excavation, not a guess"
      description="The detector cannot read the whole bundle at once. It investigates with program-analysis tools, and every claim it makes has to survive verification."
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((s, i) => (
          <Card key={s.title} className="gap-3">
            <CardHeader>
              <div className="flex items-center justify-between">
                <span className="grid size-9 place-items-center rounded-lg border bg-muted/50">
                  <s.icon className="size-4" />
                </span>
                <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
              </div>
              <CardTitle className="pt-2">{s.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{s.text}</CardContent>
          </Card>
        ))}
      </div>
    </Section>
  )
}

export function Classes({ data }: { data: SiteData }) {
  return (
    <Section
      id="classes"
      eyebrow="Taxonomy"
      title="Seven ways code and regulation can disagree"
      description="Each case binds one COBOL program bundle to one clause of the RBI Credit Card and Debit Card Directions, 2025 or the RBI KYC Directions, 2025, pinned to a version and effective date."
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {data.classes.map((c) => (
          <Card key={c.code} className={cn("relative gap-2 overflow-hidden", c.code === "D7" && "sm:col-span-2 lg:col-span-1")}>
            <div className="absolute inset-x-0 top-0 h-1" style={{ background: CLASS_COLOR[c.code] }} />
            <CardHeader>
              <Badge variant="outline" className="font-mono" style={{ color: CLASS_COLOR[c.code] }}>{c.code}</Badge>
              <CardTitle className="pt-1">{c.name}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{c.description}</CardContent>
          </Card>
        ))}
      </div>
    </Section>
  )
}

export function Benchmark({ data, classes }: { data: SiteData["benchmark"]; classes: SiteData["classes"] }) {
  const config = Object.fromEntries(
    classes.map((c) => [c.code, { label: `${c.code} ${c.name}`, color: CLASS_COLOR[c.code] }]),
  ) satisfies ChartConfig
  const rows = data.splits.map((s) => ({ name: s.name, ...s.classes }))
  return (
    <Section
      id="benchmark"
      eyebrow="Benchmark"
      title="Built to be hard to shortcut"
      description="Rows are mutations of AWS CardDemo and purpose-written programs. Benign edits are mixed in so the edit never gives the answer away, and every row compiles under GnuCOBOL 3.2."
    >
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Class mix per split</CardTitle>
            <CardDescription>Rows by drift class. Test programs appear in no other split.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={config} className="aspect-auto h-[180px] w-full">
              <BarChart data={rows} layout="vertical" stackOffset="expand" margin={{ left: 0, right: 8 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={48} tickLine={false} axisLine={false} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent hideIndicator={false} />} />
                {classes.map((c, i) => (
                  <Bar
                    key={c.code}
                    dataKey={c.code}
                    stackId="a"
                    fill={`var(--color-${c.code})`}
                    radius={i === 0 ? [4, 0, 0, 4] : i === classes.length - 1 ? [0, 4, 4, 0] : 0}
                    barSize={22}
                  />
                ))}
              </BarChart>
            </ChartContainer>
            <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
              {classes.map((c) => (
                <span key={c.code} className="flex items-center gap-1.5">
                  <span className="size-2.5 rounded-sm" style={{ background: CLASS_COLOR[c.code] }} />
                  {c.code} {c.name}
                </span>
              ))}
            </div>
          </CardContent>
          <CardFooter className="grid grid-cols-3 gap-4 border-t [.border-t]:pt-6">
            {data.splits.map((s) => (
              <div key={s.name}>
                <div className="text-2xl font-semibold tabular-nums">{s.rows}</div>
                <div className="text-xs text-muted-foreground">
                  {s.name} · {s.cross} cross-program
                </div>
              </div>
            ))}
          </CardFooter>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Temporal pairs</CardTitle>
            <CardDescription>
              One program judged under two versions of the same KYC clause ({data.versions.join(" and ")}). It keeps
              the older threshold: conformant then, stale now.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y text-sm">
              {data.targets.map((t) => (
                <li key={t.name} className="flex items-center justify-between py-2.5 capitalize">
                  {t.name}
                  <Badge variant="secondary" className="font-mono">{t.pairs}</Badge>
                </li>
              ))}
            </ul>
          </CardContent>
          <CardFooter className="text-xs text-muted-foreground">{data.pairs} pairs in total</CardFooter>
        </Card>
      </div>
    </Section>
  )
}

export function Record({ data }: { data: SiteData }) {
  return (
    <Section
      id="record"
      eyebrow="Evaluation record"
      title="Every official decision is kept"
      description={
        <>
          E1 is the first-look run. E2 is the evaluation after fixing what E1 exposed. Details are in{" "}
          <a className="font-medium text-foreground underline underline-offset-4" href={`${data.repo}/blob/master/STATUS.md`}>STATUS.md</a>.
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        {data.history.map((h) => (
          <Card key={h.run} className={cn(h.current && "ring-2 ring-primary/80")}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm text-muted-foreground">{h.run}{h.current && " · current"}</span>
                <DecisionBadge decision={h.decision} />
              </div>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{h.text}</CardContent>
          </Card>
        ))}
      </div>
    </Section>
  )
}

const COMMANDS = `# install, fetch the pinned corpora, run the offline suite
pip install -e ".[dev,models]"
bash scripts/fetch_corpora.sh
pytest tests/ -q

# the official run: detector, temporal pairs, baseline, report
python -m cobol_archaeologist.eval.runner detector --split test
python -m cobol_archaeologist.eval.runner detector --split temporal
python -m cobol_archaeologist.eval.runner rag_reranker --split test
python -m cobol_archaeologist.eval.report --split test`

export function Reproduce() {
  const [copied, setCopied] = React.useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(COMMANDS)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard unavailable */ }
  }
  return (
    <Section id="reproduce" eyebrow="Reproduce" title="Run it yourself">
      <Card className="gap-0 py-0">
        <CardHeader className="flex flex-row items-center justify-between border-b py-3 [.border-b]:pb-3">
          <CardDescription className="font-mono text-xs">bash</CardDescription>
          <Button variant="ghost" size="sm" onClick={copy}>
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
          </Button>
        </CardHeader>
        <CardContent className="px-0">
          <pre className="overflow-x-auto p-6 font-mono text-[13px] leading-7">
            {COMMANDS.split("\n").map((line, i) => (
              <div key={i} className={line.startsWith("#") ? "text-muted-foreground" : ""}>{line || " "}</div>
            ))}
          </pre>
        </CardContent>
      </Card>
    </Section>
  )
}

export function Footer() {
  return (
    <footer className="border-t pb-[calc(2rem+env(safe-area-inset-bottom,0px))] pt-8">
      <div className="mx-auto max-w-6xl space-y-4 px-4 text-sm text-muted-foreground sm:px-6">
        <p>
          Corpora: AWS CardDemo (Apache-2.0) and IBM CICS CBSA (EPL-2.0), fetched at pinned commits. Regulation texts:
          Reserve Bank of India, pinned by SHA-256.
        </p>
        <Separator />
        <p>
          Every number on this page is generated from the repository’s result files by{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">scripts/build_site.py</code>.
        </p>
      </div>
    </footer>
  )
}
