import { describe, expect, it } from "vitest";
import { LIMITS } from "../src/api/contract";
import { validate } from "../src/validation";

const ok = { text: "x".repeat(LIMITS.text.min), location: "x".repeat(LIMITS.location.min), reporter_contact: "" };

describe("Client-side validation mirrors the server's inclusive limits", () => {
  it("accepts values exactly at the minimum and maximum lengths", () => {
    expect(validate(ok)).toEqual({});
    expect(
      validate({
        text: "x".repeat(LIMITS.text.max),
        location: "x".repeat(LIMITS.location.max),
        reporter_contact: "x".repeat(LIMITS.contact.max),
      }),
    ).toEqual({});
  });

  it("rejects one character past each limit, naming the limit", () => {
    const errors = validate({
      text: "x".repeat(LIMITS.text.max + 1),
      location: "x".repeat(LIMITS.location.max + 1),
      reporter_contact: "x".repeat(LIMITS.contact.max + 1),
    });
    expect(errors.text).toBe(`Please keep it to at most ${LIMITS.text.max} characters.`);
    expect(errors.location).toContain(String(LIMITS.location.max));
    expect(errors.reporter_contact).toContain(String(LIMITS.contact.max));
  });

  it("measures trimmed text, so padding with spaces can't pass the minimum", () => {
    const errors = validate({ ...ok, text: `  ${"x".repeat(LIMITS.text.min - 1)}          ` });
    expect(errors.text).toMatch(/at least/);
  });
});
