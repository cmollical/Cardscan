import { afterEach, describe, expect, it, vi } from "vitest";
import { compressImage } from "../lib/images";
describe("photo preparation", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("rejects oversized inputs before trying to decode", async () => {
    await expect(compressImage({ size: 25_000_001 } as File)).rejects.toThrow(
      "too large",
    );
  });
  it("reports decode failures and releases object URLs", async () => {
    const revoke = vi.fn();
    vi.stubGlobal("URL", {
      createObjectURL: () => "blob:synthetic",
      revokeObjectURL: revoke,
    });
    vi.stubGlobal(
      "Image",
      class {
        src = "";
        decode() {
          return Promise.reject(new Error("encoding failed"));
        }
      },
    );
    await expect(compressImage(new File(["bad"], "bad.jpg"))).rejects.toThrow(
      "Could not open",
    );
    expect(revoke).toHaveBeenCalledWith("blob:synthetic");
  });
});
