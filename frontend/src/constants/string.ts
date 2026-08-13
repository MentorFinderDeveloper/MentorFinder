/**
 * @note 本文件是一个字符串常量文件的示例，较长的常量字符串，如各类提示文字，均可以写在这里
 *       这么做可以提高核心代码可读性，不会因为过长的字符串导致主逻辑代码难以分析
 */

export const BACKEND_URL = "";

// Prefixes are kept separate so UI code can append backend-provided detail messages when needed.
export const FAILURE_PREFIX = "Network request failed.";

export const LOGIN_SUCCESS_PREFIX = "Login successful, username: ";
export const LOGIN_FAILED = "Incorrect username or password.";

// Registration-related copy is centralized here so forms and tests share the same wording.
export const REGISTER_SUCCESS_PREFIX = "Registration successful, username: ";
export const REGISTER_FAILED = "Registration failed.";
export const REGISTER_USERNAME_TAKEN = "This username has already been used.";
export const REGISTER_EMAIL_TAKEN = "This email has already been used.";
export const REGISTER_USERNAME_INVALID =
  "Username can only contain letters, numbers, underscores, and hyphens.";
export const REGISTER_PASSWORD_MISMATCH = "The two passwords do not match.";
export const REGISTER_PASSWORD_WEAK =
  "Password must be at least 8 characters long and contain both letters and numbers.";
export const REGISTER_EMAIL_INVALID = "Invalid email format.";
export const REGISTER_CODE_REQUIRED = "Please enter the verification code sent to your email.";
export const REGISTER_CODE_INVALID = "Verification code is invalid or has expired.";
export const REGISTER_CODE_SENT = "Verification code sent. Please check your inbox.";
export const REGISTER_CODE_SEND_FAILED = "Failed to send verification code. Please try again later.";
export const REGISTER_CODE_COOLDOWN = "Please wait a moment before requesting another code.";
export const REGISTER_SEND_CODE_BUTTON = "Send code";
export const REGISTER_SEND_CODE_RESEND = "Resend";

// Password reset messages are shared across submission, validation, and success states.
export const RESET_PASSWORD_FAILED = "Failed to reset password.";
export const RESET_PASSWORD_SUCCESS = "Password reset successfully. Please sign in with your new password.";
export const RESET_PASSWORD_EMAIL_NOT_FOUND = "No account was found for this email.";
