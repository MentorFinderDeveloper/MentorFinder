import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRouter } from "next/router";
import { useDispatch } from "react-redux";
import {
    LOGIN_FAILED,
    REGISTER_CODE_INVALID,
    REGISTER_CODE_REQUIRED,
    REGISTER_CODE_SEND_FAILED,
    REGISTER_CODE_SENT,
    REGISTER_EMAIL_INVALID,
    REGISTER_EMAIL_TAKEN,
    REGISTER_FAILED,
    REGISTER_PASSWORD_MISMATCH,
    REGISTER_PASSWORD_WEAK,
    REGISTER_USERNAME_TAKEN,
    REGISTER_USERNAME_INVALID,
    RESET_PASSWORD_EMAIL_NOT_FOUND,
    RESET_PASSWORD_SUCCESS,
} from "../constants/string";
import LoginScreen from "../pages/login";
import RegisterScreen from "../pages/register";
import ResetPasswordScreen from "../pages/reset-password";
import authReducer, { loadAuthFromStorage, resetAuth, setName, setRole, setToken } from "../redux/auth";

// Mock Next.js routing so the tests can inspect navigation decisions without
// relying on the real browser/router runtime.
jest.mock("next/router", () => ({
    useRouter: jest.fn(),
}));

// Mock Redux dispatch so UI tests can verify which auth actions are emitted
// after login/register flows complete.
jest.mock("react-redux", () => ({
    useDispatch: jest.fn(),
}));

describe("auth reducer", () => {
    beforeEach(() => {
        window.localStorage.clear();
        window.sessionStorage.clear();
    });

    it("returns initial state for unknown action", () => {
        // Tests the reducer default-state module.
        // When an unrelated action is received, the reducer should return the
        // stable initial auth state instead of mutating anything unexpectedly.
        const state = authReducer(undefined, { type: "unknown/action" });

        expect(state).toEqual({
            token: "",
            name: "",
            role: "",
            userId: undefined,
            avatarUrl: "",
        });
    });

    it("sets token and user name", () => {
        // Tests the reducer update module for successful authentication.
        // This verifies that individual auth actions correctly write token,
        // username, and role into the Redux auth slice.
        let state = authReducer(undefined, { type: "unknown/action" });

        state = authReducer(state, setToken("jwt-token"));
        state = authReducer(state, setName("alice"));
        state = authReducer(state, setRole("student"));

        expect(state).toEqual({
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: undefined,
            avatarUrl: "",
        });
    });

    it("resets auth state", () => {
        // Tests the reducer reset module.
        // After logout or auth cleanup, all persisted auth fields should be
        // restored to their empty initial values.
        const stateWithAuth = {
            token: "jwt-token",
            name: "alice",
            role: "admin",
            userId: 42,
            avatarUrl: "/media/avatars/user-42.png",
        };

        const state = authReducer(stateWithAuth, resetAuth());

        expect(state).toEqual({
            token: "",
            name: "",
            role: "",
            userId: undefined,
            avatarUrl: "",
        });
    });

    it("persists auth in local storage and clears legacy session storage", () => {
        window.localStorage.setItem("mentorfinder_auth", JSON.stringify({ token: "old-token" }));

        authReducer(undefined, setToken("jwt-token"));

        expect(window.sessionStorage.getItem("mentorfinder_auth")).toBeNull();
        expect(window.localStorage.getItem("mentorfinder_auth")).toContain("jwt-token");
        expect(loadAuthFromStorage().token).toBe("jwt-token");
    });

    it("hydrates auth from legacy session storage and migrates it to local storage", () => {
        window.sessionStorage.setItem("mentorfinder_auth", JSON.stringify({
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
            avatarUrl: "",
        }));

        expect(loadAuthFromStorage()).toEqual({
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
            avatarUrl: "",
        });
        expect(window.sessionStorage.getItem("mentorfinder_auth")).toBeNull();
        expect(window.localStorage.getItem("mentorfinder_auth")).toContain("jwt-token");
    });
});

