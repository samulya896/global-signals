import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  isApiErrorStatus,
  isSafeArticleUrl,
  setCsrfToken,
} from "../lib/api";
describe("browser API client", () => {
  afterEach(() => {
    setCsrfToken("");
    vi.unstubAllGlobals();
  });
  it("includes credentials and CSRF protection on state-changing requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("test-csrf-token");
    await api("/api/v1/example", { method: "POST", body: "{}" });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.credentials).toBe("include");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe(
      "test-csrf-token",
    );
    expect(new Headers(options.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });
  it("does not attach a CSRF header to safe GET requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("test-csrf-token");
    await api("/api/v1/example");
    const [, options] = fetchMock.mock.calls[0];
    expect(new Headers(options.headers).has("X-CSRF-Token")).toBe(false);
  });
  it("surfaces safe API error details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ detail: "CSRF token is invalid." }),
      }),
    );
    await expect(
      api("/api/v1/example", { method: "DELETE" }),
    ).rejects.toMatchObject({
      message: "CSRF token is invalid.",
      status: 403,
    });
  });
  it("matches API error statuses without unsafe property casts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Authentication required." }),
      }),
    );
    let error;
    try {
      await api("/api/v1/example");
    } catch (caught) {
      error = caught;
    }
    expect(isApiErrorStatus(error, 401)).toBe(true);
    expect(isApiErrorStatus(error, 403)).toBe(false);
    expect(isApiErrorStatus(new Error("401"), 401)).toBe(false);
  });
});
describe("news article links", () => {
  it("allows HTTP(S) and rejects executable or malformed URLs", () => {
    expect(isSafeArticleUrl("https://news.example/story")).toBe(true);
    expect(isSafeArticleUrl("http://news.example/story")).toBe(true);
    expect(isSafeArticleUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeArticleUrl("not-a-url")).toBe(false);
  });
});
