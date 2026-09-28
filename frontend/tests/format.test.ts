import { describe, expect, it } from "vitest";
import { formatDate, formatMs, humanize, providerLabel } from "../src/format";

describe("format helpers", () => {
  it("humanizes snake_case into capitalized words", () => {
    expect(humanize("in_progress")).toBe("In progress");
    expect(humanize("open")).toBe("Open");
    expect(humanize("streetlights")).toBe("Streetlights");
  });

  it("formats provider labels with readable descriptions", () => {
    expect(providerLabel("llm:groq")).toBe("AI model (Groq)");
    expect(providerLabel("llm:ollama")).toBe("AI model (Ollama)");
    expect(providerLabel("rules")).toBe("Keyword rules");
    expect(providerLabel("rules:fallback")).toBe("Keyword rules (AI unavailable, fallback)");
    expect(providerLabel("simulated")).toBe("Simulated AI (test mode)");
    expect(providerLabel(null)).toBe("Not recorded");
    expect(providerLabel(undefined)).toBe("Not recorded");
  });

  it("formats latency in ms or seconds", () => {
    expect(formatMs(null)).toBe("n/a");
    expect(formatMs(undefined)).toBe("n/a");
    expect(formatMs(450)).toBe("450 ms");
    expect(formatMs(1500)).toBe("1.5 s");
  });

  it("handles valid and invalid ISO dates", () => {
    expect(formatDate("not-a-date")).toBe("not-a-date");
    expect(formatDate("2026-09-28T12:00:00Z")).toBeTruthy();
  });
});
