import { NetworkError, NetworkErrorType, request } from "../utils/network";
import { resetAuth } from "../redux/auth";

const mockGetState = jest.fn();
const mockDispatch = jest.fn();

// Mock the Redux store used internally by the network helper.
// These tests need to control the current auth token and verify whether the
// request layer dispatches resetAuth() when authorization expires.
jest.mock("../redux/store", () => ({
    __esModule: true,
    default: {
        dispatch: (action) => mockDispatch(action),
        getState: () => mockGetState(),
    },
}));

// Small helper to access the fetch mock installed in beforeEach.
const getFetchMock = () => globalThis.fetch;

// Builds a minimal fetch-like response object for JSON responses.
// This lets the tests focus on request-layer behavior instead of repeating the
// same response-shape boilerplate in every case.
const createJsonResponse = (status, payload) => ({
    status,
    headers: {
        get: jest.fn((key) => (key === "content-type" ? "application/json" : undefined)),
    },
    text: jest.fn().mockResolvedValue(JSON.stringify(payload)),
});

describe("request", () => {
    beforeEach(() => {
        // Reset store spies and install a default unauthenticated auth state
        // plus a fresh fetch mock before each request-layer test.
        mockGetState.mockReset();
        mockDispatch.mockReset();
        mockGetState.mockReturnValue({
            auth: {
                token: "",
                name: "",
            },
        });

        globalThis.fetch = jest.fn();
    });

    it("adds auth and content-type headers for authenticated POST request", async () => {
        // Tests the request-construction module for authenticated JSON writes.
        // A protected POST request should serialize the body, attach the JSON
        // content-type header, and include the bearer token from Redux state.
        mockGetState.mockReturnValue({
            auth: {
                token: "token-1",
                name: "alice",
            },
        });

        getFetchMock().mockResolvedValue({
            ...createJsonResponse(200, { code: 0, data: "ok" }),
        });

        const result = await request("/api/example", "POST", true, { value: 1 });

        expect(result).toEqual({
            code: undefined,
            data: "ok",
        });

        const options = getFetchMock().mock.calls[0][1];
        const headers = options.headers;

        expect(options.method).toBe("POST");
        expect(options.body).toBe(JSON.stringify({ value: 1 }));
        expect(headers["Content-Type"]).toBe("application/json");
        expect(headers.Authorization).toBe("Bearer token-1");
    });

    it("does not add authorization header when token is empty", async () => {
        // Tests the auth-header guard.
        // Even when the caller marks a request as authenticated, the helper
        // should not send an Authorization header if no token is available.
        getFetchMock().mockResolvedValue({
            ...createJsonResponse(200, { code: 0, data: "ok" }),
        });

        await request("/api/public", "GET", true);

        const options = getFetchMock().mock.calls[0][1];
        const headers = options.headers;

        expect(headers.Authorization).toBeUndefined();
    });

    it("throws unauthorized network error for 401 + code=2", async () => {
        // Tests the expired-auth handling module.
        // When a protected request returns the backend's unauthorized pattern
        // (HTTP 401 with code=2), the helper should:
        // 1. throw a NetworkError of type UNAUTHORIZED;
        // 2. preserve a stable error message;
        // 3. dispatch resetAuth() to clear the stale login state.
        mockGetState.mockReturnValue({
            auth: {
                token: "expired-token",
                name: "alice",
                role: "student",
            },
        });

        getFetchMock().mockResolvedValue({
            ...createJsonResponse(401, { code: 2, info: "expired" }),
        });

        const pending = request("/api/private", "GET", true);

        await expect(pending).rejects.toBeInstanceOf(NetworkError);
        await expect(pending).rejects.toMatchObject({
            type: NetworkErrorType.UNAUTHORIZED,
            message: "[401] expired",
        });
        expect(mockDispatch).toHaveBeenCalledWith(resetAuth());
    });

    it("does not reset auth for public requests that return 401 + code=2", async () => {
        // Tests the distinction between protected and public requests.
        // A public endpoint such as login may also return 401 + code=2, but in
        // that case the request layer must not wipe the current auth state.
        getFetchMock().mockResolvedValue({
            ...createJsonResponse(401, { code: 2, info: "bad credentials" }),
        });

        await expect(request("/api/login", "POST", false, { username: "alice" })).rejects.toMatchObject({
            type: NetworkErrorType.UNAUTHORIZED,
            message: "[401] bad credentials",
        });

        expect(mockDispatch).not.toHaveBeenCalled();
    });

    it("throws corrupted response for 200 + non-zero code", async () => {
        // Tests backend-contract validation.
        // If the HTTP request succeeds but the JSON payload reports a non-zero
        // application code, the helper should treat the response as corrupted
        // and surface a structured CORRUPTED_RESPONSE error.
        getFetchMock().mockResolvedValue({
            ...createJsonResponse(200, { code: 9, info: "bad payload" }),
        });

        await expect(request("/api/example", "GET", false)).rejects.toMatchObject({
            type: NetworkErrorType.CORRUPTED_RESPONSE,
            message: "[200] bad payload",
        });
    });

    it("throws stable error for empty response body instead of crashing on json parse", async () => {
        // Tests resilience against empty non-JSON error responses.
        // Instead of crashing while parsing, the helper should convert an empty
        // body into a stable UNKNOWN_ERROR with an explicit message.
        getFetchMock().mockResolvedValue({
            status: 502,
            headers: {
                get: () => "text/plain",
            },
            text: jest.fn().mockResolvedValue(""),
        });

        await expect(request("/api/example", "GET", false)).rejects.toMatchObject({
            type: NetworkErrorType.UNKNOWN_ERROR,
            message: "[502] Empty response body",
        });
    });

    it("throws stable error for non-json response body", async () => {
        // Tests resilience against plain-text or HTML backend failures.
        // If the response body is not JSON, the helper should surface that raw
        // body text through a stable UNKNOWN_ERROR message.
        getFetchMock().mockResolvedValue({
            status: 502,
            headers: {
                get: () => "text/html",
            },
            text: jest.fn().mockResolvedValue("<html>Bad Gateway</html>"),
        });

        await expect(request("/api/example", "GET", false)).rejects.toMatchObject({
            type: NetworkErrorType.UNKNOWN_ERROR,
            message: "[502] <html>Bad Gateway</html>",
        });
    });
});
