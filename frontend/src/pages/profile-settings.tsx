import { ChangeEvent, useEffect, useState } from "react";
import { useRouter } from "next/router";
import { useDispatch, useSelector } from "react-redux";

import { setAvatarUrl, setName, setToken } from "../redux/auth";
import { RootState } from "../redux/store";
import { INPUT_LIMITS } from "../constants/inputLimits";
import { describeRequestError } from "../utils/errorMessage";
import { NetworkError, NetworkErrorType, request } from "../utils/network";
import { MentorVerificationRequestResult } from "../utils/types";

interface ProfileSettings {
    avatarUrl: string;
    signature: string;
    showPersonalIntro: boolean;
    showResearchExperience: boolean;
    showHonors: boolean;
    showProjectExperience: boolean;
}

interface ProfileResponse {
    profile?: Partial<ProfileSettings>;
    mentorVerificationRequest?: MentorVerificationRequestResult;
}

interface MentorVerificationSubmitResponse {
    mentorVerificationRequest?: MentorVerificationRequestResult;
}

interface AvatarUploadResponse {
    avatarUrl?: string;
    profile?: Partial<ProfileSettings>;
}

// Default to showing all public profile sections until the user explicitly hides some of them.
const EMPTY_SETTINGS: ProfileSettings = {
    avatarUrl: "",
    signature: "",
    showPersonalIntro: true,
    showResearchExperience: true,
    showHonors: true,
    showProjectExperience: true,
};

// Normalize partial backend responses into a fully controlled settings object.
// Convert a partial backend payload into a fully controlled settings object for the form.
const normalizeSettings = (profile?: Partial<ProfileSettings>): ProfileSettings => ({
    avatarUrl: typeof profile?.avatarUrl === "string" ? profile.avatarUrl : "",
    signature: typeof profile?.signature === "string" ? profile.signature : "",
    showPersonalIntro: typeof profile?.showPersonalIntro === "boolean" ? profile.showPersonalIntro : true,
    showResearchExperience: typeof profile?.showResearchExperience === "boolean" ? profile.showResearchExperience : true,
    showHonors: typeof profile?.showHonors === "boolean" ? profile.showHonors : true,
    showProjectExperience: typeof profile?.showProjectExperience === "boolean" ? profile.showProjectExperience : true,
});

