import {
    isSafeRelativeRedirect,
    resolveRedirectTarget,
    buildRedirectHref,
} from "../utils/authRedirect";

describe("isSafeRelativeRedirect", () => {
    // Tests the redirect-safety guard: only relative paths starting with "/"
    // that are not protocol-relative ("//...") are considered safe.

    it("accepts a simple relative path", () => {
        expect(isSafeRelativeRedirect("/profile")).toBe(true);
    });

    it("accepts a nested relative path", () => {
        expect(isSafeRelativeRedirect("/users/42")).toBe(true);
    });

    it("accepts a root path", () => {
        expect(isSafeRelativeRedirect("/")).toBe(true);
    });

    it("accepts a path with query parameters", () => {
        expect(isSafeRelativeRedirect("/search?q=test")).toBe(true);
    });

    it("accepts a path with a fragment", () => {
        expect(isSafeRelativeRedirect("/profile#section")).toBe(true);
    });

    it("rejects a protocol-relative URL starting with //", () => {
        // Protocol-relative URLs like "//evil.com" would redirect to an
        // external site using the current protocol.
        expect(isSafeRelativeRedirect("//evil.com")).toBe(false);
    });

    it("rejects an absolute http URL", () => {
        expect(isSafeRelativeRedirect("http://example.com")).toBe(false);
    });

    it("rejects an absolute https URL", () => {
        expect(isSafeRelativeRedirect("https://example.com")).toBe(false);
    });

    it("rejects a non-string value (number)", () => {
        expect(isSafeRelativeRedirect(42)).toBe(false);
    });

    it("rejects a non-string value (object)", () => {
        expect(isSafeRelativeRedirect({})).toBe(false);
    });

    it("rejects a non-string value (null)", () => {
        expect(isSafeRelativeRedirect(undefined)).toBe(false);
    });

    it("rejects a non-string value (undefined)", () => {
        expect(isSafeRelativeRedirect(undefined)).toBe(false);
    });

    it("rejects an empty string", () => {
        // An empty string does not start with "/", so it is not safe.
        expect(isSafeRelativeRedirect("")).toBe(false);
    });
});

describe("resolveRedirectTarget", () => {
    // Tests the redirect resolver: safe values pass through, unsafe values
    // fall back to the supplied default.

    it("returns the redirect value when it is safe", () => {
        expect(resolveRedirectTarget("/profile")).toBe("/profile");
    });

    it("returns the fallback when the redirect value is unsafe", () => {
        expect(resolveRedirectTarget("https://evil.com")).toBe("/");
    });

    it("returns the fallback when the redirect value is null", () => {
        expect(resolveRedirectTarget(undefined)).toBe("/");
    });

    it("returns the fallback when the redirect value is undefined", () => {
        expect(resolveRedirectTarget(undefined)).toBe("/");
    });

    it("returns the custom fallback when the redirect value is unsafe", () => {
        expect(resolveRedirectTarget("//evil.com", "/custom")).toBe("/custom");
    });

    it("returns the custom fallback when the redirect value is an empty string", () => {
        expect(resolveRedirectTarget("", "/fallback")).toBe("/fallback");
    });
});

describe("buildRedirectHref", () => {
    // Tests the href builder: appends a safe redirect query parameter when
    // present, or returns the base path unchanged.

    it("builds a login href with a safe redirect parameter", () => {
        const href = buildRedirectHref("/login", "/profile");
        expect(href).toBe("/login?redirect=%2Fprofile");
    });

    it("builds a login href with a nested redirect path", () => {
        const href = buildRedirectHref("/login", "/users/42");
        expect(href).toBe("/login?redirect=%2Fusers%2F42");
    });

    it("returns the base path unchanged for an unsafe redirect", () => {
        const href = buildRedirectHref("/login", "https://evil.com");
        expect(href).toBe("/login");
    });

    it("returns the base path unchanged for undefined redirect", () => {
        const href = buildRedirectHref("/login", undefined);
        expect(href).toBe("/login");
    });

    it("returns the base path unchanged for null redirect", () => {
        const href = buildRedirectHref("/login", undefined);
        expect(href).toBe("/login");
    });

    it("returns the base path unchanged for a protocol-relative redirect", () => {
        const href = buildRedirectHref("/login", "//evil.com");
        expect(href).toBe("/login");
    });

    it("uses an empty base path", () => {
        const href = buildRedirectHref("", "/profile");
        expect(href).toBe("?redirect=%2Fprofile");
    });

    it("encodes the redirect parameter value", () => {
        // Special characters in the redirect path must be URL-encoded.
        const href = buildRedirectHref("/register", "/search?q=test");
        expect(href).toBe("/register?redirect=%2Fsearch%3Fq%3Dtest");
    });
});
