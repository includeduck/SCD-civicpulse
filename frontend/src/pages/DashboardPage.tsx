import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { listComplaints, updateStatus, updateTriage } from "../api/client";
import { CATEGORIES, PRIORITIES, STATUSES } from "../api/contract";
import { ApiError } from "../api/errors";
import type { Category, Complaint, ComplaintFilters, ComplaintList, Priority, Status } from "../api/types";
import { Badge } from "../components/Badge";
import { formatDate, humanize, providerLabel } from "../format";

const PAGE_SIZE = 20;

/** The last completed request: loading is "the key has moved on since". */
interface Result {
  key: string;
  data: ComplaintList | null;
  error: ApiError | null;
}

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return allowed.find((option) => option === value);
}

/** Filters and page live in the URL, so a filtered view can be bookmarked or shared. */
function useFilters() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const filters: ComplaintFilters = {
    category: pick<Category>(params.get("category"), CATEGORIES),
    priority: pick<Priority>(params.get("priority"), PRIORITIES),
    status: pick<Status>(params.get("status"), STATUSES),
    page,
    page_size: PAGE_SIZE,
  };

  const setFilter = (name: "category" | "priority" | "status", value: string) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(name, value);
      else next.delete(name);
      next.delete("page"); // a new filter starts from the first page
      return next;
    });
  };
  const setPage = (next: number) => {
    setParams((current) => {
      const updated = new URLSearchParams(current);
      if (next <= 1) updated.delete("page");
      else updated.set("page", String(next));
      return updated;
    });
  };
  return { filters, setFilter, setPage };
}

export function DashboardPage() {
  const { filters, setFilter, setPage } = useFilters();
  const [reloadKey, setReloadKey] = useState(0);
  const { category, priority, status, page } = filters;
  const key = JSON.stringify([category, priority, status, page, reloadKey]);
  const [result, setResult] = useState<Result>({ key: "", data: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    listComplaints({ category, priority, status, page, page_size: PAGE_SIZE }, controller.signal)
      .then((data) => setResult({ key, data, error: null }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const apiError = error instanceof ApiError ? error : new ApiError(0, String(error));
        setResult((previous) => ({ key, data: previous.data, error: apiError }));
      });
    return () => controller.abort();
  }, [key, category, priority, status, page]);

  const reload = useCallback(() => setReloadKey((n) => n + 1), []);

  const replace = useCallback((updated: Complaint) => {
    setResult((current) =>
      current.data
        ? {
            ...current,
            data: { ...current.data, complaints: current.data.complaints.map((c) => (c.id === updated.id ? updated : c)) },
          }
        : current,
    );
  }, []);

  const loading = result.key !== key;
  const data = result.data;
  const error = loading ? null : result.error;

  return (
    <div className="page">
      <h1>Operations dashboard</h1>

      <div className="filters card" role="search" aria-label="Filter complaints">
        <FilterSelect label="Category" value={category} options={CATEGORIES} onChange={(v) => setFilter("category", v)} />
        <FilterSelect label="Priority" value={priority} options={PRIORITIES} onChange={(v) => setFilter("priority", v)} />
        <FilterSelect label="Status" value={status} options={STATUSES} onChange={(v) => setFilter("status", v)} />
      </div>

      {error && (
        <div className="alert" role="alert">
          <strong>Could not load complaints</strong>
          <p>{error.message}</p>
          <button type="button" onClick={reload}>
            Try again
          </button>
        </div>
      )}

      {loading && !data && (
        <p role="status" className="muted">
          Loading complaints...
        </p>
      )}

      {data && (
        <section aria-busy={loading} aria-label="Complaints">
          <p className="muted summary-line">
            {data.total === 1 ? "1 complaint" : `${data.total} complaints`}
            {loading && " (updating...)"}
          </p>
          {data.complaints.length === 0 ? (
            <p className="card empty">No complaints match these filters.</p>
          ) : (
            <ul className="complaints">
              {data.complaints.map((complaint) => (
                <ComplaintRow key={complaint.id} complaint={complaint} onUpdated={replace} onStale={reload} />
              ))}
            </ul>
          )}
          <Pagination page={data.page} totalPages={data.total_pages} onPage={setPage} />
        </section>
      )}
    </div>
  );
}

function FilterSelect<T extends string>(props: {
  label: string;
  value: T | null | undefined;
  options: readonly T[];
  onChange: (value: string) => void;
}) {
  const id = `filter-${props.label.toLowerCase()}`;
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <select id={id} value={props.value ?? ""} onChange={(event) => props.onChange(event.target.value)}>
        <option value="">All</option>
        {props.options.map((option) => (
          <option key={option} value={option}>
            {humanize(option)}
          </option>
        ))}
      </select>
    </div>
  );
}

