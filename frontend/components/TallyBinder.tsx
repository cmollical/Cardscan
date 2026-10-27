"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Camera,
  Check,
  CheckCircle2,
  ChevronRight,
  CloudUpload,
  Download,
  FolderOpen,
  Home,
  Layers,
  LoaderCircle,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Trash2,
  WifiOff,
  X,
} from "lucide-react";
import Photos, { Photo } from "./Photos";
import { allDrafts, putDraft } from "@/lib/drafts";
import { ApiError, request, upload, download } from "@/lib/api";
import { firebaseAuth } from "@/lib/firebase";
import { signOut as firebaseSignOut } from "@firebase/auth";
import { description, editFields, money } from "@/lib/workflow";
import {
  emptyFields,
  type Card,
  type Condition,
  type Draft,
  type Fields,
  type Inventory,
  type Price,
} from "@/lib/types";

type View =
  | "home"
  | "scan"
  | "review"
  | "identity"
  | "condition"
  | "pricing"
  | "listing"
  | "inventory"
  | "settings";
type Config = {
  auth_mode?: "firebase" | "session" | "bearer";
  ai_pause_reason?: string | null;
  authenticated?: boolean;
  ai_enabled: boolean;
  model: string | null;
  access_token_required: boolean;
  max_reservation_usd: string | null;
};
type ServerDraft = {
  id: string;
  session_id: string;
  revision: number;
  fields: Fields;
  front_id: string | null;
  back_id: string | null;
  pricing: Price | null;
  updated_at: string;
  saved?: boolean;
  listing_id?: string;
  listing_revision?: number;
};
type Job = {
  id: string;
  status: string;
  error?: string;
  stale_for_intake?: boolean;
  kind: string;
  estimated_cost_usd?: string;
  intake_estimated_cost_usd?: string;
  intake_cost_complete?: boolean;
  intake_unknown_reserve_usd?: string;
  result?: {
    recommended_condition?: Condition | null;
    observations: string[];
    limitations: string[];
    catalog_candidates?: Array<{
      claim: Partial<Fields>;
      card: Card;
      match: string;
      issues: string[];
    }>;
  };
};
const conditions: Condition[] = ["NM", "LP", "MP", "HP", "DMG"];
const labels: Record<Condition, string> = {
  NM: "Near Mint",
  LP: "Lightly Played",
  MP: "Moderately Played",
  HP: "Heavily Played",
  DMG: "Damaged",
};
function fresh(session_id: string): Draft {
  return {
    id: crypto.randomUUID(),
    session_id,
    revision: 0,
    fields: { ...emptyFields },
    pricing: null,
    stage: "capture",
    listing_price: "",
    quantity: 1,
    item_name: "",
    description: "",
    listing_notes: "",
    sync_status: "local",
    updated_at: new Date().toISOString(),
  };
}
function serverDraft(r: ServerDraft): Draft {
  return {
    ...fresh(r.session_id),
    ...r,
    stage: r.fields.condition ? "pricing" : "identity",
    sync_status: "synced",
  };
}
function sameIdentity(a: Fields, b: Fields) {
  return JSON.stringify(a) === JSON.stringify(b);
}
const message = (e: unknown) =>
  e instanceof Error ? e.message : "Something went wrong. Please try again.";

