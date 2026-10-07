"use client";

import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { CARD } from "@/components/tiles";
import {
  buildDecisions, canApprove, correctableFields, decisionConflicts, decisionsFileName,
  type MappingChoice, type MappingOrigin, type MappingReview, type MappingReviewItem, type MappingReviewState,
} from "@/lib/mapping-review";

const MUTED = "text-sm text-muted-foreground";
const WORDS = "whitespace-normal break-words [overflow-wrap:anywhere]";
const NOTE_LABEL = "A reviewer's note, not an authenticated approval";

const ORIGIN_LABELS: Record<MappingOrigin, string> = {
  jev_replay: "Jev (replay)",
  jev_live: "Jev (live)",
  jev_record: "Jev (record)",
  none: "No model answer",
};

// Plain wording for the engine's reason codes. An unknown code still shows, with spaces for underscores.
const REASONS: Record<string, string> = {
  mode_off: "Jev was off for this run, so no model was asked.",
  budget_tripped: "Jev's spending limit for this run was reached before this column.",
  notes: "This column may hold notes, so its values were not sent to Jev.",
  invalid_reply: "Jev's answer was not one of the allowed fields, so it was not used.",
  not_recorded: "No saved Jev answer exists for this column.",
  http_error: "Jev returned an error or did not reply in time, so there is no answer to use.",
  field_taken: "Another column already holds this field, so this one stayed unmapped.",
};
const reasonText = (reason: string) => REASONS[reason] ?? reason.replaceAll("_", " ");

type Action = MappingChoice["action"];
interface Choice { action: Action; field: string | null }
const LEAVE: Choice = { action: "leave", field: null };

function toChoice({ action, field }: Choice): MappingChoice {
  return action === "correct" ? { action, field } : { action };
}

/** Saves text as a file in the browser. Nothing leaves the page. */
function saveFile(fileName: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

interface PanelProps {
  state: MappingReviewState | undefined;
  now?: () => string;
  download?: (fileName: string, text: string) => void;
}

/** Column mapping review on the Sources page. Decisions stay in this page until downloaded. */
export function MappingReviewPanel({ state, now = () => new Date().toISOString(), download = saveFile }: PanelProps) {
  if (state === undefined) return null;
  return (
    <section aria-label="Column mapping review" className="min-w-0 space-y-4">
      <header>
        <h2 className="text-[22px] font-semibold tracking-tight">Review column mappings</h2>
        {state.ok && state.review.items.length > 0 && (
          <p className={MUTED}>
            The dictionary and saved decisions did not settle these columns. Jev only suggests; a person decides.
            Jev mode for this run: {state.review.jev_mode}.
          </p>
        )}
      </header>
      {!state.ok ? (
        <p role="alert" className={`${CARD} p-4 text-sm ${WORDS}`}>Could not show the mapping review. {state.error}</p>
      ) : state.review.items.length === 0 ? (
        <p className={`${CARD} p-4 text-sm`}>Every column was mapped by the dictionary or a saved decision.</p>
      ) : (
        <Review key={`${state.review.run_id}:${state.review.mapping_version}`} review={state.review} now={now} download={download} />
      )}
    </section>
  );
}

function Review({ review, now, download }: { review: MappingReview; now: () => string; download: (fileName: string, text: string) => void }) {
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [reviewer, setReviewer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const nameId = useId();
  const set = (id: string, choice: Choice) => {
    setChoices((current) => ({ ...current, [id]: choice }));
    setSaved(null);
  };

  const pending = Object.fromEntries(Object.entries(choices).map(([id, choice]) => [id, toChoice(choice)]));
  const conflicts = decisionConflicts(review, pending);

  function onDownload() {
    setSaved(null);
    if (conflicts.length > 0) {
      setError(conflicts.join(" "));
      return;
    }
    try {
      const file = buildDecisions(review, pending, reviewer, now());
      if (file.decisions.length === 0) {
        setError("Make at least one decision before downloading. Columns left unresolved are not included.");
        return;
      }
      const fileName = decisionsFileName(review.run_id);
      download(fileName, `${JSON.stringify(file, null, 2)}\n`);
      setError(null);
      setSaved(`Saved ${fileName} with ${file.decisions.length} of ${review.items.length} columns decided.`);
    } catch (problem) {
      setError((problem as Error).message);
    }
  }

  return (
    <>
      {review.items.map((item) => (
        <ItemCard key={item.item_id} item={item} choice={choices[item.item_id] ?? LEAVE} onChange={(choice) => set(item.item_id, choice)} />
      ))}
      <fieldset className={`${CARD} min-w-0 space-y-3 p-4`}>
        <legend className="px-1 text-sm font-medium">{NOTE_LABEL}</legend>
        <p className={MUTED}>
          Your choices stay in this page and are never sent anywhere. Download them, then apply them with
          {" "}<code className="font-mono text-xs">intake mapping apply</code>. The name you type is not checked.
        </p>
        <div className="flex min-w-0 flex-col gap-1">
          <label htmlFor={nameId} className="text-sm font-medium">Reviewer name</label>
          <input id={nameId} type="text" value={reviewer} autoComplete="off"
            onChange={(event) => { setReviewer(event.target.value); setError(null); }}
            className="w-full max-w-sm rounded-md border border-input bg-card px-2 py-1 text-sm text-foreground" />
        </div>
        {conflicts.length > 0 && (
          <ul className="space-y-1 text-sm text-destructive">
            {conflicts.map((problem) => <li key={problem}>{problem}</li>)}
          </ul>
        )}
        <Button type="button" onClick={onDownload}>Download decisions</Button>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <p role="status" className="text-sm">{saved}</p>
      </fieldset>
    </>
  );
}

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{term}</dt>
      <dd className={WORDS}>{children}</dd>
    </div>
  );
}

