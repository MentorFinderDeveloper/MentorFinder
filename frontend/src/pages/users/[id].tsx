import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { useSelector } from "react-redux";

import FollowToggleButton from "../../components/FollowToggleButton";
import { RootState } from "../../redux/store";
import { describeRequestError } from "../../utils/errorMessage";
import { NetworkError, NetworkErrorType, request } from "../../utils/network";
import { PublicUserProfileResult } from "../../utils/types";

const DEFAULT_SIGNATURE = "这个人很懒，什么也没有留下";
const EMPTY_TEXT = "暂无填写";

interface PublicUserProfileResponse {
    user?: PublicUserProfileResult;
}

const UserPublicProfilePage = () => {
    const router = useRouter();
    const token = useSelector((state: RootState) => state.auth.token);
    const isLoggedIn = token.trim() !== "";
    const rawId = router.query.id;
    const userId = Array.isArray(rawId) ? rawId[0] : rawId;

    const [user, setUser] = useState<PublicUserProfileResult | undefined>(undefined);
    const [loading, setLoading] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");

    useEffect(() => {
        if (!router.isReady || typeof userId !== "string") {
            return;
        }

        if (!isLoggedIn) {
            // Clear any stale profile data when auth disappears so protected content does not linger on screen.
            setUser(undefined);
            return;
        }

        setLoading(true);
        setErrorMessage("");

        // Public profiles still require authentication in this app, so the page fetches through the authenticated API client.
        request<PublicUserProfileResponse>(`/api/users/${encodeURIComponent(userId)}/profile`, "GET", true)
            .then((res) => setUser(res.user))
            .catch((err) => {
                if (err instanceof NetworkError && err.type === NetworkErrorType.UNAUTHORIZED) {
                    setErrorMessage("登录已失效，请重新登录后查看用户主页");
                    return;
                }

                setErrorMessage(describeRequestError(err));
            })
            .finally(() => setLoading(false));
    }, [isLoggedIn, router.isReady, userId]);

    const sections = useMemo(() => {
        if (!user) {
            return [];
        }

        // Only render sections the profile owner explicitly marked as visible.
        return [
            {
                title: "个人简介",
                body: user.profile.personalIntro,
                visible: user.profile.showPersonalIntro,
            },
            {
                title: "科研经历",
                body: user.profile.researchExperience,
                visible: user.profile.showResearchExperience,
            },
            {
                title: "所获荣誉",
                body: user.profile.honors,
                visible: user.profile.showHonors,
            },
            {
                title: "项目经历",
                body: user.profile.projectExperience,
                visible: user.profile.showProjectExperience,
            },
        ].filter((section) => section.visible);
    }, [user]);

    const toggleFollow = async () => {
        if (!user || user.isSelf) {
            return;
        }

        // Reuse the same button for follow and unfollow, then patch only the followed flag in local state.
        setActionLoading(true);
        setErrorMessage("");

        try {
            const res = await request<{ followed?: boolean }>(
                `/api/follow/users/${user.id}`,
                user.followed ? "DELETE" : "POST",
                true,
            );
            setUser((currentUser) => (
                currentUser ? { ...currentUser, followed: Boolean(res.followed) } : currentUser
            ));
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setActionLoading(false);
        }
    };

    if (!isLoggedIn) {
        return (
            <main className="userPublicPage">
                <div className="emptyPanel">
                    {/* Redirect guests through login first because this page is only available to authenticated users. */}
                    <p>请先登录后查看用户主页。</p>
                    <button type="button" onClick={() => void router.push("/login?redirect=/follows")}>
                        去登录
                    </button>
                </div>
            </main>
        );
    }

    return (
        <main className="userPublicPage">
            <button className="backButton" type="button" onClick={() => void router.push("/")}>
                返回主界面
            </button>

            {loading ? (
                <div className="emptyPanel">
                    <p>加载中...</p>
                </div>
            ) : user ? (
                <>
                    <section className="profileHero" aria-label="用户主页信息">
                        <div className="profileInfo">
                            {user.avatarUrl ? (
                                <img className="avatarImage" src={user.avatarUrl} alt="用户头像" />
                            ) : (
                                <div className="defaultAvatar" aria-hidden="true">
                                    {user.username.slice(0, 1).toUpperCase()}
                                </div>
                            )}
                            <div className="profileText">
                                <h1>{user.realName || user.username}</h1>
                                <p>{user.signature || DEFAULT_SIGNATURE}</p>
                                {user.role === "mentor" && (
                                    // Mentor accounts receive a badge so visitors can distinguish verified professors from students.
                                    <span className="verifiedProfessorBadge">
                                        <span className="verifiedProfessorIcon" aria-hidden="true" />
                                        已认证教授
                                    </span>
                                )}
                            </div>
                        </div>

                        {user.isSelf ? (
                            <div className="selfActionGroup" aria-label="个人主页操作">
                                <button
                                    className="profileActionButton"
                                    type="button"
                                    onClick={() => void router.push("/profile")}
                                >
                                    <span className="editIcon" aria-hidden="true" />
                                    编辑主页
                                </button>
                                <button
                                    className="profileActionButton"
                                    type="button"
                                    onClick={() => void router.push("/profile-settings")}
                                >
                                    <span className="settingsIcon" aria-hidden="true" />
                                    个人设置
                                </button>
                            </div>
                        ) : (
                            <FollowToggleButton
                                className="followToggleButton"
                                followed={user.followed}
                                loading={actionLoading}
                                onClick={() => void toggleFollow()}
                            />
                        )}
                    </section>

                    <section className="profileDetails" aria-label="公开个人资料">
                        <div className="sectionHeader">
                            <h2>公开资料</h2>
                            {user.profile.updatedAt && <p>最近更新：{user.profile.updatedAt}</p>}
                        </div>

                        {sections.length === 0 ? (
                            <div className="emptyPanel">
                                <p>该用户当前未展示任何个人资料。</p>
                            </div>
                        ) : (
                            <div className="detailGrid">
                                {sections.map((section) => (
                                    <article className="detailCard" key={section.title}>
                                        <h3>{section.title}</h3>
                                        {/* Empty strings are replaced with a shared placeholder to avoid blank cards. */}
                                        <p>{section.body.trim() === "" ? EMPTY_TEXT : section.body}</p>
                                    </article>
                                ))}
                            </div>
                        )}
                    </section>
                </>
            ) : (
                <div className="emptyPanel">
                    <p>暂无用户信息。</p>
                </div>
            )}

            {errorMessage !== "" && (
                <div className="errorPanel" role="alert">
                    {errorMessage}
                </div>
            )}

            <style jsx>{`
                .userPublicPage {
                    display: flex;
                    width: 100%;
                    max-width: 1120px;
                    flex-direction: column;
                    gap: 16px;
                    margin: 0 auto;
                }

                .backButton,
                .profileActionButton {
                    align-self: flex-start;
                    border: 1px solid #222;
                    border-radius: 6px;
                    background: #fff;
                    color: #1f2328;
                    padding: 9px 12px;
                    font-weight: 700;
                }

                .selfActionGroup {
                    display: flex;
                    flex: 0 0 auto;
                    align-items: center;
                    gap: 8px;
                    flex-wrap: wrap;
                    justify-content: flex-end;
                }

                .profileActionButton {
                    display: inline-flex;
                    flex: 0 0 auto;
                    align-items: center;
                    gap: 8px;
                    white-space: nowrap;
                }

                .editIcon {
                    position: relative;
                    width: 16px;
                    height: 16px;
                    transform: rotate(-35deg);
                }

                .editIcon::before,
                .editIcon::after {
                    position: absolute;
                    content: "";
                    background: currentColor;
                }

                .editIcon::before {
                    top: 2px;
                    left: 6px;
                    width: 4px;
                    height: 13px;
                    border-radius: 2px 2px 1px 1px;
                }

                .editIcon::after {
                    top: 14px;
                    left: 5px;
                    width: 0;
                    height: 0;
                    border-right: 3px solid transparent;
                    border-left: 3px solid transparent;
                    border-top: 5px solid currentColor;
                    background: transparent;
                }

                .settingsIcon {
                    position: relative;
                    width: 16px;
                    height: 16px;
                    border: 2px solid currentColor;
                    border-radius: 50%;
                }

                .settingsIcon::before,
                .settingsIcon::after {
                    position: absolute;
                    content: "";
                    background: currentColor;
                }

                .settingsIcon::before {
                    inset: 4px;
                    border-radius: 50%;
                }

                .settingsIcon::after {
                    top: 5px;
                    left: -4px;
                    width: 20px;
                    height: 2px;
                    border-radius: 999px;
                    box-shadow: 0 -6px 0 currentColor, 0 6px 0 currentColor;
                }

                .profileHero {
                    display: flex;
                    min-height: 172px;
                    align-items: flex-end;
                    justify-content: space-between;
                    gap: 18px;
                    padding: 24px 28px;
                    border: 1px solid #d7d7d7;
                    border-radius: 8px;
                    background: linear-gradient(120deg, #202124 0%, #364652 48%, #5b5f4a 100%);
                    color: #fff;
                }

                .profileInfo {
                    display: flex;
                    flex: 1 1 auto;
                    min-width: 0;
                    align-items: center;
                    gap: 14px;
                }

                .defaultAvatar,
                .avatarImage {
                    width: 72px;
                    height: 72px;
                    flex: 0 0 auto;
                    border: 2px solid rgba(255, 255, 255, 0.9);
                    border-radius: 50%;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
                }

                .defaultAvatar {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: #eef6ff;
                    color: #0969da;
                    font-size: 28px;
                    font-weight: 800;
                }

                .avatarImage {
                    display: block;
                    object-fit: cover;
                    background: #fff;
                }

                .profileText {
                    min-width: 0;
                }

                .profileText h1 {
                    overflow-wrap: anywhere;
                    margin: 0 0 8px;
                    font-size: 30px;
                    line-height: 1.05;
                }

                .profileText p {
                    display: block;
                    margin: 0;
                    color: rgba(255, 255, 255, 0.88);
                    line-height: 1.45;
                    overflow-wrap: anywhere;
                }

                .profileText p {
                    font-size: 17px;
                    font-weight: 700;
                }

                .verifiedProfessorBadge {
                    display: inline-flex;
                    width: fit-content;
                    align-items: center;
                    gap: 6px;
                    margin-top: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.78);
                    border-radius: 999px;
                    background: rgba(255, 255, 255, 0.16);
                    color: #fff;
                    padding: 5px 10px;
                    font-size: 13px;
                    font-weight: 800;
                    line-height: 1.2;
                }

                .verifiedProfessorIcon {
                    position: relative;
                    width: 15px;
                    height: 15px;
                    flex: 0 0 auto;
                    border-radius: 50%;
                    background: #2da44e;
                }

                .verifiedProfessorIcon::after {
                    position: absolute;
                    top: 3px;
                    left: 5px;
                    width: 4px;
                    height: 7px;
                    border-right: 2px solid #fff;
                    border-bottom: 2px solid #fff;
                    content: "";
                    transform: rotate(45deg);
                }

                :global(.followToggleButton) {
                    position: relative;
                    display: inline-flex;
                    min-width: 92px;
                    min-height: 36px;
                    align-items: center;
                    justify-content: center;
                    border: 1px solid rgba(255, 255, 255, 0.82);
                    border-radius: 999px;
                    background: #fff;
                    color: #1f2328;
                    padding: 0 16px;
                    font-weight: 700;
                    overflow: hidden;
                }

                :global(.followToggleButtonOverlay) {
                    position: absolute;
                    inset: 0;
                    background: rgba(255, 255, 255, 0.55);
                }

                .profileDetails {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }

                .sectionHeader {
                    display: flex;
                    align-items: flex-end;
                    justify-content: space-between;
                    gap: 12px;
                }

                .sectionHeader h2,
                .sectionHeader p {
                    margin: 0;
                }

                .sectionHeader p {
                    color: #666;
                    font-size: 13px;
                }

                .detailGrid {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 12px;
                }

                .detailCard,
                .emptyPanel,
                .errorPanel {
                    border: 1px solid #d0d7de;
                    border-radius: 8px;
                    background: #fff;
                    padding: 14px;
                }

                .detailCard h3 {
                    margin: 0 0 8px;
                    font-size: 16px;
                }

                .detailCard p,
                .emptyPanel p,
                .errorPanel {
                    margin: 0;
                    line-height: 1.6;
                    white-space: pre-wrap;
                }

                .errorPanel {
                    border-color: #f1aeb5;
                    background: #f8d7da;
                    color: #842029;
                }

                @media (max-width: 720px) {
                    .profileHero {
                        align-items: flex-start;
                        flex-direction: column;
                    }

                    .selfActionGroup {
                        width: 100%;
                        justify-content: flex-start;
                    }

                    .detailGrid {
                        grid-template-columns: 1fr;
                    }
                }
            `}</style>
        </main>
    );
};

export default UserPublicProfilePage;
