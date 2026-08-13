/**
 * Translate backend/transport errors into natural-language Chinese messages.
 *
 * The backend reports failures as English strings such as
 * "Invalid parameters. [Chinese_name] is too long" and the request wrapper
 * prefixes them with an HTTP status like "[400] ...". Surfacing those raw
 * strings to end users is confusing, so this module centralizes the mapping
 * from backend phrasing to friendly Chinese copy. Every page that shows an
 * error should funnel the caught error through {@link describeRequestError}
 * (or pass an explicit fallback) instead of rendering String(err) directly.
 */

import { NetworkError, NetworkErrorType } from "./network";

// Friendly labels for the field names embedded in backend validation messages.
const FIELD_LABELS: Record<string, string> = {
    title: "论文标题",
    abstract: "论文摘要",
    author_names: "作者名",
    Chinese_name: "导师中文名",
    English_name: "导师英文名",
    research_direction: "研究方向",
    keyword: "搜索关键词",
    subject: "关注板块",
    submittedName: "申请姓名",
    username: "用户名",
    password: "密码",
    email: "邮箱",
    verificationCode: "验证码",
    avatar: "头像",
    body: "请求内容",
    date: "日期",
    before_date: "日期",
    after_date: "日期",
    before_id: "分页参数",
    after_id: "分页参数",
    week_start: "周起始日期",
    mentorId: "导师编号",
    role: "角色",
    status: "状态",
};

// Exact backend phrases (after stripping the status prefix) mapped to Chinese.
const EXACT_MESSAGES: Record<string, string> = {
    "Unauthorized": "登录状态已失效，请重新登录后再试",
    "User not found": "未找到对应的用户",
    "User is banned": "该账号已被封禁，请联系管理员",
    "Wrong password": "用户名或密码错误",
    "User already exists": "该用户名已被使用，请更换其他用户名",
    "Email already exists": "该邮箱已被注册，请更换其他邮箱",
    "Username already exists": "该用户名已被占用，请更换其他用户名",
    "Verification code is required": "请输入邮箱验证码",
    "Verification code is invalid or expired": "验证码错误或已过期，请重新获取",
    "Permission denied": "没有权限执行该操作",
    "Mentor already exists in your private library": "该导师已在你的私有库中，请勿重复添加",
    "Mentor not found": "未找到对应的导师",
    "Paper not found": "未找到对应的论文",
    "Subject not found": "未找到对应的关注板块",
    "Weekly push not found": "未找到对应的周报",
    "Verification request not found": "未找到对应的认证申请",
    "Verification request has already been reviewed": "该认证申请已被处理",
    "A pending mentor verification request already exists": "你已有一条待审核的导师认证申请，请耐心等待",
    "Mentor binding is required for approval": "审核通过前需要先绑定导师",
    "Mentor binding is required for mentor role": "设置为导师角色前需要先绑定导师",
    "Mentor is already bound to another user": "该导师已被其他用户绑定",
    "Only mentor role can bind a mentor profile": "仅导师角色可以绑定导师信息",
    "Cannot follow yourself": "不能关注自己",
    "Admin cannot ban self": "管理员不能封禁自己",
};

// Remove the "[400] " style status prefix the request wrapper prepends.
const stripStatusPrefix = (message: string): string => {
    return message.replace(/^\[\d+\]\s*/, "").trim();
};

// Remove the shared "Invalid parameters. " lead-in used by validation errors.
const stripInvalidParamsPrefix = (message: string): string => {
    return message.replace(/^Invalid parameters\.\s*/, "").trim();
};

const labelFor = (field: string): string => FIELD_LABELS[field] ?? field;

// Translate a single backend message body (no status prefix) into Chinese.
// Returns undefined when the phrasing is not recognized so callers can fall
// back to a generic message rather than leaking raw English text.
const translateMessageBody = (body: string): string | undefined => {
    if (body in EXACT_MESSAGES) {
        return EXACT_MESSAGES[body];
    }

    const detail = stripInvalidParamsPrefix(body);

    // The username regex rule has a dedicated, user-friendly phrasing.
    if (/^\[username\] can only contain/.test(detail)) {
        return "用户名只能包含字母、数字、下划线和连字符";
    }

    const tooLong = detail.match(/^\[(\w+)\] is too long$/);
    if (tooLong) {
        return `${labelFor(tooLong[1])}过长，请缩短后重试`;
    }

    const cannotBeEmpty = detail.match(/^\[(\w+)\] cannot be empty$/);
    if (cannotBeEmpty) {
        return `${labelFor(cannotBeEmpty[1])}不能为空`;
    }

    if (/^\[email\] format is invalid$/.test(detail)) {
        return "邮箱格式不正确";
    }

    const formatInvalid = detail.match(/^\[(\w+)\] format is invalid$/);
    if (formatInvalid) {
        return `${labelFor(formatInvalid[1])}格式不正确`;
    }

    if (/^\[avatar\] is too large$/.test(detail)) {
        return "头像图片过大，请更换更小的图片";
    }

    if (/^\[avatar\] must be an image$/.test(detail)) {
        return "请选择图片文件作为头像";
    }

    // Type / format constraints such as "[mentorId] must be an integer" or
    // "[date] must be YYYY-MM-DD" all reduce to a "格式不正确" hint.
    const mustBe = detail.match(/^\[(\w+)\] (?:must be|is invalid)/);
    if (mustBe) {
        return `${labelFor(mustBe[1])}格式不正确`;
    }

    const missing = detail.match(/^Missing or error type of \[(\w+)\]$/);
    if (missing) {
        return `${labelFor(missing[1])}缺失或格式不正确`;
    }

    return undefined;
};

// Generic Chinese fallback derived from the NetworkError category, used when
// the specific message body is not recognized by the table above.
const genericFallbackFor = (err: unknown): string => {
    if (err instanceof NetworkError) {
        switch (err.type) {
            case NetworkErrorType.UNAUTHORIZED:
                return "登录状态已失效，请重新登录后再试";
            case NetworkErrorType.REJECTED:
                return "没有权限执行该操作";
            case NetworkErrorType.CORRUPTED_RESPONSE:
                return "服务器返回了异常数据，请稍后重试";
            default:
                return "操作失败，请稍后重试";
        }
    }

    return "网络请求失败，请检查网络后重试";
};

/**
 * Convert any caught error into a friendly Chinese message.
 *
 * @param err caught error (NetworkError, Error, or anything thrown)
 * @param fallback optional override used when the message cannot be mapped to
 *        a known backend phrase; defaults to a category-based generic message.
 */
export const describeRequestError = (err: unknown, fallback?: string): string => {
    const body = stripStatusPrefix(String(err));
    const translated = translateMessageBody(body);
    if (translated !== undefined) {
        return translated;
    }

    return fallback ?? genericFallbackFor(err);
};
