/**
 * Named aliases over the generated OpenAPI types (schema.d.ts).
 *
 * Every request and response type here is derived from the backend's own
 * OpenAPI document, so a backend contract change that the frontend has not
 * caught up with fails `tsc`, not a user.
 */
import type { components, paths } from "./schema";

type Schemas = components["schemas"];
type JsonOf<R> = R extends { content: { "application/json": infer Body } } ? Body : never;

export type Category = Schemas["Category"];
export type Priority = Schemas["Priority"];
export type Status = Schemas["Status"];
export type TriagedBy = Schemas["TriagedBy"];

type CreateOp = paths["/api/complaints"]["post"];
type ListOp = paths["/api/complaints"]["get"];
type StatusOp = paths["/api/complaints/{complaint_id}/status"]["patch"];
type TriageOp = paths["/api/complaints/{complaint_id}/triage"]["patch"];

export type ComplaintCreate = JsonOf<CreateOp["requestBody"]>;
export type Complaint = JsonOf<CreateOp["responses"][201]>;
export type ComplaintList = JsonOf<ListOp["responses"][200]>;
export type ComplaintFilters = NonNullable<ListOp["parameters"]["query"]>;
export type StatusUpdate = JsonOf<StatusOp["requestBody"]>;
export type TriageCorrection = JsonOf<TriageOp["requestBody"]>;
export type Stats = JsonOf<paths["/api/stats"]["get"]["responses"][200]>;
export type Providers = JsonOf<paths["/api/meta/providers"]["get"]["responses"][200]>;