export default function TallyBinder() {
  const [view, setView] = useState<View>("home");
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const ref = useRef<Draft[]>([]);
  const [capture, setCapture] = useState<Draft | null>(null);
  const [selected, setSelected] = useState("");
  const [session, setSession] = useState("");
  const [ready, setReady] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [online, setOnline] = useState(true);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<Record<string, string>>({});
  const locks = useRef(new Set<string>());
  const [inventory, setInventory] = useState<Inventory[]>([]);
  const [inventoryTotal, setInventoryTotal] = useState(0);
  const [inventoryQuery, setInventoryQuery] = useState("");
  const [inventoryCondition, setInventoryCondition] = useState("");
  const [search, setSearch] = useState("");
  const [searchSet, setSearchSet] = useState("");
  const [searchNumber, setSearchNumber] = useState("");
  const [results, setResults] = useState<Card[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [accessToken, setAccessToken] = useState("");
  const current = drafts.find((d) => d.id === selected);
  const pending = drafts.filter((d) => !d.saved && d.stage !== "capture");
  const syncing = drafts.filter((d) => d.sync_status === "syncing").length;
  const go = useCallback((next: View) => {
    setView(next);
    window.scrollTo({ top: 0 });
  }, []);
  const remember = useCallback(async (d: Draft) => {
    await putDraft(d);
    ref.current = [d, ...ref.current.filter((x) => x.id !== d.id)];
    setDrafts(ref.current);
    return d;
  }, []);
  const latest = (id: string) => ref.current.find((d) => d.id === id);
  const setWorking = (id: string, text: string) =>
    setBusy((b) => ({ ...b, [id]: text }));
  async function loadInventory(offset = 0) {
    try {
      const data = await request<{ items: Inventory[]; total: number }>(
        "/inventory?" +
          new URLSearchParams({
            q: inventoryQuery,
            condition: inventoryCondition,
            limit: "50",
            offset: String(offset),
          })
            .toString()
            .replace(/condition=&?/, ""),
      );
      setInventory((items) =>
        offset ? [...items, ...data.items] : data.items,
      );
      setInventoryTotal(data.total);
    } catch (e) {
      setNotice(message(e));
    }
  }
  useEffect(() => {
    let alive = true;
    const init = async () => {
      try {
        const saved = await allDrafts();
        if (!alive) return;
        ref.current = saved;
        setDrafts(saved);
        let id = localStorage.getItem("tallybinder.session");
        if (!id) {
          id = crypto.randomUUID();
          localStorage.setItem("tallybinder.session", id);
        }
        setSession(id);
        const unsent = localStorage.getItem("tallybinder.capture");
        const draft =
          saved.find((d) => d.id === unsent && d.stage === "capture") ||
          saved.find((d) => d.stage === "capture");
        setCapture(draft || fresh(id));
        setAccessToken(localStorage.getItem("tallybinder.accessToken") || "");
        setReady(true);
        const cfg = await request<Config>("/app/config");
        if (alive) setConfig(cfg);
        if (cfg.auth_mode === "session" || cfg.auth_mode === "firebase") {
          localStorage.removeItem("tallybinder.accessToken");
          setAccessToken("");
          if (!cfg.authenticated) {
            setNotice(
              "Sign in to connect your cloud binder.",
            );
            go("settings");
            return;
          }
        }
        const remote = await request<{ items: ServerDraft[]; total: number }>(
          "/intake?limit=100",
        );
        while (remote.items.length < remote.total) {
          const page = await request<{ items: ServerDraft[] }>(
            "/intake?limit=100&offset=" + remote.items.length,
          );
          if (!page.items.length) break;
          remote.items.push(...page.items);
        }
        const remoteInventory = await request<{
          items: Inventory[];
          total: number;
        }>("/inventory?limit=100");
        if (!alive) return;
        setInventory(remoteInventory.items);
        setInventoryTotal(remoteInventory.total);
        for (const r of remote.items) {
          if (!ref.current.some((x) => x.id === r.id))
            await remember(serverDraft(r));
        }
        for (const item of remoteInventory.items) {
          const d = latest(item.intake_id);
          if (d && !d.saved)
            await remember({
              ...d,
              saved: true,
              listing_id: item.id,
              listing_revision: item.revision,
            });
        }
      } catch (e) {
        if (alive) {
          setReady(true);
          setNotice(
            "Backend unavailable or access token required. Your local drafts are safe. " +
              message(e),
          );
        }
      }
    };
    void init();
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    if ("serviceWorker" in navigator)
      void navigator.serviceWorker.register("/sw.js").catch(() => {});
    return () => {
      alive = false;
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, [remember]);
  useEffect(() => {
    if (view === "inventory")
      void loadInventory(); /* query is deliberately sent only on input debounce */
  }, [view]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (view !== "inventory") return;
    const timer = setTimeout(() => void loadInventory(), 250);
    return () => clearTimeout(timer);
  }, [inventoryQuery, inventoryCondition]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!current?.job_id) {
      setJob(null);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await request<Job>("/jobs/" + current.job_id);
        if (!alive) return;
        setJob(data);
        if (data.status === "queued" || data.status === "running")
          timer = setTimeout(() => void poll(), 1500);
      } catch (e) {
        if (alive) setNotice(message(e));
      }
    };
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [current?.job_id, current?.revision]);
  async function photo(side: "front" | "back", blob: Blob) {
    if (!capture) return;
    const next = {
      ...capture,
      [side]: blob,
      [side + "_id"]: null,
      [side + "_name"]: crypto.randomUUID(),
      pricing: null,
      fields: { ...capture.fields, condition: null },
      saved: false,
      updated_at: new Date().toISOString(),
    };
    await putDraft(next);
    localStorage.setItem("tallybinder.capture", next.id);
    setCapture(next);
  }
  async function sync(d: Draft): Promise<Draft> {
    if (locks.current.has(d.id))
      throw new Error(
        "This card is syncing. Wait a moment, then confirm again.",
      );
    locks.current.add(d.id);
    setWorking(d.id, "Saving draft…");
    try {
      await request("/intake/sessions", {
        method: "POST",
        body: JSON.stringify({ id: d.session_id, name: "Card intake" }),
      });
      let front_id = d.front_id,
        back_id = d.back_id;
      if (!front_id && d.front) front_id = (await upload(d.front)).id;
      if (!back_id && d.back) back_id = (await upload(d.back)).id;
      const persist = (revision: number) =>
        request<ServerDraft>("/intake/" + d.id, {
          method: "PUT",
          body: JSON.stringify({
            session_id: d.session_id,
            expected_revision: revision,
            fields: d.fields,
            front_id: front_id || null,
            back_id: back_id || null,
          }),
        });
      let saved: ServerDraft;
      try {
        saved = await persist(d.revision);
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 409) throw e;
        const remote = await request<ServerDraft>("/intake/" + d.id);
        if (
          sameIdentity(remote.fields, d.fields) &&
          remote.front_id === front_id &&
          remote.back_id === back_id
        )
          saved = remote;
        else if (
          d.revision === 0 &&
          !remote.fields.product_id &&
          !remote.fields.name &&
          !remote.fields.number &&
          !remote.fields.condition &&
          remote.front_id === front_id &&
          remote.back_id === back_id
        )
          saved = await persist(remote.revision);
        else {
          await remember({
            ...latest(d.id)!,
            revision: remote.revision,
            pricing: null,
          });
          throw new Error(
            "A newer server draft exists. Review your local details before confirming again.",
          );
        }
      }
      const now = latest(d.id) || d;
      const changed =
        !sameIdentity(now.fields, d.fields) ||
        now.front_name !== d.front_name ||
        now.back_name !== d.back_name;
      const next = {
        ...now,
        revision: saved.revision,
        front_id:
          changed && now.front_name !== d.front_name ? now.front_id : front_id,
        back_id:
          changed && now.back_name !== d.back_name ? now.back_id : back_id,
        pricing: changed ? null : saved.pricing,
        sync_status: changed ? ("local" as const) : ("synced" as const),
        error: undefined,
      };
      await remember(next);
      if (changed)
        throw new Error(
          "The draft changed while saving. Confirm the latest details again.",
        );
      return next;
    } catch (e) {
      const now = latest(d.id) || d;
      await remember({ ...now, sync_status: "error", error: message(e) });
      throw e;
    } finally {
      locks.current.delete(d.id);
      setWorking(d.id, "");
    }
  }
  async function queueCard() {
    if (!capture?.front || !capture?.back) return;
    setNotice("");
    try {
      const next = { ...capture, stage: "identity" as const };
      await remember(next);
      localStorage.removeItem("tallybinder.capture");
      setCapture(fresh(session));
      setNotice("Card added to review. You can capture the next one.");
      void sync(next).catch(() => {});
    } catch (e) {
      setNotice("Could not save this card locally. " + message(e));
    }
  }
  async function edit(changes: Partial<Fields>) {
    if (!current) return;
    const d = editFields(latest(current.id) || current, changes);
    await remember(d);
  }
  async function pick(card: Card) {
    if (!current) return;
    setWorking(current.id, "Loading printing…");
    try {
      const full = await request<Card>("/cards/" + card.id);
      const variants = full.variants || [];
      const unambiguous = (key: "language" | "edition" | "finish") => {
        const values = new Set(variants.map((v) => v[key]));
        return values.size === 1 ? [...values][0] : null;
      };
      const d = editFields(latest(current.id) || current, {
        product_id: Number(full.tcgplayer_product_id),
        name: full.name,
        set_name: full.set_name,
        number: full.collector_number || "",
        language: unambiguous("language") || "",
        edition: unambiguous("edition") as Fields["edition"],
        finish: unambiguous("finish") as Fields["finish"],
        rarity: full.metadata_json
          ? JSON.parse(full.metadata_json).rarity || null
          : null,
      });
      await remember(d);
      setResults([]);
      setSearch("");
    } catch (e) {
      setNotice(message(e));
    } finally {
      setWorking(current.id, "");
    }
  }
  async function find() {
    setSearching(true);
    setSearchError("");
    try {
      const q = new URLSearchParams({ q: search, limit: "25" });
      if (searchSet) q.set("set_name", searchSet);
      if (searchNumber) q.set("number", searchNumber);
      const data = await request<{ items: Card[] }>("/cards/search?" + q);
      setResults(data.items);
      if (!data.items.length)
        setSearchError(
          "No catalog match. Try the name, or use the exact set and full collector number.",
        );
    } catch (e) {
      setSearchError(message(e));
    } finally {
      setSearching(false);
    }
  }
  async function confirmIdentity() {
    if (!current) return;
    try {
      const d = await sync(current);
      await remember({ ...d, stage: "condition" });
      go("condition");
    } catch (e) {
      setNotice(message(e));
    }
  }
  async function price() {
    if (!current) return;
    setNotice("");
    try {
      const d = await sync(current);
      await remember({ ...d, stage: "pricing", pricing: null });
      go("pricing");
      setWorking(d.id, "Looking up exact SKU…");
      const result = await request<Price>(
        "/intake/" + d.id + "/price?revision=" + d.revision,
        { method: "POST" },
      );
      const now = latest(d.id);
      if (now && sameIdentity(now.fields, d.fields))
        await remember({ ...now, pricing: result });
    } catch (e) {
      setNotice(message(e));
    } finally {
      if (current) setWorking(current.id, "");
    }
  }
  async function startJob(kind: "identify" | "condition") {
    if (!current) return;
    if (
      !window.confirm(
        `Use paid AI for this card? The server reserves up to $${config?.max_reservation_usd || "0.50"} per request. Results still need your review.`,
      )
    )
      return;
    try {
      const d = await sync(current);
      setWorking(d.id, "Starting photo research…");
      const record = await request<Job>("/intake/" + d.id + "/jobs", {
        method: "POST",
        body: JSON.stringify({
          kind,
          authorize_paid: true,
          expected_revision: d.revision,
        }),
      });
      await remember({ ...latest(d.id)!, job_id: record.id });
      setJob(record);
    } catch (e) {
      setNotice(message(e));
    } finally {
      setWorking(current.id, "");
    }
  }
  async function listing() {
    if (!current) return;
    await remember({
      ...current,
      stage: "listing",
      item_name:
        current.item_name ||
        `${current.fields.name} · ${current.fields.number} · ${current.fields.condition}`,
      description: current.description || description(current),
    });
    go("listing");
  }
  async function save() {
    if (!current) return;
    setWorking(current.id, "Saving listing…");
    setNotice("");
    try {
      const d = await sync(current);
      const body = {
        intake_id: d.id,
        intake_revision: d.revision,
        expected_revision: d.listing_revision || null,
        item_name: d.item_name,
        description: d.description,
        listing_price: d.listing_price,
        quantity: d.quantity,
        notes: d.listing_notes,
        approved: true,
      };
      const saved = await request<Inventory>(
        d.listing_id ? "/inventory/" + d.listing_id : "/inventory",
        { method: d.listing_id ? "PUT" : "POST", body: JSON.stringify(body) },
      );
      await remember({
        ...latest(d.id)!,
        saved: true,
        listing_id: saved.id,
        listing_revision: saved.revision,
      });
      setNotice("Saved to inventory. Ready for the next card.");
      go("review");
      await loadInventory();
    } catch (e) {
      setNotice(message(e));
    } finally {
      setWorking(current.id, "");
    }
  }
  async function openInventory(item: Inventory) {
    try {
      const r = await request<ServerDraft>("/intake/" + item.intake_id);
      const d = {
        ...(latest(r.id) || serverDraft(r)),
        ...r,
        stage: "listing" as const,
        listing_id: item.id,
        listing_revision: item.revision,
        item_name: item.listing.item_name,
        description: item.listing.description,
        listing_price: item.listing.listing_price,
        quantity: item.listing.quantity,
        listing_notes: item.listing.notes,
        saved: true,
      };
      await remember(d);
      setSelected(d.id);
      go("listing");
    } catch (e) {
      setNotice(message(e));
    }
  }
  async function deleteListing(item: Inventory) {
    if (
      !window.confirm(
        "Delete this listing? Its intake, photos and audit remain on your personal server.",
      )
    )
      return;
    try {
      await request("/inventory/" + item.id + "?confirm=true", {
        method: "DELETE",
      });
      await loadInventory();
      setNotice("Listing removed from inventory.");
    } catch (e) {
      setNotice(message(e));
    }
  }
  async function exportCsv() {
    try {
      const blob = await download("/inventory/export.csv");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "TallyBinder-inventory.csv";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setNotice(message(e));
    }
  }
  function review(d: Draft) {
    if (d.stage === "capture") {
      setCapture(d);
      go("scan");
      return;
    }
    setSelected(d.id);
    go(d.stage);
    setNotice("");
  }
  const step = (stage: Exclude<Draft["stage"], "capture">) => {
    if (current) go(stage);
  };
  const field = (
    label: string,
    key: keyof Fields,
    options?: { value: string; label: string }[],
  ) => (
    <label className="field" key={key}>
      <span>{label}</span>
      {options ? (
        <select
          aria-label={label}
          value={String(current?.fields[key] ?? "")}
          onChange={(e) => void edit({ [key]: e.target.value || null })}
        >
          <option value="">Unspecified</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          aria-label={label}
          value={String(current?.fields[key] ?? "")}
          onChange={(e) =>
            void edit({
              [key]: e.target.value,
              ...(["name", "set_name", "number"].includes(key)
                ? { product_id: null }
                : {}),
            })
          }
        />
      )}
    </label>
  );
  const title: Record<View, string> = {
    home: "Your collection, in order.",
    scan: "One card at a time.",
    review: "Ready for a closer look.",
    identity: "Find the right printing.",
    condition: "Give it a closer look.",
    pricing: "A price with context.",
    listing: current?.listing_id
      ? "Edit your listing."
      : "Ready for your binder.",
    inventory: "The collection.",
    settings: "Make it yours.",
  };
  return (
    <div className="app-shell">
      <header className="app-header">
        <button
          className="brand"
          onClick={() => go("home")}
          aria-label="TallyBinder home"
        >
          <span className="brand-mark">
            <Layers size={20} />
          </span>
          TallyBinder<span className="beta">EARLY EDITION</span>
        </button>
        <button
          className="icon-button"
          aria-label="Settings"
          onClick={() => go("settings")}
        >
          <Settings size={21} />
        </button>
      </header>
      <main>
        {!online && (
          <div className="notice">
            <WifiOff size={17} /> Offline · drafts stay on this device. Sync and
            pricing need a connection.
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            <span>{notice}</span>
            <button aria-label="Dismiss message" onClick={() => setNotice("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {!ready ? (
          <div className="empty">
            <LoaderCircle className="spin" />
            <p>Opening your binder…</p>
          </div>
        ) : (
          <>
            <div className="page-heading">
              {!["home", "scan", "review", "inventory"].includes(view) && (
                <button
                  className="back"
                  onClick={() => go(view === "settings" ? "home" : "review")}
                >
                  <ArrowLeft size={17} /> Back
                </button>
              )}
              <span className="eyebrow">
                {view === "home"
                  ? "A PLACE FOR EVERY CARD"
                  : view === "scan"
                    ? "CAPTURE · REVIEW · COLLECT"
                    : view === "review"
                      ? `${pending.length} CARDS IN YOUR QUEUE`
                      : view === "inventory"
                        ? "YOUR PERSONAL INVENTORY"
                        : view === "settings"
                          ? "TALLYBINDER SETTINGS"
                          : "HUMAN REVIEW, ALWAYS"}
              </span>
              <h1>{title[view]}</h1>
            </div>
            {view === "home" && (
              <>
                <section className="scan-hero">
                  <div>
                    <span className="eyebrow">
                      LESS SORTING. MORE COLLECTING.
                    </span>
                    <h2>
                      From card
                      <br />
                      to collection.
                    </h2>
                    <p>
                      Two photos. A careful review.
                      <br />
                      One more card, accounted for.
                    </p>
                    <button onClick={() => go("scan")} className="light-button">
                      <Camera size={19} /> Scan a card <ArrowRight size={18} />
                    </button>
                  </div>
                  <div className="hero-cards" aria-hidden="true">
                    <div className="ghost-card" />
                    <div className="hero-card">
                      <span className="mini-brand">TB</span>
                      <div className="card-spark">✦</div>
                      <div className="card-lines">
                        <i />
                        <i />
                      </div>
                    </div>
                    <span className="hero-badge">
                      <Check size={14} /> Yours to keep
                    </span>
                  </div>
                </section>
                <div className="metrics">
                  <button onClick={() => go("inventory")}>
                    <span className="metric-icon">
                      <Layers size={19} />
                    </span>
                    <strong>{inventoryTotal}</strong>
                    <span>in your inventory</span>
                  </button>
                  <button onClick={() => go("review")}>
                    <span className="metric-icon warm">
                      <FolderOpen size={19} />
                    </span>
                    <strong>{pending.length}</strong>
                    <span>waiting for review</span>
                  </button>
                </div>
                <div className="section-heading">
                  <h2>On your desk</h2>
                  <button onClick={() => go("review")}>
                    View queue <ArrowRight size={16} />
                  </button>
                </div>
                {pending.length ? (
                  pending
                    .slice(0, 3)
                    .map((d) => (
                      <QueueRow
                        key={d.id}
                        draft={d}
                        onClick={() => review(d)}
                      />
                    ))
                ) : (
                  <div className="quiet-card">
                    <span className="round-icon">
                      <CheckCircle2 size={22} />
                    </span>
                    <div>
                      <strong>A clean slate.</strong>
                      <p>Your next great find starts with a photo.</p>
                    </div>
                  </div>
                )}
                <div className="trust-note">
                  <ShieldCheck size={20} />
                  <p>
                    <strong>Your call, at every step.</strong>
                    <br />
                    Confirm the printing, inspect the condition, choose your
                    price.
                  </p>
                </div>
              </>
            )}
            {view === "scan" && capture && (
              <>
                <p className="intro">
                  Front and back. We’ll keep this card in your review queue
                  while you capture the next.
                </p>
                <Photos
                  key={capture.id}
                  front={capture.front}
                  back={capture.back}
                  onChange={photo}
                />
                <button
                  className="primary"
                  disabled={!capture.front || !capture.back}
                  onClick={() => void queueCard()}
                >
                  Add to review queue <ArrowRight size={18} />
                </button>
                <p className="caption">
                  Photos stay on this device until you add the card to review.
                </p>
                <button className="text-button" onClick={() => go("review")}>
                  Review {pending.length} queued{" "}
                  {pending.length === 1 ? "card" : "cards"}{" "}
                  <ChevronRight size={16} />
                </button>
              </>
            )}
            {view === "review" && (
              <>
                <div className="queue-summary">
                  <span>
                    <CloudUpload size={18} />
                    {syncing
                      ? `${syncing} syncing…`
                      : "Capture another card whenever you’re ready."}
                  </span>
                  <button onClick={() => go("scan")}>
                    <Plus size={17} /> Add card
                  </button>
                </div>
                {pending.length ? (
                  pending.map((d) => (
                    <div key={d.id}>
                      <QueueRow draft={d} onClick={() => review(d)} />
                      {d.error && (
                        <div className="queue-error">
                          <span>{d.error}</span>
                          <button
                            disabled={!!busy[d.id]}
                            onClick={() =>
                              void sync(d).catch((e) => setNotice(message(e)))
                            }
                          >
                            Retry sync
                          </button>
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <Empty
                    icon={<CheckCircle2 />}
                    title="All caught up."
                    text="Your reviewed cards live in inventory. Capture another to keep going."
                    action={() => go("scan")}
                    label="Scan a card"
                  />
                )}
              </>
            )}
            {current &&
              ["identity", "condition", "pricing", "listing"].includes(
                view,
              ) && (
                <>
                  <div className="review-strip">
                    <Photo
                      blob={current.front}
                      id={current.front_id}
                      alt="Card front"
                    />
                    <div>
                      <strong>
                        {current.fields.name || "Unidentified card"}
                      </strong>
                      <span>
                        {current.fields.set_name || "Choose a catalog match"}
                        {current.fields.number
                          ? " · " + current.fields.number
                          : ""}
                      </span>
                    </div>
                    <span className="pill">
                      {current.saved ? "Saved" : "In review"}
                    </span>
                  </div>
                  <nav className="steps" aria-label="Review steps">
                    {(
                      ["identity", "condition", "pricing", "listing"] as const
                    ).map((s, i) => (
                      <button
                        key={s}
                        className={view === s ? "active" : ""}
                        onClick={() => step(s)}
                      >
                        <b>{i + 1}</b>
                        <span>
                          {s === "identity"
                            ? "Identify"
                            : s === "condition"
                              ? "Condition"
                              : s === "pricing"
                                ? "Price"
                                : "Listing"}
                        </span>
                      </button>
                    ))}
                  </nav>
                  {current.error && (
                    <div className="notice error" role="alert">
                      {current.error}
                    </div>
                  )}
                  {view === "identity" && (
                    <>
                      <section className="panel">
                        <div className="section-heading">
                          <h2>Find it in the catalog</h2>
                          <span className="pill">Pokémon</span>
                        </div>
                        <label className="search-box">
                          <Search size={18} />
                          <input
                            aria-label="Search card name"
                            placeholder="Card name, e.g. Charizard"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") void find();
                            }}
                          />
                        </label>
                        <div className="field-grid">
                          <label className="field">
                            <span>Set (optional)</span>
                            <input
                              aria-label="Search set"
                              placeholder="Base Set"
                              value={searchSet}
                              onChange={(e) => setSearchSet(e.target.value)}
                            />
                          </label>
                          <label className="field">
                            <span>Full number (optional)</span>
                            <input
                              aria-label="Search collector number"
                              placeholder="4/102"
                              value={searchNumber}
                              onChange={(e) => setSearchNumber(e.target.value)}
                            />
                          </label>
                        </div>
                        <button
                          className="secondary full"
                          onClick={() => void find()}
                          disabled={searching}
                        >
                          {searching ? (
                            <LoaderCircle className="spin" size={16} />
                          ) : (
                            <Search size={16} />
                          )}{" "}
                          Search catalog
                        </button>
                        {searchError && (
                          <p className="caption" role="status">
                            {searchError}
                          </p>
                        )}
                        <div className="search-results">
                          {results.map((c) => (
                            <button key={c.id} onClick={() => void pick(c)}>
                              <span>
                                <strong>{c.name}</strong>
                                <small>
                                  {c.set_name} ·{" "}
                                  {c.collector_number || "Number unavailable"}
                                </small>
                              </span>
                              <ChevronRight size={18} />
                            </button>
                          ))}
                        </div>
                      </section>
                      <button
                        className="ai-button"
                        onClick={() => void startJob("identify")}
                        disabled={!config?.ai_enabled || !!busy[current.id]}
                      >
                        <span className="ai-spark">✦</span>
                        <span>
                          <strong>
                            {config?.ai_enabled
                              ? "Research the front photo with AI"
                              : "AI is optional"}
                          </strong>
                          <small>
                            {config?.ai_enabled
                              ? "Paid request · review every result"
                              : "Manual catalog search works without an API key."}
                          </small>
                        </span>
                        <ArrowRight size={18} />
                      </button>
                      {job?.kind === "identify" && (
                        <JobPanel job={job} onPick={(c) => void pick(c)} />
                      )}
                      <section className="panel">
                        <h2>Confirm the printing</h2>
                        <p className="caption">
                          Choose a catalog entry first. Changing its name, set
                          or number requires a new selection.
                        </p>
                        <div className="field-grid">
                          {field("Card name", "name")}
                          {field("Set", "set_name")}
                          {field("Collector number", "number")}
                          {field("Language", "language", [
                            { value: "english", label: "English" },
                            { value: "japanese", label: "Japanese" },
                            { value: "french", label: "French" },
                            { value: "german", label: "German" },
                            { value: "spanish", label: "Spanish" },
                            { value: "korean", label: "Korean" },
                            {
                              value: "simplified chinese",
                              label: "Simplified Chinese",
                            },
                            {
                              value: "traditional chinese",
                              label: "Traditional Chinese",
                            },
                          ])}
                          {field("Edition", "edition", [
                            { value: "standard", label: "Standard" },
                            { value: "unlimited", label: "Unlimited" },
                            { value: "first edition", label: "First Edition" },
                            { value: "shadowless", label: "Shadowless" },
                          ])}
                          {field("Finish", "finish", [
                            { value: "holo", label: "Holofoil" },
                            { value: "non-holo", label: "Non-holo" },
                            { value: "reverse holo", label: "Reverse holo" },
                          ])}
                          {field("Rarity (optional)", "rarity")}
                        </div>
                        <p className="caption">
                          Unknown attributes stay unspecified. AI and catalog
                          candidates are never automatically approved.
                        </p>
                      </section>
                      <button
                        className="primary"
                        disabled={
                          !current.fields.product_id ||
                          !current.fields.language ||
                          !!busy[current.id]
                        }
                        onClick={() => void confirmIdentity()}
                      >
                        Confirm identity <ArrowRight size={18} />
                      </button>
                    </>
                  )}
                  {view === "condition" && (
                    <>
                      <div className="condition-photos">
                        <Photo
                          blob={current.front}
                          id={current.front_id}
                          alt="Front photo"
                        />
                        <Photo
                          blob={current.back}
                          id={current.back_id}
                          alt="Back photo"
                        />
                      </div>
                      <section className="panel">
                        <h2>How does it look in hand?</h2>
                        <p className="caption">
                          Check corners, edges, whitening, scratches and
                          creases. Photos can miss dents and surface wear.
                        </p>
                        <div className="condition-options">
                          {conditions.map((c) => (
                            <button
                              key={c}
                              aria-pressed={current.fields.condition === c}
                              className={
                                current.fields.condition === c ? "selected" : ""
                              }
                              onClick={() => void edit({ condition: c })}
                            >
                              <b>{c}</b>
                              <span>{labels[c]}</span>
                              {current.fields.condition === c && (
                                <Check size={17} />
                              )}
                            </button>
                          ))}
                        </div>
                      </section>
                      <button
                        className="ai-button"
                        disabled={!config?.ai_enabled || !!busy[current.id]}
                        onClick={() => void startJob("condition")}
                      >
                        <span className="ai-spark">✦</span>
                        <span>
                          <strong>Optional photo assessment</strong>
                          <small>
                            Preliminary guidance, never professional grading.
                          </small>
                        </span>
                        <ArrowRight size={18} />
                      </button>
                      {job?.kind === "condition" && (
                        <JobPanel
                          job={job}
                          onCondition={(c) => void edit({ condition: c })}
                        />
                      )}
                      <button
                        className="primary"
                        disabled={
                          !current.fields.condition || !!busy[current.id]
                        }
                        onClick={() => void price()}
                      >
                        Confirm condition & get price <ArrowRight size={18} />
                      </button>
                    </>
                  )}
                  {view === "pricing" && (
                    <>
                      <section className="price-panel">
                        <div className="section-heading">
                          <span className="eyebrow">
                            CONDITION-SPECIFIC REFERENCE
                          </span>
                          <span className="pill">
                            {current.fields.condition || "Unconfirmed"}
                          </span>
                        </div>
                        <div className="price-value">
                          {current.pricing &&
                          ["exact_match", "stale_price"].includes(
                            current.pricing.status,
                          )
                            ? money(current.pricing.market_price)
                            : "Price unavailable"}
                        </div>
                        <p>
                          {busy[current.id] ||
                            (!current.pricing
                              ? "Confirm the identity and condition to request an exact lookup."
                              : current.pricing.status === "ambiguous_match"
                                ? "Printing information is incomplete or ambiguous. Choose a manual selling price."
                                : current.pricing.status === "price_unavailable"
                                  ? "No reported price for this exact SKU. You can still set your own selling price."
                                  : "Provider-reported market reference, not an authenticated individual sale.")}
                        </p>
                        {current.pricing?.source && (
                          <dl>
                            <div>
                              <dt>Source</dt>
                              <dd>{current.pricing.source}</dd>
                            </div>
                            <div>
                              <dt>Provider SKU</dt>
                              <dd>{current.pricing.provider_sku_id}</dd>
                            </div>
                            <div>
                              <dt>Updated</dt>
                              <dd>
                                {current.pricing.source_updated_at
                                  ? new Date(
                                      current.pricing.source_updated_at,
                                    ).toLocaleString()
                                  : "Not supplied"}
                              </dd>
                            </div>
                          </dl>
                        )}
                        {current.pricing?.status === "stale_price" && (
                          <div className="notice">
                            This reference is stale. Review before setting your
                            price.
                          </div>
                        )}
                        {current.pricing?.warnings?.map((w) => (
                          <p className="caption" key={w}>
                            {w.replaceAll("_", " ")}
                          </p>
                        ))}
                      </section>
                      {!!current.pricing?.generic_references?.length && (
                        <details className="panel generic">
                          <summary>Separate generic references</summary>
                          <p className="caption">
                            These combine conditions and do not establish an
                            NM/LP/MP/HP/DMG value.
                          </p>
                          {current.pricing.generic_references.map((r, i) => (
                            <div key={i}>
                              {r.subtype || "Generic"}{" "}
                              <strong>{money(r.market_price)}</strong>
                            </div>
                          ))}
                        </details>
                      )}
                      <section className="panel">
                        <h2>Your selling price</h2>
                        <p className="caption">
                          You choose the asking price. Shipping and taxes are
                          not added to market value.
                        </p>
                        <label className="field">
                          <span>Listing price (USD)</span>
                          <div className="money-input">
                            <span>$</span>
                            <input
                              aria-label="Listing price"
                              inputMode="decimal"
                              placeholder="0.00"
                              value={current.listing_price}
                              onChange={(e) =>
                                void remember({
                                  ...current,
                                  listing_price: e.target.value,
                                })
                              }
                            />
                          </div>
                        </label>
                        {current.pricing?.market_price &&
                          ["exact_match", "stale_price"].includes(
                            current.pricing.status,
                          ) && (
                            <button
                              className="text-button"
                              onClick={() =>
                                void remember({
                                  ...current,
                                  listing_price: current.pricing!.market_price!,
                                })
                              }
                            >
                              Use market reference as my asking price
                            </button>
                          )}
                      </section>
                      <button
                        className="primary"
                        onClick={() => void listing()}
                        disabled={
                          !/^\d{1,8}(\.\d{1,2})?$/.test(current.listing_price)
                        }
                      >
                        Preview listing <ArrowRight size={18} />
                      </button>
                      <button
                        className="text-button"
                        onClick={() => void price()}
                        disabled={
                          !current.fields.condition || !!busy[current.id]
                        }
                      >
                        Refresh exact price
                      </button>
                    </>
                  )}
                  {view === "listing" && (
                    <>
                      <div className="listing-photos">
                        <Photo
                          blob={current.front}
                          id={current.front_id}
                          alt="Listing front"
                        />
                        <Photo
                          blob={current.back}
                          id={current.back_id}
                          alt="Listing back"
                        />
                      </div>
                      <section className="panel">
                        <label className="field">
                          <span>Item name</span>
                          <input
                            aria-label="Listing item name"
                            value={current.item_name}
                            onChange={(e) =>
                              void remember({
                                ...current,
                                item_name: e.target.value,
                              })
                            }
                          />
                        </label>
                        <div className="listing-facts">
                          {[
                            ["Game", "Pokémon"],
                            ["Set", current.fields.set_name],
                            ["Number", current.fields.number],
                            ["Language", current.fields.language],
                            [
                              "Edition",
                              current.fields.edition || "Unspecified",
                            ],
                            ["Finish", current.fields.finish || "Unspecified"],
                            [
                              "Condition",
                              current.fields.condition || "Unconfirmed",
                            ],
                          ].map(([k, v]) => (
                            <div key={k}>
                              <span>{k}</span>
                              <strong>{v}</strong>
                            </div>
                          ))}
                        </div>
                        <div className="field-grid">
                          <label className="field">
                            <span>Selling price · USD</span>
                            <input
                              aria-label="Final listing price"
                              inputMode="decimal"
                              value={current.listing_price}
                              onChange={(e) =>
                                void remember({
                                  ...current,
                                  listing_price: e.target.value,
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>Quantity</span>
                            <input
                              aria-label="Quantity"
                              type="number"
                              min="0"
                              max="100000"
                              value={current.quantity}
                              onChange={(e) =>
                                void remember({
                                  ...current,
                                  quantity: Number(e.target.value),
                                })
                              }
                            />
                          </label>
                        </div>
                        <label className="field">
                          <span>Description</span>
                          <textarea
                            aria-label="Listing description"
                            rows={5}
                            value={current.description}
                            onChange={(e) =>
                              void remember({
                                ...current,
                                description: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label className="field">
                          <span>Private notes</span>
                          <textarea
                            aria-label="Listing notes"
                            rows={3}
                            value={current.listing_notes}
                            onChange={(e) =>
                              void remember({
                                ...current,
                                listing_notes: e.target.value,
                              })
                            }
                          />
                        </label>
                        <p className="caption">
                          Market reference:{" "}
                          {money(current.pricing?.market_price)}. Your selling
                          price is separate. Confirm the photos, printing and
                          condition before saving.
                        </p>
                      </section>
                      <button
                        className="primary"
                        disabled={
                          !!busy[current.id] ||
                          !current.fields.product_id ||
                          !current.fields.condition ||
                          !/^\d{1,8}(\.\d{1,2})?$/.test(current.listing_price)
                        }
                        onClick={() => void save()}
                      >
                        <CheckCircle2 size={18} />
                        {busy[current.id] || "Approve & save to inventory"}
                      </button>
                      <button
                        className="text-button"
                        onClick={() => go("identity")}
                      >
                        Edit card identity or condition
                      </button>
                    </>
                  )}
                </>
              )}
            {["identity", "condition", "pricing", "listing"].includes(view) &&
              !current && (
                <Empty
                  icon={<FolderOpen />}
                  title="Pick a card to review."
                  text="Your scan queue keeps every card together."
                  action={() => go("review")}
                  label="Open review queue"
                />
              )}
            {view === "inventory" && (
              <>
                <div className="inventory-tools">
                  <label className="search-box">
                    <Search size={18} />
                    <input
                      aria-label="Search inventory"
                      placeholder="Find a card in your binder"
                      value={inventoryQuery}
                      onChange={(e) => setInventoryQuery(e.target.value)}
                    />
                  </label>
                  <select
                    aria-label="Filter inventory condition"
                    value={inventoryCondition}
                    onChange={(e) => setInventoryCondition(e.target.value)}
                  >
                    <option value="">All conditions</option>
                    {conditions.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </div>
                <div className="section-heading">
                  <span className="caption">
                    {inventoryTotal}{" "}
                    {inventoryTotal === 1 ? "listing" : "listings"}
                  </span>
                  <button onClick={() => void exportCsv()}>
                    <Download size={16} /> Export CSV
                  </button>
                </div>
                {inventory.length ? (
                  inventory.map((item) => (
                    <article className="inventory-card" key={item.id}>
                      <button
                        className="inventory-open"
                        onClick={() => void openInventory(item)}
                      >
                        <Photo
                          id={item.listing.front_image_id}
                          alt={item.listing.name}
                        />
                        <div>
                          <span className="pill">{item.listing.condition}</span>
                          <h3>{item.listing.item_name}</h3>
                          <p>
                            {item.listing.set_name} · {item.listing.number}
                          </p>
                          <strong>
                            {money(item.listing.listing_price)}{" "}
                            <small>× {item.listing.quantity}</small>
                          </strong>
                        </div>
                        <ChevronRight size={18} />
                      </button>
                      <div className="inventory-foot">
                        <span>{item.listing.sku}</span>
                        <button
                          aria-label={"Delete " + item.listing.item_name}
                          onClick={() => void deleteListing(item)}
                        >
                          <Trash2 size={15} /> Delete
                        </button>
                      </div>
                    </article>
                  ))
                ) : (
                  <Empty
                    icon={<Layers />}
                    title="Start your first page."
                    text="Approved listings appear here with your photos, quantities and chosen prices."
                    action={() => go("scan")}
                    label="Scan your first card"
                  />
                )}
                {inventory.length < inventoryTotal && (
                  <button
                    className="secondary full"
                    onClick={() => void loadInventory(inventory.length)}
                  >
                    Load more listings
                  </button>
                )}
              </>
            )}
            {view === "settings" && (
              <>
                <section className="panel">
                  <div className="section-heading">
                    <h2>Your setup</h2>
                    <span className="pill">Personal edition</span>
                  </div>
                  <dl>
                    <div>
                      <dt>AI research</dt>
                      <dd>
                        {config?.ai_enabled
                          ? "Available · paid, opt-in"
                          : "Off · manual workflow ready"}
                      </dd>
                    </div>
                    <div>
                      <dt>AI model</dt>
                      <dd>{config?.model || "Not enabled"}</dd>
                    </div>
                    <div>
                      <dt>Market pricing</dt>
                      <dd>Local SKU database</dd>
                    </div>
                  </dl>
                  <p className="caption">
                    AI credentials and spending limits are configured on your
                    backend. Never enter an OpenAI key here.
                  </p>
                  {config?.ai_pause_reason && (
                    <p className="notice">
                      AI is paused pending operator review of API usage after a
                      backup restore. Manual identification and pricing remain
                      available.
                    </p>
                  )}
                  {config?.auth_mode !== "firebase" && <label className="field">
                    <span>
                      {config?.auth_mode === "session"
                        ? "Personal access key"
                        : "Personal app access token (optional)"}
                    </span>
                    <input
                      aria-label="App access token"
                      type="password"
                      autoComplete="off"
                      value={accessToken}
                      onChange={(e) => setAccessToken(e.target.value)}
                    />
                  </label>}
                  {config?.auth_mode !== "firebase" && <button
                    className="secondary full"
                    onClick={() => {
                      if (config?.auth_mode === "session") {
                        void request("/auth/login", {
                          method: "POST",
                          body: JSON.stringify({ access_key: accessToken }),
                        })
                          .then(() => {
                            localStorage.removeItem("tallybinder.accessToken");
                            location.reload();
                          })
                          .catch((e) => setNotice(message(e)));
                      } else {
                        localStorage.setItem(
                          "tallybinder.accessToken",
                          accessToken,
                        );
                        location.reload();
                      }
                    }}
                  >
                    {config?.auth_mode === "session"
                      ? "Sign in securely"
                      : "Save access token & reconnect"}
                  </button>}
                  {config?.auth_mode === "firebase" && (
                    <div className="account-row">
                      <span>
                        <small>Signed in as</small>
                        <strong>{firebaseAuth?.currentUser?.email || "Firebase account"}</strong>
                      </span>
                      <ShieldCheck size={21} />
                    </div>
                  )}
                  {config?.auth_mode === "session" && (
                    <>
                      <p className="caption">
                        Your key is exchanged for a secure, HttpOnly session
                        cookie and is not saved in browser storage.
                      </p>
                      <button
                        className="text-button"
                        onClick={() =>
                          void request("/auth/logout", { method: "POST" })
                            .then(() => location.reload())
                            .catch((e) => setNotice(message(e)))
                        }
                      >
                        Sign out of cloud binder
                      </button>
                    </>
                  )}
                  {config?.auth_mode === "firebase" && firebaseAuth && (
                    <button
                      className="text-button"
                      onClick={() => {
                        if (firebaseAuth) void firebaseSignOut(firebaseAuth);
                      }}
                    >
                      Sign out
                    </button>
                  )}
                </section>
                <section className="panel">
                  <h2>Keep TallyBinder close.</h2>
                  <p>
                    In Safari, tap Share, then{" "}
                    <strong>Add to Home Screen</strong>. Camera access needs
                    HTTPS.
                  </p>
                  <p className="caption">
                    The public shell can open offline. Unsent drafts remain in
                    this browser; identification, pricing and server inventory
                    need a connection. Pending uploads resume only while the app
                    is open. Server jobs need the backend to stay running.
                  </p>
                </section>
                <section className="panel">
                  <h2>A careful estimate, always.</h2>
                  <p className="caption">
                    Prices are provider-reported market references, not verified
                    individual sales. Photos cannot establish professional
                    grades. Commercial data rights remain unresolved.
                  </p>
                  <p className="caption">TallyBinder · Early edition 0.1.0</p>
                </section>
              </>
            )}
          </>
        )}
      </main>
      <nav className="bottom-nav" aria-label="Main navigation">
        {(
          [
            { id: "home", label: "Home", icon: Home },
            { id: "scan", label: "Scan", icon: Camera },
            { id: "review", label: "Review", icon: FolderOpen },
            { id: "inventory", label: "Inventory", icon: Layers },
          ] as const
        ).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            aria-label={label}
            aria-current={
              view === id ||
              (id === "review" &&
                ["identity", "condition", "pricing", "listing"].includes(view))
                ? "page"
                : undefined
            }
            className={
              view === id ||
              (id === "review" &&
                ["identity", "condition", "pricing", "listing"].includes(view))
                ? "active"
                : ""
            }
            onClick={() => go(id)}
          >
            <span>
              <Icon size={22} />
              {id === "review" && pending.length > 0 && <b>{pending.length}</b>}
            </span>
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
function QueueRow({ draft, onClick }: { draft: Draft; onClick: () => void }) {
  return (
    <button className="queue-row" onClick={onClick}>
      <Photo blob={draft.front} id={draft.front_id} alt="Card preview" />
      <span>
        <strong>{draft.fields.name || "New card"}</strong>
        <small>
          {draft.fields.set_name
            ? draft.fields.set_name + " · " + draft.fields.number
            : "Front and back captured"}
        </small>
        <em>
          {draft.sync_status === "error"
            ? "Sync needs attention"
            : draft.sync_status === "local"
              ? "Saved on this device"
              : draft.fields.condition
                ? labels[draft.fields.condition]
                : "Confirm identity & condition"}
        </em>
      </span>
      <ChevronRight size={19} />
    </button>
  );
}
function Empty({
  icon,
  title,
  text,
  action,
  label,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
  action: () => void;
  label: string;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h2>{title}</h2>
      <p>{text}</p>
      <button className="secondary" onClick={action}>
        {label}
        <ArrowRight size={16} />
      </button>
    </div>
  );
}
function JobPanel({
  job,
  onPick,
  onCondition,
}: {
  job: Job;
  onPick?: (c: Card) => void;
  onCondition?: (c: Condition) => void;
}) {
  return (
    <section className="panel ai-result">
      <span className="eyebrow">PHOTO RESEARCH · HUMAN REVIEW REQUIRED</span>
      {job.status === "queued" || job.status === "running" ? (
        <p>
          <LoaderCircle size={16} className="spin" />{" "}
          {job.status === "queued"
            ? "Queued for photo research."
            : "Researching photos."}{" "}
          You can keep scanning.{" "}
          {job.error ? job.error.replaceAll("_", " ") : ""}
        </p>
      ) : job.status !== "completed" ? (
        <p>
          Photo research {job.status}. {job.error?.replaceAll("_", " ")}.
          Continue manually.
        </p>
      ) : job.stale_for_intake ? (
        <p>
          This result belongs to an earlier draft. Review the current photos and
          details manually.
        </p>
      ) : (
        <>
          {job.result?.catalog_candidates?.map((c, i) => (
            <button
              className="candidate"
              key={i}
              onClick={() => onPick?.(c.card)}
            >
              <strong>{c.card.name}</strong>
              <span>
                {c.card.set_name} · {c.card.collector_number}
              </span>
              <small>
                {c.match.replaceAll("_", " ")}
                {c.issues.length
                  ? " · " + c.issues.join(", ").replaceAll("_", " ")
                  : ""}
              </small>
            </button>
          ))}
          {job.result?.recommended_condition && (
            <button
              className="secondary"
              onClick={() => onCondition?.(job.result!.recommended_condition!)}
            >
              Use {labels[job.result.recommended_condition]} recommendation
            </button>
          )}
          <ul>
            {job.result?.observations.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
          {job.result?.limitations.map((s, i) => (
            <p key={i} className="caption">
              {s}
            </p>
          ))}
        </>
      )}
      {job.estimated_cost_usd && (
        <p className="caption">This request: ${job.estimated_cost_usd}</p>
      )}
      {job.intake_estimated_cost_usd && (
        <p className="caption">
          Recorded AI cost for this card: ${job.intake_estimated_cost_usd}
          {!job.intake_cost_complete
            ? ` · incomplete; $${job.intake_unknown_reserve_usd} reserved for unknown usage`
            : ""}
        </p>
      )}
    </section>
  );
}
