import { FormEvent, RefCallback, useEffect, useRef, useState } from "react";
import {
    REGISTER_CODE_COOLDOWN,
    REGISTER_CODE_INVALID,
    REGISTER_CODE_REQUIRED,
    REGISTER_CODE_SEND_FAILED,
    REGISTER_CODE_SENT,
    REGISTER_EMAIL_INVALID,
    REGISTER_EMAIL_TAKEN,
    REGISTER_FAILED,
    REGISTER_PASSWORD_MISMATCH,
    REGISTER_PASSWORD_WEAK,
    REGISTER_SEND_CODE_BUTTON,
    REGISTER_SEND_CODE_RESEND,
    REGISTER_USERNAME_TAKEN,
    REGISTER_USERNAME_INVALID,
} from "../constants/string";
import { INPUT_LIMITS } from "../constants/inputLimits";
import { useRouter } from "next/router";
import { setName, setRole, setToken, setUserId } from "../redux/auth";
import { useDispatch } from "react-redux";
import { buildRedirectHref } from "../utils/authRedirect";
import { describeRequestError } from "../utils/errorMessage";

// Registration validates usernames locally before asking the backend to avoid unnecessary requests.
const USERNAME_REGEX = /^[\w-]+$/;
const EMAIL_REGEX = /^[\w.%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i;
const FEATURE_LIST_CLOSE_ANIMATION_MS = 500;
const USERNAME_DUPLICATE_ERROR = "duplicate";
const DEFAULT_RESEND_COOLDOWN_SECONDS = 60;

// The registration APIs do not always guarantee strict JSON payloads, so parse responses defensively.
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

// Render the registration page and coordinate local validation, code sending, and account creation.
const RegisterScreen = () => {
    const [userName, setUserName] = useState("");
    const [userNameBlurred, setUserNameBlurred] = useState(false);
    const [password, setPassword] = useState("");
    const [passwordBlurred, setPasswordBlurred] = useState(false);
    const [confirmPassword, setConfirmPassword] = useState("");
    const [confirmPasswordBlurred, setConfirmPasswordBlurred] = useState(false);
    const [email, setEmail] = useState("");
    const [emailBlurred, setEmailBlurred] = useState(false);
    const [verificationCode, setVerificationCode] = useState("");
    const [verificationCodeError, setVerificationCodeError] = useState("");
    const [codeStatusMessage, setCodeStatusMessage] = useState("");
    const [sendingCode, setSendingCode] = useState(false);
    const [resendCooldown, setResendCooldown] = useState(0);
    const [codeSentForEmail, setCodeSentForEmail] = useState("");
    const [registerErrorMessage, setRegisterErrorMessage] = useState("");
    const [userNameErrorMessage, setUserNameErrorMessage] = useState("");
    const [userNameErrorSource, setUserNameErrorSource] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [featureListOpen, setFeatureListOpen] = useState(false);
    const [featureListClosing, setFeatureListClosing] = useState(false);
    const emailInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const passwordInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const confirmPasswordInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const userNameInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const verificationCodeInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const featureListCloseTimerRef = useRef<number | undefined>(undefined);
    const resendCooldownTimerRef = useRef<number | undefined>(undefined);

    const router = useRouter();
    const dispatch = useDispatch();
    // Store the email input node so validation can focus it when the email is missing or invalid.
    const bindEmailInputRef: RefCallback<HTMLInputElement> = (node) => {
        emailInputRef.current = node ?? undefined;
    };
    // Store the password input node so validation can focus it when the password is weak.
    const bindPasswordInputRef: RefCallback<HTMLInputElement> = (node) => {
        passwordInputRef.current = node ?? undefined;
    };
    // Store the confirm-password input node so validation can focus it on mismatch.
    const bindConfirmPasswordInputRef: RefCallback<HTMLInputElement> = (node) => {
        confirmPasswordInputRef.current = node ?? undefined;
    };
    // Store the username input node so validation can focus it when the username is invalid or taken.
    const bindUserNameInputRef: RefCallback<HTMLInputElement> = (node) => {
        userNameInputRef.current = node ?? undefined;
    };
    // Store the verification-code input node so the page can focus it when the code is missing or invalid.
    const bindVerificationCodeInputRef: RefCallback<HTMLInputElement> = (node) => {
        verificationCodeInputRef.current = node ?? undefined;
    };

    useEffect(() => {
        return () => {
            // Clear pending timers so the accordion animation and resend countdown do not leak across unmounts.
            if (featureListCloseTimerRef.current !== undefined) {
                window.clearTimeout(featureListCloseTimerRef.current);
            }
            if (resendCooldownTimerRef.current !== undefined) {
                window.clearInterval(resendCooldownTimerRef.current);
            }
        };
    }, []);

    // Start or restart the resend countdown shown on the verification-code button.
    const startResendCooldown = (seconds: number) => {
        // Reuse a single interval to drive the resend button countdown.
        if (resendCooldownTimerRef.current !== undefined) {
            window.clearInterval(resendCooldownTimerRef.current);
        }
        setResendCooldown(seconds);
        resendCooldownTimerRef.current = window.setInterval(() => {
            setResendCooldown((prev) => {
                if (prev <= 1) {
                    if (resendCooldownTimerRef.current !== undefined) {
                        window.clearInterval(resendCooldownTimerRef.current);
                        resendCooldownTimerRef.current = undefined;
                    }
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);
    };

    const featureItems = [
        // The left-hand marketing panel summarizes the major product capabilities during sign-up.
        {
            title: "Discover mentors by research interests",
            description: "Search mentors and papers together to quickly narrow down the right academic fit.",
        },
        {
            title: "Track papers on a living timeline",
            description: "Follow publication activity across directions and stay aligned with new research momentum.",
        },
        {
            title: "Save and manage followed mentors",
            description: "Keep a focused shortlist of mentors you want to revisit, compare, and contact later.",
        },
        {
            title: "Build a personal academic profile",
            description: "Show research experience, honors, and projects in one place for future mentor interactions.",
        },
        {
            title: "Add private mentors and request verification",
            description: "Maintain your own mentor library and support mentor identity workflows when needed.",
        },
    ];

    // Check whether a password satisfies the page's strength requirements.
    const isPasswordStrong = (passwordToCheck: string) => {
        // Match the backend rule: password must contain both letters and numbers and be at least 8 chars.
        if (passwordToCheck.length < 8) {
            return false;
        }

        let hasLetter = false;
        let hasDigit = false;

        for (const char of passwordToCheck) {
            if (char >= "0" && char <= "9") {
                hasDigit = true;
            }

            if (char.toLowerCase() !== char.toUpperCase()) {
                hasLetter = true;
            }

            if (hasLetter && hasDigit) {
                return true;
            }
        }

        return false;
    };

    const normalizedUserName = userName.trim();
    const isUserNameInvalid = userName !== "" && !USERNAME_REGEX.test(normalizedUserName);

    const isPasswordWeak = password !== "" && !isPasswordStrong(password);
    const shouldShowPasswordMismatchHint =
        confirmPasswordBlurred && confirmPassword !== "" && password !== confirmPassword;
    const shouldShowPasswordWeakHint = passwordBlurred && isPasswordWeak && !shouldShowPasswordMismatchHint;

    // Validate email format before enabling verification-code and submit flows.
    const isEmailValid = (emailToCheck: string) => {
        return EMAIL_REGEX.test(emailToCheck.trim());
    };

    const isEmailInvalid = email !== "" && !isEmailValid(email);
    const shouldShowUserNameFormatError = userNameBlurred && isUserNameInvalid;

    useEffect(() => {
        if (shouldShowUserNameFormatError) {
            setUserNameErrorMessage(REGISTER_USERNAME_INVALID);
            setUserNameErrorSource("format");
            return;
        }

        if (userNameErrorSource === "format") {
            setUserNameErrorMessage("");
            setUserNameErrorSource("");
        }
    }, [shouldShowUserNameFormatError, userNameErrorSource]);

    // Intercept native form submission and route it through the registration workflow.
    const submitRegister = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        register();
    };

    // Request a verification code for the current email and start the resend cooldown when successful.
    const handleSendVerificationCode = () => {
        setVerificationCodeError("");
        setCodeStatusMessage("");

        const trimmedEmail = email.trim();
        if (trimmedEmail === "" || !isEmailValid(trimmedEmail)) {
            setEmailBlurred(true);
            emailInputRef.current?.focus();
            return;
        }
        if (sendingCode || resendCooldown > 0) {
            return;
        }

        setSendingCode(true);
        // Request the verification code separately so the user can finish the rest of the form at their own pace.
        fetch("/api/register/verification-code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: trimmedEmail }),
        })
            .then((res) => parseJsonSafely(res))
            .then((res) => {
                const code = Number(res.code);
                if (code === 0) {
                    // Store which email the current code belongs to so stale messages disappear when the email changes.
                    const cooldownSeconds = typeof res.cooldownSeconds === "number"
                        ? res.cooldownSeconds
                        : DEFAULT_RESEND_COOLDOWN_SECONDS;
                    setCodeStatusMessage(REGISTER_CODE_SENT);
                    setCodeSentForEmail(trimmedEmail);
                    startResendCooldown(cooldownSeconds);
                }
                else if (code === 4) {
                    setRegisterErrorMessage(REGISTER_EMAIL_TAKEN);
                }
                else if (code === 6) {
                    setCodeStatusMessage(REGISTER_CODE_COOLDOWN);
                    startResendCooldown(DEFAULT_RESEND_COOLDOWN_SECONDS);
                }
                else {
                    setVerificationCodeError(REGISTER_CODE_SEND_FAILED);
                }
            })
            .catch((err) => setVerificationCodeError(describeRequestError(err)))
            .finally(() => setSendingCode(false));
    };

    // Validate the full form, submit the registration request, and log the user in on success.
    const register = () => {
        setRegisterErrorMessage("");

        if (email.trim() === "" || !isEmailValid(email)) {
            setEmailBlurred(true);
            emailInputRef.current?.focus();
            return;
        }

        if (password === "" || !isPasswordStrong(password)) {
            setPasswordBlurred(true);
            passwordInputRef.current?.focus();
            return;
        }

        if (password !== confirmPassword) {
            setConfirmPasswordBlurred(true);
            confirmPasswordInputRef.current?.focus();
            return;
        }

        if (confirmPassword === "") {
            setConfirmPasswordBlurred(true);
            confirmPasswordInputRef.current?.focus();
            return;
        }

        if (normalizedUserName === "" || !USERNAME_REGEX.test(normalizedUserName)) {
            setUserNameBlurred(true);
            setUserNameErrorMessage(REGISTER_USERNAME_INVALID);
            setUserNameErrorSource("format");
            userNameInputRef.current?.focus();
            return;
        }

        const trimmedEmail = email.trim();
        if (verificationCode.trim() === "") {
            setVerificationCodeError(REGISTER_CODE_REQUIRED);
            verificationCodeInputRef.current?.focus();
            return;
        }

        setSubmitting(true);
        // Submit only after local validation passes so the backend mainly handles uniqueness and code verification.
        fetch("/api/register", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                username: normalizedUserName,
                password,
                email: trimmedEmail,
                verificationCode: verificationCode.trim(),
            }),
        })
            .then((res) => parseJsonSafely(res))
            .then((res) => {
                if (Number(res.code) === 0 && typeof res.token === "string") {
                    // Registration logs the user in immediately and seeds the global auth store.
                    dispatch(setToken(res.token));
                    dispatch(setRole(typeof res.role === "string" ? res.role : "student"));
                    dispatch(setUserId(typeof res.userId === "number" ? res.userId : undefined));
                    dispatch(setName(normalizedUserName));
                    router.push("/");
                }
                else if (Number(res.code) === 3) {
                    setUserNameErrorMessage(REGISTER_USERNAME_TAKEN);
                    setUserNameErrorSource(USERNAME_DUPLICATE_ERROR);
                }
                else if (Number(res.code) === 4) {
                    setRegisterErrorMessage(REGISTER_EMAIL_TAKEN);
                }
                else if (Number(res.code) === 5) {
                    setVerificationCodeError(REGISTER_CODE_INVALID);
                    verificationCodeInputRef.current?.focus();
                }
                else {
                    setRegisterErrorMessage(REGISTER_FAILED);
                }
            })
            .catch((err) => setRegisterErrorMessage(describeRequestError(err)))
            .finally(() => setSubmitting(false));
    };

    // Open or close the marketing feature accordion while preserving its close animation.
    const toggleFeatureList = () => {
        if (featureListCloseTimerRef.current !== undefined) {
            window.clearTimeout(featureListCloseTimerRef.current);
            featureListCloseTimerRef.current = undefined;
        }

        // Keep the closing animation visible briefly instead of snapping the details block shut immediately.
        if (featureListClosing) {
            setFeatureListClosing(false);
            setFeatureListOpen(true);
            return;
        }

        if (featureListOpen) {
            setFeatureListOpen(false);
            setFeatureListClosing(true);
            featureListCloseTimerRef.current = window.setTimeout(() => {
                setFeatureListClosing(false);
                featureListCloseTimerRef.current = undefined;
            }, FEATURE_LIST_CLOSE_ANIMATION_MS);
            return;
        }

        setFeatureListClosing(false);
        setFeatureListOpen(true);
    };

    const shouldRenderFeatureList = featureListOpen || featureListClosing;
    const detailsClassName = featureListClosing
        ? "registerAuthDetails registerAuthDetailsClosing"
        : featureListOpen
            ? "registerAuthDetails registerAuthDetailsOpen"
            : "registerAuthDetails";
    const chevronClassName = featureListOpen && !featureListClosing
        ? "registerAuthChevron registerAuthChevronOpen"
        : "registerAuthChevron";

    return (
        <section className="registerAuthPage" aria-label="Sign up page">
            <aside className="registerAuthMarketing" aria-label="MentorFinder feature overview">
                <div className="registerAuthMarketingContent">
                    <h1 className="registerAuthMarketingTitle">Create your account</h1>
                    <p className="registerAuthMarketingCopy">
                        Explore MentorFinder's unique features for both students and teachers
                    </p>
                    <details className={detailsClassName} open={shouldRenderFeatureList}>
                        <summary
                            className="registerAuthMarketingToggle"
                            aria-expanded={featureListOpen && !featureListClosing}
                            onClick={(event) => {
                                event.preventDefault();
                                toggleFeatureList();
                            }}
                        >
                            <span>See what&apos;s included</span>
                            <span className={chevronClassName}>
                                <svg
                                    aria-hidden="true"
                                    height="16"
                                    viewBox="0 0 16 16"
                                    version="1.1"
                                    width="16"
                                >
                                    <path d="M12.78 5.22a.749.749 0 0 1 0 1.06l-4.25 4.25a.749.749 0 0 1-1.06 0L3.22 6.28a.749.749 0 1 1 1.06-1.06L8 8.939l3.72-3.719a.749.749 0 0 1 1.06 0Z" />
                                </svg>
                            </span>
                        </summary>

                        {shouldRenderFeatureList && (
                            <div className="registerAuthDetailsContent">
                                <ul className="registerAuthFeatureList">
                                    {featureItems.map((item) => (
                                        <li key={item.title} className="registerAuthFeatureItem">
                                            <span className="registerAuthFeatureCheck" aria-hidden="true">
                                                <svg
                                                    aria-hidden="true"
                                                    height="16"
                                                    viewBox="0 0 16 16"
                                                    version="1.1"
                                                    width="16"
                                                >
                                                    <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z" />
                                                </svg>
                                            </span>
                                            <div>
                                                <p className="registerAuthFeatureTitle">{item.title}</p>
                                                <p className="registerAuthFeatureDescription">{item.description}</p>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </details>
                </div>
                <div className="registerAuthVisual" aria-hidden="true">
                    <img src="/signupbg.png" alt="" className="registerAuthVisualImage" />
                </div>
            </aside>

            <div className="registerAuthPanel">
                <div className="registerAuthTopLink">
                    <span>Already have an account?</span>
                    <a
                        href={buildRedirectHref("/login", router.query.redirect)}
                        className="registerAuthTopLinkAnchor"
                        onClick={(event) => {
                            event.preventDefault();
                            // Mirror the login page by preserving redirect intent when switching auth pages.
                            void router.push(buildRedirectHref("/login", router.query.redirect));
                        }}
                    >
                        Sign in →
                    </a>
                </div>

                <div className="registerAuthFormWrap">
                    <h2 className="registerAuthFormTitle" aria-label="Sign up for MentorFinder">
                        <span className="registerAuthFormLead">Sign up for</span>
                        <button
                            type="button"
                            className="registerAuthFormLogoRow"
                            aria-label="Go to home page"
                            onClick={() => void router.push("/")}
                        >
                            <img
                                src="/mentorfinder-logo-1.svg"
                                alt=""
                                aria-hidden="true"
                                className="registerAuthFormLogo"
                            />
                        </button>
                    </h2>

                    <form onSubmit={submitRegister}>
                        <label className="registerAuthField">
                            <span className="registerAuthLabel">Email</span>
                            <div className="registerAuthEmailRow">
                                <input
                                    ref={bindEmailInputRef}
                                    type="text"
                                    inputMode="email"
                                    autoComplete="email"
                                    placeholder="Email"
                                    maxLength={INPUT_LIMITS.EMAIL}
                                    value={email}
                                    onChange={(e) => {
                                        setEmail(e.target.value);
                                        if (codeSentForEmail !== "" && codeSentForEmail !== e.target.value.trim()) {
                                            setCodeStatusMessage("");
                                        }
                                    }}
                                    onBlur={() => setEmailBlurred(true)}
                                />
                                <button
                                    type="button"
                                    className="registerAuthSendCodeButton"
                                    onClick={handleSendVerificationCode}
                                    disabled={
                                        sendingCode
                                        || resendCooldown > 0
                                        || email.trim() === ""
                                    }
                                    aria-label="Send verification code"
                                >
                                    {sendingCode
                                        ? "Sending..."
                                        : resendCooldown > 0
                                            ? `${REGISTER_SEND_CODE_RESEND} (${resendCooldown}s)`
                                            : codeSentForEmail !== ""
                                                ? REGISTER_SEND_CODE_RESEND
                                                : REGISTER_SEND_CODE_BUTTON}
                                </button>
                            </div>
                        </label>
                        {emailBlurred && isEmailInvalid && (
                            <p className="registerAuthError">{REGISTER_EMAIL_INVALID}</p>
                        )}

                        <label className="registerAuthField">
                            <span className="registerAuthLabel">Verification code</span>
                            <input
                                ref={bindVerificationCodeInputRef}
                                type="text"
                                inputMode="numeric"
                                autoComplete="one-time-code"
                                maxLength={6}
                                placeholder="Enter the 6-digit code"
                                value={verificationCode}
                                onChange={(e) => {
                                    setVerificationCode(e.target.value.replace(/\D/g, "").slice(0, 6));
                                    if (verificationCodeError !== "") {
                                        setVerificationCodeError("");
                                    }
                                }}
                            />
                        </label>
                        {codeStatusMessage !== "" && (
                            <p className="registerAuthHelper">{codeStatusMessage}</p>
                        )}
                        {verificationCodeError !== "" && (
                            <p className="registerAuthError">{verificationCodeError}</p>
                        )}

                        <label className="registerAuthField">
                            <span className="registerAuthLabel">Password</span>
                            <input
                                ref={bindPasswordInputRef}
                                type="password"
                                placeholder="Password"
                                maxLength={INPUT_LIMITS.PASSWORD}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                onBlur={() => setPasswordBlurred(true)}
                            />
                        </label>
                        <p className="registerAuthHelper">
                            Password must be at least 8 characters and include both letters and numbers.
                        </p>
                        {shouldShowPasswordWeakHint && (
                            <p className="registerAuthError">{REGISTER_PASSWORD_WEAK}</p>
                        )}

                        <label className="registerAuthField">
                            <span className="registerAuthLabel">Confirm your password</span>
                            <input
                                ref={bindConfirmPasswordInputRef}
                                type="password"
                                placeholder="Confirm your password"
                                maxLength={INPUT_LIMITS.PASSWORD}
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                onBlur={() => setConfirmPasswordBlurred(true)}
                            />
                        </label>
                        {shouldShowPasswordMismatchHint && (
                            <p className="registerAuthError">{REGISTER_PASSWORD_MISMATCH}</p>
                        )}

                        <label className="registerAuthField">
                            <span className="registerAuthLabel">Username</span>
                            <input
                                ref={bindUserNameInputRef}
                                type="text"
                                placeholder="Username"
                                maxLength={INPUT_LIMITS.USERNAME}
                                value={userName}
                                onChange={(e) => {
                                    setUserName(e.target.value);
                                    if (userNameErrorSource === USERNAME_DUPLICATE_ERROR) {
                                        setUserNameErrorMessage("");
                                        setUserNameErrorSource("");
                                    }
                                }}
                                onBlur={() => setUserNameBlurred(true)}
                            />
                        </label>
                        <p className="registerAuthHelper">
                            Username may only contain letters, numbers, underscores, and hyphens.
                        </p>
                        {userNameErrorMessage !== "" && (
                            <p className="registerAuthError">{userNameErrorMessage}</p>
                        )}

                        {registerErrorMessage !== "" && (
                            <p className="registerAuthError">{registerErrorMessage}</p>
                        )}

                        <button
                            type="submit"
                            className="registerAuthSubmit"
                            disabled={submitting}
                        >
                            {submitting ? "Creating account..." : "Create account"}
                        </button>
                    </form>
                </div>
            </div>
        </section>
    );
};

export default RegisterScreen;
