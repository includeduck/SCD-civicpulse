import { LIMITS } from "./api/contract";

export type Field = "text" | "location" | "reporter_contact";
export type Values = Record<Field, string>;
export type FieldErrors = Partial<Record<Field, string>>;

/**
 * Mirrors the server's limits (read from its OpenAPI schema) so people get
 * instant feedback. The server still validates everything; its 400 errors
 * are shown against the same fields.
 */
export function validate(values: Values): FieldErrors {
  const errors: FieldErrors = {};
  const text = values.text.trim();
  const location = values.location.trim();
  if (text.length < LIMITS.text.min) errors.text = `Please describe the problem in at least ${LIMITS.text.min} characters.`;
  else if (text.length > LIMITS.text.max) errors.text = `Please keep it under ${LIMITS.text.max} characters.`;
  if (location.length < LIMITS.location.min)
    errors.location = `Please give a location of at least ${LIMITS.location.min} characters.`;
  else if (location.length > LIMITS.location.max)
    errors.location = `Please keep the location under ${LIMITS.location.max} characters.`;
  if (values.reporter_contact.trim().length > LIMITS.contact.max)
    errors.reporter_contact = `Please keep contact details under ${LIMITS.contact.max} characters.`;
  return errors;
}
