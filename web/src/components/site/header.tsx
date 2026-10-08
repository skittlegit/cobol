import { Pickaxe } from "lucide-react"

import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/site/common"

function GithubMark() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 0-.8.4-1.3.7-1.6-2.7-.3-5.5-1.3-5.5-6 0-1.2.5-2.3 1.3-3.1-.2-.4-.6-1.6 0-3.2 0 0 1-.3 3.4 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.6 1.6.2 2.8.1 3.2.8.8 1.3 1.9 1.3 3.2 0 4.6-2.8 5.6-5.5 5.9.5.4.9 1.1.9 2.2v3.3c0 .3.1.7.8.6A12 12 0 0 0 12 .3" />
    </svg>
  )
}

const LINKS = [
  ["Result", "#result"],
  ["Method", "#method"],
  ["Classes", "#classes"],
  ["Benchmark", "#benchmark"],
  ["Record", "#record"],
] as const

export function SiteHeader({ repo }: { repo: string }) {
  return (
    <header className="sticky top-[env(safe-area-inset-top,0px)] z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:px-6">
        <a href="#" className="mr-4 flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
            <Pickaxe className="size-4" />
          </span>
          <span className="hidden sm:inline">COBOL Archaeologist</span>
        </a>
        <nav className="hidden items-center md:flex">
          {LINKS.map(([label, href]) => (
            <Button key={href} variant="ghost" size="sm" asChild className="text-muted-foreground hover:text-foreground">
              <a href={href}>{label}</a>
            </Button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="outline" size="sm" asChild>
            <a href={repo}><GithubMark /> GitHub</a>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
