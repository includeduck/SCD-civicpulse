import { useEffect, useState } from "react";
import { getProviders, getStats, type CacheState } from "../api/client";
import { ApiError } from "../api/errors";
import type { Providers, Stats } from "../api/types";
import { formatDate, formatMs, humanize } from "../format";

interface Fetch {
  cache: CacheState;
  at: Date;
}

interface Result {
  request: number;
  stats: Stats | null;
  error: ApiError | null;
}

const HISTORY = 6;

export function StatsPage() {
  const [request, setRequest] = useState(0);
  const [result, setResult] = useState<Result>({ request: -1, stats: null, error: null });
  const [history, setHistory] = useState<Fetch[]>([]);

  useEffect(() => {
    let active = true;
    getStats()
      .then(({ stats, cache }) => {
        if (!active) return;
        setResult({ request, stats, error: null });
        setHistory((current) => [{ cache, at: new Date() }, ...current].slice(0, HISTORY));
      })
      .catch((caught: unknown) => {
        if (!active) return;
        const error = caught instanceof ApiError ? caught : new ApiError(0, String(caught));
        setResult((previous) => ({ request, stats: previous.stats, error }));
      });
    return () => {
      active = false;
    };
  }, [request]);

  const loading = result.request !== request;
  const stats = result.stats;
  const error = loading ? null : result.error;
  const latest = history[0];

  return (
    <div className="page">
      <div className="page-head">
        <h1>Statistics</h1>
        <button type="button" onClick={() => setRequest((n) => n + 1)} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {latest && <CacheBanner fetch={latest} history={history} />}

      {error && (
        <div className="alert" role="alert">
          <strong>Could not load statistics</strong>
          <p>{error.message}</p>
        </div>
      )}
      {!stats && loading && (
        <p role="status" className="muted">
          Loading statistics...
        </p>
      )}

      {stats && (
        <>
          <section className="tiles" aria-label="Totals">
            <Tile label="Total complaints" value={stats.total_complaints} />
            <Tile label="Open" value={stats.open_count} />
            <Tile label="In progress" value={stats.in_progress_count} />
            <Tile label="Resolved" value={stats.resolved_count} />
            <Tile label="Rejected" value={stats.rejected_count} />
          </section>
          <div className="columns">
            <Breakdown
              title="By category"
              total={stats.total_complaints}
              rows={stats.by_category.map((row) => ({ label: row.category, count: row.count }))}
            />
            <Breakdown
              title="By priority"
              total={stats.total_complaints}
              rows={stats.by_priority.map((row) => ({ label: row.priority, count: row.count }))}
            />
          </div>
        </>
      )}

      <ProvidersPanel />
    </div>
  );
}

/** Where the numbers came from, straight from the X-Cache response header. */
function CacheBanner({ fetch, history }: { fetch: Fetch; history: Fetch[] }) {
  const text: Record<CacheState, string> = {
    HIT: "Served from the Redis cache: no database query was needed.",
    MISS: "Computed from PostgreSQL just now, and cached for the next requests.",
    unknown: "The response did not say whether it came from the cache.",
  };
  return (
    <section className="card cache" data-cache={fetch.cache} aria-live="polite" aria-label="Cache status">
      <div>
        <span className="cache-badge">X-Cache: {fetch.cache}</span>
        <span>{text[fetch.cache]}</span>
      </div>
      {history.length > 1 && (
        <ol className="cache-history" aria-label="Recent loads, newest first">
          {history.map((entry) => (
            <li key={entry.at.getTime()} data-cache={entry.cache} title={entry.at.toLocaleTimeString()}>
              {entry.cache}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="card tile">
      <span className="tile-value">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}

function Breakdown({ title, total, rows }: { title: string; total: number; rows: { label: string; count: number }[] }) {
  const sorted = [...rows].sort((a, b) => b.count - a.count);
  return (
    <section className="card breakdown" aria-label={title}>
      <h2>{title}</h2>
      {sorted.length === 0 ? (
        <p className="muted">No complaints yet.</p>
      ) : (
        <ul>
          {sorted.map((row) => {
            const share = total > 0 ? Math.round((row.count / total) * 100) : 0;
            return (
              <li key={row.label}>
                <span className="bar-label">{humanize(row.label)}</span>
                <span className="bar" aria-hidden="true">
                  <span style={{ width: `${share}%` }} />
                </span>
                <span className="bar-count">{row.count}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** The triage observability surface: GET /api/meta/providers. */
function ProvidersPanel() {
  const [providers, setProviders] = useState<Providers | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getProviders()
      .then((data) => active && setProviders(data))
      .catch((caught: unknown) => active && setError(caught instanceof ApiError ? caught.message : String(caught)));
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="card providers" aria-label="Triage provider">
      <h2>AI triage</h2>
      {error && <p className="alert inline">{error}</p>}
      {!providers && !error && <p className="muted">Loading...</p>}
      {providers && (
        <>
          <p>
            Active provider: <strong>{providers.active_provider}</strong>
            {" · "}AI cache hit rate:{" "}
            <strong>
              {providers.cache.hit_rate === null ? "no lookups yet" : `${Math.round(providers.cache.hit_rate * 100)}%`}
            </strong>{" "}
            <span className="muted">
              ({providers.cache.hits} hits, {providers.cache.misses} misses)
            </span>
          </p>
          {providers.recent_outcomes.length > 0 && (
            <div className="table-wrap">
              <table>
                <caption className="muted">Last {providers.recent_outcomes.length} triage outcomes</caption>
                <thead>
                  <tr>
                    <th scope="col">When</th>
                    <th scope="col">Provider</th>
                    <th scope="col">Latency</th>
                    <th scope="col">Fallback</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.recent_outcomes.map((outcome) => (
                    <tr key={outcome.complaint_id}>
                      <td>{formatDate(outcome.created_at)}</td>
                      <td>{outcome.provider}</td>
                      <td>{formatMs(outcome.latency_ms)}</td>
                      <td>{outcome.fallback ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
