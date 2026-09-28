/** Display labels only. No decisions are made here. */
import type { TriagedBy } from "./api/types";

export function humanize(value: string): string {
  const words = value.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const PROVIDER_LABELS: Record<TriagedBy, string> = {
  "llm:groq": "AI model (Groq)",
  "llm:ollama": "AI model (Ollama)",
  rules: "Keyword rules",
  "rules:fallback": "Keyword rules (AI unavailable, fallback)",
  simulated: "Simulated AI (test mode)",
};

export function providerLabel(triagedBy: TriagedBy | null | undefined): string {
  if (!triagedBy) return "Not recorded";
  return PROVIDER_LABELS[triagedBy] ?? triagedBy;
}

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateFormat.format(date);
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "n/a";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}