describe("LoginScreen", () => {
    const mockPush = jest.fn();
    const mockDispatch = jest.fn();
    const mockRouter = {
        push: mockPush,
        query: {},
    };

    beforeEach(() => {
        // Reset router/dispatch mocks and install a fresh fetch mock before
        // every login test so each case runs with isolated state.
        mockPush.mockReset();
        mockDispatch.mockReset();
        mockRouter.query = {};

        useRouter.mockReturnValue(mockRouter);
        useDispatch.mockReturnValue(mockDispatch);

        globalThis.fetch = jest.fn();
        jest.spyOn(globalThis, "alert").mockImplementation(() => {});
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it("dispatches auth info and navigates home when login succeeds", async () => {
        // Tests the main successful login module:
        // the page should submit credentials, store returned auth data in
        // Redux, and redirect the user to the default landing page.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "jwt-token", username: "alice", role: "admin" }),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledTimes(1);
        });

        expect(globalThis.fetch).toHaveBeenCalledWith("/api/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                username: "alice",
                password: "abc12345",
            }),
        });

        await waitFor(() => {
            expect(mockDispatch).toHaveBeenCalledWith(setToken("jwt-token"));
            expect(mockDispatch).toHaveBeenCalledWith(setRole("admin"));
            expect(mockDispatch).toHaveBeenCalledWith(setName("alice"));
            expect(mockPush).toHaveBeenCalledWith("/");
        });
        expect(globalThis.alert).not.toHaveBeenCalled();
    });

    it("uses returned username as display name when login is submitted with email", async () => {
        // Tests the login identity normalization module.
        // Even if the user signs in with an email address, the UI should use
        // the backend-returned username as the stored display name.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "jwt-token", username: "alice", role: "student" }),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(mockDispatch).toHaveBeenCalledWith(setName("alice"));
        });
    });

    it("submits login form when the form is submitted", async () => {
        // Tests form submission wiring.
        // The login flow should work not only through button click, but also
        // through native form submission semantics.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "jwt-token", role: "student" }),
        });

        const { container } = render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.submit(container.querySelector("form"));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    username: "alice",
                    password: "abc12345",
                }),
            });
        });
    });

    it("keeps sign in enabled and focuses username when both fields are empty", () => {
        // Tests client-side required-field guidance for login.
        // If both fields are empty, the page should not submit and should move
        // focus to the username/email input to guide the user.
        render(<LoginScreen />);

        const userNameInput = screen.getByPlaceholderText("Username or email address");
        const signInButton = screen.getByRole("button", { name: "Sign in" });

        expect(signInButton).toBeEnabled();
        fireEvent.click(signInButton);

        expect(userNameInput).toHaveFocus();
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it("focuses password when username is filled but password is missing", () => {
        // Tests the second validation step in the login form.
        // Once the username is present, the next missing required field should
        // receive focus instead of allowing a network request.
        render(<LoginScreen />);

        const userNameInput = screen.getByPlaceholderText("Username or email address");
        const passwordInput = screen.getByPlaceholderText("Password");

        fireEvent.change(userNameInput, { target: { value: "alice" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        expect(passwordInput).toHaveFocus();
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it("redirects to the requested relative path after successful login", async () => {
        // Tests safe post-login redirect handling.
        // If a relative redirect target is present in the query string, the
        // page should send the user there after authentication succeeds.
        mockRouter.query = {
            redirect: "/profile",
        };
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "jwt-token", role: "student" }),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith("/profile");
        });
    });

    it("falls back to home after successful login when redirect is unsafe", async () => {
        // Tests redirect sanitization.
        // Unsafe redirect targets such as absolute external URLs must be
        // ignored to prevent open-redirect behavior.
        mockRouter.query = {
            redirect: "https://evil.example.com",
        };
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "jwt-token", role: "student" }),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith("/");
        });
    });

    it("shows failure message and stays on page when login fails", async () => {
        // Tests the generic login failure module.
        // A failed backend response should render a stable error message and
        // must not navigate away from the login screen.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 1 }),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(screen.getByText(LOGIN_FAILED)).toBeInTheDocument();
        });

        expect(mockPush).not.toHaveBeenCalled();
    });

    it("shows stable failure message when login is rejected for banned user", async () => {
        // Tests error normalization for a specific backend rejection reason.
        // Even if the backend exposes a banned-user detail, the UI should show
        // the stable login failure message rather than leaking backend wording.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 3, info: "User is banned" }),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "banned_user" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(screen.getByText(LOGIN_FAILED)).toBeInTheDocument();
        });

        expect(mockPush).not.toHaveBeenCalled();
    });

    it("does not crash when login response body is empty", async () => {
        // Tests resilience against malformed empty responses.
        // If the backend returns an empty body, the page should still fail
        // gracefully instead of throwing or partially updating auth state.
        globalThis.fetch.mockResolvedValue({
            text: jest.fn().mockResolvedValue(""),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(screen.getByText(LOGIN_FAILED)).toBeInTheDocument();
        });

        expect(mockPush).not.toHaveBeenCalled();
        expect(mockDispatch).not.toHaveBeenCalled();
    });

    it("shows stable failure message when login response is non-json text", async () => {
        // Tests resilience against non-JSON login responses.
        // HTML or gateway text should be treated as a failure case with the
        // same stable user-facing error message.
        globalThis.fetch.mockResolvedValue({
            text: jest.fn().mockResolvedValue("<html>502 Bad Gateway</html>"),
        });

        render(<LoginScreen />);

        fireEvent.change(screen.getByPlaceholderText("Username or email address"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

        await waitFor(() => {
            expect(screen.getByText(LOGIN_FAILED)).toBeInTheDocument();
        });

        expect(mockPush).not.toHaveBeenCalled();
        expect(mockDispatch).not.toHaveBeenCalled();
    });

    it("renders the MentorFinder login shell and placeholder actions", () => {
        // Tests the static login page shell.
        // This verifies that the intended branding, CTA layout, and supported
        // entry points are present, while unsupported placeholder actions stay
        // hidden from the current product UI.
        render(<LoginScreen />);

        expect(screen.getByRole("heading", { name: "Sign in to MentorFinder" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
        expect(screen.queryByRole("button", { name: "Continue with TsinghuaID" })).not.toBeInTheDocument();
        expect(screen.getByText("New to MentorFinder?")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Create an account" })).toBeInTheDocument();
        expect(screen.queryByText("Continue with Apple")).not.toBeInTheDocument();
        expect(screen.queryByText("Sign in with a passkey")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "返回首页" })).not.toBeInTheDocument();
    });

    it("navigates to register page when clicking account creation link", () => {
        // Tests the login-to-register navigation module.
        // Users without an account should be able to move to the signup page.
        render(<LoginScreen />);

        fireEvent.click(screen.getByRole("link", { name: "Create an account" }));

        expect(mockPush).toHaveBeenCalledWith("/register");
    });

    it("navigates to home page when clicking the login logo", () => {
        // Tests logo-based navigation from the login screen back to home.
        render(<LoginScreen />);

        fireEvent.click(screen.getByRole("button", { name: "Go to home page" }));

        expect(mockPush).toHaveBeenCalledWith("/");
    });

    it("preserves redirect when navigating from login to register", () => {
        // Tests redirect propagation between auth pages.
        // If login was opened with a redirect target, that target should be
        // preserved when the user chooses to register instead.
        mockRouter.query = {
            redirect: "/follows",
        };

        render(<LoginScreen />);

        fireEvent.click(screen.getByRole("link", { name: "Create an account" }));

        expect(mockPush).toHaveBeenCalledWith("/register?redirect=%2Ffollows");
    });

    it("navigates to reset-password page when clicking forgot password", () => {
        // Tests entry into the password recovery module from the login page.
        render(<LoginScreen />);

        fireEvent.click(screen.getByRole("link", { name: "Forgot password?" }));

        expect(mockPush).toHaveBeenCalledWith("/reset-password");
    });
});

describe("ResetPasswordScreen", () => {
    const mockPush = jest.fn();
    const mockDispatch = jest.fn();
    const mockRouter = {
        push: mockPush,
        query: {},
    };

    beforeEach(() => {
        // Reset navigation, dispatch, and fetch mocks for the password-reset
        // suite so each case observes only its own interactions.
        mockPush.mockReset();
        mockDispatch.mockReset();
        mockRouter.query = {};

        useRouter.mockReturnValue(mockRouter);
        useDispatch.mockReturnValue(mockDispatch);

        globalThis.fetch = jest.fn();
    });

    afterEach(() => {
        jest.useRealTimers();
        jest.restoreAllMocks();
    });

    it("requests a password reset verification code for an existing email", async () => {
        // Tests the password-reset code request module.
        // The page should call the verification-code endpoint with the email
        // and show the success message when the backend accepts the request.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, cooldownSeconds: 60 }),
        });

        render(<ResetPasswordScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Send verification code" }));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/password-reset/verification-code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: "alice@example.com" }),
            });
        });
        expect(await screen.findByText(REGISTER_CODE_SENT)).toBeInTheDocument();
    });

    it("resets password with email code and returns to login", async () => {
        // Tests the full password reset completion workflow:
        // submit email + verification code + new password, show the success
        // message, then redirect back to login after the short delay.
        jest.useFakeTimers();
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0 }),
        });

        render(<ResetPasswordScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.change(screen.getByPlaceholderText("New password"), { target: { value: "newpass123" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm new password"), { target: { value: "newpass123" } });
        fireEvent.click(screen.getByRole("button", { name: "Reset password" }));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/password-reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    email: "alice@example.com",
                    password: "newpass123",
                    verificationCode: "123456",
                }),
            });
        });
        expect(await screen.findByText(RESET_PASSWORD_SUCCESS)).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(600);
        });
        expect(mockPush).toHaveBeenCalledWith("/login");
    });

    it("shows email-not-found message when reset code request is rejected", async () => {
        // Tests the rejected reset-code request module.
        // If the backend reports that the email does not exist, the page
        // should show the dedicated "email not found" error message.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 2 }),
        });

        render(<ResetPasswordScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "missing@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Send verification code" }));

        expect(await screen.findByText(RESET_PASSWORD_EMAIL_NOT_FOUND)).toBeInTheDocument();
    });
});

