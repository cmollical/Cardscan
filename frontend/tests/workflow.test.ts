import { describe, it, expect } from "vitest";
import {
  editFields,
  description,
  money,
  shouldAutoSelectPrinting,
} from "../lib/workflow";
import { emptyFields, type Draft } from "../lib/types";
const draft: Draft = {
  id: "synthetic",
  session_id: "synthetic",
  revision: 1,
  fields: {
    ...emptyFields,
    name: "Charizard",
    set_name: "base set",
    number: "4/102",
    condition: "LP",
    edition: "unlimited",
    finish: "holo",
    language: "english",
    product_id: 42382,
  },
  pricing: { status: "exact_match", market_price: "527.7" },
  stage: "pricing",
  listing_price: "500",
  quantity: 1,
  item_name: "",
  description: "",
  listing_notes: "",
  sync_status: "synced",
  updated_at: "",
};
describe("review integrity", () => {
  it.each([
    { condition: "MP" },
    { edition: "first edition" },
    { language: "japanese" },
    { finish: "reverse holo" },
    { product_id: 1 },
    { number: "4/130" },
  ])("invalidates price after identity or condition changes %s", (change) => {
    const r = editFields(draft, change as never);
    expect(r.pricing).toBeNull();
    expect(r.listing_price).toBe("500");
  });
  it("keeps a separate chosen selling price and retains a quote for notes-only edits", () => {
    const r = editFields(draft, { notes: "Visible edge wear" });
    expect(r.pricing?.market_price).toBe("527.7");
    expect(r.listing_price).toBe("500");
  });
  it("does not silently fill unknown condition or edition", () => {
    const r = editFields(draft, { edition: null, condition: null });
    expect(r.fields.edition).toBeNull();
    expect(r.fields.condition).toBeNull();
    expect(description(r)).toContain("edition unspecified");
  });
  it("uses deterministic listing text and missing-price labels", () => {
    expect(description(draft)).toContain("Raw card, LP");
    expect(money(null)).toBe("Price unavailable");
    expect(money("500")).toBe("$500.00");
  });
  it("prefills only one exact candidate into an untouched identity form", () => {
    const blank = {
      ...draft.fields,
      product_id: null,
      name: "",
      set_name: "",
      number: "",
    };
    expect(shouldAutoSelectPrinting(blank, 1)).toBe(true);
    expect(shouldAutoSelectPrinting(blank, 2)).toBe(false);
    expect(shouldAutoSelectPrinting(blank, 1, true)).toBe(false);
    expect(shouldAutoSelectPrinting({ ...blank, name: "Manual entry" }, 1)).toBe(
      false,
    );
    expect(shouldAutoSelectPrinting(draft.fields, 1)).toBe(false);
  });
});
