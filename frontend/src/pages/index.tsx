import { RootState } from "../redux/store";
import { useSelector } from "react-redux";
import { useEffect, useRef, useState } from "react";
import LatexText from "../components/LatexText";
import { getArxivSubjectDisplayName } from "../constants/arxivSubjects";
import { request } from "../utils/network";
import {
    WeeklyPushHistoryResponse,
    WeeklyPushItem,
    WeeklyPushPaper,
    WeeklyPushSubjectGroup,
    WeeklyPushResponse,
} from "../utils/types";

const GENERATED_BY_LABELS: Record<string, string> = {
    rule: "规则摘要",
    "thucs-openai": "AI摘要",
};
// These constants keep the homepage skeletons and carousels visually consistent across sections.
const WEEKLY_PUSH_PAPERS_PER_VIEW = 2;
const WEEKLY_PUSH_CAROUSEL_GAP = 12;
const SUBJECT_GROUP_CAROUSEL_GAP = 16;
const HOME_SKELETON_HISTORY_COUNT = 3;
const HOME_SKELETON_STAT_COUNT = 5;
const HOME_SKELETON_PAPER_COUNT = 10;
const HOME_SKELETON_SUBJECT_COUNT = 2;

// Create stable keys for repeated homepage skeleton placeholders.
const createHomeSkeletonKeys = (count: number, prefix: string) => (
    Array.from({ length: count }, (_, idx) => `${prefix}-${idx}`)
);

// Fall back to the raw backend value if a new generation mode appears before the UI labels are updated.
// Convert a backend generation identifier into the label shown in the UI.
const formatGeneratedBy = (generatedBy: string) => GENERATED_BY_LABELS[generatedBy] || generatedBy;

// Normalize unknown generation failures into a readable homepage error message.
const getErrorMessage = (error: unknown) => {
    if (error instanceof Error && error.message.trim() !== "") {
        return error.message;
    }
    return "个性周报生成失败，请稍后重试。";
};

// Fetch one personalized weekly report, optionally for a specific historical week.
const fetchPersonalizedWeeklyPush = async (weekStart?: string) => {
    const query = weekStart
        ? `?week_start=${encodeURIComponent(weekStart)}`
        : "";
    // Personalized reports depend on the current user's follows, so they use a dedicated authenticated endpoint.
    return request<WeeklyPushResponse>(
        `/api/dataset/weekly-push/personalized${query}`,
        "GET",
        true,
    );
};

// Fetch the available history entries for personalized weekly reports.
const fetchPersonalizedWeeklyPushHistory = async () => (
    request<WeeklyPushHistoryResponse>(
        "/api/dataset/weekly-push/personalized/history",
        "GET",
        true,
    )
);

// Update previous/next button state based on the current carousel scroll position.
const syncCarouselControls = (
    viewport: HTMLDivElement,
    setCanScrollPrev: (value: boolean) => void,
    setCanScrollNext: (value: boolean) => void,
) => {
    // Derive button availability from actual scroll position so resizing does not desync the controls.
    const maxScrollLeft = Math.max(viewport.scrollWidth - viewport.clientWidth, 0);
    setCanScrollPrev(viewport.scrollLeft > 4);
    setCanScrollNext(viewport.scrollLeft < maxScrollLeft - 4);
};

// Compute how far a carousel should scroll for one previous/next action.
const getCarouselScrollStep = (
    viewport: HTMLDivElement,
    cardSelector: string,
    fallbackItemCount: number,
    gap: number,
) => {
    // Scroll by one card width when measurable; otherwise estimate from the viewport width.
    const firstCard = viewport.querySelector<HTMLElement>(cardSelector) ?? undefined;
    if (firstCard !== undefined) {
        return firstCard.offsetWidth + gap;
    }
    return viewport.clientWidth / fallbackItemCount;
};

interface WeeklyPushPaperListProps {
    papers: WeeklyPushPaper[];
    emptyText: string;
    showMentorNames?: boolean;
}

interface WeeklyPaperAbstractPreviewProps {
    text: string;
}

// Render a clamped abstract preview and show an ellipsis indicator when the text is truncated.
const WeeklyPaperAbstractPreview = ({ text }: WeeklyPaperAbstractPreviewProps) => {
    const containerRef = useRef<HTMLDivElement | undefined>(undefined);
    const [isTruncated, setIsTruncated] = useState(false);

    useEffect(() => {
        const container = containerRef.current;
        if (container === undefined) {
            return undefined;
        }

        const updateTruncationState = () => {
            // Compare scrollHeight and clientHeight to detect whether the abstract clamp is actually truncating text.
            setIsTruncated(container.scrollHeight - container.clientHeight > 1);
        };

        updateTruncationState();

        if (typeof window !== "undefined") {
            window.addEventListener("resize", updateTruncationState);
        }

        if (typeof ResizeObserver === "undefined") {
            return () => {
                if (typeof window !== "undefined") {
                    window.removeEventListener("resize", updateTruncationState);
                }
            };
        }

        const observer = new ResizeObserver(() => {
            updateTruncationState();
        });
        observer.observe(container);

        return () => {
            observer.disconnect();
            if (typeof window !== "undefined") {
                window.removeEventListener("resize", updateTruncationState);
            }
        };
    }, [text]);

    return (
        <div className="homeWeeklyPaperAbstractRow">
            <div
                ref={(node) => {
                    containerRef.current = node ?? undefined;
                }}
                className={`homeWeeklyPaperAbstractClamp${isTruncated ? " homeWeeklyPaperAbstractClampTruncated" : ""}`}
            >
                <div className="homeWeeklyPaperAbstractContent">
                    <LatexText text={text} />
                </div>
            </div>
            {isTruncated && <div className="homeWeeklyPaperAbstractEllipsis">...</div>}
        </div>
    );
};

