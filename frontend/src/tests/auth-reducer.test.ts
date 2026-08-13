import authReducer, {
    hydrateAuth,
    setToken,
    setName,
    setRole,
    setUserId,
    setAvatarUrl,
    resetAuth,
    loadAuthFromStorage,
} from "../redux/auth";

// These tests cover the auth reducer actions and storage helpers that are
// not tested in the existing auth.test.js (which focuses on page integration).
//
// Each test starts with a clean storage slate and a fresh reducer state
// derived from the initial state.

beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
});

describe("auth reducer: individual field actions", () => {
    // Tests the reducer update module for individual field setters.
    // Each setter should update only its own field while preserving the
    // rest of the auth state.

    it("sets userId to a numeric value", () => {
        const state = authReducer(undefined, setUserId(42));
        expect(state.userId).toBe(42);
    });

    it("sets userId to undefined", () => {
        const state = authReducer({ token: "t", name: "a", role: "s", userId: 42, avatarUrl: "" }, setUserId(undefined));
        expect(state.userId).toBeUndefined();
    });

    it("sets avatarUrl", () => {
        const state = authReducer(undefined, setAvatarUrl("/media/avatars/user-42.png"));
        expect(state.avatarUrl).toBe("/media/avatars/user-42.png");
    });

    it("sets avatarUrl to an empty string", () => {
        const state = authReducer({ token: "t", name: "a", role: "s", userId: 42, avatarUrl: "/img.png" }, setAvatarUrl(""));
        expect(state.avatarUrl).toBe("");
    });

    it("hydrateAuth replaces the entire auth state", () => {
        const state = authReducer(
            undefined,
            hydrateAuth({ token: "full-token", name: "bob", role: "mentor", userId: 99, avatarUrl: "/avatar/bob.png" }),
        );
        expect(state).toEqual({
            token: "full-token",
            name: "bob",
            role: "mentor",
            userId: 99,
            avatarUrl: "/avatar/bob.png",
        });
    });

    it("hydrateAuth preserves partial fields from the payload", () => {
        // hydrateAuth replaces the whole state, so partial payloads result
        // in undefined fields that should fall through.
        const state = authReducer(
            { token: "old", name: "old", role: "old", userId: 1, avatarUrl: "old.png" },
            hydrateAuth({ token: "new-token", name: "new", role: "", userId: undefined, avatarUrl: "" }),
        );
        expect(state).toEqual({
            token: "new-token",
            name: "new",
            role: "",
            userId: undefined,
            avatarUrl: "",
        });
    });

    it("preserves other fields when setting a single field", () => {
        const base = { token: "t", name: "a", role: "s", userId: 1, avatarUrl: "img.png" };
        const state = authReducer(base, setUserId(99));
        expect(state.name).toBe("a");
        expect(state.role).toBe("s");
        expect(state.token).toBe("t");
        expect(state.avatarUrl).toBe("img.png");
    });
});

describe("auth reducer: storage persistence on actions", () => {
    // Tests that each action that modifies auth state also persists the
    // updated state to localStorage via saveAuthToStorage.

    it("persists to localStorage when setToken is called", () => {
        authReducer(undefined, setToken("persist-token"));
        const rawToken = window.localStorage.getItem("mentorfinder_auth") as string;
        const stored = JSON.parse(rawToken);
        expect(stored.token).toBe("persist-token");
    });

    it("persists to localStorage when setName is called", () => {
        authReducer(undefined, setName("persist-name"));
        const rawName = window.localStorage.getItem("mentorfinder_auth") as string;
        const stored = JSON.parse(rawName);
        expect(stored.name).toBe("persist-name");
    });

    it("persists to localStorage when setRole is called", () => {
        authReducer(undefined, setRole("mentor"));
        const rawRole = window.localStorage.getItem("mentorfinder_auth") as string;
        const stored = JSON.parse(rawRole);
        expect(stored.role).toBe("mentor");
    });

    it("persists to localStorage when setUserId is called", () => {
        authReducer(undefined, setUserId(77));
        const rawUserId = window.localStorage.getItem("mentorfinder_auth") as string;
        const stored = JSON.parse(rawUserId);
        expect(stored.userId).toBe(77);
    });

    it("persists to localStorage when setAvatarUrl is called", () => {
        authReducer(undefined, setAvatarUrl("/avatar/test.png"));
        const rawAvatar = window.localStorage.getItem("mentorfinder_auth") as string;
        const stored = JSON.parse(rawAvatar);
        expect(stored.avatarUrl).toBe("/avatar/test.png");
    });

    it("removes storage entry when resetAuth clears the state", () => {
        // Set some auth data first, then reset. The storage entry should
        // be removed entirely, not set to an empty object.
        authReducer(undefined, setToken("temp-token"));
        expect(window.localStorage.getItem("mentorfinder_auth")).not.toBeNull();

        authReducer({ token: "temp-token", name: "a", role: "s", userId: 1, avatarUrl: "img.png" }, resetAuth());
        expect(window.localStorage.getItem("mentorfinder_auth")).toBeNull();
    });

    it("clears legacy session storage when setToken is called", () => {
        // simulate legacy data in sessionStorage
        window.sessionStorage.setItem("mentorfinder_auth", JSON.stringify({ token: "legacy" }));

        authReducer(undefined, setToken("new-token"));

        expect(window.sessionStorage.getItem("mentorfinder_auth")).toBeNull();
        expect(window.localStorage.getItem("mentorfinder_auth")).toContain("new-token");
    });
});

