import type { Metadata } from "next";
import Link from "next/link";
import { ReviewPackageSummary } from "@/components/review-package";

export const metadata: Metadata = {
  title: "Synthetic review package | Agency Intake Kit",
  description: "Independent source, identity, financial, and human review evidence for a synthetic agency package.",
};

const PANEL = "consulting-panel rounded-lg border border-border bg-card p-5";
const EVIDENCE_LINK = "inline-flex min-h-11 items-center py-2 font-medium text-primary underline dark:text-accent-foreground";

export default function PackagePage() {
  return (
    <div className="page-stack">
      <header className="page-header">
        <div className="page-provenance">
          <p className="eyebrow">Agency Data Trust Series</p>
          <span className="synthetic-label">Synthetic agency package</span>
        </div>
        <h1>Synthetic review package</h1>
        <p className="page-description">
          Review each evidence stream before making a release decision. Source completeness, excluded records,
          identity uncertainty, financial totals, and human decisions answer different questions.
        </p>
      </header>

      <ReviewPackageSummary />

      <details className="space-y-4"><summary className="cursor-pointer py-3 font-semibold">Evidence guide and production limits</summary>
      <section aria-labelledby="package-scope" className={PANEL}>
        <div className="panel-heading"><h2 id="package-scope">Keep the evidence in scope</h2></div>
        <p className="mt-3 text-sm text-muted-foreground">
          The summary above validates only its imported package, with no aggregate go-live verdict. The links below are a separate review guide. Sources, exceptions, and tie-out show the demo or the run loaded
          in this browser. Source readiness imports a separate dated snapshot; it does not automatically correspond to the loaded Intake run.
          The receipt ledger also opens its own export and does not inherit the loaded run.
          Companion dashboards open separate demos and do not inherit that run, agency, or review state.
          Plan Diff also offers a separately selected public Texas run; public carrier evidence does not establish a client&apos;s enrollment.
        </p>
        <p className="mt-3 text-sm text-muted-foreground">
          Local package tools must use the same explicit agency and Intake run IDs, verify pinned artifact hashes,
          and retain provenance. Hashes establish snapshot consistency, not authenticity. Client plan worklists need
          separately supplied synthetic coverage evidence; missing county or plan year stays unresolved.
        </p>
      </section>

      <div className="grid min-w-0 gap-4 md:grid-cols-2">
        <section aria-labelledby="source-completeness" className={PANEL}>
          <div className="panel-heading"><h2 id="source-completeness">Source completeness</h2></div>
          <p className="mt-3 text-sm text-muted-foreground">
            Compare required sources, expected and received rows, and the mapping used for this snapshot.
            A successful row check does not prove that all agency records were received.
          </p>
          <Link className={EVIDENCE_LINK} href="/sources">Inspect source evidence</Link>
          <p className="mt-2 text-sm text-muted-foreground">
            Readiness checks expected-file coverage and freshness from a separately imported package. Verify its agency,
            Intake run, and as-of date against the evidence you intend to review.
          </p>
          <Link className={EVIDENCE_LINK} href="/readiness">Review source readiness snapshot</Link>
        </section>

        <section aria-labelledby="excluded-records" className={PANEL}>
          <div className="panel-heading"><h2 id="excluded-records">Excluded records</h2></div>
          <p className="mt-3 text-sm text-muted-foreground">
            Inspect errors, unresolved references, and records kept out of the clean outputs. Keep warnings and
            unsupported records visible; exclusion does not resolve their business meaning.
          </p>
          <Link className={EVIDENCE_LINK} href="/exceptions">Inspect exceptions</Link>
        </section>

        <section aria-labelledby="identity-uncertainty" className={PANEL}>
          <div className="panel-heading"><h2 id="identity-uncertainty">Identity uncertainty</h2></div>
          <p className="mt-3 text-sm text-muted-foreground">
            Bob&apos;s deterministic links preserve match evidence and conflicts. Resolved does not mean human-confirmed;
            singleton, ambiguous, and unsupported identities remain review work.
          </p>
          <p className="mt-3 text-xs text-muted-foreground">Separate Bob demo; no shared agency run is loaded.</p>
          <ul className="flex flex-wrap gap-x-5">
            <li><a className={EVIDENCE_LINK} href="https://bob-resolve-nine.vercel.app/clusters">Inspect identity clusters</a></li>
            <li><a className={EVIDENCE_LINK} href="https://bob-resolve-nine.vercel.app/review">Open identity review queue</a></li>
          </ul>
          <p className="mt-2 text-sm text-muted-foreground">
            In the local Bob dashboard, open Evidence workflow for separately supplied review context. Its browser-memory
            drafts and declared reviewer names are unauthenticated; accepting evidence does not merge people or resolve identity.
          </p>
        </section>

        <section aria-labelledby="financial-totals" className={PANEL}>
          <div className="panel-heading"><h2 id="financial-totals">Financial totals</h2></div>
          <p className="mt-3 text-sm text-muted-foreground">
            Check statement groups, matched transactions, unmapped evidence, and variance by the stated basis.
            A tie-out result does not settle identity, source completeness, or permission to post to an ERP.
          </p>
          <Link className={EVIDENCE_LINK} href="/tie-out">Inspect financial tie-out</Link>
          <p className="mt-2 text-sm text-muted-foreground">
            The receipt ledger opens a separate synthetic JSON export; its bundled example is a committed demo snapshot.
            The page uses browser memory. Durable receipt storage uses the local SQLite finance command, with no hosted persistence.
          </p>
          <Link className={EVIDENCE_LINK} href="/ledger">Inspect receipt ledger snapshot</Link>
        </section>

        <section aria-labelledby="human-review" className={`${PANEL} md:col-span-2`}>
          <div className="panel-heading"><h2 id="human-review">Human review</h2></div>
          <p className="mt-3 text-sm text-muted-foreground">
            Record an evidenced human decision separately from automatic checks. Browser review labels are not authenticated approval.
            Plan change flags identify evidence to review; they are not suitability or purchase recommendations.
            Incomplete benefits, missing citations, unresolved identities, and missing coverage still require attention.
          </p>
          <p className="mt-3 text-xs text-muted-foreground">Separate Plan Diff demo; select its run and inspect citations before interpreting a flag.</p>
          <ul className="flex flex-wrap gap-x-5">
            <li><a className={EVIDENCE_LINK} href="https://plan-diff.vercel.app/changes">Inspect plan changes</a></li>
            <li><a className={EVIDENCE_LINK} href="https://plan-diff.vercel.app/trust">Inspect plan trust evidence</a></li>
          </ul>
        </section>
      </div>

      <section aria-labelledby="release-gates" className={PANEL}>
        <div className="panel-heading"><h2 id="release-gates">Production access gates</h2></div>
        <p className="mt-3 text-sm text-muted-foreground">These gates need separate authorization and implementation before production use.</p>
        <ul className="mt-3 grid gap-3 text-sm text-muted-foreground sm:grid-cols-2">
          <li><strong className="text-foreground">Real authentication.</strong> Verify reviewer identity, roles, and evidence of approval.</li>
          <li><strong className="text-foreground">Hosted storage.</strong> Establish authorized storage, retention, and access controls for agency artifacts.</li>
          <li><strong className="text-foreground">ERP posting.</strong> Approve the destination, posting basis, and controlled release process.</li>
          <li><strong className="text-foreground">Agency data.</strong> Obtain explicit permission for real data and validate the agency-specific sources and mappings.</li>
        </ul>
      </section>
      </details>
    </div>
  );
}