function ItemCard({ item, choice, onChange }: { item: MappingReviewItem; choice: Choice; onChange: (choice: Choice) => void }) {
  const group = useId();
  const selectId = useId();
  const fields = correctableFields(item);
  const approvable = canApprove(item);
  const radio = (action: Action, label: React.ReactNode, disabled = false) => (
    <label className={`flex min-w-0 items-start gap-2 text-sm ${disabled ? "text-muted-foreground" : ""}`}>
      <input type="radio" name={group} value={action} checked={choice.action === action} disabled={disabled}
        onChange={() => onChange({ action, field: action === "correct" ? choice.field : null })} className="mt-1" />
      <span className={WORDS}>{label}</span>
    </label>
  );
  return (
    <article aria-label={`Column ${item.header}, ${item.file_name}`} className={`${CARD} min-w-0 space-y-3 p-4`}>
      <header className={WORDS}>
        <h3 className="font-mono text-base font-medium">{item.header}</h3>
        <p className={`font-mono ${MUTED}`}>{item.file_name}</p>
      </header>
      <dl className="grid min-w-0 grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <Fact term="Sample values (masked)">
          {item.samples_withheld ? (
            "Samples withheld: this column may hold notes or ID numbers"
          ) : item.samples.length === 0 ? (
            "No values to sample"
          ) : (
            <span className="block overflow-x-auto">
              <span className="flex flex-wrap gap-1">
                {item.samples.map((sample, index) => (
                  <code key={`${index}:${sample}`} className="rounded bg-muted px-1 font-mono text-xs">{sample}</code>
                ))}
              </span>
            </span>
          )}
        </Fact>
        <Fact term="Proposal">
          {item.proposed_field === null ? "No proposal" : <code className="font-mono text-xs">{item.proposed_field}</code>}
        </Fact>
        <Fact term="Where the proposal came from">{ORIGIN_LABELS[item.origin]}</Fact>
        <Fact term="Confidence (model's confidence, not measured accuracy)">
          {item.confidence === null ? "None" : `${Math.round(item.confidence * 100)}%`}
        </Fact>
        <Fact term="Rows with a value">{item.rows_with_value.toLocaleString("en-US")}</Fact>
        <Fact term="Linked exceptions">
          {item.exception_ids.length === 0 ? "None" : (
            <ul className="space-y-0.5">{item.exception_ids.map((id) => <li key={id} className="font-mono text-xs break-all">{id}</li>)}</ul>
          )}
        </Fact>
      </dl>
      <p className={`text-sm ${WORDS}`}>{item.explanation}</p>
      {item.reason !== null && (
        <p className={`text-sm ${WORDS}`}><span className="font-medium">Why a person must decide: </span>{reasonText(item.reason)}</p>
      )}
      <fieldset className="min-w-0 space-y-2">
        <legend className="text-sm font-medium">Your decision</legend>
        {radio("leave", "Leave unresolved")}
        {radio("approve", approvable ? `Approve the proposal (${item.proposed_field})` : "Approve the proposal (no proposal to approve)", !approvable)}
        {radio("correct", "Correct to another field", fields.length === 0)}
        <div className="min-w-0 pl-6">
          <label htmlFor={selectId} className="block text-xs text-muted-foreground">
            Correct field<span className="sr-only"> for {item.header}</span>
          </label>
          <select id={selectId} value={choice.action === "correct" ? choice.field ?? "" : ""} disabled={choice.action !== "correct"}
            onChange={(event) => onChange({ action: "correct", field: event.target.value || null })}
            className="w-full max-w-sm rounded-md border border-input bg-card px-2 py-1 font-mono text-xs text-foreground disabled:text-muted-foreground">
            <option value="">Pick a field</option>
            {fields.map((field) => <option key={field} value={field}>{field}</option>)}
          </select>
          {choice.action === "correct" && choice.field === null && (
            <p className={`mt-1 ${MUTED}`}>Pick a field, or this column stays unresolved.</p>
          )}
        </div>
        {radio("ignore", "Ignore this column")}
      </fieldset>
    </article>
  );
}
