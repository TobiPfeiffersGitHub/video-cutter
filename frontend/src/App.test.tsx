import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("shows the backend as online when the ping succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "ok" }) }),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: "videocut" })).toBeInTheDocument();
    expect(await screen.findByText("Backend: online")).toBeInTheDocument();
  });

  it("shows the backend as offline when the ping fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    render(<App />);
    expect(await screen.findByText("Backend: offline")).toBeInTheDocument();
  });
});
