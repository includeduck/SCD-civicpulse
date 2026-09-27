import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SubmitPage } from "../src/pages/SubmitPage";
import { call, complaint, jsonResponse, mockFetch, renderAt } from "./helpers";

async function fillValid(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("What is the problem?"), "Pipe burst ho gaya hai, paani sarak par beh raha hai");
  await user.type(screen.getByLabelText("Where is it?"), "F-8 Markaz");
}

describe("Submit page", () => {
  it("blocks input that breaks the server's limits without calling the API", async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();
    renderAt(<SubmitPage />);

    await user.type(screen.getByLabelText("What is the problem?"), "too short");
    await user.type(screen.getByLabelText("Where is it?"), "F8");
    await user.click(screen.getByRole("button", { name: "Submit complaint" }));

    expect(await screen.findByText(/at least 10 characters/)).toBeInTheDocument();
    expect(screen.getByText(/location of at least 3 characters/)).toBeInTheDocument();
    expect(screen.getByLabelText("What is the problem?")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows an honest loading state and locks the form while triage runs", async () => {
    const fetchMock = mockFetch();
    let answer!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise<Response>((resolve) => (answer = resolve)));
    const user = userEvent.setup();
    renderAt(<SubmitPage />);

    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Submit complaint" }));

    expect(screen.getByRole("status")).toHaveTextContent(/Analyzing complaint/);
    expect(screen.getByRole("status")).toHaveTextContent(/keyword rules answer instead/);
    expect(screen.getByRole("button", { name: /Analyzing complaint/ })).toBeDisabled();
    expect(screen.getByLabelText("Where is it?")).toBeDisabled();

    answer(jsonResponse(complaint(), { status: 201 }));
    expect(await screen.findByRole("heading", { name: "Complaint received" })).toBeInTheDocument();
  });

  it("renders the category, priority, AI summary and provider the server returned", async () => {
    const fetchMock = mockFetch();
    fetchMock.mockResolvedValueOnce(jsonResponse(complaint(), { status: 201 }));
    const user = userEvent.setup();
    renderAt(<SubmitPage />);

    await fillValid(user);
    await user.type(screen.getByLabelText("Contact (optional)"), "  ");
    await user.click(screen.getByRole("button", { name: "Submit complaint" }));

    await screen.findByRole("heading", { name: "Complaint received" });
    expect(screen.getByText("Water")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Burst water pipe flooding the road in F-8 Markaz.")).toBeInTheDocument();
    expect(screen.getByText("AI model (Ollama)")).toBeInTheDocument();

    const request = call(fetchMock);
    expect(request).toMatchObject({ url: "/api/complaints", method: "POST" });
    expect(request.body).toEqual({
      text: "Pipe burst ho gaya hai, paani sarak par beh raha hai",
      location: "F-8 Markaz",
      reporter_contact: null,
    });
  });

  it("says so when the rules answered because the AI failed", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(complaint({ triaged_by: "rules:fallback" }), { status: 201 }));
    const user = userEvent.setup();
    renderAt(<SubmitPage />);

    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Submit complaint" }));

    expect(await screen.findByText("Keyword rules (AI unavailable, fallback)")).toBeInTheDocument();
    expect(screen.getByText(/AI could not answer in time/)).toBeInTheDocument();
  });

  it("shows the server's field errors from a 400 next to the right field", async () => {
    mockFetch().mockResolvedValueOnce(
      jsonResponse(
        {
          code: "validation_error",
          detail: [{ loc: ["body", "location"], msg: "String should have at least 3 characters", type: "string_too_short" }],
        },
        { status: 400 },
      ),
    );
    const user = userEvent.setup();
    renderAt(<SubmitPage />);

    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Submit complaint" }));

    expect(await screen.findByText("String should have at least 3 characters")).toBeInTheDocument();
    expect(screen.getByLabelText("Where is it?")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Where is it?")).toHaveValue("F-8 Markaz"); // nothing typed is lost
  });

  it("explains a 429 with the server's own message", async () => {
    mockFetch().mockResolvedValueOnce(
      jsonResponse(
        { detail: "Rate limit exceeded: at most 10 complaints per 60 s. Try again in 42 s.", code: "rate_limited" },
        { status: 429, headers: { "Retry-After": "42" } },
      ),
    );
    const user = userEvent.setup();
    renderAt(<SubmitPage />);

    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Submit complaint" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Too many submissions");
    expect(alert).toHaveTextContent("Rate limit exceeded: at most 10 complaints per 60 s. Try again in 42 s.");
    await waitFor(() => expect(screen.getByRole("button", { name: "Submit complaint" })).toBeEnabled());
  });
});
