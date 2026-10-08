import { TooltipProvider } from "@/components/ui/tooltip"
import { Benchmark, Classes, Footer, Method, Record, Reproduce } from "@/components/site/about"
import { Detail } from "@/components/site/detail"
import { SiteHeader } from "@/components/site/header"
import { Hero } from "@/components/site/hero"
import { Results } from "@/components/site/results"
import { isEvaluated, type SiteData } from "@/types"
import site from "./site.json"

const data = site as unknown as SiteData

export default function App() {
  return (
    <TooltipProvider delayDuration={100}>
      <SiteHeader repo={data.repo} />
      <main>
        <Hero data={data} />
        <Results data={data} />
        {isEvaluated(data.results) && <Detail results={data.results} />}
        <Method />
        <Classes data={data} />
        <Benchmark data={data.benchmark} classes={data.classes} />
        <Record data={data} />
        <Reproduce />
      </main>
      <Footer />
    </TooltipProvider>
  )
}
