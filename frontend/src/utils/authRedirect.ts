// Utilities for handling auth-related redirect parameters.
// These helpers keep login/register redirect targets constrained to safe
// in-site relative paths so the app avoids open-redirect behavior.

// Accept only safe relative routes such as `/profile`.
// Reject external URLs and protocol-relative values like `//evil.example.com`.
export const isSafeRelativeRedirect = (value: unknown): value is string => {
    return typeof value === "string" && value.startsWith("/") && !value.startsWith("//");
};

// Resolve a user-provided redirect target to a safe internal path.
// If the value is unsafe or missing, fall back to the supplied default route.
export const resolveRedirectTarget = (
    redirectValue: unknown,
    fallback = "/",
) => {
    return isSafeRelativeRedirect(redirectValue) ? redirectValue : fallback;
};

// Build a navigation href that preserves a safe redirect target when present.
// If the redirect is invalid or absent, return the base path unchanged.
export const buildRedirectHref = (
    basePath: string,
    redirectValue: unknown,
) => {
    const redirectTarget = resolveRedirectTarget(redirectValue, "");
    if (redirectTarget === "") {
        return basePath;
    }

    return `${basePath}?redirect=${encodeURIComponent(redirectTarget)}`;
};
