/**
 * Values read from the backend's OpenAPI document instead of being retyped
 * here: input limits for client-side validation, and enum values for filters.
 *
 * These are data the server publishes. Business rules (triage, which status
 * may follow which) are not here, and never will be: the server decides them
 * and the UI renders what it is told (e.g. `allowed_transitions`).
 */
import { components } from "../../openapi.json";
import type { Category, Priority, Status } from "./types";

const schemas = components.schemas;
const create = schemas.ComplaintCreate.properties;

export const LIMITS = {
  text: { min: create.text.minLength, max: create.text.maxLength },
  location: { min: create.location.minLength, max: create.location.maxLength },
  contact: { max: create.reporter_contact.anyOf[0]?.maxLength ?? 255 },
} as const;

export const CATEGORIES = schemas.Category.enum as Category[];
export const PRIORITIES = schemas.Priority.enum as Priority[];
export const STATUSES = schemas.Status.enum as Status[];
