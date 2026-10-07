# DRAFTS. Alex rewrites these in his own words before anything is sent.

Nothing in this file has been emailed, messaged, or posted. These are starting points, not messages.

**Timing.** Medicare Annual Enrollment (AEP) runs October 15 to December 7, and Gyde will be busy. The roadmap sends the note to George and the LinkedIn post after the v1.0.0 tag (planned October 27 to November 2), and saves the fuller conversation for after December 7.

**Where every number comes from.** README "Results (synthetic)" and "How Jev is used", which read `dashboard/public/demo-run/scorecard.json` and `manifest.json` (the committed demo run, seed 42, Jev in replay). If the demo run is regenerated, check every number again before sending.

---

## 1. Note to George Quievryn at Gyde

Hi George,

On our call you said agencies often arrive without a reliable CRM. That stuck with me, so I built a small intake kit on synthetic data. It reads the files an acquired agency hands over, checks every row against 46 written rules, and ties out the book three ways against carrier commission statements and the CRM. Every row keeps a record of where it came from. Jev answers only narrow questions the rules cannot, and a person decides the rest. On a synthetic test agency it found all 717 planted mistakes it is built to catch, with no false alarms. I wrote the spec and AI coding agents did the typing.

Demo: https://agency-intake-kit.vercel.app
Code: https://github.com/alexmunzon/agency-intake-kit

I know AEP keeps your team busy, so no reply needed.

Alex

**Check before sending:**
- The CRM point is from Alex's call notes (ROADMAP section 2). Do not put words in George's mouth beyond that.
- "717 planted mistakes" and "no false alarms" are measured on synthetic data (README Results: 22 scored types, 0 false alarms on 11,234 clean rows). The generator also plants identity mistakes this kit reports but does not score, which is why the note says "built to catch".
- Open the live demo first and confirm it shows the real demo run (the Overview should say "Yes, with fixes to review.").

## 2. LinkedIn post

When an insurance agency is bought, its records arrive as a pile of mismatched files. Someone then checks them by hand for weeks.

I wrote that checking down as code. agency-intake-kit reads a CRM export, an enrollment export, carrier commission statements, and an agent roster. It checks every row against 46 written rules, ties out the commissions three ways, and flags policies sold by agents who were not ready to sell them. A small decision model answers only narrow questions the rules cannot. A person decides the rest.

On a synthetic test agency it found all 717 planted mistakes it is built to catch.

I wrote the spec. AI coding agents did the typing.

Demo and code: [links]

Post with one screenshot: `docs/screenshots/overview-1440.png`.

## 3. Subject lines for the note

1. Built something after our call (no reply needed)
2. An intake kit, after what you said about agency CRMs
3. A three-way tie-out on a synthetic agency book

## 4. What this demonstrates, by role

**AI Deployment Specialist.** The job is to stand up a newly acquired agency in GydeOS within 30 days: validate and clean the book of business and ready-to-sell uploads, then build reconciliation views. The Exceptions page is that work as a queue. Every problem has a severity, a suggested fix, and the exact source row, sorted so the worst comes first. Errors hold their rows out of the load files and warnings pass with a flag. Open any row and the lineage drawer shows the source file, sheet, row number, and a fingerprint of the raw row, so a fix can be traced back to the file the agency sent. The Sources page shows whether every file arrived with the promised row count, and the Agents page shows the 27 policies written without ready-to-sell status. Column mapping goes dictionary first, then Jev, then a person, which matched 129 of 134 headers versus 107 with the dictionary alone. That set is small, synthetic and seen (partly drawn from the files the dictionary was built from, with Jev answers recorded for those exact headers), so it is not a measure on unfamiliar exports.

**M&A Analyst.** The job is to turn a seller's book and carrier commission statements into numbers you can trust, line by line. The tie-out does that three ways in SQL: the book against the statements, the statements against the book, and the CRM against the statements. On the synthetic agency it found $3,530.75 expected but not paid on 134 active policies, $1,580.00 paid on 71 lines that match no policy in the book, and 40 policies where the CRM status disagrees with the carrier. That is $5,110.75 across 245 items. It also flags 66 lines paid off the rate table and 48 carrier or agent totals off by more than 0.5 percent. One example: Harborline's August statement pays $61.05 for a member who is in no policy. Money is exact to the cent, never rounded.

## 5. Resume bullet candidates

Each is 107 to 115 characters and uses Built or Shipped only for what is in this repo. Keep "synthetic" in both.

- Shipped an agency intake kit (Python, DuckDB SQL) that found all 717 planted defects in 14,879 synthetic rows
- Built a three-way commission tie-out in SQL flagging $5,110.75 in variances across 245 items on a synthetic agency
