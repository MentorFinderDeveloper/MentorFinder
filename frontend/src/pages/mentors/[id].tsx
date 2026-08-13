import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { useSelector } from "react-redux";

import FollowToggleButton from "../../components/FollowToggleButton";
import LatexText from "../../components/LatexText";
import { RootState } from "../../redux/store";
import { describeRequestError } from "../../utils/errorMessage";
import { request } from "../../utils/network";
import { readPendingMentorSearchReturn } from "../../utils/searchNavigation";
import {
    MentorDetail,
    MentorRecentDirectionAnalysisResponse,
    SearchMentorResult,
} from "../../utils/types";

// Next.js stores an internal key in history.state, which lets the page detect whether "back" returns to the same search entry.
const getCurrentHistoryEntryKey = () => {
    if (typeof window === "undefined") {
        return "";
    }

    const historyState = window.history.state as { key?: unknown } | undefined;
    return typeof historyState?.key === "string" ? historyState.key.trim() : "";
};

// Keep the page-level inline layout constants together so the three-column view stays easy to tune.
const mentorPageShellStyle = {
    width: "100%",
    margin: "0 auto",
    display: "flex",
    flexDirection: "column" as const,
    gap: 12,
};

const mentorPageCardStyle = {
    position: "relative" as const,
    padding: 12,
    border: "1px solid #ccc",
    borderRadius: 6,
};

const mentorPageMainColumnStyle = {
    width: "794px",
    minWidth: 0,
};

// Match the follow button style to the mentor detail card instead of the generic list-page button skin.
const buildMentorFollowButtonStyle = (followed: boolean) => ({
    position: "relative" as const,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: 72,
    minHeight: 28,
    border: "0 solid transparent",
    borderRadius: 6,
    padding: "0 12px",
    backgroundColor: followed ? "rgba(246, 248, 250, 0.96)" : "rgb(8, 109, 177)",
    color: followed ? "#000000" : "#ffffff",
    fontSize: 14,
    fontWeight: 500,
    lineHeight: 1,
    whiteSpace: "nowrap" as const,
    overflow: "hidden",
    cursor: "pointer",
    boxShadow: "none",
    transition: "none",
    appearance: "none" as const,
    opacity: 1,
});

// These headings are highlighted inside the generated mentor profile block to make long prose easier to scan.
const mentorProfileHighlightedHeadings = new Set([
    "教育背景",
    "社会兼职",
    "研究领域",
    "研究概况",
    "奖励与荣誉",
]);