function Pagination({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (page: number) => void }) {
  if (totalPages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Pagination">
      <button type="button" className="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {totalPages}
      </span>
      <button type="button" className="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </nav>
  );
}

/**
 * One complaint and its status actions.
 *
 * The buttons are exactly the complaint's `allowed_transitions`, as computed
 * by the server; this component has no idea which transitions are legal. If
 * the list is stale (someone else moved the complaint), the server answers
 * 409 and its message is shown word for word, then the list is refreshed.
 */
function ComplaintRow({
  complaint,
  onUpdated,
  onStale,
}: {
  complaint: Complaint;
  onUpdated: (complaint: Complaint) => void;
  onStale: () => void;
}) {
  const [pending, setPending] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<Category>(complaint.category);
  const [priority, setPriority] = useState<Priority>(complaint.priority);
  const [triagePending, setTriagePending] = useState(false);
  const [triageError, setTriageError] = useState<string | null>(null);

  useEffect(() => {
    setCategory(complaint.category);
    setPriority(complaint.priority);
  }, [complaint.category, complaint.priority]);

  async function move(target: Status) {
    setPending(target);
    setError(null);
    try {
      onUpdated(await updateStatus(complaint.id, target));
    } catch (caught) {
      const apiError = caught instanceof ApiError ? caught : new ApiError(0, String(caught));
      setError(apiError.message);
      if (apiError.status === 409 || apiError.status === 404) onStale();
    } finally {
      setPending(null);
    }
  }

  async function saveTriage() {
    setTriagePending(true);
    setTriageError(null);
    try {
      onUpdated(await updateTriage(complaint.id, { category, priority }));
    } catch (caught) {
      const apiError = caught instanceof ApiError ? caught : new ApiError(0, String(caught));
      setTriageError(apiError.message);
    } finally {
      setTriagePending(false);
    }
  }

  const headingId = `complaint-${complaint.id}`;
  const categorySelectId = `triage-cat-${complaint.id}`;
  const prioritySelectId = `triage-pri-${complaint.id}`;

  return (
    <li className="card complaint" aria-labelledby={headingId}>
      <div className="complaint-head">
        <h2 id={headingId}>{complaint.location}</h2>
        <time dateTime={complaint.created_at} className="muted">
          {formatDate(complaint.created_at)}
        </time>
      </div>
      <p className="complaint-text">{complaint.text}</p>
      {complaint.ai_summary && (
        <p className="complaint-summary">
          <span className="muted">AI summary of the report:</span> {complaint.ai_summary}
        </p>
      )}
      <div className="badges">
        <Badge kind="category" value={complaint.category} />
        <Badge kind="priority" value={complaint.priority} />
        <Badge kind="status" value={complaint.status} />
        <span className="muted small">{providerLabel(complaint.triaged_by)}</span>
        {complaint.triage_corrected_at && (
          <span className="muted small" title={`Corrected at ${formatDate(complaint.triage_corrected_at)}`}>
            (triage corrected)
          </span>
        )}
      </div>

      <div className="triage-correction" aria-label="Triage correction">
        <label htmlFor={categorySelectId}>Correct category</label>
        <select
          id={categorySelectId}
          aria-label="Correct category"
          value={category}
          disabled={triagePending}
          onChange={(e) => setCategory(e.target.value as Category)}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {humanize(c)}
            </option>
          ))}
        </select>

        <label htmlFor={prioritySelectId}>Correct priority</label>
        <select
          id={prioritySelectId}
          aria-label="Correct priority"
          value={priority}
          disabled={triagePending}
          onChange={(e) => setPriority(e.target.value as Priority)}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {humanize(p)}
            </option>
          ))}
        </select>

        <button
          type="button"
          className="secondary"
          disabled={triagePending}
          onClick={() => void saveTriage()}
        >
          {triagePending ? "Saving triage..." : "Save triage"}
        </button>
      </div>
      {triageError && (
        <p className="alert inline" role="alert">
          {triageError}
        </p>
      )}

      <div className="actions" role="group" aria-label={`Change status of complaint at ${complaint.location}`}>
        {complaint.allowed_transitions.length === 0 ? (
          <span className="muted small">No further status changes.</span>
        ) : (
          complaint.allowed_transitions.map((target) => (
            <button
              key={target}
              type="button"
              className="secondary"
              disabled={pending !== null}
              onClick={() => void move(target)}
            >
              {pending === target ? "Saving..." : `Mark ${humanize(target).toLowerCase()}`}
            </button>
          ))
        )}
      </div>
      {error && (
        <p className="alert inline" role="alert">
          {error}
        </p>
      )}
    </li>
  );
}
