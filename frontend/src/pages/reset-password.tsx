import { FormEvent, RefCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import {
    REGISTER_CODE_COOLDOWN,
    REGISTER_CODE_INVALID,
    REGISTER_CODE_REQUIRED,
    REGISTER_CODE_SEND_FAILED,
    REGISTER_CODE_SENT,
    REGISTER_EMAIL_INVALID,
    REGISTER_PASSWORD_MISMATCH,
    REGISTER_PASSWORD_WEAK,
    REGISTER_SEND_CODE_BUTTON,
    REGISTER_SEND_CODE_RESEND,
    RESET_PASSWORD_EMAIL_NOT_FOUND,
    RESET_PASSWORD_FAILED,
    RESET_PASSWORD_SUCCESS,
} from "../constants/string";
import { INPUT_LIMITS } from "../constants/inputLimits";
import { describeRequestError } from "../utils/errorMessage";

const EMAIL_REGEX = /^[\w.%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i;
const DEFAULT_RESEND_COOLDOWN_SECONDS = 60;

// Password reset shares the same defensive response parsing strategy as registration.
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

// Render the password-reset page and coordinate code sending plus password update flow.
const ResetPasswordScreen = () => {
    const [email, setEmail] = useState("");
    const [emailBlurred, setEmailBlurred] = useState(false);
    const [verificationCode, setVerificationCode] = useState("");
    const [verificationCodeError, setVerificationCodeError] = useState("");
    const [codeStatusMessage, setCodeStatusMessage] = useState("");
    const [password, setPassword] = useState("");
    const [passwordBlurred, setPasswordBlurred] = useState(false);
    const [confirmPassword, setConfirmPassword] = useState("");
    const [confirmPasswordBlurred, setConfirmPasswordBlurred] = useState(false);
    const [resetErrorMessage, setResetErrorMessage] = useState("");
    const [resetStatusMessage, setResetStatusMessage] = useState("");
    const [sendingCode, setSendingCode] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [resendCooldown, setResendCooldown] = useState(0);
    const [codeSentForEmail, setCodeSentForEmail] = useState("");

    const emailInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const verificationCodeInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const passwordInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const confirmPasswordInputRef = useRef<HTMLInputElement | undefined>(undefined);
    const resendCooldownTimerRef = useRef<number | undefined>(undefined);
    const router = useRouter();

    // Store the email input node so validation can focus it when the email is missing or invalid.
    const bindEmailInputRef: RefCallback<HTMLInputElement> = (node) => {
        emailInputRef.current = node ?? undefined;
    };
    // Store the verification-code input node so validation can focus it when the code is missing or invalid.
    const bindVerificationCodeInputRef: RefCallback<HTMLInputElement> = (node) => {
        verificationCodeInputRef.current = node ?? undefined;
    };
    // Store the password input node so validation can focus it when the new password is weak.
    const bindPasswordInputRef: RefCallback<HTMLInputElement> = (node) => {
        passwordInputRef.current = node ?? undefined;
    };
    // Store the confirm-password input node so validation can focus it when the two passwords do not match.
    const bindConfirmPasswordInputRef: RefCallback<HTMLInputElement> = (node) => {
        confirmPasswordInputRef.current = node ?? undefined;
    };

    useEffect(() => {
        return () => {
            // Stop the resend countdown when leaving the page.
            if (resendCooldownTimerRef.current !== undefined) {
                window.clearInterval(resendCooldownTimerRef.current);
            }
        };
    }, []);

    // Start or restart the resend countdown shown on the verification-code button.
    const startResendCooldown = (seconds: number) => {
        // Reinitialize the cooldown interval each time a new verification code is sent.
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

    // Validate email format before requesting a reset code or submitting the form.
    const isEmailValid = (emailToCheck: string) => EMAIL_REGEX.test(emailToCheck.trim());

    // Check whether the new password satisfies the page's strength requirements.
    const isPasswordStrong = (passwordToCheck: string) => {
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

    const isEmailInvalid = email !== "" && !isEmailValid(email);
    const shouldShowPasswordMismatchHint =
        confirmPasswordBlurred && confirmPassword !== "" && password !== confirmPassword;
    const shouldShowPasswordWeakHint =
        passwordBlurred && password !== "" && !isPasswordStrong(password) && !shouldShowPasswordMismatchHint;

    // Request a password-reset verification code for the current email.
    const handleSendVerificationCode = () => {
        setResetErrorMessage("");
        setVerificationCodeError("");
        setCodeStatusMessage("");
        setResetStatusMessage("");

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
        // Request a reset code before the password form is submitted, mirroring the registration flow.
        fetch("/api/password-reset/verification-code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: trimmedEmail }),
        })
            .then((res) => parseJsonSafely(res))
            .then((res) => {
                const code = Number(res.code);
                if (code === 0) {
                    // Track the email tied to the current code so the UI can clear stale success messages.
                    const cooldownSeconds = typeof res.cooldownSeconds === "number"
                        ? res.cooldownSeconds
                        : DEFAULT_RESEND_COOLDOWN_SECONDS;
                    setCodeStatusMessage(REGISTER_CODE_SENT);
                    setCodeSentForEmail(trimmedEmail);
                    startResendCooldown(cooldownSeconds);
                }
                else if (code === 2) {
                    setResetErrorMessage(RESET_PASSWORD_EMAIL_NOT_FOUND);
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

    // Intercept native form submission and route it through the reset workflow.
    const submitResetPassword = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        resetPassword();
    };

    // Validate the form, submit the password-reset request, and redirect back to login on success.
    const resetPassword = () => {
        setResetErrorMessage("");
        setResetStatusMessage("");

        const trimmedEmail = email.trim();
        if (trimmedEmail === "" || !isEmailValid(trimmedEmail)) {
            setEmailBlurred(true);
            emailInputRef.current?.focus();
            return;
        }

        if (verificationCode.trim() === "") {
            setVerificationCodeError(REGISTER_CODE_REQUIRED);
            verificationCodeInputRef.current?.focus();
            return;
        }

        if (password === "" || !isPasswordStrong(password)) {
            setPasswordBlurred(true);
            passwordInputRef.current?.focus();
            return;
        }

        if (confirmPassword === "" || password !== confirmPassword) {
            setConfirmPasswordBlurred(true);
            confirmPasswordInputRef.current?.focus();
            return;
        }

        setSubmitting(true);
        // Only submit once all local validity checks pass, then let the backend verify the code.
        fetch("/api/password-reset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: trimmedEmail,
                password,
                verificationCode: verificationCode.trim(),
            }),
        })
            .then((res) => parseJsonSafely(res))
            .then((res) => {
                const code = Number(res.code);
                if (code === 0) {
                    // Clear sensitive inputs and redirect back to login shortly after a successful reset.
                    setResetStatusMessage(RESET_PASSWORD_SUCCESS);
                    setVerificationCode("");
                    setPassword("");
                    setConfirmPassword("");
                    window.setTimeout(() => {
                        void router.push("/login");
                    }, 600);
                }
                else if (code === 2) {
                    setResetErrorMessage(RESET_PASSWORD_EMAIL_NOT_FOUND);
                }
                else if (code === 5) {
                    setVerificationCodeError(REGISTER_CODE_INVALID);
                    verificationCodeInputRef.current?.focus();
                }
                else {
                    setResetErrorMessage(RESET_PASSWORD_FAILED);
                }
            })
            .catch((err) => setResetErrorMessage(describeRequestError(err)))
            .finally(() => setSubmitting(false));
    };

    return (
        <section className="loginAuthPage" aria-label="Reset password page">
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

            <h1 className="loginAuthTitle">Reset your password</h1>

            <form className="loginAuthForm" onSubmit={submitResetPassword}>
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

                <label className="loginAuthField">
                    <span className="loginAuthLabel">Verification code</span>
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

                <label className="loginAuthField">
                    <span className="loginAuthLabel">New password</span>
                    <input
                        ref={bindPasswordInputRef}
                        type="password"
                        placeholder="New password"
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

                <label className="loginAuthField">
                    <span className="loginAuthLabel">Confirm new password</span>
                    <input
                        ref={bindConfirmPasswordInputRef}
                        type="password"
                        placeholder="Confirm new password"
                        maxLength={INPUT_LIMITS.PASSWORD}
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        onBlur={() => setConfirmPasswordBlurred(true)}
                    />
                </label>
                {shouldShowPasswordMismatchHint && (
                    <p className="registerAuthError">{REGISTER_PASSWORD_MISMATCH}</p>
                )}

                {resetStatusMessage !== "" && (
                    <p className="registerAuthHelper">{resetStatusMessage}</p>
                )}
                {resetErrorMessage !== "" && (
                    <p className="loginAuthError">{resetErrorMessage}</p>
                )}

                <button
                    type="submit"
                    className="loginAuthSubmit"
                    disabled={submitting}
                >
                    {submitting ? "Resetting..." : "Reset password"}
                </button>
            </form>

            <p className="loginAuthSignup">
                Remembered your password?{" "}
                <a
                    href="/login"
                    className="loginAuthInlineLink"
                    onClick={(event) => {
                        event.preventDefault();
                        if (submitting) {
                            return;
                        }
                        void router.push("/login");
                    }}
                >
                    Sign in
                </a>
            </p>
        </section>
    );
};

export default ResetPasswordScreen;