const MentorDetailPage = () => {
    const router = useRouter();
    const { id } = router.query;
    const authToken = useSelector((state: RootState) => state.auth.token);
    const authRole = useSelector((state: RootState) => state.auth.role);
    const isLoggedIn = authToken.trim() !== "";
    const canFollow = isLoggedIn && authRole === "student";

    const [mentor, setMentor] = useState<MentorDetail | undefined>(undefined);
    const [loading, setLoading] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");
    const [followed, setFollowed] = useState(false);
    const [followLoading, setFollowLoading] = useState(false);
    const [analysisLoading, setAnalysisLoading] = useState(false);
    const [analysisResult, setAnalysisResult] = useState<MentorRecentDirectionAnalysisResponse | undefined>(undefined);

    useEffect(() => {
        if (typeof id !== "string") {
            return;
        }

        const fetchMentor = async () => {
            setLoading(true);
            setErrorMessage("");
            // Reset the previous AI result when switching to a different mentor.
            setAnalysisResult(undefined);

            try {
                const res = await request<{ mentor?: MentorDetail }>(
                    `/api/dataset/mentors/${id}`,
                    "GET",
                    isLoggedIn,
                );
                setMentor(res.mentor);
            }
            catch (err) {
                setErrorMessage(describeRequestError(err));
            }
            finally {
                setLoading(false);
            }
        };

        void fetchMentor();
    }, [id, isLoggedIn]);

    useEffect(() => {
        if (!canFollow || typeof id !== "string") {
            // Non-students and signed-out users should always see the mentor as not followable here.
            setFollowed(false);
            return;
        }

        const fetchFollowedMentors = async () => {
            try {
                // Reuse the follow list endpoint to infer whether this mentor is already in the user's collection.
                const res = await request<{ mentors?: SearchMentorResult[] }>(
                    "/api/follow/mentors",
                    "GET",
                    true,
                );
                const followedMentors = Array.isArray(res.mentors) ? res.mentors : [];
                setFollowed(followedMentors.some((item) => item.id === Number(id)));
            }
            catch {
                setFollowed(false);
            }
        };

        void fetchFollowedMentors();
    }, [canFollow, id]);

    const toggleFollow = async () => {
        if (typeof id !== "string") {
            return;
        }

        // Use POST to follow and DELETE to unfollow through the same resource path.
        setFollowLoading(true);
        setErrorMessage("");

        try {
            const res = await request<{ followed?: boolean }>(
                `/api/follow/mentors/${id}`,
                followed ? "DELETE" : "POST",
                true,
            );
            setFollowed(Boolean(res.followed));
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setFollowLoading(false);
        }
    };

    const analyzeRecentDirection = async () => {
        if (typeof id !== "string") {
            return;
        }

        // Ask the backend to summarize only this mentor's recent papers and expose the source list alongside the summary.
        setAnalysisLoading(true);
        setErrorMessage("");

        try {
            const res = await request<MentorRecentDirectionAnalysisResponse>(
                `/api/dataset/mentors/${id}/recent-direction-analysis`,
                "POST",
                isLoggedIn,
            );
            setAnalysisResult(res);
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setAnalysisLoading(false);
        }
    };

    const returnToSearch = async () => {
        const mentorId = Number(id);
        const pendingSearchReturn = readPendingMentorSearchReturn();
        const currentEntryKey = getCurrentHistoryEntryKey();

        // When the user came from a search result card in the same history entry, preserve their previous search state via router.back().
        if (
            Number.isInteger(mentorId) &&
            mentorId > 0 &&
            pendingSearchReturn?.mentorId === mentorId &&
            pendingSearchReturn.sourcePath === "/search" &&
            pendingSearchReturn.targetEntryKey === currentEntryKey
        ) {
            await router.back();
            return;
        }

        await router.push("/search");
    };

    if (loading) {
        return (
            <div style={mentorPageShellStyle}>
                <p style={{ margin: 0, textAlign: "center" }}>加载中...</p>
            </div>
        );
    }

    if (errorMessage !== "") {
        return (
            <div style={mentorPageShellStyle}>
                <button onClick={() => void returnToSearch()}>返回检索</button>
                <p style={{ color: "#c62828" }}>{errorMessage}</p>
            </div>
        );
    }

    if (mentor === undefined) {
        return (
            <div style={mentorPageShellStyle}>
                <button onClick={() => void returnToSearch()}>返回检索</button>
                <p>暂无导师信息</p>
            </div>
        );
    }

    const mentorProfileText = mentor.profile || "暂无导师画像";
    const mentorProfileLines = mentorProfileText.split(/\r?\n/);

    return (
        <div style={mentorPageShellStyle} className="mentorDetailPageWide">
            <div className="mentorDetailLayout">
                <aside
                    aria-label="AI 分析"
                    className="mentorDetailAiSidebar"
                >
                    <h3 className="mentorDetailSidebarTitle">AI 分析</h3>

                    <div style={{ marginTop: 8 }}>
                        <button onClick={() => void analyzeRecentDirection()} disabled={analysisLoading}>
                            {analysisLoading ? "AI正在分析近一年论文，请稍候..." : "AI分析最近研究方向"}
                        </button>
                    </div>

                    {(analysisLoading || analysisResult !== undefined) && (
                        <div className="mentorDetailAiResultCard">
                            <h3 style={{ margin: "0 0 8px" }}>最近研究方向分析</h3>
                            {analysisLoading && (
                                <p style={{ margin: 0 }}>正在读取该导师近一年论文的题目和摘要并生成总结，请稍候...</p>
                            )}
                            {!analysisLoading && analysisResult !== undefined && (
                                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                    <p style={{ margin: 0, color: "#666" }}>
                                        近一年论文数：{analysisResult.paperCount} ｜ 生成方式：{analysisResult.generatedBy}
                                    </p>
                                    <p style={{ margin: 0, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                                        {analysisResult.analysis}
                                    </p>
                                    {analysisResult.papers.length > 0 && (
                                        <div>
                                            <p style={{ margin: "4px 0" }}>本次分析使用的论文：</p>
                                            <ul style={{ margin: 0, paddingLeft: 20 }}>
                                                {analysisResult.papers.map((paper) => (
                                                    <li key={paper.id}>
                                                        {paper.title}
                                                        {paper.publish_date ? `（${paper.publish_date}）` : ""}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </aside>

                <div style={mentorPageMainColumnStyle}>
                    <div style={mentorPageCardStyle}>
                        {canFollow && (
                            <div
                                style={{
                                    position: "absolute",
                                    top: 8,
                                    right: 8,
                                    display: "flex",
                                    alignItems: "center",
                                    zIndex: 1,
                                }}
                            >
                                <FollowToggleButton
                                    className="searchMentorFollowButton"
                                    followed={followed}
                                    followedLabel="已关注"
                                    loading={followLoading}
                                    onClick={() => void toggleFollow()}
                                    style={buildMentorFollowButtonStyle(followed)}
                                />
                            </div>
                        )}

                        <h2 style={{ margin: "0 0 8px", fontSize: "20px" }}>{mentor.Chinese_name}</h2>

                        {mentor.is_private && (
                            <p style={{ margin: "4px 0", color: "#555" }}>我的私有导师</p>
                        )}

                        <div className="mentorDetailSidebarItem" style={{ margin: "4px 0" }}>
                            <div className="mentorDetailSidebarLabel">
                                <img src="/Mentor_Profile.ico" alt="" aria-hidden="true" className="mentorDetailSidebarIcon" />
                                <span>导师画像</span>
                            </div>
                            <div className="mentorDetailSidebarValue mentorDetailProfileValue">
                                {mentorProfileLines.map((line, index) => {
                                    const trimmedLine = line.trim();
                                    // Highlight a few known section titles inside the free-form profile text.
                                    const isHighlightedHeading = mentorProfileHighlightedHeadings.has(trimmedLine);

                                    return (
                                        <span key={`${index}-${trimmedLine}`} className="mentorDetailProfileLine">
                                            <span
                                                className={isHighlightedHeading ? "mentorDetailProfileHeadingHighlight" : undefined}
                                                data-highlighted-profile-heading={isHighlightedHeading ? "true" : undefined}
                                            >
                                                {line === "" ? "\u00A0" : line}
                                            </span>
                                        </span>
                                    );
                                })}
                            </div>
                        </div>

                        <p style={{ margin: "8px 0 4px", fontSize: "14px" }}>相关论文：</p>
                        {mentor.paper_ids.length > 0 ? (
                            <ul style={{ margin: 0, paddingLeft: 0, fontSize: "14px", listStyle: "none" }}>
                                {mentor.paper_ids.map((paper) => (
                                    <li key={paper.id}>
                                        {paper.arxiv_url ? (
                                            <a
                                                href={paper.arxiv_url}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="mentorPaperLink"
                                            >
                                                <img
                                                    src="/arxiv.ico"
                                                    alt=""
                                                    aria-hidden="true"
                                                    className="mentorPaperLinkIcon"
                                                />
                                                <span className="mentorPaperLinkText">
                                                    <LatexText text={paper.title} forceInlineMath />
                                                </span>
                                            </a>
                                        ) : (
                                            <span
                                                className="mentorPaperLink"
                                                style={{ color: "#1f2328", cursor: "default" }}
                                            >
                                                <img
                                                    src="/arxiv.ico"
                                                    alt=""
                                                    aria-hidden="true"
                                                    className="mentorPaperLinkIcon"
                                                />
                                                <span className="mentorPaperLinkText">
                                                    <LatexText text={paper.title} forceInlineMath />
                                                </span>
                                            </span>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p style={{ margin: "4px 0" }}>暂无相关论文</p>
                        )}
                    </div>
                </div>

                <div className="mentorDetailRightColumn">
                    <aside
                        aria-label="导师信息"
                        className="mentorDetailSidebar"
                    >
                        <h3 className="mentorDetailSidebarTitle">导师信息</h3>

                        <section className="mentorDetailSidebarItem">
                            <div className="mentorDetailSidebarLabel">
                                <img src="/English_Name.ico" alt="" aria-hidden="true" className="mentorDetailSidebarIcon" />
                                <span>英文名</span>
                            </div>
                            <p className="mentorDetailSidebarValue">{mentor.English_name?.trim() || "暂无英文名"}</p>
                        </section>

                        <section className="mentorDetailSidebarItem">
                            <div className="mentorDetailSidebarLabel">
                                <img src="/Reseach_Direction.ico" alt="" aria-hidden="true" className="mentorDetailSidebarIcon" />
                                <span>研究方向</span>
                            </div>
                            <p className="mentorDetailSidebarValue">{mentor.research_direction || "暂无研究方向"}</p>
                        </section>

                        <section className="mentorDetailSidebarItem">
                            <div className="mentorDetailSidebarLabel">
                                <img src="/Email.ico" alt="" aria-hidden="true" className="mentorDetailSidebarIcon" />
                                <span>邮箱</span>
                            </div>
                            <p className="mentorDetailSidebarValue">{mentor.email || "暂无邮箱"}</p>
                        </section>
                    </aside>

                    <button
                        type="button"
                        onClick={() => void returnToSearch()}
                        className="mentorDetailReturnButton"
                    >
                        <img
                            src="/return_back_arrow.ico"
                            alt=""
                            aria-hidden="true"
                            className="mentorDetailReturnButtonIcon"
                        />
                        <span className="mentorDetailReturnButtonText">返回检索</span>
                    </button>
                </div>
            </div>

            <style jsx>{`
                :global(.appMain:has(.mentorDetailPageWide)) {
                    width: min(1412px, calc(100% - 32px));
                }

                .mentorDetailPageWide {
                    /* Keep the sticky sidebars below the global top navigation. */
                    --mentor-detail-sticky-top: 80px;
                }

                .mentorDetailLayout {
                    display: grid;
                    grid-template-columns: 300px 794px 270px;
                    gap: 24px;
                    align-items: start;
                }

                .mentorDetailAiSidebar,
                .mentorDetailSidebar {
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    background: #ffffff;
                    padding: 12px;
                }

                .mentorDetailRightColumn {
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                    position: sticky;
                    top: var(--mentor-detail-sticky-top);
                    align-self: start;
                    max-height: calc(100vh - var(--mentor-detail-sticky-top) - 16px);
                    overflow-y: auto;
                }

                .mentorDetailSidebarTitle {
                    margin: 0 0 12px;
                    font-size: 16px;
                }

                .mentorDetailAiSidebar {
                    font-size: 14px;
                    position: sticky;
                    top: var(--mentor-detail-sticky-top);
                    align-self: start;
                    max-height: calc(100vh - var(--mentor-detail-sticky-top) - 16px);
                    overflow-y: auto;
                }

                .mentorDetailAiSidebar :global(button) {
                    font-size: 14px;
                }

                .mentorDetailAiSidebar p,
                .mentorDetailAiSidebar li,
                .mentorDetailAiSidebar ul,
                .mentorDetailAiSidebar div {
                    font-size: 14px;
                }

                .mentorDetailAiResultCard {
                    margin-top: 16px;
                    padding: 12px;
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    background-color: #fafafa;
                }

                .mentorDetailSidebarItem {
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                }

                .mentorDetailSidebarItem + .mentorDetailSidebarItem {
                    margin-top: 12px;
                }

                .mentorDetailSidebarLabel {
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    font-size: 14px;
                    font-weight: 600;
                    color: #1f2328;
                }

                .mentorDetailSidebarIcon {
                    width: 16px;
                    height: 16px;
                    object-fit: contain;
                    display: block;
                    flex: 0 0 auto;
                }

                .mentorDetailSidebarValue {
                    margin: 0;
                    font-size: 14px;
                    color: #1f2328;
                    word-break: break-word;
                    white-space: normal;
                }

                .mentorDetailProfileValue {
                    display: flex;
                    flex-direction: column;
                    gap: 2px;
                }

                .mentorDetailProfileLine {
                    display: block;
                    white-space: pre-wrap;
                }

                .mentorDetailProfileHeadingHighlight {
                    background-color: #fff36d;
                    padding: 0 2px;
                    border-radius: 2px;
                }

                .mentorDetailReturnButton {
                    width: 100%;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 6px;
                }

                .mentorDetailReturnButtonIcon {
                    width: 16px;
                    height: 16px;
                    object-fit: contain;
                    display: block;
                    flex: 0 0 auto;
                }

                .mentorDetailReturnButtonText {
                    display: inline-block;
                }

                @media (max-width: 1440px) {
                    .mentorDetailLayout {
                        grid-template-columns: minmax(0, 1fr);
                    }

                    .mentorDetailAiSidebar {
                        order: 3;
                        position: static;
                        top: auto;
                        max-height: none;
                        overflow: visible;
                    }

                    .mentorDetailSidebar {
                        order: 2;
                    }

                    .mentorDetailRightColumn {
                        order: 2;
                        position: static;
                        top: auto;
                        max-height: none;
                        overflow: visible;
                    }
                }
            `}</style>
        </div>
    );
};

export default MentorDetailPage;