describe("RegisterScreen", () => {
    const mockPush = jest.fn();
    const mockDispatch = jest.fn();
    const mockRouter = {
        push: mockPush,
        query: {},
    };

    beforeEach(() => {
        // Reset navigation, dispatch, fetch, and alert spies before each
        // register test to keep the signup scenarios isolated.
        mockPush.mockReset();
        mockDispatch.mockReset();
        mockRouter.query = {};

        useRouter.mockReturnValue(mockRouter);
        useDispatch.mockReturnValue(mockDispatch);

        globalThis.fetch = jest.fn();
        jest.spyOn(globalThis, "alert").mockImplementation(() => {});
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it("keeps create account enabled and focuses email when the form is empty", () => {
        // Tests the first required-field validation step in signup.
        // With a fully empty form, submission should be blocked and focus
        // should move to the email field.
        render(<RegisterScreen />);

        const emailInput = screen.getByPlaceholderText("Email");
        const createAccountButton = screen.getByRole("button", { name: "Create account" });

        expect(createAccountButton).toBeEnabled();
        fireEvent.click(createAccountButton);

        expect(emailInput).toHaveFocus();
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it("focuses password when email is filled but password is missing", () => {
        // Tests progressive validation in the register form.
        // Once email is present, the next required missing field should take
        // focus before any backend request is sent.
        render(<RegisterScreen />);

        const emailInput = screen.getByPlaceholderText("Email");
        const passwordInput = screen.getByPlaceholderText("Password");

        fireEvent.change(emailInput, { target: { value: "alice@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        expect(passwordInput).toHaveFocus();
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it("focuses confirm password when password is filled but confirmation is missing", () => {
        // Tests confirmation-field guidance.
        // If the password exists but confirmation is missing, focus should move
        // to the confirmation input to complete the pair.
        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        expect(screen.getByPlaceholderText("Confirm your password")).toHaveFocus();
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it("focuses username when other fields are valid but username is missing", () => {
        // Tests late-stage required-field validation in signup.
        // After email and passwords are valid, the form should still block
        // submission until the username field is completed.
        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        expect(screen.getByPlaceholderText("Username")).toHaveFocus();
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it("shows weak-password hint after password input is blurred", () => {
        // Tests password-strength hint rendering.
        // The weak-password message should appear after the field has been
        // interacted with and blurred, not immediately on each keystroke.
        render(<RegisterScreen />);

        const passwordInput = screen.getByPlaceholderText("Password");

        fireEvent.change(passwordInput, { target: { value: "abc12" } });
        expect(screen.queryByText(REGISTER_PASSWORD_WEAK)).not.toBeInTheDocument();

        fireEvent.blur(passwordInput);

        expect(screen.getByText(REGISTER_PASSWORD_WEAK)).toBeInTheDocument();
    });

    it("prioritizes mismatch hint over weak-password hint", () => {
        // Tests validation message priority.
        // When both "weak password" and "password mismatch" could apply, the
        // mismatch message should take precedence because it blocks correction.
        render(<RegisterScreen />);

        const passwordInput = screen.getByPlaceholderText("Password");
        const confirmPasswordInput = screen.getByPlaceholderText("Confirm your password");

        fireEvent.change(passwordInput, { target: { value: "abc12" } });
        fireEvent.blur(passwordInput);

        fireEvent.change(confirmPasswordInput, { target: { value: "zzz" } });
        fireEvent.blur(confirmPasswordInput);

        expect(screen.getByText(REGISTER_PASSWORD_MISMATCH)).toBeInTheDocument();
        expect(screen.queryByText(REGISTER_PASSWORD_WEAK)).not.toBeInTheDocument();
    });

    it("shows invalid-email hint after email input is blurred", () => {
        // Tests client-side email format validation in signup.
        render(<RegisterScreen />);

        const emailInput = screen.getByPlaceholderText("Email");

        fireEvent.change(emailInput, { target: { value: "invalid" } });
        fireEvent.blur(emailInput);

        expect(screen.getByText(REGISTER_EMAIL_INVALID)).toBeInTheDocument();
    });

    it("shows invalid-username hint after username input is blurred", () => {
        // Tests client-side username format validation in signup.
        render(<RegisterScreen />);

        const usernameInput = screen.getByPlaceholderText("Username");

        fireEvent.change(usernameInput, { target: { value: "bad user!" } });
        fireEvent.blur(usernameInput);

        expect(screen.getByText(REGISTER_USERNAME_INVALID)).toBeInTheDocument();
    });

    it("dispatches auth info and navigates home when register succeeds", async () => {
        // Tests the main successful registration module:
        // submit all required signup data, trim the username, persist returned
        // auth info to Redux, and redirect to the home page.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "register-token", role: "student" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: " alice " } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });

        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledTimes(1);
        });

        expect(globalThis.fetch).toHaveBeenCalledWith("/api/register", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                username: "alice",
                password: "abc12345",
                email: "alice@example.com",
                verificationCode: "123456",
            }),
        });

        await waitFor(() => {
            expect(mockDispatch).toHaveBeenCalledWith(setToken("register-token"));
            expect(mockDispatch).toHaveBeenCalledWith(setRole("student"));
            expect(mockDispatch).toHaveBeenCalledWith(setName("alice"));
            expect(mockPush).toHaveBeenCalledWith("/");
        });
        expect(globalThis.alert).not.toHaveBeenCalled();
    });

    it("submits register form when the form is submitted", async () => {
        // Tests native form submission wiring for signup.
        // The register request should be triggered through the form submit
        // event, not only through clicking the button.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "register-token", role: "student" }),
        });

        const { container } = render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.submit(container.querySelector(".registerAuthFormWrap form"));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/register", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    username: "alice",
                    password: "abc12345",
                    email: "alice@example.com",
                    verificationCode: "123456",
                }),
            });
        });
    });

    it("still navigates home after successful register when redirect is present", async () => {
        // Tests the post-register navigation policy.
        // Unlike login, registration currently ignores redirect targets and
        // still returns the user to the home page after success.
        mockRouter.query = {
            redirect: "/follows",
        };
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "register-token", role: "student" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith("/");
        });
    });

    it("falls back to home after successful register when redirect is unsafe", async () => {
        // Tests the same safe navigation policy under an explicitly unsafe
        // redirect value, confirming that signup still ends at home.
        mockRouter.query = {
            redirect: "//evil.example.com",
        };
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "register-token", role: "student" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith("/");
        });
    });

    it("does not crash when register response body is empty", async () => {
        // Tests resilience against empty backend responses during signup.
        // The page should show a stable register failure message instead of
        // navigating or dispatching partial auth state.
        globalThis.fetch.mockResolvedValue({
            text: jest.fn().mockResolvedValue(""),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_FAILED)).toBeInTheDocument();
        });

        expect(mockPush).not.toHaveBeenCalled();
        expect(mockDispatch).not.toHaveBeenCalled();
    });

    it("shows stable message when register response is non-json text", async () => {
        // Tests resilience against malformed non-JSON register responses.
        globalThis.fetch.mockResolvedValue({
            text: jest.fn().mockResolvedValue("<html>502 Bad Gateway</html>"),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_FAILED)).toBeInTheDocument();
        });

        expect(mockPush).not.toHaveBeenCalled();
        expect(mockDispatch).not.toHaveBeenCalled();
    });

    it("shows a clear message when register username is already used", async () => {
        // Tests backend-to-UI mapping for duplicate username errors.
        // A backend duplicate-username code should become the specific
        // user-facing "username already taken" message.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 3, info: "User already exists" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_USERNAME_TAKEN)).toBeInTheDocument();
        });
        expect(screen.queryByText(REGISTER_USERNAME_INVALID)).not.toBeInTheDocument();

        expect(mockPush).not.toHaveBeenCalled();
        expect(mockDispatch).not.toHaveBeenCalled();
    });

    it("shows a clear message when register email is already used", async () => {
        // Tests backend-to-UI mapping for duplicate email errors.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 4, info: "Email already exists" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_EMAIL_TAKEN)).toBeInTheDocument();
        });
        expect(screen.queryByText(REGISTER_FAILED)).not.toBeInTheDocument();

        expect(mockPush).not.toHaveBeenCalled();
        expect(mockDispatch).not.toHaveBeenCalled();
    });

    it("replaces invalid-username hint with duplicate-username hint when duplicate is triggered later", async () => {
        // Tests validation state replacement.
        // A local "invalid username" hint should be replaced by the backend
        // duplicate-username error once the input becomes valid and submit runs.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 3, info: "User already exists" }),
        });

        render(<RegisterScreen />);

        const usernameInput = screen.getByPlaceholderText("Username");
        fireEvent.change(usernameInput, { target: { value: "bad user!" } });
        fireEvent.blur(usernameInput);
        expect(screen.getByText(REGISTER_USERNAME_INVALID)).toBeInTheDocument();

        fireEvent.change(usernameInput, { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_USERNAME_TAKEN)).toBeInTheDocument();
        });
        expect(screen.queryByText(REGISTER_USERNAME_INVALID)).not.toBeInTheDocument();
    });

    it("clears duplicate-username hint when username changes", async () => {
        // Tests stale-error cleanup for signup.
        // After a duplicate-username error is shown, editing the username
        // should clear that error so the UI reflects the new input state.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 3, info: "User already exists" }),
        });

        render(<RegisterScreen />);

        const usernameInput = screen.getByPlaceholderText("Username");
        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(usernameInput, { target: { value: "alice" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_USERNAME_TAKEN)).toBeInTheDocument();
        });

        fireEvent.change(usernameInput, { target: { value: "alice-new" } });

        expect(screen.queryByText(REGISTER_USERNAME_TAKEN)).not.toBeInTheDocument();
    });

    it("renders the MentorFinder signup shell and marketing content", () => {
        // Tests the static signup page shell and marketing module.
        // This verifies the expected branding/content blocks and confirms that
        // unsupported external-auth or unrelated profile controls are absent.
        render(<RegisterScreen />);

        expect(screen.getByRole("heading", { name: "Sign up for MentorFinder" })).toBeInTheDocument();
        expect(screen.getByText("Already have an account?")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Sign in →" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Continue with TsinghuaID" })).not.toBeInTheDocument();
        expect(screen.getByText("Create your account")).toBeInTheDocument();
        expect(screen.getByText("Explore MentorFinder's unique features for both students and teachers")).toBeInTheDocument();
        expect(screen.getByText("See what's included")).toBeInTheDocument();
        expect(screen.queryByText("Continue with Apple")).not.toBeInTheDocument();
        expect(screen.queryByText("Your Country/Region")).not.toBeInTheDocument();
        expect(screen.queryByText("Email preferences")).not.toBeInTheDocument();
    });

    it("toggles the marketing feature list", () => {
        // Tests the expandable marketing-details module.
        // The feature list should appear when expanded, remain during the close
        // animation window, and disappear after the collapse timer completes.
        jest.useFakeTimers();
        try {
            render(<RegisterScreen />);

            const toggleButton = screen.getByText("See what's included").closest("summary");
            expect(screen.queryByText("Discover mentors by research interests")).not.toBeInTheDocument();
            expect(toggleButton).not.toBeNull();

            fireEvent.click(toggleButton);
            expect(toggleButton).toHaveAttribute("aria-expanded", "true");
            expect(screen.getByText("Discover mentors by research interests")).toBeInTheDocument();
            expect(screen.getByText("Track papers on a living timeline")).toBeInTheDocument();

            fireEvent.click(toggleButton);
            expect(toggleButton).toHaveAttribute("aria-expanded", "false");
            expect(screen.getByText("Discover mentors by research interests")).toBeInTheDocument();

            act(() => {
                jest.advanceTimersByTime(500);
            });
            expect(screen.queryByText("Discover mentors by research interests")).not.toBeInTheDocument();
        }
        finally {
            jest.useRealTimers();
        }
    });

    it("navigates to login page when clicking sign-in link", () => {
        // Tests signup-to-login navigation for existing users.
        render(<RegisterScreen />);

        fireEvent.click(screen.getByRole("link", { name: "Sign in →" }));

        expect(mockPush).toHaveBeenCalledWith("/login");
    });

    it("navigates to home page when clicking the signup logo", () => {
        // Tests logo-based navigation from the signup page back to home.
        render(<RegisterScreen />);

        fireEvent.click(screen.getByRole("button", { name: "Go to home page" }));

        expect(mockPush).toHaveBeenCalledWith("/");
    });

    it("preserves redirect when navigating from register to login", () => {
        // Tests redirect propagation when switching from register to login.
        mockRouter.query = {
            redirect: "/profile",
        };

        render(<RegisterScreen />);

        fireEvent.click(screen.getByRole("link", { name: "Sign in →" }));

        expect(mockPush).toHaveBeenCalledWith("/login?redirect=%2Fprofile");
    });

    it("renders the verification code field and send-code button", () => {
        // Tests that the email-verification module is present in the register
        // form: both the code input and the send-code action must be rendered.
        render(<RegisterScreen />);

        expect(screen.getByPlaceholderText("Enter the 6-digit code")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Send verification code" })).toBeInTheDocument();
    });

    it("disables send-code button when email is empty", () => {
        // Tests the precondition guard for requesting a verification code.
        // The send-code action must stay disabled until an email is provided.
        render(<RegisterScreen />);

        expect(screen.getByRole("button", { name: "Send verification code" })).toBeDisabled();
    });

    it("requests verification code from backend when send-code button is clicked", async () => {
        // Tests the signup verification-code request module.
        // Clicking the send-code button should call the backend with the email
        // and then show the "code sent" confirmation message.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, cooldownSeconds: 60 }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "newuser@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Send verification code" }));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/register/verification-code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: "newuser@example.com" }),
            });
        });

        await waitFor(() => {
            expect(screen.getByText(REGISTER_CODE_SENT)).toBeInTheDocument();
        });
    });

    it("blocks registration when verification code is missing", async () => {
        // Tests the register pre-submit gate for email verification.
        // Even if the main form fields are valid, signup must not proceed until
        // the verification code field is filled.
        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "newuser@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "newuser" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        expect(screen.getByText(REGISTER_CODE_REQUIRED)).toBeInTheDocument();
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it("shows code-invalid error when backend returns code 5 from register", async () => {
        // Tests backend-to-UI mapping for invalid or expired verification code
        // errors returned by the register endpoint.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 5, info: "Verification code is invalid or expired" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "newuser@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "newuser" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "999999" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_CODE_INVALID)).toBeInTheDocument();
        });
        expect(mockPush).not.toHaveBeenCalled();
    });

    it("includes the verification code in the register body", async () => {
        // Tests request payload completeness for signup.
        // The verification code must be included in the final register request
        // body, not only stored in local UI state.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, token: "register-token", role: "student" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "verified@example.com" } });
        fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Confirm your password"), { target: { value: "abc12345" } });
        fireEvent.change(screen.getByPlaceholderText("Username"), { target: { value: "verified" } });
        fireEvent.change(screen.getByPlaceholderText("Enter the 6-digit code"), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));

        await waitFor(() => {
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: "verified",
                    password: "abc12345",
                    email: "verified@example.com",
                    verificationCode: "123456",
                }),
            });
        });
    });

    it("disables send-code button and shows resend countdown after successful send", async () => {
        // Tests the resend cooldown module for signup verification emails.
        // After a successful send, the button should be disabled and display a
        // countdown so the user cannot spam the endpoint immediately.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 0, cooldownSeconds: 60 }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "fresh@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Send verification code" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_CODE_SENT)).toBeInTheDocument();
        });

        const resendButton = screen.getByRole("button", { name: "Send verification code" });
        expect(resendButton).toBeDisabled();
        expect(resendButton.textContent).toMatch(/Resend \(\d+s\)/);
    });

    it("shows code-send-failed when backend returns unknown error from verification-code endpoint", async () => {
        // Tests the error branch of the signup verification-code module.
        // Unknown backend failures while sending the code should map to the
        // stable "send verification code failed" user-facing message.
        globalThis.fetch.mockResolvedValue({
            json: jest.fn().mockResolvedValue({ code: 7, info: "smtp down" }),
        });

        render(<RegisterScreen />);

        fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "fresh@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Send verification code" }));

        await waitFor(() => {
            expect(screen.getByText(REGISTER_CODE_SEND_FAILED)).toBeInTheDocument();
        });
    });
});
