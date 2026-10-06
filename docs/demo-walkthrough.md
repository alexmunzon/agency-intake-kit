# Agency Data Trust: three-demo walkthrough

Three small working examples answer the same question: what can an operations team safely trust, and what still needs a person? The sites are separate, read-only demonstrations using frozen runs. They do not transfer client records between projects or make real coverage decisions.

## 1. Intake Kit: can the incoming files be used?

Open [Intake Kit](https://agency-intake-kit.vercel.app).

1. Overview distinguishes blockers, rows held out, and warnings. A successful pipeline is not an authenticated package approval.
2. Open [Exceptions](https://agency-intake-kit.vercel.app/exceptions), then a row. Show the rule, suggested fix, and source file/sheet/row.
3. Open [Tie-out](https://agency-intake-kit.vercel.app/tie-out). Show a commission difference with its source evidence. Checks can overlap, so their variance sums are not a single net missing-revenue number.
4. Open [Runs](https://agency-intake-kit.vercel.app/runs). Packages load in the browser; invalid evidence is rejected, and clear/reload returns to the demo. Use only synthetic files here.

The default run contains 14,879 synthetic rows and 717 planted mistakes across 22 scored types. Those figures describe this generated agency, not unfamiliar exports. The header-mapping benchmark is a seen, header-only replay check. An unfamiliar unrecorded header still goes to a person.

![Intake overview](screenshots/overview-1440.png)

## 2. Bob Resolve: which records belong to the same person?

Open [Bob Resolve](https://bob-resolve-nine.vercel.app).

1. In Clusters, inspect Robert/Bob Murphy's strong match and the source of each golden-record field.
2. In Review, contrast a GR-007 name-and-birth-date-only pair with a GR-005 conflicting pair. A high score does not confirm either direct pair. A blocked direct pair may already share a cluster through other accepted links; read that notice separately from the pair-level suggestion.
3. In Benchmark, distinguish automatic results, actual human confirmations, and the hypothetical result if every suggestion were confirmed.

The default fixture uses shared MBI to match records and masks it afterward. It is not an identifier-free result. The two-agency set was used during tuning; its shared-ID and no-shared-ID results are separate seen regression measurements. Browser review is read-only; an explicit decision file is applied by the CLI into a new run.

Detailed examples and screenshots: [Bob v1 walkthrough](https://github.com/alexmunzon/bob-resolve/blob/main/docs/v1-walkthrough-2026-10-06/README.md).

## 3. Plan Diff: what changed, and what is still uncertain?

Open [Plan Diff](https://plan-diff.vercel.app).

1. Start with the synthetic slice. H9999-001 shows a $25 monthly premium increase; H9999-002 is consolidated and H9999-003 is terminated.
2. Inspect H9999-004's ambiguous maximum out-of-pocket field. It needs review; missing evidence does not become zero or unchanged.
3. Show the source document and page for a benefit, then its CMS comparison. A conflicting copay remains a disagreement, and allowances without matching periods are not comparable.
4. Switch to the public Texas slice and read its separate Trust page. Public documents are real sources; extraction checks on documents used to build the parser are in-sample evidence.

“Shop again” flags a reason for a broker to review a plan change. It is not a suitability recommendation, enrollment action, or promise that another plan is better.

## Scope and evidence

- Intake and Bob use synthetic client records. Plan Diff keeps synthetic and public-source slices separate.
- Rules, provenance and unresolved states are part of the demonstration. No model can override a deterministic refusal.
- No live paid model calls are needed for this tour. Browser pages render committed results.
- New carrier coverage, real integrations, unseen evaluation, authenticated approvals and a connected client worklist remain future work.
- Check each repository's current validation notes and CI before treating a new branch as delivered. A local change or open PR is not a production release.