// Render the personal settings page for avatar, signature, visibility, and mentor verification controls.
const ProfileSettingsPage = () => {
    const router = useRouter();
    const dispatch = useDispatch();
    const token = useSelector((state: RootState) => state.auth.token);
    const userId = useSelector((state: RootState) => state.auth.userId);
    const currentUsername = useSelector((state: RootState) => state.auth.name);
    const [usernameInput, setUsernameInput] = useState("");
    const [usernameUpdating, setUsernameUpdating] = useState(false);
    const [usernameMessage, setUsernameMessage] = useState<{ type: "error" | "success"; text: string } | undefined>(undefined);
    const [settings, setSettings] = useState<ProfileSettings>(EMPTY_SETTINGS);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [uploadingAvatar, setUploadingAvatar] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");
    const [successMessage, setSuccessMessage] = useState("");
    // Avatar upload feedback is shown beside the avatar controls instead of the page-bottom panel.
    const [avatarMessage, setAvatarMessage] = useState<{ type: "error" | "success"; text: string } | undefined>(undefined);
    const [mentorVerificationName, setMentorVerificationName] = useState("");
    const [mentorVerificationSubmitting, setMentorVerificationSubmitting] = useState(false);
    // Mentor-verification feedback is shown next to its own section, matching the other inline hints.
    const [mentorVerificationMessage, setMentorVerificationMessage] = useState<{ type: "error" | "success"; text: string } | undefined>(undefined);
    const [mentorVerificationRequest, setMentorVerificationRequest] = useState<MentorVerificationRequestResult | undefined>(undefined);

    useEffect(() => {
        if (token.trim() === "") {
            setSettings(EMPTY_SETTINGS);
            setMentorVerificationRequest(undefined);
            return;
        }

        setLoading(true);
        setErrorMessage("");
        setMentorVerificationRequest(undefined);

        // Load both visibility settings and the most recent mentor verification request in one request.
        request<ProfileResponse>("/api/profile/me", "GET", true)
            .then((res) => {
                setSettings(normalizeSettings(res.profile));
                setMentorVerificationRequest(
                    typeof res.mentorVerificationRequest === "object" && res.mentorVerificationRequest
                        ? res.mentorVerificationRequest
                        : undefined,
                );
            })
            .catch((err) => {
                if (err instanceof NetworkError && err.type === NetworkErrorType.UNAUTHORIZED) {
                    setErrorMessage("登录已失效，请重新登录后再试");
                    return;
                }
                setErrorMessage(describeRequestError(err));
            })
            .finally(() => setLoading(false));
    }, [token]);

    useEffect(() => {
        setUsernameInput(currentUsername ?? "");
    }, [currentUsername]);

    const updateUsername = async () => {
        const nextUsername = usernameInput.trim();
        if (nextUsername === "") {
            setUsernameMessage({ type: "error", text: "用户名不能为空" });
            return;
        }
        if (nextUsername === currentUsername) {
            setUsernameMessage({ type: "error", text: "新用户名与当前用户名相同" });
            return;
        }

        setUsernameUpdating(true);
        setUsernameMessage(undefined);

        try {
            const response = await fetch("/api/profile/username", {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ username: nextUsername }),
            });
            const payload = await response.json() as { code?: number; info?: string; username?: string; token?: string };

            if (Number(payload.code) === 0) {
                const updatedName = typeof payload.username === "string" ? payload.username : nextUsername;
                if (typeof payload.token === "string" && payload.token !== "") {
                    dispatch(setToken(payload.token));
                }
                dispatch(setName(updatedName));
                setUsernameInput(updatedName);
                setUsernameMessage({ type: "success", text: "用户名修改成功" });
            } else if (Number(payload.code) === 3) {
                setUsernameMessage({ type: "error", text: "该用户名已被占用，请更换其他用户名" });
            } else if (response.status === 401) {
                setUsernameMessage({ type: "error", text: "登录已失效，请重新登录后再试" });
            } else {
                setUsernameMessage({ type: "error", text: describeRequestError(payload.info, "用户名修改失败") });
            }
        } catch (err) {
            setUsernameMessage({ type: "error", text: describeRequestError(err) });
        } finally {
            setUsernameUpdating(false);
        }
    };

    const saveSettings = async () => {
        setSaving(true);
        setSuccessMessage("");
        setErrorMessage("");

        try {
            // Save the full settings payload because every field is user-controlled on this page.
            const res = await request<ProfileResponse>("/api/profile/me", "PUT", true, settings);
            setSettings(normalizeSettings(res.profile));
            // Keep the navbar avatar in sync immediately after a successful save.
            dispatch(setAvatarUrl(typeof res.profile?.avatarUrl === "string" ? res.profile.avatarUrl : ""));
            setSuccessMessage("个人设置保存成功");
        } catch (err) {
            if (err instanceof NetworkError && err.type === NetworkErrorType.UNAUTHORIZED) {
                setErrorMessage("登录已失效，请重新登录后再试");
                return;
            }
            setErrorMessage(describeRequestError(err));
        } finally {
            setSaving(false);
        }
    };

    // Upload a local avatar image after validating file type and size constraints.
    const uploadAvatar = async (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file === undefined) {
            return;
        }
        event.target.value = "";

        // Validate locally so obviously invalid files never hit the upload endpoint.
        if (!file.type.startsWith("image/")) {
            setAvatarMessage({ type: "error", text: "请选择图片文件作为头像" });
            return;
        }

        if (file.size > 2 * 1024 * 1024) {
            setAvatarMessage({ type: "error", text: "头像图片不能超过 2MB" });
            return;
        }

        setUploadingAvatar(true);
        setAvatarMessage(undefined);

        const formData = new FormData();
        formData.append("avatar", file);

        try {
            // Avatar upload uses raw fetch because it needs multipart/form-data rather than the JSON helper.
            const response = await fetch("/api/profile/avatar", {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                },
                body: formData,
            });
            const payload = await response.json() as AvatarUploadResponse & { code?: number; info?: string };
            if (Number(payload.code) !== 0) {
                setAvatarMessage({ type: "error", text: describeRequestError(payload.info, "头像上传失败") });
                return;
            }

            setSettings(normalizeSettings(payload.profile));
            dispatch(setAvatarUrl(typeof payload.profile?.avatarUrl === "string" ? payload.profile.avatarUrl : ""));
            setAvatarMessage({ type: "success", text: "头像上传成功" });
        } catch (err) {
            setAvatarMessage({ type: "error", text: describeRequestError(err) });
        } finally {
            setUploadingAvatar(false);
        }
    };

    // Submit a mentor-verification request that an admin can later review and bind to a mentor record.
    const submitMentorVerificationRequest = async () => {
        const submittedName = mentorVerificationName.trim();
        if (submittedName === "") {
            setMentorVerificationMessage({ type: "error", text: "导师身份申请姓名不能为空" });
            return;
        }

        // Users submit a name first; an admin later maps the request to a concrete public mentor record.
        setMentorVerificationSubmitting(true);
        setMentorVerificationMessage(undefined);

        try {
            const res = await request<MentorVerificationSubmitResponse>("/api/profile/mentor-verification-request", "POST", true, {
                submittedName,
            });
            setMentorVerificationRequest(res.mentorVerificationRequest);
            setMentorVerificationName("");
            setMentorVerificationMessage({ type: "success", text: "导师身份认证申请已提交" });
        } catch (err) {
            if (err instanceof NetworkError && err.type === NetworkErrorType.UNAUTHORIZED) {
                setMentorVerificationMessage({ type: "error", text: "登录已失效，请重新登录后再试" });
                return;
            }
            setMentorVerificationMessage({ type: "error", text: describeRequestError(err) });
        } finally {
            setMentorVerificationSubmitting(false);
        }
    };

    const profileHref = userId === undefined ? "/follows" : `/users/${userId}`;

    if (token.trim() === "") {
        return (
            <main className="settingsPage">
                <h2>个人设置</h2>
                <p>请先登录后再修改个人设置。</p>
                <button type="button" onClick={() => void router.push("/")}>返回首页</button>
            </main>
        );
    }

    return (
        <main className="settingsPage">
            <div className="pageHeader">
                <div>
                    <h2>个人设置</h2>
                    <p>管理头像、个性签名和个人主页展示内容。</p>
                </div>
                <div className="headerActions">
                    <button type="button" onClick={() => void router.push("/private-mentor")}>添加个人导师</button>
                    <button type="button" onClick={() => void router.push(profileHref)}>返回个人主页</button>
                </div>
            </div>

            {loading ? (
                <p>加载中...</p>
            ) : (
                <>
                    <section className="settingsSection" aria-label="用户名设置">
                        <h3>用户名</h3>
                        <p>修改后将作为你的登录名与主页显示名称。</p>
                        <label htmlFor="username">用户名</label>
                        <input
                            id="username"
                            type="text"
                            value={usernameInput}
                            maxLength={INPUT_LIMITS.USERNAME}
                            placeholder="输入新的用户名"
                            onChange={(e) => {
                                setUsernameInput(e.target.value);
                                setUsernameMessage(undefined);
                            }}
                            disabled={usernameUpdating}
                        />
                        <div className="actions">
                            <button
                                type="button"
                                onClick={() => void updateUsername()}
                                disabled={usernameUpdating || usernameInput.trim() === "" || usernameInput.trim() === currentUsername}
                            >
                                {usernameUpdating ? "修改中..." : "修改用户名"}
                            </button>
                        </div>
                        {usernameMessage && (
                            <p className={usernameMessage.type === "error" ? "usernameHint usernameHintError" : "usernameHint usernameHintSuccess"}>
                                {usernameMessage.text}
                            </p>
                        )}
                    </section>

                    <section className="settingsSection" aria-label="头像和签名设置">
                        <div className="avatarPreview">
                            {settings.avatarUrl.trim() === "" ? (
                                <div className="defaultAvatar" aria-label="默认头像" />
                            ) : (
                                <img src={settings.avatarUrl} alt="头像预览" />
                            )}
                        </div>

                        <label htmlFor="avatarUrl">头像地址</label>
                        <input
                            id="avatarUrl"
                            type="text"
                            value={settings.avatarUrl}
                            maxLength={INPUT_LIMITS.AVATAR_URL}
                            placeholder="粘贴图片 URL，留空则使用默认头像"
                            onChange={(e) => setSettings((prev) => ({ ...prev, avatarUrl: e.target.value }))}
                        />

                        <label htmlFor="avatarFile">上传本地头像</label>
                        <input
                            id="avatarFile"
                            type="file"
                            accept="image/png,image/jpeg,image/gif,image/webp"
                            onChange={(event) => void uploadAvatar(event)}
                            disabled={uploadingAvatar}
                        />
                        <p className="avatarUploadHint">
                            支持 PNG、JPG、GIF、WebP，大小不超过 2MB。
                        </p>
                        {uploadingAvatar && <p className="avatarUploadHint">头像上传中...</p>}
                        {avatarMessage && (
                            <p className={avatarMessage.type === "error" ? "usernameHint usernameHintError" : "usernameHint usernameHintSuccess"}>
                                {avatarMessage.text}
                            </p>
                        )}

                        <label htmlFor="signature">个性签名</label>
                        <textarea
                            id="signature"
                            value={settings.signature}
                            placeholder="写一句想展示在个人主页顶部的话"
                            maxLength={INPUT_LIMITS.SIGNATURE}
                            onChange={(e) => setSettings((prev) => ({ ...prev, signature: e.target.value }))}
                        />
                    </section>

                    <section className="settingsSection" aria-label="展示内容设置">
                        <h3>个人主页展示</h3>
                        {/* These toggles control which text blocks are visible on the public /users/[id] page. */}
                        <div className="visibilityOptions">
                            <label className="checkboxRow">
                                <input
                                    type="checkbox"
                                    checked={settings.showPersonalIntro}
                                    onChange={(e) => setSettings((prev) => ({ ...prev, showPersonalIntro: e.target.checked }))}
                                />
                                <span>展示个人简介</span>
                            </label>
                            <label className="checkboxRow">
                                <input
                                    type="checkbox"
                                    checked={settings.showResearchExperience}
                                    onChange={(e) => setSettings((prev) => ({ ...prev, showResearchExperience: e.target.checked }))}
                                />
                                <span>展示科研经历</span>
                            </label>
                            <label className="checkboxRow">
                                <input
                                    type="checkbox"
                                    checked={settings.showHonors}
                                    onChange={(e) => setSettings((prev) => ({ ...prev, showHonors: e.target.checked }))}
                                />
                                <span>展示所获荣誉</span>
                            </label>
                            <label className="checkboxRow">
                                <input
                                    type="checkbox"
                                    checked={settings.showProjectExperience}
                                    onChange={(e) => setSettings((prev) => ({ ...prev, showProjectExperience: e.target.checked }))}
                                />
                                <span>展示项目经历</span>
                            </label>
                        </div>
                    </section>

                    <section className="settingsSection" aria-label="导师身份认证申请">
                        <h3>导师身份认证申请</h3>
                        <p>非管理员用户可在此提交导师身份绑定申请，请填写你的姓名。</p>
                        <input
                            type="text"
                            value={mentorVerificationName}
                            maxLength={INPUT_LIMITS.NAME}
                            placeholder="填写申请绑定的导师姓名"
                            onChange={(e) => setMentorVerificationName(e.target.value)}
                            disabled={mentorVerificationSubmitting}
                        />
                        <div className="actions">
                            <button
                                type="button"
                                onClick={() => void submitMentorVerificationRequest()}
                                disabled={mentorVerificationSubmitting || mentorVerificationName.trim() === ""}
                            >
                                {mentorVerificationSubmitting ? "提交中..." : "提交导师身份申请"}
                            </button>
                        </div>

                        {mentorVerificationMessage && (
                            <p className={mentorVerificationMessage.type === "error" ? "usernameHint usernameHintError" : "usernameHint usernameHintSuccess"}>
                                {mentorVerificationMessage.text}
                            </p>
                        )}

                        {mentorVerificationRequest && (
                            // Show the most recent request so the user can see whether it is still pending or already reviewed.
                            <div className="mentorRequestPanel">
                                <p>最近申请姓名：{mentorVerificationRequest.submittedName}</p>
                                <p>当前状态：{mentorVerificationRequest.status}</p>
                                <p>提交时间：{mentorVerificationRequest.createdAt || "未知"}</p>
                            </div>
                        )}
                    </section>

                    <div className="actions">
                        <button type="button" onClick={() => void saveSettings()} disabled={saving}>
                            {saving ? "保存中..." : "保存设置"}
                        </button>
                    </div>
                </>
            )}

            {errorMessage !== "" && <div className="errorPanel">{errorMessage}</div>}
            {successMessage !== "" && <div className="successPanel">{successMessage}</div>}

            <style jsx>{`
                .settingsPage {
                    display: flex;
                    flex-direction: column;
                    gap: 14px;
                    max-width: 760px;
                    margin: 0 auto;
                }

                .pageHeader {
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    gap: 16px;
                }

                .headerActions {
                    display: flex;
                    gap: 8px;
                    flex-wrap: wrap;
                    justify-content: flex-end;
                }

                .pageHeader h2 {
                    margin: 0 0 6px;
                }

                .pageHeader p {
                    margin: 0;
                    color: #555;
                }

                .settingsSection {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                    padding: 16px;
                    border: 1px solid #d7d7d7;
                    border-radius: 8px;
                    background: #fff;
                }

                .settingsSection h3 {
                    margin: 0 0 4px;
                }

                .settingsSection input[type="text"],
                .settingsSection input[type="file"],
                .settingsSection textarea {
                    width: 100%;
                    box-sizing: border-box;
                    padding: 9px 10px;
                    border: 1px solid #bbb;
                    border-radius: 4px;
                    font-size: 15px;
                }

                .settingsSection input[type="file"] {
                    background: #fafafa;
                }

                .settingsSection textarea {
                    min-height: 88px;
                    resize: vertical;
                }

                .avatarPreview {
                    display: flex;
                    align-items: center;
                    min-height: 84px;
                }

                .avatarPreview img,
                .defaultAvatar {
                    width: 72px;
                    height: 72px;
                    border: 1px solid #ccc;
                    border-radius: 50%;
                    object-fit: cover;
                    background:
                        linear-gradient(135deg, transparent 0 18%, #5ba8e6 18% 30%, transparent 30% 100%),
                        linear-gradient(45deg, #f7fbff 0 25%, transparent 25% 50%, #76b9ec 50% 74%, transparent 74% 100%),
                        #d9eefc;
                }

                .avatarUploadHint {
                    margin: -4px 0 0;
                    color: #555;
                    font-size: 13px;
                    line-height: 1.5;
                }

                .visibilityOptions {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 10px 12px;
                }

                .checkboxRow {
                    display: grid;
                    grid-template-columns: 18px minmax(0, 1fr);
                    align-items: center;
                    gap: 10px;
                    min-height: 42px;
                    padding: 10px 12px;
                    border: 1px solid #d7d7d7;
                    border-radius: 6px;
                    background: #fafafa;
                    cursor: pointer;
                }

                .checkboxRow input {
                    width: 16px;
                    height: 16px;
                    margin: 0;
                }

                .checkboxRow span {
                    min-width: 0;
                    line-height: 1.4;
                    overflow-wrap: anywhere;
                }

                .actions {
                    display: flex;
                    gap: 8px;
                }

                .mentorRequestPanel {
                    display: flex;
                    flex-direction: column;
                    gap: 4px;
                    padding: 12px;
                    border: 1px solid #d7d7d7;
                    border-radius: 6px;
                    background: #fafafa;
                }

                .mentorRequestPanel p {
                    margin: 0;
                    line-height: 1.5;
                }

                .errorPanel,
                .successPanel {
                    padding: 12px;
                    border-radius: 6px;
                }

                .errorPanel {
                    border: 1px solid #f1aeb5;
                    background: #f8d7da;
                }

                .successPanel {
                    border: 1px solid #badbcc;
                    background: #d1e7dd;
                }

                .usernameHint {
                    margin: 0;
                    font-size: 13px;
                    line-height: 1.5;
                }

                .usernameHintError {
                    color: #b02a37;
                }

                .usernameHintSuccess {
                    color: #0f5132;
                }

                @media (max-width: 560px) {
                    .pageHeader {
                        flex-direction: column;
                    }

                    .visibilityOptions {
                        grid-template-columns: 1fr;
                    }
                }
            `}</style>
        </main>
    );
};

export default ProfileSettingsPage;
