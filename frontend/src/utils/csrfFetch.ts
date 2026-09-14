import { withPublicSitePath } from "./publicPath";

// Fetch a fresh masked token and its cookie before each authentication POST.
// The response body also works when the CSRF cookie is HttpOnly.
export const csrfFetch = async (url: string, init: RequestInit): Promise<Response> => {
    const bootstrap = await fetch(withPublicSitePath("/api/csrf"), {
        credentials: "same-origin",
        cache: "no-store",
    });
    if (!bootstrap.ok) {
        throw new Error("Unable to initialize secure request. Please try again.");
    }
    const { csrfToken } = await bootstrap.json();
    if (typeof csrfToken !== "string" || csrfToken.length === 0) {
        throw new Error("Unable to initialize secure request. Please try again.");
    }
    const headers = new Headers(init.headers);
    headers.set("X-CSRFToken", csrfToken);
    return fetch(url, { ...init, headers, credentials: "same-origin" });
};
