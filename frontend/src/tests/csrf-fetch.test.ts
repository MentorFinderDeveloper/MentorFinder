import { csrfFetch } from "../utils/csrfFetch";

describe("authentication CSRF transport", () => {
    const originalFetch = globalThis.fetch;
    const originalSitePath = process.env.NEXT_PUBLIC_SITE_PATH;

    afterEach(() => {
        globalThis.fetch = originalFetch;
        if (originalSitePath === undefined) {
            delete process.env.NEXT_PUBLIC_SITE_PATH;
        } else {
            process.env.NEXT_PUBLIC_SITE_PATH = originalSitePath;
        }
        jest.resetModules();
    });

    it("bootstraps the cookie and sends the token with the authentication payload", async () => {
        process.env.NEXT_PUBLIC_SITE_PATH = "/se-projects/mentorfinder";
        jest.resetModules();
        const { csrfFetch: fetchWithSitePath } = require("../utils/csrfFetch") as typeof import("../utils/csrfFetch");
        const response = { ok: true };
        const fetchMock = jest.fn()
            .mockResolvedValueOnce({ ok: true, json: async () => ({ csrfToken: "masked-token" }) })
            .mockResolvedValueOnce(response);
        globalThis.fetch = fetchMock;
        const body = JSON.stringify({ email: "new@example.com" });
        expect(await fetchWithSitePath("/se-projects/mentorfinder/api/register/verification-code", {
            method: "POST", headers: { "Content-Type": "application/json" }, body,
        })).toBe(response);
        expect(fetchMock.mock.calls[0]).toEqual([
            "/se-projects/mentorfinder/api/csrf",
            { credentials: "same-origin", cache: "no-store" },
        ]);
        const [url, options] = fetchMock.mock.calls[1];
        expect(url).toBe("/se-projects/mentorfinder/api/register/verification-code");
        expect(options).toMatchObject({ method: "POST", body, credentials: "same-origin" });
        expect(options.headers.get("X-CSRFToken")).toBe("masked-token");
        expect(options.headers.get("Content-Type")).toBe("application/json");
    });

    it.each([
        { ok: false },
        { ok: true, json: async () => ({}) },
    ])("does not submit credentials if CSRF initialization fails", async (bootstrap) => {
        const fetchMock = jest.fn().mockResolvedValue(bootstrap);
        globalThis.fetch = fetchMock;
        await expect(csrfFetch("/api/login", { method: "POST" })).rejects.toThrow("secure request");
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
});
