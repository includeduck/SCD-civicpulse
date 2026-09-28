import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DashboardPage } from "../src/pages/DashboardPage";
import { call, complaint, jsonResponse, mockFetch, page, renderAt } from "./helpers";

const CONFLICT = "Cannot transition complaint from 'resolved' to 'in_progress'.";

describe("Dashboard", () => {
  it("offers exactly the transitions the server allows for each complaint", async () => {
    mockFetch().mockResolvedValueOnce(
      jsonResponse(
        page([
          complaint({ id: "a", location: "G-9", allowed_transitions: ["in_progress", "rejected"] }),
          complaint({ id: "b", location: "I-8", status: "resolved", allowed_transitions: [] }),
        ]),
      ),
    );
    renderAt(<DashboardPage />, "/dashboard");

    const open = await screen.findByRole("group", { name: /complaint at G-9/ });
    expect(within(open).getAllByRole("button").map((b) => b.textContent)).toEqual(["Mark in progress", "Mark rejected"]);
    const resolved = screen.getByRole("group", { name: /complaint at I-8/ });
    expect(within(resolved).queryAllByRole("button")).toHaveLength(0);
    expect(within(resolved).getByText("No further status changes.")).toBeInTheDocument();
  });

  it("shows the server's 409 message verbatim, then refreshes the stale list", async () => {
    const fetchMock = mockFetch();
    const stale = complaint({ id: "a", location: "G-9", status: "open", allowed_transitions: ["in_progress"] });
    fetchMock
      .mockResolvedValueOnce(jsonResponse(page([stale])))
      .mockResolvedValueOnce(jsonResponse({ detail: CONFLICT, code: "invalid_transition" }, { status: 409 }))
      .mockResolvedValueOnce(jsonResponse(page([{ ...stale, status: "resolved", allowed_transitions: [] }])));
    const user = userEvent.setup();
    renderAt(<DashboardPage />, "/dashboard");

    await user.click(await screen.findByRole("button", { name: "Mark in progress" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(CONFLICT);
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument();
    expect(call(fetchMock, 1)).toMatchObject({ url: "/api/complaints/a/status", method: "PATCH", body: { status: "in_progress" } });
    await waitFor(() => expect(screen.getByText("No further status changes.")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent(CONFLICT); // still visible after the refresh
  });

  it("updates the row from the server's answer after a successful transition", async () => {
    const fetchMock = mockFetch();
    const before = complaint({ id: "a", allowed_transitions: ["in_progress", "rejected"] });
    fetchMock
      .mockResolvedValueOnce(jsonResponse(page([before])))
      .mockResolvedValueOnce(jsonResponse({ ...before, status: "in_progress", allowed_transitions: ["resolved", "rejected"] }));
    const user = userEvent.setup();
    renderAt(<DashboardPage />, "/dashboard");

    await user.click(await screen.findByRole("button", { name: "Mark in progress" }));

    expect(await screen.findByRole("button", { name: "Mark resolved" })).toBeInTheDocument();
    expect(within(screen.getByRole("listitem")).getByText("In progress")).toBeInTheDocument();
  });

  it("sends filters to the server and goes back to page 1 when they change", async () => {
    const fetchMock = mockFetch();
    fetchMock.mockImplementation(async (input) => {
      const current = Number(new URL(String(input), "http://x").searchParams.get("page"));
      return jsonResponse(page([complaint()], { total: 45, page: current, total_pages: 3 }));
    });
    const user = userEvent.setup();
    renderAt(<DashboardPage />, "/dashboard?page=2");

    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
    expect(call(fetchMock, 0).url).toBe("/api/complaints?page=2&page_size=20");

    await user.selectOptions(screen.getByLabelText("Category"), "water");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(call(fetchMock, 1).url).toBe("/api/complaints?category=water&page=1&page_size=20");

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(call(fetchMock, 2).url).toBe("/api/complaints?category=water&page=2&page_size=20");
  });

  it("shows the reason when the list cannot load, with a retry", async () => {
    const fetchMock = mockFetch();
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(page([])));
    const user = userEvent.setup();
    renderAt(<DashboardPage />, "/dashboard");

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach CivicPulse right now");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No complaints match these filters.")).toBeInTheDocument();
  });

  it("renders AI summary label as 'AI summary of the report:'", async () => {
    mockFetch().mockResolvedValueOnce(
      jsonResponse(page([complaint({ ai_summary: "Flooded street" })])),
    );
    renderAt(<DashboardPage />, "/dashboard");

    expect(await screen.findByText("AI summary of the report:")).toBeInTheDocument();
    expect(screen.getByText("Flooded street")).toBeInTheDocument();
  });

  it("allows operators to correct triage category and priority", async () => {
    const fetchMock = mockFetch();
    const initial = complaint({
      id: "comp-1",
      category: "water",
      priority: "high",
      triage_corrected_at: null,
    });
    const corrected = {
      ...initial,
      category: "roads" as const,
      priority: "low" as const,
      triage_corrected_at: "2026-09-28T12:00:00Z",
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(page([initial])))
      .mockResolvedValueOnce(jsonResponse(corrected));

    const user = userEvent.setup();
    renderAt(<DashboardPage />, "/dashboard");

    expect(await screen.findByText("Water")).toBeInTheDocument();
    expect(screen.queryByText("(triage corrected)")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Correct category"), "roads");
    await user.selectOptions(screen.getByLabelText("Correct priority"), "low");
    await user.click(screen.getByRole("button", { name: "Save triage" }));

    expect(call(fetchMock, 1)).toMatchObject({
      url: "/api/complaints/comp-1/triage",
      method: "PATCH",
      body: { category: "roads", priority: "low" },
    });

    expect(await screen.findByText("(triage corrected)")).toBeInTheDocument();
    expect(within(screen.getByRole("listitem")).getByText("Roads", { selector: ".badge" })).toBeInTheDocument();
    expect(within(screen.getByRole("listitem")).getByText("Low", { selector: ".badge" })).toBeInTheDocument();
  });

  it("displays server error verbatim when triage correction fails", async () => {
    const fetchMock = mockFetch();
    const initial = complaint({ id: "comp-2" });
    const ERROR_DETAIL = "At least one of category or priority must be provided.";
    fetchMock
      .mockResolvedValueOnce(jsonResponse(page([initial])))
      .mockResolvedValueOnce(
        jsonResponse({ detail: ERROR_DETAIL, code: "empty_triage_correction" }, { status: 400 }),
      );

    const user = userEvent.setup();
    renderAt(<DashboardPage />, "/dashboard");

    await screen.findByRole("button", { name: "Save triage" });
    await user.click(screen.getByRole("button", { name: "Save triage" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(ERROR_DETAIL);
  });
});
