import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createComplaint } from "../api/client";
import { LIMITS } from "../api/contract";
import { ApiError } from "../api/errors";
import type { Complaint } from "../api/types";
import { Badge } from "../components/Badge";
import { formatMs, providerLabel } from "../format";
import { validate, type Field, type FieldErrors, type Values } from "../validation";


type State =
  | { phase: "idle" }
  | { phase: "submitting"; startedAt: number }
  | { phase: "success"; complaint: Complaint }
  | { phase: "error"; error: ApiError };

const EMPTY: Values = { text: "", location: "", reporter_contact: "" };

function useElapsedSeconds(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000));
}

export function SubmitPage() {
  const [values, setValues] = useState<Values>(EMPTY);
  const [clientErrors, setClientErrors] = useState<FieldErrors>({});
  const [state, setState] = useState<State>({ phase: "idle" });
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const submitting = state.phase === "submitting";
  const elapsed = useElapsedSeconds(submitting ? state.startedAt : null);
  const serverErrors: FieldErrors = state.phase === "error" ? state.error.fieldErrors : {};
  const errorFor = (field: Field) => clientErrors[field] ?? serverErrors[field];

  function update(field: Field, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    if (clientErrors[field]) setClientErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validate(values);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) return;

    abort.current = new AbortController();
    setState({ phase: "submitting", startedAt: Date.now() });
    try {
      const complaint = await createComplaint(
        {
          text: values.text.trim(),
          location: values.location.trim(),
          reporter_contact: values.reporter_contact.trim() || null,
        },
        abort.current.signal,
      );
      setState({ phase: "success", complaint });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      const apiError = error instanceof ApiError ? error : new ApiError(0, "Something unexpected happened. Please try again.");
      setState({ phase: "error", error: apiError });
    }
  }

  function reset() {
    setValues(EMPTY);
    setClientErrors({});
    setState({ phase: "idle" });
  }

  if (state.phase === "success") return <TriageResult complaint={state.complaint} onAnother={reset} />;

  return (
    <div className="page narrow">
      <h1>Report a problem</h1>
      <p className="lede">
        Tell us what is wrong and where. English, Urdu or Roman Urdu are all fine. Our triage reads it and routes it to
        the right department.
      </p>

      <form className="card" onSubmit={onSubmit} noValidate aria-busy={submitting}>
        <fieldset disabled={submitting}>
          <FieldShell id="text" label="What is the problem?" error={errorFor("text")}>
            <textarea
              id="text"
              rows={6}
              value={values.text}
              onChange={(event) => update("text", event.target.value)}
              aria-invalid={Boolean(errorFor("text"))}
              aria-describedby="text-error text-count"
              placeholder="e.g. Pipe burst ho gaya hai, paani sarak par beh raha hai"
            />
            <span id="text-count" className="hint">
              {values.text.trim().length} / {LIMITS.text.max}
            </span>
          </FieldShell>

          <FieldShell id="location" label="Where is it?" error={errorFor("location")}>
            <input
              id="location"
              value={values.location}
              onChange={(event) => update("location", event.target.value)}
              aria-invalid={Boolean(errorFor("location"))}
              aria-describedby="location-error"
              placeholder="e.g. Street 12, F-8/3, Islamabad"
            />
          </FieldShell>

          <FieldShell id="reporter_contact" label="Contact (optional)" error={errorFor("reporter_contact")}>
            <input
              id="reporter_contact"
              value={values.reporter_contact}
              onChange={(event) => update("reporter_contact", event.target.value)}
              aria-invalid={Boolean(errorFor("reporter_contact"))}
              aria-describedby="reporter_contact-error contact-hint"
              autoComplete="tel"
            />
            <span id="contact-hint" className="hint">
              Phone or email, only for follow-up. It is never shown publicly or sent to the AI.
            </span>
          </FieldShell>

          <button type="submit">{submitting ? "Analyzing complaint..." : "Submit complaint"}</button>
        </fieldset>

        {submitting && (
          <div className="loading" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <div>
              <strong>Analyzing complaint... {elapsed > 0 && `${elapsed}s`}</strong>
              <p>
                AI triage usually takes a few seconds. If the AI is slow or unavailable, our keyword rules answer
                instead, so your complaint is saved either way.
              </p>
            </div>
          </div>
        )}

        {state.phase === "error" && <SubmitError error={state.error} />}
      </form>
    </div>
  );
}

function FieldShell({ id, label, error, children }: { id: Field; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      <span id={`${id}-error`} className="field-error" role={error ? "alert" : undefined}>
        {error}
      </span>
    </div>
  );
}

/** The server's message, word for word (a 429 already says when to retry). */
function SubmitError({ error }: { error: ApiError }) {
  return (
    <div className="alert" role="alert">
      <strong>{error.status === 429 ? "Too many submissions" : "Your complaint was not submitted"}</strong>
      <p>{error.message}</p>
    </div>
  );
}

function TriageResult({ complaint, onAnother }: { complaint: Complaint; onAnother: () => void }) {
  const fellBack = complaint.triaged_by === "rules:fallback";
  return (
    <div className="page narrow">
      <section className="card result" aria-labelledby="result-heading">
        <h1 id="result-heading">Complaint received</h1>
        <p className="lede">
          Reference <code>{complaint.id}</code>
        </p>
        <dl className="facts">
          <div>
            <dt>Category</dt>
            <dd>
              <Badge kind="category" value={complaint.category} />
            </dd>
          </div>
          <div>
            <dt>Priority</dt>
            <dd>
              <Badge kind="priority" value={complaint.priority} />
            </dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <Badge kind="status" value={complaint.status} />
            </dd>
          </div>
          <div className="wide">
            <dt>Summary</dt>
            <dd>{complaint.ai_summary ?? "No summary was produced."}</dd>
          </div>
          <div>
            <dt>Triaged by</dt>
            <dd>{providerLabel(complaint.triaged_by)}</dd>
          </div>
          <div>
            <dt>Triage time</dt>
            <dd>{formatMs(complaint.triage_latency_ms)}</dd>
          </div>
        </dl>
        {fellBack && (
          <p className="note">
            The AI could not answer in time, so our keyword rules categorised this complaint instead.
          </p>
        )}
        <button type="button" onClick={onAnother}>
          Report another problem
        </button>
      </section>
    </div>
  );
}
