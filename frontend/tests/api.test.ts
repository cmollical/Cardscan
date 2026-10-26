import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { request, ApiError } from "../lib/api";
describe("backend client", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());
  it("uses only same-origin URLs and keeps access tokens in headers", async () => {
    localStorage.setItem("tallybinder.accessToken", "synthetic-token");
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetch);
    await request("/intake", { method: "POST", body: "{}" });
    expect(fetch.mock.calls[0][0]).toBe("/api/backend/intake");
    const headers = fetch.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer synthetic-token");
    expect(headers.get("X-TallyBinder-Client")).toBe("web");
  });
  it("surfaces errors instead of fabricating results", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 503,
          json: async () => ({ detail: { code: "database_unavailable" } }),
        }),
    );
    await expect(request("/inventory")).rejects.toThrow("database unavailable");
  });
  it("preserves browser multipart boundaries", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ id: "synthetic" }) });
    vi.stubGlobal("fetch", fetch);
    await request("/media/upload", { method: "POST", body: new FormData() });
    expect(
      (fetch.mock.calls[0][1].headers as Headers).has("Content-Type"),
    ).toBe(false);
  });
});
