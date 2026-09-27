import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, onTestFinished, vi } from "vitest";
import spec from "../openapi.json";
import { CATEGORIES, LIMITS, STATUSES } from "../src/api/contract";
import { toApiError } from "../src/api/errors";
import { App } from "../src/App";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { jsonResponse, renderAt } from "./helpers";

function Broken(): never {
  throw new Error("render exploded");
}

describe("Error boundary", () => {
  it("replaces a crashed view with a recovery screen", async () => {
    // React (dev build) and jsdom both report the thrown error; keep the test output clean.
    vi.spyOn(console, "error").mockImplementation(() => {});
    const silence = (event: ErrorEvent) => event.preventDefault();
    window.addEventListener("error", silence);
    onTestFinished(() => window.removeEventListener("error", silence));
    renderAt(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("heading", { name: "Something went wrong on this page" })).toBeInTheDocument();
    expect(screen.getByText("render exploded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload the app" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByRole("heading", { name: "Something went wrong on this page" })).toBeInTheDocument();
  });
});

describe("Routing", () => {
  it("renders each view at its path", () => {
    renderAt(<App />, "/nowhere");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });
});

describe("API contract", () => {
  it("takes validation limits and enum values from the backend's OpenAPI schema", () => {
    const create = spec.components.schemas.ComplaintCreate.properties;
    expect(LIMITS.text).toEqual({ min: create.text.minLength, max: create.text.maxLength });
    expect(LIMITS.location).toEqual({ min: 3, max: 200 });
    expect(CATEGORIES).toContain("streetlights");
    expect(STATUSES).toEqual(["open", "in_progress", "resolved", "rejected"]);
  });

  it("keeps the server's error message and falls back only for non-JSON bodies", async () => {
    const conflict = await toApiError(jsonResponse({ detail: "Cannot transition", code: "invalid_transition" }, { status: 409 }));
    expect([conflict.status, conflict.message, conflict.code]).toEqual([409, "Cannot transition", "invalid_transition"]);

    const gateway = await toApiError(new Response("<html>502</html>", { status: 502, statusText: "Bad Gateway" }));
    expect(gateway.message).toBe("The server returned 502 Bad Gateway.");
  });
});
