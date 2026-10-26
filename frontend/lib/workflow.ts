import type { Draft, Fields } from "./types";
export const identityKeys: (keyof Fields)[] = [
  "game",
  "product_id",
  "name",
  "set_name",
  "number",
  "language",
  "edition",
  "finish",
  "condition",
  "graded",
];
export function editFields(draft: Draft, changes: Partial<Fields>): Draft {
  const changed = identityKeys.some(
    (k) => k in changes && changes[k] !== draft.fields[k],
  );
  return {
    ...draft,
    fields: { ...draft.fields, ...changes },
    pricing: changed ? null : draft.pricing,
    sync_status: "local",
    error: undefined,
    updated_at: new Date().toISOString(),
  };
}
export function description(draft: Draft) {
  const f = draft.fields;
  return `${f.name} from ${f.set_name}, card ${f.number}. ${f.language}; ${f.edition || "edition unspecified"}; ${f.finish || "finish unspecified"}. Raw card, ${f.condition || "condition to confirm"}. Condition confirmed by the seller; photos show the actual card.`;
}
export function money(value: string | null | undefined) {
  return value == null
    ? "Price unavailable"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(Number(value));
}
