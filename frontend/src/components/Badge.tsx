import { humanize } from "../format";

type Kind = "category" | "priority" | "status";

/** A labelled pill; the value picks a colour via a data attribute in CSS. */
export function Badge({ kind, value }: { kind: Kind; value: string }) {
  return (
    <span className="badge" data-kind={kind} data-value={value}>
      {humanize(value)}
    </span>
  );
}
