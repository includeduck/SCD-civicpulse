import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Providers, Stats } from "../src/api/types";
import { StatsPage } from "../src/pages/StatsPage";
import { jsonResponse, mockFetch, renderAt } from "./helpers";

const STATS: Stats = {
  total_complaints: 12,
  by_category: [
    { category: "water", count: 7 },
    { category: "roads", count: 5 },
  ],
  by_priority: [
    { priority: "high", count: 4 },
    { priority: "normal", count: 8 },
  ],
  open_count: 6,
  in_progress_count: 3,
  resolved_count: 2,
  rejected_count: 1,
};

const PROVIDERS: Providers = {
  active_provider: "ollama",
  providers: [],
  recent_outcomes: [],
  cache: { hits: 3, misses: 1, hit_rate: 0.75 },
};

/** Stats and provider requests can arrive in either order; answer by URL. */
function server(xCache: string[]) {
  const fetchMock = mockFetch();
  const answers = [...xCache];
  fetchMock.mockImplementation(async (input) => {
    if (String(input) === "/api/meta/providers") return jsonResponse(PROVIDERS);
    return jsonResponse(STATS, { headers: { "X-Cache": answers.shift() ?? "HIT" } });
  });
  return fetchMock;
}

describe("Stats page", () => {
  it("renders the aggregates by category and priority", async () => {
    server(["MISS"]);
    renderAt(<StatsPage />, "/stats");

    const byCategory = await screen.findByRole("region", { name: "By category" });
    expect(within(byCategory).getByText("Water")).toBeInTheDocument();
    expect(within(byCategory).getByText("7")).toBeInTheDocument();
    const byPriority = screen.getByRole("region", { name: "By priority" });
    expect(within(byPriority).getByText("8")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Totals" })).getByText("12")).toBeInTheDocument();
  });

  it("shows whether Redis served the numbers, from the X-Cache header", async () => {
    server(["MISS", "HIT"]);
    const user = userEvent.setup();
    renderAt(<StatsPage />, "/stats");

    const banner = await screen.findByRole("region", { name: "Cache status" });
    expect(banner).toHaveTextContent("X-Cache: MISS");
    expect(banner).toHaveTextContent("Computed from PostgreSQL");

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByText("X-Cache: HIT")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Cache status" })).toHaveTextContent("Served from the Redis cache");
    expect(screen.getByRole("list", { name: /Recent loads/ })).toHaveTextContent("HITMISS");
  });

  it("shows the active triage provider and AI cache hit rate", async () => {
    server(["HIT"]);
    renderAt(<StatsPage />, "/stats");

    const panel = await screen.findByRole("region", { name: "Triage provider" });
    expect(await within(panel).findByText("ollama")).toBeInTheDocument();
    expect(panel).toHaveTextContent("75%");
  });

  it("keeps the last numbers on screen and shows the server's reason when a refresh fails", async () => {
    const fetchMock = mockFetch();
    let statsCalls = 0;
    fetchMock.mockImplementation(async (input) => {
      if (String(input) === "/api/meta/providers") return jsonResponse(PROVIDERS);
      statsCalls += 1;
      if (statsCalls === 1) return jsonResponse(STATS, { headers: { "X-Cache": "MISS" } });
      return jsonResponse({ detail: "Database unavailable", code: "internal_error" }, { status: 503 });
    });
    const user = userEvent.setup();
    renderAt(<StatsPage />, "/stats");

    await screen.findByRole("region", { name: "By category" });
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not load statistics");
    expect(alert).toHaveTextContent("Database unavailable");
    expect(within(screen.getByRole("region", { name: "Totals" })).getByText("12")).toBeInTheDocument();
  });
});
