/** One error type for every failed API call, carrying the server's own words. */

export class ApiError extends Error {
  /** HTTP status; 0 when the server could not be reached at all. */
  readonly status: number;
  /** Machine-readable code from the body, e.g. "invalid_transition". */
  readonly code: string | null;
  /** Per-field messages from a 400, keyed by field name ("text", "location", ...). */
  readonly fieldErrors: Readonly<Record<string, string>>;
  /** Seconds from a 429's Retry-After header. */
  readonly retryAfter: number | null;

  constructor(
    status: number,
    message: string,
    options: { code?: string | null; fieldErrors?: Record<string, string>; retryAfter?: number | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = options.code ?? null;
    this.fieldErrors = options.fieldErrors ?? {};
    this.retryAfter = options.retryAfter ?? null;
  }
}

interface FieldIssue {
  loc?: unknown[];
  msg?: string;
}

function fieldErrorsFrom(issues: FieldIssue[]): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const issue of issues) {
    const field = issue.loc?.at(-1);
    if (typeof field === "string" && issue.msg && !(field in errors)) errors[field] = issue.msg;
  }
  return errors;
}

/**
 * Turn a non-2xx response into an ApiError.
 *
 * The backend's message is kept verbatim (a 409 names the attempted
 * transition, a 429 says when to retry). Only when the body isn't the
 * backend's JSON (a proxy's HTML 502, say) do we write our own message.
 */
export async function toApiError(response: Response): Promise<ApiError> {
  const header = response.headers.get("Retry-After");
  const retryAfter = header !== null && /^\d+$/.test(header) ? Number(header) : null;

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON: fall through to the generic message below.
  }

  if (body && typeof body === "object" && "detail" in body) {
    const { detail, code } = body as { detail: unknown; code?: unknown };
    const errorCode = typeof code === "string" ? code : null;
    if (typeof detail === "string") {
      return new ApiError(response.status, detail, { code: errorCode, retryAfter });
    }
    if (Array.isArray(detail)) {
      const fieldErrors = fieldErrorsFrom(detail as FieldIssue[]);
      return new ApiError(response.status, "Some fields need attention.", { code: errorCode, fieldErrors, retryAfter });
    }
  }
  const statusText = response.statusText ? ` ${response.statusText}` : "";
  return new ApiError(response.status, `The server returned ${response.status}${statusText}.`, { retryAfter });
}