describe("loadAuthFromStorage", () => {
    // Tests the storage loading helper that rehydrates auth state on app
    // startup and page refresh.

    it("returns initialState when localStorage is empty", () => {
        const result = loadAuthFromStorage();
        expect(result).toEqual({
            token: "",
            name: "",
            role: "",
            userId: undefined,
            avatarUrl: "",
        });
    });

    it("loads a valid auth snapshot from localStorage", () => {
        window.localStorage.setItem(
            "mentorfinder_auth",
            JSON.stringify({ token: "x", name: "y", role: "z", userId: 10, avatarUrl: "/img.png" }),
        );

        const result = loadAuthFromStorage();
        expect(result).toEqual({
            token: "x",
            name: "y",
            role: "z",
            userId: 10,
            avatarUrl: "/img.png",
        });
    });

    it("normalizes a partial snapshot with missing fields", () => {
        // If the stored JSON has a missing or wrong-type field, the loader
        // should fall back to defaults for that field instead of crashing.
        window.localStorage.setItem(
            "mentorfinder_auth",
            JSON.stringify({ token: "x" }),
        );

        const result = loadAuthFromStorage();
        expect(result).toEqual({
            token: "x",
            name: "",
            role: "",
            userId: undefined,
            avatarUrl: "",
        });
    });

    it("normalizes a snapshot with invalid field types", () => {
        // userId should be a number or undefined; a string value should be
        // discarded.
        window.localStorage.setItem(
            "mentorfinder_auth",
            JSON.stringify({ token: "t", name: "n", role: "r", userId: "not-a-number", avatarUrl: "a" }),
        );

        const result = loadAuthFromStorage();
        expect(result.userId).toBeUndefined();
        expect(result.token).toBe("t");
    });

    it("returns initialState for corrupted JSON data", () => {
        // Corrupted JSON should be silently discarded and the corrupted
        // key removed from storage.
        window.localStorage.setItem("mentorfinder_auth", "not-valid-json{{}}");

        const result = loadAuthFromStorage();
        expect(result).toEqual({
            token: "",
            name: "",
            role: "",
            userId: undefined,
            avatarUrl: "",
        });
        // The corrupted entry should be removed from storage.
        expect(window.localStorage.getItem("mentorfinder_auth")).toBeNull();
    });

    it("migrates legacy auth from sessionStorage to localStorage", () => {
        window.sessionStorage.setItem(
            "mentorfinder_auth",
            JSON.stringify({ token: "migrated-token", name: "alice", role: "student", userId: 1, avatarUrl: "" }),
        );

        const result = loadAuthFromStorage();
        expect(result.token).toBe("migrated-token");

        // After migration, the data should be in localStorage and removed
        // from sessionStorage.
        expect(window.localStorage.getItem("mentorfinder_auth")).toContain("migrated-token");
        expect(window.sessionStorage.getItem("mentorfinder_auth")).toBeNull();
    });

    it("clears corrupted legacy sessionStorage entry during migration attempt", () => {
        window.sessionStorage.setItem("mentorfinder_auth", "broken{json");

        const result = loadAuthFromStorage();
        expect(result.token).toBe("");
        expect(window.sessionStorage.getItem("mentorfinder_auth")).toBeNull();
    });

    it("prefers localStorage over sessionStorage when both exist", () => {
        window.localStorage.setItem(
            "mentorfinder_auth",
            JSON.stringify({ token: "local", name: "", role: "", userId: undefined, avatarUrl: "" }),
        );
        window.sessionStorage.setItem(
            "mentorfinder_auth",
            JSON.stringify({ token: "session", name: "", role: "", userId: undefined, avatarUrl: "" }),
        );

        const result = loadAuthFromStorage();
        // localStorage is checked first, and since it has valid data the
        // sessionStorage entry is never read.
        expect(result.token).toBe("local");
    });
});
