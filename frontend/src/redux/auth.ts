import { createSlice, PayloadAction } from "@reduxjs/toolkit";

// Store the minimal authenticated user information needed across the frontend.
export interface AuthState {
    token: string;
    name: string;
    role: string;
    userId: number | undefined;
    avatarUrl: string;
}

// Default to a fully signed-out auth state before hydration from browser storage.
const initialState: AuthState = {
    token: "",
    name: "",
    role: "",
    userId: undefined,
    avatarUrl: "",
};

const AUTH_STORAGE_KEY = "mentorfinder_auth";

const authStorage = () => window.localStorage;
const legacyAuthStorage = () => window.sessionStorage;

// Persist auth state to local storage so refreshed pages and new tabs share the
// same logged-in session. Session storage is cleared as legacy cleanup.
const saveAuthToStorage = (state: AuthState) => {
    if (typeof window === "undefined") {
        return;
    }

    legacyAuthStorage().removeItem(AUTH_STORAGE_KEY);

    // Remove the storage entry entirely when the auth state is effectively empty.
    if (state.token === "" && state.name === "" && state.role === "" && state.userId === undefined && state.avatarUrl === "") {
        authStorage().removeItem(AUTH_STORAGE_KEY);
        return;
    }

    authStorage().setItem(AUTH_STORAGE_KEY, JSON.stringify(state));
};

// Load the persisted auth snapshot from local storage and normalize missing fields safely.
export const loadAuthFromStorage = (): AuthState => {
    if (typeof window === "undefined") {
        return initialState;
    }

    const sources = [authStorage(), legacyAuthStorage()];

    for (const storage of sources) {
        const raw = storage.getItem(AUTH_STORAGE_KEY) ?? "";
        if (raw === "") {
            continue;
        }

        try {
            const parsed = JSON.parse(raw) as Partial<AuthState>;
            const nextState = {
                token: typeof parsed.token === "string" ? parsed.token : "",
                name: typeof parsed.name === "string" ? parsed.name : "",
                role: typeof parsed.role === "string" ? parsed.role : "",
                userId: typeof parsed.userId === "number" ? parsed.userId : undefined,
                avatarUrl: typeof parsed.avatarUrl === "string" ? parsed.avatarUrl : "",
            };

            if (storage !== authStorage()) {
                authStorage().setItem(AUTH_STORAGE_KEY, JSON.stringify(nextState));
                storage.removeItem(AUTH_STORAGE_KEY);
            }

            return nextState;
        }
        catch {
            // Corrupted auth data should be discarded so the app falls back to a clean signed-out state.
            storage.removeItem(AUTH_STORAGE_KEY);
        }
    }

    return initialState;
};

/**
 * @todo [Step 4] 请在下述一处代码缺失部分以正确设置 JWT 信息
 */
export const authSlice = createSlice({
    name: "auth",
    initialState,
    reducers: {
        // Replace the entire auth state from a hydrated storage snapshot.
        hydrateAuth: (state, action: PayloadAction<AuthState>) => {
            state.token = action.payload.token;
            state.name = action.payload.name;
            state.role = action.payload.role;
            state.userId = action.payload.userId;
            state.avatarUrl = action.payload.avatarUrl;
        },
        // Update the JWT token and persist the new auth snapshot.
        setToken: (state, action: PayloadAction<string>) => {
            state.token = action.payload;
            saveAuthToStorage({ token: state.token, name: state.name, role: state.role, userId: state.userId, avatarUrl: state.avatarUrl });
        },
        // Update the display name and persist the new auth snapshot.
        setName: (state, action: PayloadAction<string>) => {
            state.name = action.payload;
            saveAuthToStorage({ token: state.token, name: state.name, role: state.role, userId: state.userId, avatarUrl: state.avatarUrl });
        },
        // Update the user role and persist the new auth snapshot.
        setRole: (state, action: PayloadAction<string>) => {
            state.role = action.payload;
            saveAuthToStorage({ token: state.token, name: state.name, role: state.role, userId: state.userId, avatarUrl: state.avatarUrl });
        },
        // Update the user id and persist the new auth snapshot.
        setUserId: (state, action: PayloadAction<number | undefined>) => {
            state.userId = action.payload;
            saveAuthToStorage({ token: state.token, name: state.name, role: state.role, userId: state.userId, avatarUrl: state.avatarUrl });
        },
        // Update the avatar URL and persist the new auth snapshot.
        setAvatarUrl: (state, action: PayloadAction<string>) => {
            state.avatarUrl = action.payload;
            saveAuthToStorage({ token: state.token, name: state.name, role: state.role, userId: state.userId, avatarUrl: state.avatarUrl });
        },
        // Clear every auth field and remove the persisted auth snapshot.
        resetAuth: (state) => {
            state.token = "";
            state.name = "";
            state.role = "";
            state.userId = undefined;
            state.avatarUrl = "";
            saveAuthToStorage({ token: state.token, name: state.name, role: state.role, userId: state.userId, avatarUrl: state.avatarUrl });
        },
    },
});

// Export action creators used throughout the app for login, logout, hydration, and profile updates.
export const { hydrateAuth, setToken, setName, setRole, setUserId, setAvatarUrl, resetAuth } = authSlice.actions;
export default authSlice.reducer;
