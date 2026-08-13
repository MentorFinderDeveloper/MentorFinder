import { describeRequestError } from "../utils/errorMessage";
import { NetworkError, NetworkErrorType } from "../utils/network";

describe("describeRequestError", () => {
    // Tests the translateMessageBody module: exact match against known
    // backend message bodies (after stripping the status prefix).

    it("translates Unauthorized exactly", () => {
        // Backend returns "[401] Unauthorized" when the session token is
        // expired or invalid.
        const result = describeRequestError("[401] Unauthorized");
        expect(result).toBe("登录状态已失效，请重新登录后再试");
    });

    it("translates User not found exactly", () => {
        const result = describeRequestError("[404] User not found");
        expect(result).toBe("未找到对应的用户");
    });

    it("translates Wrong password exactly", () => {
        const result = describeRequestError("[400] Wrong password");
        expect(result).toBe("用户名或密码错误");
    });

    it("translates User already exists exactly", () => {
        const result = describeRequestError("[400] User already exists");
        expect(result).toBe("该用户名已被使用，请更换其他用户名");
    });

    it("translates Email already exists exactly", () => {
        const result = describeRequestError("[400] Email already exists");
        expect(result).toBe("该邮箱已被注册，请更换其他邮箱");
    });

    it("translates Permission denied exactly", () => {
        const result = describeRequestError("[403] Permission denied");
        expect(result).toBe("没有权限执行该操作");
    });

    it("translates Verification code is invalid or expired exactly", () => {
        const result = describeRequestError("[400] Verification code is invalid or expired");
        expect(result).toBe("验证码错误或已过期，请重新获取");
    });

    it("translates Cannot follow yourself exactly", () => {
        const result = describeRequestError("[400] Cannot follow yourself");
        expect(result).toBe("不能关注自己");
    });

    it("translates Admin cannot ban self exactly", () => {
        const result = describeRequestError("[400] Admin cannot ban self");
        expect(result).toBe("管理员不能封禁自己");
    });

    it("translates Mentor already exists in your private library exactly", () => {
        const result = describeRequestError("[400] Mentor already exists in your private library");
        expect(result).toBe("该导师已在你的私有库中，请勿重复添加");
    });

    // Tests the translateMessageBody module: validation field patterns
    // such as "[field] is too long", "[field] cannot be empty", etc.

    it("translates [Chinese_name] is too long with field label", () => {
        // Backend validates field lengths and returns a parameterised message.
        const result = describeRequestError("[400] Invalid parameters. [Chinese_name] is too long");
        expect(result).toBe("导师中文名过长，请缩短后重试");
    });

    it("translates [title] is too long with field label", () => {
        const result = describeRequestError("[400] Invalid parameters. [title] is too long");
        expect(result).toBe("论文标题过长，请缩短后重试");
    });

    it("translates [abstract] is too long with field label", () => {
        const result = describeRequestError("[400] Invalid parameters. [abstract] is too long");
        expect(result).toBe("论文摘要过长，请缩短后重试");
    });

    it("translates [keyword] is too long with field label", () => {
        const result = describeRequestError("[400] Invalid parameters. [keyword] is too long");
        expect(result).toBe("搜索关键词过长，请缩短后重试");
    });

    it("translates [password] cannot be empty with field label", () => {
        const result = describeRequestError("[400] Invalid parameters. [password] cannot be empty");
        expect(result).toBe("密码不能为空");
    });

    it("translates [username] cannot be empty with field label", () => {
        const result = describeRequestError("[400] Invalid parameters. [username] cannot be empty");
        expect(result).toBe("用户名不能为空");
    });

    it("translates [email] format is invalid", () => {
        const result = describeRequestError("[400] Invalid parameters. [email] format is invalid");
        expect(result).toBe("邮箱格式不正确");
    });

    it("translates [date] format is invalid with field label", () => {
        const result = describeRequestError("[400] Invalid parameters. [date] format is invalid");
        expect(result).toBe("日期格式不正确");
    });

    it("translates [avatar] is too large", () => {
        const result = describeRequestError("[400] Invalid parameters. [avatar] is too large");
        expect(result).toBe("头像图片过大，请更换更小的图片");
    });

    it("translates [avatar] must be an image", () => {
        const result = describeRequestError("[400] Invalid parameters. [avatar] must be an image");
        expect(result).toBe("请选择图片文件作为头像");
    });

    it("translates [mentorId] must be an integer via generic must-be pattern", () => {
        const result = describeRequestError("[400] Invalid parameters. [mentorId] must be an integer");
        expect(result).toBe("导师编号格式不正确");
    });

    it("translates [date] must be YYYY-MM-DD via generic pattern", () => {
        const result = describeRequestError("[400] Invalid parameters. [date] must be YYYY-MM-DD");
        expect(result).toBe("日期格式不正确");
    });

    it("translates [role] is invalid via generic pattern", () => {
        const result = describeRequestError("[400] Invalid parameters. [role] is invalid");
        expect(result).toBe("角色格式不正确");
    });

    it("translates Missing or error type of [keyword]", () => {
        const result = describeRequestError("[400] Missing or error type of [keyword]");
        expect(result).toBe("搜索关键词缺失或格式不正确");
    });

    it("translates [username] regex rule message", () => {
        // The username regex validation returns a specific lead-in that
        // triggers a dedicated Chinese message instead of a generic one.
        const result = describeRequestError(
            "[400] Invalid parameters. [username] can only contain letters, numbers, underscores, and hyphens",
        );
        expect(result).toBe("用户名只能包含字母、数字、下划线和连字符");
    });

    it("falls through to generic for an unknown field name", () => {
        // Unknown field names should pass through labelFor which returns
        // the raw field key when no label is registered.
        const result = describeRequestError("[400] Invalid parameters. [unknownField] is too long");
        expect(result).toBe("unknownField过长，请缩短后重试");
    });

    // Tests the genericFallbackFor module: category-based fallback messages
    // derived from the NetworkError type when no specific translation matched.

    it("uses UNAUTHORIZED generic fallback for NetworkError UNAUTHORIZED", () => {
        const err = new NetworkError(NetworkErrorType.UNAUTHORIZED, "[401] some unknown message");
        const result = describeRequestError(err);
        expect(result).toBe("登录状态已失效，请重新登录后再试");
    });

    it("uses REJECTED generic fallback for NetworkError REJECTED", () => {
        const err = new NetworkError(NetworkErrorType.REJECTED, "[403] some unknown message");
        const result = describeRequestError(err);
        expect(result).toBe("没有权限执行该操作");
    });

    it("uses CORRUPTED_RESPONSE generic fallback for NetworkError CORRUPTED_RESPONSE", () => {
        const err = new NetworkError(NetworkErrorType.CORRUPTED_RESPONSE, "bad json");
        const result = describeRequestError(err);
        expect(result).toBe("服务器返回了异常数据，请稍后重试");
    });

    it("uses UNKNOWN_ERROR generic fallback for NetworkError UNKNOWN_ERROR", () => {
        const err = new NetworkError(NetworkErrorType.UNKNOWN_ERROR, "something broke");
        const result = describeRequestError(err);
        expect(result).toBe("操作失败，请稍后重试");
    });

    it("uses non-NetworkError fallback for plain Error objects", () => {
        // A plain Error that is not a NetworkError should get the
        // "网络请求失败" fallback rather than any NetworkError branch.
        const err = new Error("Network error");
        const result = describeRequestError(err);
        expect(result).toBe("网络请求失败，请检查网络后重试");
    });

    it("uses non-NetworkError fallback for string errors", () => {
        // Callers sometimes throw plain strings; these should also get
        // the generic network-failure message.
        const result = describeRequestError("something went wrong");
        expect(result).toBe("网络请求失败，请检查网络后重试");
    });

    it("uses non-NetworkError fallback for undefined", () => {
        // Even undefined thrown values should not crash and should
        // produce a sensible generic fallback.
        const result = describeRequestError(undefined);
        expect(result).toBe("网络请求失败，请检查网络后重试");
    });

    it("accepts custom fallback override for unmapped messages", () => {
        // Callers can provide an explicit fallback string when the
        // automatic translation and generic fallback are not suitable.
        const result = describeRequestError("[599] Weird error", "自定义错误信息");
        expect(result).toBe("自定义错误信息");
    });

    it("prefers backticks in status prefix stripping edge case", () => {
        // The status prefix regex should handle various spacing patterns
        // such as "[200]" with varying whitespace after the bracket.
        const result = describeRequestError("[200]   some message");
        expect(result).toBe("网络请求失败，请检查网络后重试");
    });

    it("does not strip leading text that looks like a status code but is not one", () => {
        // A message containing " [200] " deeper in the string should not
        // be affected by the prefix-only regex.
        const result = describeRequestError("note: [200] is not a prefix");
        expect(result).toBe("网络请求失败，请检查网络后重试");
    });

    it("handles empty string gracefully", () => {
        const result = describeRequestError("");
        expect(result).toBe("网络请求失败，请检查网络后重试");
    });

    // Tests the stripInvalidParamsPrefix flow: ensure the "Invalid parameters. "
    // prefix is correctly removed before pattern matching.

    it("strips Invalid parameters prefix for [body] cannot be empty", () => {
        const result = describeRequestError("[400] Invalid parameters. [body] cannot be empty");
        expect(result).toBe("请求内容不能为空");
    });

    it("strips Invalid parameters prefix for [subject] is too long", () => {
        const result = describeRequestError("[400] Invalid parameters. [subject] is too long");
        expect(result).toBe("关注板块过长，请缩短后重试");
    });

    it("strips Invalid parameters prefix for [week_start] is too long", () => {
        const result = describeRequestError("[400] Invalid parameters. [week_start] is too long");
        expect(result).toBe("周起始日期过长，请缩短后重试");
    });

    it("strips status prefix when message body has extra brackets", () => {
        // Ensure the regex-based prefix stripping does not accidentally
        // trim content beyond the initial [NNN] marker.
        const result = describeRequestError("[400] [username] is too long");
        expect(result).toBe("用户名过长，请缩短后重试");
    });

    it("passes through if body starts with a known exact match even with different status", () => {
        // The same backend message could appear with different HTTP status
        // codes; the translation should only depend on the message body.
        const result = describeRequestError("[500] Wrong password");
        expect(result).toBe("用户名或密码错误");
    });

    it("translates Username already exists exactly", () => {
        const result = describeRequestError("[400] Username already exists");
        expect(result).toBe("该用户名已被占用，请更换其他用户名");
    });

    it("translates Verification code is required exactly", () => {
        const result = describeRequestError("[400] Verification code is required");
        expect(result).toBe("请输入邮箱验证码");
    });
});
