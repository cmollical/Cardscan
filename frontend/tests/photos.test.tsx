import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ download: vi.fn() }));
vi.mock("../lib/api", () => ({ download: mocks.download }));

import { Photo } from "../components/Photos";

afterEach(() => {
  cleanup();
  mocks.download.mockReset();
});

describe("Photo", () => {
  it("reuses a resolved cloud photo when it appears again in a later step", async () => {
    mocks.download.mockResolvedValue(new Blob(["photo"], { type: "image/jpeg" }));
    const first = render(<Photo id="front-1" alt="Review front" />);
    await screen.findByRole("img", { name: "Review front" });
    first.unmount();

    render(<Photo id="front-1" alt="Listing front" />);
    expect(screen.getByRole("img", { name: "Listing front" })).toBeTruthy();
    expect(mocks.download).toHaveBeenCalledTimes(1);
  });

  it("falls back to cloud media when a persisted local photo is unreadable", async () => {
    mocks.download.mockResolvedValue(new Blob(["photo"], { type: "image/jpeg" }));
    render(
      <Photo
        blob={{} as Blob}
        id="front-fallback"
        alt="Recovered front"
      />,
    );
    await screen.findByRole("img", { name: "Recovered front" });
    expect(mocks.download).toHaveBeenCalledWith("/media/front-fallback");
  });
});
