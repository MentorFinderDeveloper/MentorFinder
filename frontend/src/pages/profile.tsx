import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { useSelector } from "react-redux";

import { RootState } from "../redux/store";
import { INPUT_LIMITS } from "../constants/inputLimits";
import { describeRequestError } from "../utils/errorMessage";
import { NetworkError, NetworkErrorType, request } from "../utils/network";

// Represent the editable fields on the user's public profile page.
interface ProfilePayload {
    personalIntro: string;
    researchExperience: string;
    honors: string;
    projectExperience: string;
    updatedAt?: string;
}

// Use a shared empty payload when the profile has not loaded yet or needs to be reset.
const EMPTY_PROFILE: ProfilePayload = {
    personalIntro: "",
    researchExperience: "",
    honors: "",
    projectExperience: "",
};

interface ProfileResponse {
    profile?: Partial<ProfilePayload>;
}

// Render the editable public-profile form for the current authenticated user.
const ProfileScreen = () => {
    const router = useRouter();
    // Read the current auth state so the page can guard access and link back to the public profile.
    const token = useSelector((state: RootState) => state.auth.token);
    const userId = useSelector((state: RootState) => state.auth.userId);
    const profileHref = userId === undefined ? "/follows" : `/users/${userId}`;

    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");
    const [successMessage, setSuccessMessage] = useState("");
    const [profile, setProfile] = useState<ProfilePayload>(EMPTY_PROFILE);

    useEffect(() => {
        if (token === "") {
            return;
        }

        setLoading(true);
        setErrorMessage("");

        // Load the current editable profile fields from the authenticated "me" endpoint.
        request<ProfileResponse>("/api/profile/me", "GET", true)
            .then((res) => {
                const raw = res.profile ?? {};
                // Normalize missing fields to empty strings so controlled textareas stay stable.
                setProfile({
                    personalIntro: typeof raw.personalIntro === "string" ? raw.personalIntro : "",
                    researchExperience: typeof raw.researchExperience === "string" ? raw.researchExperience : "",
                    honors: typeof raw.honors === "string" ? raw.honors : "",
                    projectExperience: typeof raw.projectExperience === "string" ? raw.projectExperience : "",
                    updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : "",
                });
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

    // Submit the editable profile text blocks and refresh local state from the server response.
    const saveProfile = async () => {
        setSaving(true);
        setSuccessMessage("");
        setErrorMessage("");

        try {
            // Save only the editable text blocks; visibility controls live on the profile settings page.
            const res = await request<ProfileResponse>("/api/profile/me", "PUT", true, {
                personalIntro: profile.personalIntro,
                researchExperience: profile.researchExperience,
                honors: profile.honors,
                projectExperience: profile.projectExperience,
            });

            // Refresh from the server response so timestamps and any normalization stay in sync.
            const raw = res.profile ?? {};
            setProfile({
                personalIntro: typeof raw.personalIntro === "string" ? raw.personalIntro : "",
                researchExperience: typeof raw.researchExperience === "string" ? raw.researchExperience : "",
                honors: typeof raw.honors === "string" ? raw.honors : "",
                projectExperience: typeof raw.projectExperience === "string" ? raw.projectExperience : "",
                updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : "",
            });
            setSuccessMessage("个人信息保存成功");
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

    if (token === "") {
        return (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
                <h2>编辑主页</h2>
                <p>请先登录后再维护个人信息。</p>
                <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => router.push("/")}>返回首页</button>
                </div>
            </div>
        );
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
                <h2>编辑主页</h2>
            <p>你可以在这里维护个人简介、科研经历、所获荣誉与项目经历等信息。</p>

            <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => router.push(profileHref)}>返回个人主页</button>
                <button onClick={() => router.push("/search")}>去检索</button>
            </div>

            {loading ? (
                <p>加载中...</p>
            ) : (
                <>
                    {/* Each textarea maps directly to one public-profile section rendered on /users/[id]. */}
                    <label htmlFor="personalIntro">个人简介</label>
                    <textarea
                        id="personalIntro"
                        value={profile.personalIntro}
                        maxLength={INPUT_LIMITS.LONG_TEXT}
                        placeholder="例如：你的研究兴趣、能力特点、未来规划等"
                        onChange={(e) => setProfile((prev) => ({ ...prev, personalIntro: e.target.value }))}
                        style={{ minHeight: 100 }}
                    />

                    <label htmlFor="researchExperience">科研经历</label>
                    <textarea
                        id="researchExperience"
                        value={profile.researchExperience}
                        maxLength={INPUT_LIMITS.LONG_TEXT}
                        placeholder="例如：参与实验室方向、发表论文、科研竞赛等"
                        onChange={(e) => setProfile((prev) => ({ ...prev, researchExperience: e.target.value }))}
                        style={{ minHeight: 120 }}
                    />

                    <label htmlFor="honors">所获荣誉</label>
                    <textarea
                        id="honors"
                        value={profile.honors}
                        maxLength={INPUT_LIMITS.LONG_TEXT}
                        placeholder="例如：奖学金、竞赛获奖、优秀学生等"
                        onChange={(e) => setProfile((prev) => ({ ...prev, honors: e.target.value }))}
                        style={{ minHeight: 120 }}
                    />

                    <label htmlFor="projectExperience">项目经历</label>
                    <textarea
                        id="projectExperience"
                        value={profile.projectExperience}
                        maxLength={INPUT_LIMITS.LONG_TEXT}
                        placeholder="例如：项目名称、你的职责、技术栈、结果等"
                        onChange={(e) => setProfile((prev) => ({ ...prev, projectExperience: e.target.value }))}
                        style={{ minHeight: 120 }}
                    />

                    <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={() => void saveProfile()} disabled={saving}>
                            {saving ? "保存中..." : "保存个人信息"}
                        </button>
                    </div>

                    {profile.updatedAt && <p style={{ margin: 0 }}>最近更新：{profile.updatedAt}</p>}
                </>
            )}

            {errorMessage !== "" && (
                <div style={{ padding: 12, border: "1px solid #f1aeb5", backgroundColor: "#f8d7da" }}>
                    {errorMessage}
                </div>
            )}

            {successMessage !== "" && (
                <div style={{ padding: 12, border: "1px solid #badbcc", backgroundColor: "#d1e7dd" }}>
                    {successMessage}
                </div>
            )}
        </div>
    );
};

export default ProfileScreen;
