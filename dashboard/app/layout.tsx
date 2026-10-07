import type { Metadata } from "next";
import { ShieldCheck } from "lucide-react";
import { LoadedRunBanner, LoadedRunProvider } from "@/components/loaded-run";
import { NavLink } from "@/components/nav-link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agency Intake Kit",
  description:
    "Review source coverage, exceptions, financial tie-out, and independent release evidence. Synthetic data only; production access and human approval require separate evidence.",
};

const PAGES: { label: string; href: string }[] = [
  { label: "Overview", href: "/" },
  { label: "Review package", href: "/package" },
  { label: "Sources", href: "/sources" },
  { label: "Source readiness", href: "/readiness" },
  { label: "Exceptions", href: "/exceptions" },
  { label: "Tie-out", href: "/tie-out" },
  { label: "Receipt ledger", href: "/ledger" },
  { label: "Agents", href: "/agents" },
  { label: "Runs", href: "/runs" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-background text-foreground lg:flex-row">
        <LoadedRunProvider>
          <a href="#main-content" className="skip-link">Skip to content</a>
          <nav aria-label="Main" className="app-sidebar">
            <div className="sidebar-brand">
              <span className="brand-symbol"><ShieldCheck aria-hidden className="size-5" /></span>
              <div>
                <p className="brand-title">Agency Intake Kit</p>
                <p className="brand-caption">Data trust series / 01</p>
              </div>
            </div>
            <p className="sidebar-label">Assessment workspace</p>
            <ul className="sidebar-pages">
              {PAGES.map(({ label, href }) => (
                <li key={label}><NavLink href={href} label={label} /></li>
              ))}
            </ul>
            <section aria-label="Agency Data Trust Series" className="sidebar-series">
              <p>Agency Data Trust Series</p>
              <p>Separate demos, shared trust principles.</p>
              <ol>
                <li><span aria-current="page">1. Intake Kit</span></li>
                <li><a href="https://bob-resolve-nine.vercel.app" className="underline">2. Bob Resolve</a></li>
                <li><a href="https://plan-diff.vercel.app" className="underline">3. Plan Diff</a></li>
              </ol>
            </section>
          </nav>
          <main id="main-content" tabIndex={-1} className="app-main min-w-0">
            <LoadedRunBanner />
            <aside aria-label="Review scope" className="trust-note mb-6 text-sm text-muted-foreground">
              Synthetic review only. Source completeness, exclusions, identity uncertainty, and financial totals require separate evidence. Browser review labels are not authenticated approval.
            </aside>
            {children}
          </main>
        </LoadedRunProvider>
      </body>
    </html>
  );
}
