/**
 * Central network-request wrapper used by the frontend.
 * This module keeps request construction, auth-header injection, response
 * parsing, and normalized error handling in one place.
 */

import store from "../redux/store";
import { resetAuth } from "../redux/auth";

export enum NetworkErrorType {
    // Authentication is missing or expired and the user should re-authenticate.
    UNAUTHORIZED,
    // The server explicitly rejected the action even though the request shape
    // itself was valid, for example a forbidden operation.
    REJECTED,
    // The HTTP layer succeeded, but the response does not match the API
    // contract expected by the frontend.
    CORRUPTED_RESPONSE,
    // Fallback bucket for all remaining transport/response failures.
    UNKNOWN_ERROR,
}

// Custom error class used by the request wrapper so callers can branch on a
// stable semantic error type instead of parsing raw text messages.
export class NetworkError extends Error {
    type: NetworkErrorType;
    message: string;

    constructor(
        _type: NetworkErrorType,
        _message: string,
    ) {
        super(_message);

        this.type = _type;
        this.message = _message;
    }

    toString(): string { return this.message; }
    valueOf(): string { return this.message; }
}

// Perform a typed HTTP request against the backend API.
// Responsibilities:
// 1. attach JSON and auth headers when needed;
// 2. serialize request bodies;
// 3. parse backend JSON consistently;
// 4. translate status/code combinations into stable frontend errors.
export const request = async <T extends object = Record<string, unknown>>(
    url: string,
    method: "GET" | "POST" | "PUT" | "DELETE",
    needAuth: boolean,
    body?: object,
): Promise<T> => {
    const headers: Record<string, string> = {};

    // Send JSON content-type only when a request body is present.
    if (body !== undefined) {
        headers["Content-Type"] = "application/json";
    }

    // Inject the bearer token for authenticated requests when the Redux auth
    // store currently contains a non-empty token.
    if (needAuth) {
        const token = store.getState().auth.token;

        if (token !== "") {
            headers.Authorization = `Bearer ${token}`;
        }
    }

    const response = await fetch(url, {
        method,
        body: body && JSON.stringify(body),
        headers,
    });

    const contentType = response.headers.get("content-type") || "";
    const rawBody = await response.text();
    let data: Record<string, unknown>;
    try {
        // The backend contract is JSON-based even for most failures, so parse
        // the raw body first and classify non-JSON responses explicitly below.
        data = JSON.parse(rawBody);
    }
    catch {
        // A 200 response with non-JSON content means the backend violated the
        // expected API contract rather than returning a normal business error.
        if (response.status === 200) {
            throw new NetworkError(
                NetworkErrorType.CORRUPTED_RESPONSE,
                `[${response.status}] Non-JSON response from ${url}, content-type=${contentType}, body=${rawBody.slice(0, 120)}`,
            );
        }

        // Non-200 responses may still return plain text or an empty body.
        // Convert those cases into stable, non-crashing frontend errors.
        throw new NetworkError(
            NetworkErrorType.UNKNOWN_ERROR,
            `[${response.status}] ${rawBody === "" ? "Empty response body" : rawBody}`,
        );
    }

    const code = Number(data.code);
    const info = String(data.info ?? "Unknown error");

    // HTTP 401 is handled specially because protected requests should also
    // clear stale auth state from Redux when the backend reports code=2.
    if (response.status === 401 && code === 2) {
        if (needAuth) {
            store.dispatch(resetAuth());
        }

        throw new NetworkError(
            NetworkErrorType.UNAUTHORIZED,
            "[401] " + info,
        );
    }
    else if (response.status === 401) {
        throw new NetworkError(
            NetworkErrorType.CORRUPTED_RESPONSE,
            "[401] " + info,
        );
    }

    // HTTP 403 with code=3 represents an explicit backend rejection rather
    // than an auth-expiration event.
    if (response.status === 403 && code === 3) {
        throw new NetworkError(
            NetworkErrorType.REJECTED,
            "[403] " + info,
        );
    }
    else if (response.status === 403) {
        throw new NetworkError(
            NetworkErrorType.CORRUPTED_RESPONSE,
            "[403] " + info,
        );
    }

    // A successful business response is encoded as HTTP 200 + code 0.
    // The returned object strips the backend's success code because callers
    // typically only care about the payload fields.
    if (response.status === 200 && code === 0) {
        return { ...data, code: undefined } as T;
    }
    else if (response.status === 200) {
        throw new NetworkError(
            NetworkErrorType.CORRUPTED_RESPONSE,
            "[200] " + info,
        );
    }

    // Final fallback for status/code combinations not yet classified above.
    throw new NetworkError(
        NetworkErrorType.UNKNOWN_ERROR,
        `[${response.status}] ` + info,
    );
};
