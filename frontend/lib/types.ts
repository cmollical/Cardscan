export type Condition = "NM" | "LP" | "MP" | "HP" | "DMG";
export type Fields = {
  game: "pokemon";
  product_id: number | null;
  name: string;
  set_name: string;
  number: string;
  language: string;
  edition: "standard" | "unlimited" | "first edition" | "shadowless" | null;
  finish: "holo" | "non-holo" | "reverse holo" | null;
  rarity: string | null;
  condition: Condition | null;
  graded: false;
  notes: string;
};
export type Price = {
  status: string;
  market_price: string | null;
  currency?: string;
  source?: string;
  source_updated_at?: string;
  retrieved_at?: string;
  warnings?: string[];
  provider_sku_id?: string;
  identity_key?: string;
  generic_references?: Array<{
    market_price: string | null;
    subtype: string | null;
    source_url: string;
  }>;
  candidates?: unknown[];
  required_fields?: Array<"language" | "finish">;
  available_languages?: string[];
  available_finishes?: Array<"holo" | "non-holo" | "reverse holo">;
};
export type Draft = {
  id: string;
  session_id: string;
  revision: number;
  fields: Fields;
  front?: Blob;
  back?: Blob;
  front_id?: string | null;
  back_id?: string | null;
  front_name?: string;
  back_name?: string;
  pricing: Price | null;
  stage: "capture" | "identity" | "condition" | "pricing" | "listing";
  listing_price: string;
  quantity: number;
  item_name: string;
  description: string;
  listing_notes: string;
  sync_status: "local" | "syncing" | "synced" | "error";
  error?: string;
  saved?: boolean;
  listing_id?: string;
  listing_revision?: number;
  job_id?: string;
  updated_at: string;
};
export type Variant = {
  id: number;
  provider_sku_id: string;
  condition: string | null;
  language: string | null;
  edition: string | null;
  finish: string | null;
  graded: number | null;
  active: number;
  raw_variant_json: string;
};
export type Card = {
  id: number;
  name: string;
  set_name: string;
  collector_number: string | null;
  tcgplayer_product_id: string;
  metadata_json?: string;
  variants?: Variant[];
};
export type Inventory = {
  id: string;
  intake_id: string;
  revision: number;
  listing: Fields & {
    item_name: string;
    description: string;
    sku: string;
    listing_price: string;
    quantity: number;
    market_reference: Price | null;
    front_image_id: string;
    back_image_id: string;
    notes: string;
  };
  publication?: {
    status: "sending" | "published" | "failed";
    provider: string;
    external_listing_id?: string | null;
    created_at: string;
  } | null;
};
export const emptyFields: Fields = {
  game: "pokemon",
  product_id: null,
  name: "",
  set_name: "",
  number: "",
  language: "",
  edition: null,
  finish: null,
  rarity: null,
  condition: null,
  graded: false,
  notes: "",
};