// Render the paper carousel used inside weekly report cards.
const WeeklyPushPaperList = ({
    papers,
    emptyText,
    showMentorNames = false,
}: WeeklyPushPaperListProps) => {
    const viewportRef = useRef<HTMLDivElement | undefined>(undefined);
    const [canScrollPrev, setCanScrollPrev] = useState(false);
    const [canScrollNext, setCanScrollNext] = useState(
        papers.length > WEEKLY_PUSH_PAPERS_PER_VIEW,
    );
    const [hoverTooltip, setHoverTooltip] = useState<{
        x: number;
        y: number;
        text: string;
    } | undefined>(undefined);

    // Move the paper carousel one step left or right.
    const scrollCarousel = (direction: -1 | 1) => {
        const viewport = viewportRef.current;
        if (viewport === undefined) {
            return;
        }

        const scrollStep = getCarouselScrollStep(
            viewport,
            "[data-weekly-push-paper-card='true']",
            WEEKLY_PUSH_PAPERS_PER_VIEW,
            WEEKLY_PUSH_CAROUSEL_GAP,
        );
        const nextLeft = viewport.scrollLeft + direction * scrollStep;
        if (typeof viewport.scrollBy === "function") {
            // Prefer smooth native scrolling while keeping a deterministic fallback for unsupported environments.
            viewport.scrollBy({
                left: direction * scrollStep,
                behavior: "smooth",
            });
            return;
        }

        viewport.scrollLeft = nextLeft;
        syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
    };

    // Recompute carousel control state after manual scrolling.
    const handleViewportScroll = () => {
        const viewport = viewportRef.current;
        if (viewport === undefined) {
            return;
        }
        syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
    };

    useEffect(() => {
        const viewport = viewportRef.current;
        if (viewport === undefined) {
            return;
        }

        // Reset the carousel when a different weekly report replaces the paper list.
        if (typeof viewport.scrollTo === "function") {
            viewport.scrollTo({ left: 0, behavior: "auto" });
        }
        else {
            viewport.scrollLeft = 0;
        }
        syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
    }, [papers]);

    useEffect(() => {
        if (typeof window === "undefined") {
            return undefined;
        }

        const handleResize = () => {
            const viewport = viewportRef.current;
            if (viewport === undefined) {
                return;
            }
            syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
        };
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    if (papers.length === 0) {
        return <div style={{ color: "#666" }}>{emptyText}</div>;
    }

    return (
        <div className="homeWeeklyPaperCarouselShell">
            {papers.length > WEEKLY_PUSH_PAPERS_PER_VIEW && (
                <div className="homeWeeklyPaperCarouselControls">
                    <button
                        type="button"
                        className="homeWeeklyPaperCarouselButton"
                        onClick={() => scrollCarousel(-1)}
                        disabled={!canScrollPrev}
                    >
                        上一篇
                    </button>
                    <button
                        type="button"
                        className="homeWeeklyPaperCarouselButton"
                        onClick={() => scrollCarousel(1)}
                        disabled={!canScrollNext}
                    >
                        下一篇
                    </button>
                </div>
            )}
            <div
                ref={(node) => {
                    viewportRef.current = node ?? undefined;
                }}
                className="homeWeeklyPaperCarouselViewport"
                onScroll={handleViewportScroll}
            >
                <div className="homeWeeklyPaperCarouselTrack">
                    {papers.map((paper) => (
                        <article
                            key={paper.id}
                            data-weekly-push-paper-card="true"
                            className="homeWeeklyPaperCarouselCard"
                        >
                            <div style={{ border: "1px solid #eee", borderRadius: 6, padding: 10, backgroundColor: "#fff", minHeight: "100%" }}>
                                <div style={{ fontWeight: 600 }}>
                                    {paper.arxivUrl ? (
                                        <a
                                            href={paper.arxivUrl}
                                            target="_blank"
                                            rel="noreferrer"
                                            title="前往此论文 arXiv 页面"
                                            onMouseEnter={(event) => setHoverTooltip({
                                                x: event.clientX + 14,
                                                y: event.clientY + 18,
                                                text: "前往此论文 arXiv 页面",
                                            })}
                                            onMouseMove={(event) => setHoverTooltip((current) => (
                                                current === undefined
                                                    ? undefined
                                                    : {
                                                        ...current,
                                                        x: event.clientX + 14,
                                                        y: event.clientY + 18,
                                                    }
                                            ))}
                                            onMouseLeave={() => setHoverTooltip(undefined)}
                                        >
                                            <LatexText text={paper.title} forceInlineMath />
                                        </a>
                                    ) : (
                                        <LatexText text={paper.title} forceInlineMath />
                                    )}
                                </div>
                                <div className="homeWeeklyPaperMeta">
                                    <div className="homeWeeklyPaperAuthors">
                                        作者：{paper.authorNames || "未知"}
                                    </div>
                                    <div className="homeWeeklyPaperDate">
                                        {paper.publishDate || "未知日期"}
                                    </div>
                                </div>
                                {showMentorNames && paper.mentorNames && paper.mentorNames.length > 0 && (
                                    <div style={{ fontSize: 13, color: "#0f5c4d", marginTop: 4 }}>
                                        关联导师：{paper.mentorNames.join("、")}
                                    </div>
                                )}
                                <WeeklyPaperAbstractPreview text={paper.tldr || paper.abstract || "暂无摘要"} />
                            </div>
                        </article>
                    ))}
                </div>
            </div>
            {hoverTooltip !== undefined && (
                <div
                    className="homeWeeklyPaperHoverTooltip"
                    style={{
                        left: hoverTooltip.x,
                        top: hoverTooltip.y,
                    }}
                >
                    {hoverTooltip.text}
                </div>
            )}
        </div>
    );
};

interface WeeklyPushSubjectGroupsProps {
    groups: WeeklyPushSubjectGroup[];
}

// Render followed subject groups as a carousel and show the full paper list in a modal when clicked.
export const WeeklyPushSubjectGroups = ({ groups }: WeeklyPushSubjectGroupsProps) => {
    const viewportRef = useRef<HTMLDivElement | undefined>(undefined);
    const modalCloseButtonRef = useRef<HTMLButtonElement | undefined>(undefined);
    const previousOverflowRef = useRef("");
    const [canScrollPrev, setCanScrollPrev] = useState(false);
    const [canScrollNext, setCanScrollNext] = useState(false);
    const [selectedGroup, setSelectedGroup] = useState<WeeklyPushSubjectGroup | undefined>(undefined);

    // Close the currently open subject detail modal.
    const closeModal = () => {
        setSelectedGroup(undefined);
    };

    // Move the subject-group carousel one step left or right.
    const scrollCarousel = (direction: -1 | 1) => {
        const viewport = viewportRef.current;
        if (viewport === undefined) {
            return;
        }

        const scrollStep = getCarouselScrollStep(
            viewport,
            "[data-weekly-push-subject-card='true']",
            1,
            SUBJECT_GROUP_CAROUSEL_GAP,
        );
        const nextLeft = viewport.scrollLeft + direction * scrollStep;

        if (typeof viewport.scrollBy === "function") {
            viewport.scrollBy({
                left: direction * scrollStep,
                behavior: "smooth",
            });
            return;
        }

        viewport.scrollLeft = nextLeft;
        syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
    };

    // Recompute subject carousel control state after manual scrolling.
    const handleViewportScroll = () => {
        const viewport = viewportRef.current;
        if (viewport === undefined) {
            return;
        }
        syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
    };

    useEffect(() => {
        const viewport = viewportRef.current;
        if (viewport === undefined) {
            return;
        }

        if (typeof viewport.scrollTo === "function") {
            viewport.scrollTo({ left: 0, behavior: "auto" });
        }
        else {
            viewport.scrollLeft = 0;
        }
        syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
    }, [groups]);

    useEffect(() => {
        if (typeof window === "undefined") {
            return undefined;
        }

        const handleResize = () => {
            const viewport = viewportRef.current;
            if (viewport === undefined) {
                return;
            }
            syncCarouselControls(viewport, setCanScrollPrev, setCanScrollNext);
        };
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    useEffect(() => {
        if (typeof document === "undefined") {
            return undefined;
        }

        if (selectedGroup === undefined) {
            document.body.style.overflow = previousOverflowRef.current;
            return undefined;
        }

        previousOverflowRef.current = document.body.style.overflow;
        // Prevent the page behind the modal from scrolling while a subject detail dialog is open.
        document.body.style.overflow = "hidden";

        return () => {
            document.body.style.overflow = previousOverflowRef.current;
        };
    }, [selectedGroup]);

    useEffect(() => {
        if (selectedGroup === undefined) {
            return undefined;
        }

        // Support keyboard dismissal and initial focus placement for the subject modal.
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                event.preventDefault();
                closeModal();
            }
        };

        if (typeof window !== "undefined") {
            window.addEventListener("keydown", handleKeyDown);
        }

        if (typeof window !== "undefined" && typeof window.setTimeout === "function") {
            window.setTimeout(() => {
                const modalCloseButton = modalCloseButtonRef.current;
                if (modalCloseButton !== undefined) {
                    modalCloseButton.focus();
                }
            }, 0);
        }

        return () => {
            if (typeof window !== "undefined") {
                window.removeEventListener("keydown", handleKeyDown);
            }
        };
    }, [selectedGroup]);

    if (groups.length === 0) {
        return (
            <div className="homePersonalizedPlaceholder">
                你关注的板块本周暂无新增论文。
            </div>
        );
    }

    const selectedSubjectDisplayName = selectedGroup === undefined
        ? ""
        : getArxivSubjectDisplayName(selectedGroup.subject);

    return (
        <>
            <div className="homeSubjectCarouselShell">
                {groups.length > 1 && (
                    <div className="homeSubjectCarouselControls">
                        <button
                            type="button"
                            className="homeWeeklyPaperCarouselButton"
                            onClick={() => scrollCarousel(-1)}
                            disabled={!canScrollPrev}
                        >
                            上一板块
                        </button>
                        <button
                            type="button"
                            className="homeWeeklyPaperCarouselButton"
                            onClick={() => scrollCarousel(1)}
                            disabled={!canScrollNext}
                        >
                            下一板块
                        </button>
                    </div>
                )}
                <div
                    ref={(node) => {
                        viewportRef.current = node ?? undefined;
                    }}
                    className="homeSubjectCarouselViewport"
                    onScroll={handleViewportScroll}
                >
                    <div className="homeSubjectCarouselTrack">
                        {groups.map((group) => {
                            const subjectDisplayName = getArxivSubjectDisplayName(group.subject);
                            return (
                                <button
                                    key={group.subject}
                                    type="button"
                                    data-weekly-push-subject-card="true"
                                    className="homeSubjectCarouselCard"
                                    onClick={() => setSelectedGroup(group)}
                                    aria-label={`查看板块 ${group.subject} 的 ${group.paperCount} 篇论文`}
                                >
                                    <div className="homeSubjectCarouselCardContent">
                                        <div className="homeSubjectCarouselHeader">
                                            <div className="homeSubjectCarouselCode">
                                                {group.subject}
                                            </div>
                                            {subjectDisplayName !== "" && subjectDisplayName !== group.subject && (
                                                <div className="homeSubjectCarouselDisplayName">
                                                    {subjectDisplayName}
                                                </div>
                                            )}
                                        </div>
                                        <div className="homeSubjectCarouselCount">{group.paperCount}篇</div>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>
            {selectedGroup !== undefined && (
                <div
                    className="homeSubjectModalOverlay"
                    role="presentation"
                    onClick={(event) => {
                        if (event.target === event.currentTarget) {
                            closeModal();
                        }
                    }}
                >
                    <div
                        className="homeSubjectModalDialog"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="home-subject-modal-title"
                    >
                        <button
                            ref={(node) => {
                                modalCloseButtonRef.current = node ?? undefined;
                            }}
                            type="button"
                            className="homeSubjectModalCloseButton"
                            onClick={closeModal}
                            aria-label={`关闭 ${selectedGroup.subject} 板块详情`}
                        >
                            <span className="homeSubjectModalCloseIcon" aria-hidden="true" />
                        </button>
                        <div className="homeSubjectModalHeader">
                            <div className="homeSubjectModalEyebrow">关注板块动态</div>
                            <div className="homeSubjectModalCode">{selectedGroup.subject}</div>
                            {selectedSubjectDisplayName !== "" && selectedSubjectDisplayName !== selectedGroup.subject && (
                                <div id="home-subject-modal-title" className="homeSubjectModalDisplayName homeSubjectModalDisplayNameHeading">
                                    {selectedSubjectDisplayName}
                                </div>
                            )}
                            {!(selectedSubjectDisplayName !== "" && selectedSubjectDisplayName !== selectedGroup.subject) && (
                                <h5 id="home-subject-modal-title" className="homeSubjectModalTitle">
                                    <LatexText text={selectedGroup.subject} forceInlineMath />
                                </h5>
                            )}
                            <div className="homeSubjectModalCount">{selectedGroup.paperCount}篇</div>
                        </div>
                        <div className="homeSubjectModalBody">
                            {selectedGroup.papers.map((paper) => (
                                <article
                                    className="homeSubjectModalPaperCard"
                                    key={`${selectedGroup.subject}-${paper.id}`}
                                >
                                    <div className="homeSubjectPaperTitle">
                                        <LatexText text={paper.title} forceInlineMath />
                                    </div>
                                    <div className="homeSubjectPaperMeta">
                                        作者：{paper.authorNames || "未知"} ｜ {paper.publishDate || "未知日期"} ｜ 分类：{paper.subjects.join(", ") || selectedGroup.subject}
                                    </div>
                                    <div className="homePersonalizedLatexText">
                                        <LatexText text={paper.abstractPreview || "暂无摘要"} />
                                    </div>
                                </article>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

interface WeeklyPushDetailCardProps {
    push: WeeklyPushItem;
    emptyPaperText: string;
    showMentorNames?: boolean;
    showPersonalizedSummary?: boolean;
    showSplitSummary?: boolean;
    summaryVariant?: "personalized" | "public";
    showLargeTitle?: boolean;
    hideTitle?: boolean;
}

// Render one weekly report card, including summaries, metadata, papers, and subject activity.
export const WeeklyPushDetailCard = ({
    push,
    emptyPaperText,
    showMentorNames = false,
    showPersonalizedSummary = false,
    showSplitSummary = false,
    summaryVariant = "personalized",
    showLargeTitle = false,
    hideTitle = false,
}: WeeklyPushDetailCardProps) => {
    // Render separate blocks only when the AI summary actually differs from the fixed summary.
    const distinctAiSummary = push.aiSummary.trim() !== "" && push.aiSummary !== push.fixedSummary;
    const shouldRenderSplitSummary = showSplitSummary || showPersonalizedSummary;
    const summaryStackClassName = summaryVariant === "public"
        ? "homeWeeklySummaryStack"
        : "homePersonalizedSummaryStack";
    const summaryBlockClassName = summaryVariant === "public"
        ? "homeWeeklySummaryBlock"
        : "homePersonalizedSummaryBlock";
    const summaryAccentClassName = summaryVariant === "public"
        ? "homeWeeklySummaryBlockAccent"
        : "homePersonalizedSummaryBlockAccent";
    const summaryLabelClassName = summaryVariant === "public"
        ? "homeWeeklySummaryLabel"
        : "homePersonalizedSummaryLabel";
    const summaryTextClassName = summaryVariant === "public"
        ? "homeWeeklySummaryText"
        : "homePersonalizedLatexText";

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {!hideTitle && (
                <div className={showLargeTitle ? "homeWeeklyPushCardTitle homeWeeklyPushCardTitleLarge" : "homeWeeklyPushCardTitle"}>
                    {push.title}
                </div>
            )}
            {shouldRenderSplitSummary ? (
                <div className={summaryStackClassName}>
                    {distinctAiSummary ? (
                        <>
                            <div className={summaryBlockClassName}>
                                <div className={summaryLabelClassName}>周概览</div>
                                <div className={summaryTextClassName}>
                                    <LatexText text={push.fixedSummary} />
                                </div>
                            </div>
                            <div className={`${summaryBlockClassName} ${summaryAccentClassName}`}>
                                <div className={summaryLabelClassName}>AI总结</div>
                                <div className={summaryTextClassName}>
                                    <LatexText text={push.aiSummary} />
                                </div>
                            </div>
                        </>
                    ) : (
                        <div className={summaryBlockClassName}>
                            <div className={summaryLabelClassName}>摘要结果</div>
                            <div className={summaryTextClassName}>
                                <LatexText text={push.content} />
                            </div>
                        </div>
                    )}
                </div>
            ) : (
                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{push.content}</div>
            )}
            <div>
                <h4 className="homeWeeklyPushSectionTitle">本周论文</h4>
                <WeeklyPushPaperList
                    papers={push.papers}
                    emptyText={emptyPaperText}
                    showMentorNames={showMentorNames}
                />
            </div>
            {showPersonalizedSummary && (
                <div>
                    <h4 className="homeWeeklyPushSectionTitle">关注板块动态</h4>
                    <WeeklyPushSubjectGroups groups={push.subjectGroups || []} />
                </div>
            )}
        </div>
    );
};

// Render placeholder paper cards while a weekly report is loading.
const renderHomePaperSkeletonGrid = () => (
    <div className="homeSkeletonPaperGrid" aria-hidden="true">
        {createHomeSkeletonKeys(HOME_SKELETON_PAPER_COUNT, "home-paper").map((key) => (
            <article key={key} className="homeSkeletonPaperCard">
                <span className="homeSkeletonBlock homeSkeletonPaperTitle" />
                <span className="homeSkeletonBlock homeSkeletonPaperMeta" />
                <span className="homeSkeletonBlock homeSkeletonPaperMeta homeSkeletonPaperMetaShort" />
                <div className="homeSkeletonParagraph">
                    <span className="homeSkeletonBlock homeSkeletonLine" />
                    <span className="homeSkeletonBlock homeSkeletonLine" />
                    <span className="homeSkeletonBlock homeSkeletonLine homeSkeletonLineShort" />
                </div>
            </article>
        ))}
    </div>
);

// Render the public weekly report skeleton layout.
const renderHomeWeeklyPushSkeleton = () => (
    <div className="homeSkeletonStack" data-testid="home-weekly-push-skeleton" aria-hidden="true">
        <div className="homeSkeletonHeader">
            <span className="homeSkeletonBlock homeSkeletonTitle" />
            <span className="homeSkeletonBlock homeSkeletonMeta" />
        </div>
        <div className="homeSkeletonParagraph">
            <span className="homeSkeletonBlock homeSkeletonLine" />
            <span className="homeSkeletonBlock homeSkeletonLine" />
            <span className="homeSkeletonBlock homeSkeletonLine homeSkeletonLineMedium" />
        </div>
        <span className="homeSkeletonBlock homeSkeletonSectionTitle" />
        {renderHomePaperSkeletonGrid()}
    </div>
);

// Render the personalized weekly report skeleton layout with stats and subject sections.
const renderHomePersonalizedPushSkeleton = () => (
    <div className="homeSkeletonStack" data-testid="home-personalized-push-skeleton" aria-hidden="true">
        <div className="homeSkeletonStats">
            {createHomeSkeletonKeys(HOME_SKELETON_STAT_COUNT, "home-stat").map((key) => (
                <div key={key} className="homeSkeletonStatCard">
                    <span className="homeSkeletonBlock homeSkeletonStatLabel" />
                    <span className="homeSkeletonBlock homeSkeletonStatValue" />
                </div>
            ))}
        </div>
        <div className="homeSkeletonSummaryGrid">
            <div className="homeSkeletonSummaryBlock">
                <span className="homeSkeletonBlock homeSkeletonSummaryLabel" />
                <span className="homeSkeletonBlock homeSkeletonLine" />
                <span className="homeSkeletonBlock homeSkeletonLine" />
                <span className="homeSkeletonBlock homeSkeletonLine homeSkeletonLineMedium" />
            </div>
            <div className="homeSkeletonSummaryBlock">
                <span className="homeSkeletonBlock homeSkeletonSummaryLabel" />
                <span className="homeSkeletonBlock homeSkeletonLine" />
                <span className="homeSkeletonBlock homeSkeletonLine" />
                <span className="homeSkeletonBlock homeSkeletonLine homeSkeletonLineShort" />
            </div>
        </div>
        <span className="homeSkeletonBlock homeSkeletonSectionTitle" />
        {renderHomePaperSkeletonGrid()}
        <span className="homeSkeletonBlock homeSkeletonSectionTitle" />
        <div className="homeSkeletonSubjectGrid">
            {createHomeSkeletonKeys(HOME_SKELETON_SUBJECT_COUNT, "home-subject").map((key) => (
                <div key={key} className="homeSkeletonSubjectCard">
                    <span className="homeSkeletonBlock homeSkeletonSubjectCode" />
                    <span className="homeSkeletonBlock homeSkeletonSubjectName" />
                    <span className="homeSkeletonBlock homeSkeletonSubjectCount" />
                </div>
            ))}
        </div>
    </div>
);

// Render placeholder history items for the weekly-report history lists.
const renderHomeHistorySkeleton = (testId: string) => (
    <div className="homeSkeletonHistoryList" data-testid={testId} aria-hidden="true">
        {createHomeSkeletonKeys(HOME_SKELETON_HISTORY_COUNT, testId).map((key) => (
            <div key={key} className="homeSkeletonHistoryItem">
                <span className="homeSkeletonBlock homeSkeletonHistoryTitle" />
                <span className="homeSkeletonBlock homeSkeletonHistoryMeta" />
            </div>
        ))}
    </div>
);

// Render the homepage dashboard for public and personalized weekly paper reports.
const HomeScreen = () => {
    const auth = useSelector((state: RootState) => state.auth);
    const isLoggedIn = auth.token !== "";
    const [weeklyPush, setWeeklyPush] = useState<WeeklyPushItem | undefined>(undefined);
    const [weeklyPushHistory, setWeeklyPushHistory] = useState<WeeklyPushHistoryResponse["history"]>([]);
    const [selectedWeekStart, setSelectedWeekStart] = useState("");
    const [personalizedWeeklyPush, setPersonalizedWeeklyPush] = useState<WeeklyPushItem | undefined>(undefined);
    const [personalizedWeeklyPushHistory, setPersonalizedWeeklyPushHistory] = useState<WeeklyPushHistoryResponse["history"]>([]);
    const [selectedPersonalizedWeekStart, setSelectedPersonalizedWeekStart] = useState("");
    const [loadingWeeklyPush, setLoadingWeeklyPush] = useState(true);
    const [loadingPersonalizedWeeklyPush, setLoadingPersonalizedWeeklyPush] = useState(isLoggedIn);
    const [isGeneratingPersonalized, setIsGeneratingPersonalized] = useState(false);
    const [personalizedError, setPersonalizedError] = useState("");

    useEffect(() => {
        const loadWeeklyPush = async () => {
            setLoadingWeeklyPush(true);
            try {
                // Load the latest public report and its history in parallel for the homepage dashboard.
                const [latestRes, historyRes] = await Promise.all([
                    request<WeeklyPushResponse>("/api/dataset/weekly-push/latest", "GET", false),
                    request<WeeklyPushHistoryResponse>("/api/dataset/weekly-push/history", "GET", false),
                ]);

                setWeeklyPushHistory(historyRes.history || []);
                setWeeklyPush(latestRes.weeklyPush);
                setSelectedWeekStart(latestRes.weeklyPush?.weekStart || historyRes.history[0]?.weekStart || "");
            }
            catch {
                setWeeklyPush(undefined);
                setWeeklyPushHistory([]);
                setSelectedWeekStart("");
            }
            finally {
                setLoadingWeeklyPush(false);
            }
        };

        void loadWeeklyPush();
    }, []);

    useEffect(() => {
        if (selectedWeekStart === "") {
            return;
        }

        if (weeklyPush?.weekStart === selectedWeekStart) {
            return;
        }

        const loadSelectedPush = async () => {
            setLoadingWeeklyPush(true);
            try {
                // Changing the selected history week reuses the same endpoint with an explicit week_start query.
                const res = await request<WeeklyPushResponse>(
                    `/api/dataset/weekly-push/latest?week_start=${encodeURIComponent(selectedWeekStart)}`,
                    "GET",
                    false,
                );
                setWeeklyPush(res.weeklyPush);
            }
            catch {
                setWeeklyPush(undefined);
            }
            finally {
                setLoadingWeeklyPush(false);
            }
        };

        void loadSelectedPush();
    }, [selectedWeekStart, weeklyPush?.weekStart]);

    useEffect(() => {
        if (!isLoggedIn) {
            setPersonalizedWeeklyPush(undefined);
            setPersonalizedWeeklyPushHistory([]);
            setSelectedPersonalizedWeekStart("");
            setPersonalizedError("");
            setLoadingPersonalizedWeeklyPush(false);
            return;
        }

        const loadStoredPersonalizedPush = async () => {
            setLoadingPersonalizedWeeklyPush(true);
            try {
                // Logged-in users see their latest personalized report and its history immediately on page load.
                const [latestRes, historyRes] = await Promise.all([
                    fetchPersonalizedWeeklyPush(),
                    fetchPersonalizedWeeklyPushHistory(),
                ]);
                const history = historyRes.history || [];
                const latestPush = latestRes.weeklyPush;

                setPersonalizedWeeklyPushHistory(history);
                setPersonalizedWeeklyPush(latestPush);
                setSelectedPersonalizedWeekStart(
                    latestPush?.weekStart || history[0]?.weekStart || "",
                );
                setPersonalizedError("");
            }
            catch {
                setPersonalizedWeeklyPush(undefined);
                setPersonalizedWeeklyPushHistory([]);
                setSelectedPersonalizedWeekStart("");
            }
            finally {
                setLoadingPersonalizedWeeklyPush(false);
            }
        };

        void loadStoredPersonalizedPush();
    }, [isLoggedIn]);

    useEffect(() => {
        if (!isLoggedIn || selectedPersonalizedWeekStart === "") {
            return;
        }

        if (personalizedWeeklyPush?.weekStart === selectedPersonalizedWeekStart) {
            return;
        }

        const loadSelectedPersonalizedPush = async () => {
            setLoadingPersonalizedWeeklyPush(true);
            try {
                const res = await fetchPersonalizedWeeklyPush(selectedPersonalizedWeekStart);
                setPersonalizedWeeklyPush(res.weeklyPush);
                setPersonalizedError("");
            }
            catch {
                setPersonalizedWeeklyPush(undefined);
            }
            finally {
                setLoadingPersonalizedWeeklyPush(false);
            }
        };

        void loadSelectedPersonalizedPush();
    }, [isLoggedIn, personalizedWeeklyPush?.weekStart, selectedPersonalizedWeekStart]);

    // Trigger generation of a fresh personalized weekly report for the current user.
    const handleGeneratePersonalizedPush = async () => {
        setIsGeneratingPersonalized(true);
        setPersonalizedError("");

        try {
            // Personalized generation is explicit because it may trigger fresh backend summarization work.
            const res = await request<WeeklyPushResponse>(
                "/api/dataset/weekly-push/personalized",
                "POST",
                true,
            );
            const generatedPush = res.weeklyPush;
            setPersonalizedWeeklyPush(generatedPush);
            setSelectedPersonalizedWeekStart(generatedPush?.weekStart || "");

            try {
                const historyRes = await fetchPersonalizedWeeklyPushHistory();
                setPersonalizedWeeklyPushHistory(historyRes.history || []);
            }
            catch {
                // Keep the freshly generated result visible even if history refresh fails.
            }
        }
        catch (error) {
            setPersonalizedError(getErrorMessage(error));
        }
        finally {
            setIsGeneratingPersonalized(false);
        }
    };

    return (
        <div className="homePageShell">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <h2 className="homePageTitle">欢迎回来！</h2>
            </div>

            <div className="homePageLayout">
                <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
                    <section className="homePersonalizedPanel">
                        <div className="homePersonalizedPanelHeader">
                            <div className="homePersonalizedPanelHeaderMain">
                                <h3 className="homePanelTitle">个性周报</h3>
                            </div>
                            {isLoggedIn && (
                                <div className="homePersonalizedPanelHeaderActions">
                                    <button
                                        type="button"
                                        onClick={handleGeneratePersonalizedPush}
                                        disabled={isGeneratingPersonalized}
                                        className="homePersonalizedButton"
                                    >
                                        {isGeneratingPersonalized
                                            ? "正在生成..."
                                            : personalizedWeeklyPush
                                                ? "重新生成个性周报"
                                                : "生成个性周报"}
                                    </button>
                                    {personalizedWeeklyPush && (
                                        <div className="homePersonalizedDateRange">
                                            {personalizedWeeklyPush.weekStart} ~ {personalizedWeeklyPush.weekEnd}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        {!isLoggedIn && (
                            <div className="homePersonalizedPlaceholder">
                                登录后即可基于你关注的导师和板块生成专属周报。
                            </div>
                        )}

                        {isLoggedIn && isGeneratingPersonalized && (
                            <div className="homePersonalizedStatusCard">
                                正在整理你关注导师和板块本周的新增论文，并生成 AI 总结，请稍候。
                            </div>
                        )}

                        {isLoggedIn && personalizedError !== "" && (
                            <div className="homePersonalizedErrorCard">{personalizedError}</div>
                        )}

                        {isLoggedIn && loadingPersonalizedWeeklyPush && !isGeneratingPersonalized && (
                            renderHomePersonalizedPushSkeleton()
                        )}

                        {isLoggedIn && !loadingPersonalizedWeeklyPush && personalizedWeeklyPush && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                <div className="homePersonalizedStats">
                                    <div className="homePersonalizedStatItem">
                                        <span>关注导师</span>
                                        <strong>{personalizedWeeklyPush.trackedMentorCount ?? 0}</strong>
                                    </div>
                                    <div className="homePersonalizedStatItem">
                                        <span>命中导师</span>
                                        <strong>{personalizedWeeklyPush.activeMentorCount ?? 0}</strong>
                                    </div>
                                    <div className="homePersonalizedStatItem">
                                        <span>关注板块</span>
                                        <strong>{personalizedWeeklyPush.trackedSubjectCount ?? 0}</strong>
                                    </div>
                                    <div className="homePersonalizedStatItem">
                                        <span>命中板块</span>
                                        <strong>{personalizedWeeklyPush.activeSubjectCount ?? 0}</strong>
                                    </div>
                                    <div className="homePersonalizedStatItem">
                                        <span>新增论文</span>
                                        <strong>{personalizedWeeklyPush.paperCount}</strong>
                                    </div>
                                </div>

                                <WeeklyPushDetailCard
                                    push={personalizedWeeklyPush}
                                    emptyPaperText="你关注的导师本周暂无新增论文明细。"
                                    showMentorNames
                                    showPersonalizedSummary
                                    hideTitle
                                />
                            </div>
                        )}

                        {isLoggedIn && loadingPersonalizedWeeklyPush && personalizedWeeklyPushHistory.length === 0 && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                <h4 className="homePersonalizedHistoryTitle">往期个性周报</h4>
                                {renderHomeHistorySkeleton("home-personalized-history-skeleton")}
                            </div>
                        )}

                        {isLoggedIn && personalizedWeeklyPushHistory.length > 0 && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                <h4 className="homePersonalizedHistoryTitle">往期个性周报</h4>
                                <div className="homeWeeklyHistoryList">
                                    {personalizedWeeklyPushHistory.map((item) => (
                                        <button
                                            key={`personalized-${item.weekStart}`}
                                            type="button"
                                            onClick={() => setSelectedPersonalizedWeekStart(item.weekStart)}
                                            style={{
                                                textAlign: "left",
                                                padding: 10,
                                                borderRadius: 6,
                                                border: selectedPersonalizedWeekStart === item.weekStart ? "1px solid #0d6efd" : "1px solid #ccc",
                                                backgroundColor: selectedPersonalizedWeekStart === item.weekStart ? "#e7f1ff" : "#fff",
                                                cursor: "pointer",
                                            }}
                                        >
                                            <div className="homeWeeklyHistoryButtonTitle">{item.title}</div>
                                            <div className="homeWeeklyHistoryButtonMeta">
                                                {item.weekStart} ~ {item.weekEnd} ｜ {item.paperCount} 篇 ｜ {formatGeneratedBy(item.generatedBy)}
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {isLoggedIn && !loadingPersonalizedWeeklyPush && !isGeneratingPersonalized && personalizedWeeklyPush === undefined && (
                            <div className="homePersonalizedPlaceholder">
                                点击上方按钮后，会按你当前关注的导师和板块即时生成一份专属周报。
                            </div>
                        )}
                    </section>

                    <section className="homeWeeklyPanel">
                        <div className="homeWeeklyPanelHeader">
                            <h3 className="homePanelTitle">每周论文推送</h3>
                            {weeklyPush && !loadingWeeklyPush && (
                                <div className="homeWeeklyPanelDateRange">
                                    {weeklyPush.weekStart} ~ {weeklyPush.weekEnd}
                                </div>
                            )}
                        </div>
                        {loadingWeeklyPush ? (
                            renderHomeWeeklyPushSkeleton()
                        ) : weeklyPush ? (
                            <WeeklyPushDetailCard
                                push={weeklyPush}
                                emptyPaperText="本周暂无论文明细。"
                                showSplitSummary
                                summaryVariant="public"
                                hideTitle
                            />
                        ) : (
                            <div className="homeWeeklyPanelEmpty">暂无周推送，请等待定时任务生成。</div>
                        )}
                        {(loadingWeeklyPush && weeklyPushHistory.length === 0) && (
                            <div className="homeWeeklyPanelHistorySection">
                                <h3 className="homePublicHistoryTitle">往期周报</h3>
                                {renderHomeHistorySkeleton("home-weekly-history-skeleton")}
                            </div>
                        )}

                        {weeklyPushHistory.length > 0 && (
                            <div className="homeWeeklyPanelHistorySection">
                                <h3 className="homePublicHistoryTitle">往期周报</h3>
                                <div className="homeWeeklyHistoryList">
                                    {weeklyPushHistory.map((item) => (
                                        <button
                                            key={item.weekStart}
                                            type="button"
                                            onClick={() => setSelectedWeekStart(item.weekStart)}
                                            className={`homePublicHistoryButton${selectedWeekStart === item.weekStart ? " homePublicHistoryButtonActive" : ""}`}
                                        >
                                            <div className="homeWeeklyHistoryButtonTitle">{item.title}</div>
                                            <div className="homeWeeklyHistoryButtonMeta">
                                                {item.weekStart} ~ {item.weekEnd} ｜ {item.paperCount} 篇 ｜ {formatGeneratedBy(item.generatedBy)}
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                    </section>
                </div>
            </div>
        </div>
    );
};

export default HomeScreen;
