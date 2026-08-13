import { FormEvent, RefCallback, useRef, useState } from "react";
import { LOGIN_FAILED } from "../constants/string";
import { INPUT_LIMITS } from "../constants/inputLimits";
import { useRouter } from "next/router";
import { setName, setRole, setToken, setUserId } from "../redux/auth";
import { useDispatch } from "react-redux";
import { buildRedirectHref, resolveRedirectTarget } from "../utils/authRedirect";
import { describeRequestError } from "../utils/errorMessage";

// Some backend endpoints return empty bodies or non-JSON text, so the login page parses them defensively.
const parseJsonSafely = async (response: Response) => {
    if (typeof response.text === "function") {
        const rawText = await response.text();
        if (rawText.trim() === "") {
            return {};
        }

        try {
            return JSON.parse(rawText) as Record<string, unknown>;
        }
        catch {
            return {
                info: rawText,
            };
        }
    }

    if (typeof response.json === "function") {
        try {
            return await response.json() as Record<string, unknown>;
        }
        catch {
            return {};
        }
    }

    return {};
};

// Render the sign-in page and wire the form to the login flow.
const LoginScreen = () => {
    const [userName, setUserName] = useState("");
    const [password, setPassword] = useState("");
    const [loginErrorMessage, setLoginErrorMessage] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const userNameInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const passwordInputRef = useRef<HTMLInputElement | undefined>(undefined);

    const router = useRouter();
    const dispatch = useDispatch();
    // Keep the post-login destination safe and relative even when the redirect query is malformed.
    const redirectTarget = resolveRedirectTarget(router.query.redirect);
    // Store the username input node so validation can move focus there when the field is empty.
    const bindUserNameInputRef: RefCallback<HTMLInputElement> = (node) => {
        userNameInputRef.current = node ?? undefined;
    };
    // Store the password input node so validation can move focus there when the field is empty.
    const bindPasswordInputRef: RefCallback<HTMLInputElement> = (node) => {
        passwordInputRef.current = node ?? undefined;
    };

    // Intercept native form submission and route it through the page's login workflow.
    const submitLogin = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        login();
    };

    // Validate credentials, call the login endpoint, and hydrate global auth state on success.
    const login = () => {
        if (userName.trim() === "") {
            userNameInputRef.current?.focus();
            return;
        }

        if (password === "") {
            passwordInputRef.current?.focus();
            return;
        }

        setLoginErrorMessage("");
        setSubmitting(true);
        // Login is handled directly here because the form needs to hydrate Redux auth state from the response.
        fetch("/api/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                username: userName,
                password,
            }),
        })
            .then((res) => parseJsonSafely(res))
            .then((res) => {
                if (Number(res.code) === 0 && typeof res.token === "string") {
                    // Persist the auth token plus lightweight profile fields used across the navbar and profile pages.
                    dispatch(setToken(res.token));
                    dispatch(setRole(typeof res.role === "string" ? res.role : ""));
                    dispatch(setUserId(typeof res.userId === "number" ? res.userId : undefined));

                    dispatch(setName(typeof res.username === "string" ? res.username : userName.trim()));

                    router.push(redirectTarget);
                }
                else {
                    setLoginErrorMessage(LOGIN_FAILED);
                }
            })
            .catch((err) => setLoginErrorMessage(describeRequestError(err)))
            .finally(() => setSubmitting(false));
    };

    return (
        <section className="loginAuthPage" aria-label="Sign in page">
            <button
                type="button"
                className="loginAuthBrand"
                aria-label="Go to home page"
                onClick={() => void router.push("/")}
            >
                <img
                    src="/mentorfinder-logo-1.svg"
                    alt=""
                    className="loginAuthBrandLogo"
                />
            </button>

            <h1 className="loginAuthTitle">Sign in to MentorFinder</h1>

            <form className="loginAuthForm" onSubmit={submitLogin}>
                <label className="loginAuthField">
                    <span className="loginAuthLabel">Username or email address</span>
                    <input
                        ref={bindUserNameInputRef}
                        type="text"
                        placeholder="Username or email address"
                        maxLength={INPUT_LIMITS.EMAIL}
                        value={userName}
                        onChange={(e) => setUserName(e.target.value)}
                    />
                </label>

                <label className="loginAuthField">
                    <div className="loginAuthPasswordRow">
                        <span className="loginAuthLabel">Password</span>
                        <a
                            href="/reset-password"
                            className="loginAuthInlineLink"
                            onClick={(event) => {
                                event.preventDefault();
                                if (submitting) {
                                    return;
                                }
                                void router.push("/reset-password");
                            }}
                        >
                            Forgot password?
                        </a>
                    </div>
                    <input
                        ref={bindPasswordInputRef}
                        type="password"
                        placeholder="Password"
                        maxLength={INPUT_LIMITS.PASSWORD}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                    />
                </label>

                {loginErrorMessage !== "" && (
                    <p className="loginAuthError">{loginErrorMessage}</p>
                )}

                <button
                    type="submit"
                    className="loginAuthSubmit"
                    disabled={submitting}
                >
                    {submitting ? "Signing in..." : "Sign in"}
                </button>
            </form>

            <p className="loginAuthSignup">
                New to MentorFinder?{" "}
                <a
                    href={buildRedirectHref("/register", router.query.redirect)}
                    className="loginAuthInlineLink"
                    onClick={(event) => {
                        event.preventDefault();
                        // Preserve the original redirect target when users switch from login to register.
                        if (submitting) {
                            return;
                        }
                        void router.push(buildRedirectHref("/register", router.query.redirect));
                    }}
                >
                    Create an account
                </a>
            </p>
        </section>
    );
};

export default LoginScreen;
