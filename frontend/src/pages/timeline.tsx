import {
    useEffect,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
    type TouchEvent as ReactTouchEvent,
    type WheelEvent as ReactWheelEvent,
} from "react";

import LatexText from "../components/LatexText";
import { describeRequestError } from "../utils/errorMessage";
import { request } from "../utils/network";
import {
    TimelineCalendarResponse,
    TimelineDirectionSummary,
    TimelineDirectionsResponse,
    TimelinePaper,
    TimelinePapersResponse,
} from "../utils/types";

const INITIAL_BATCH_SIZE = 6;
const WINDOW_BATCH_SIZE = 5;
const DEFAULT_TIMELINE_LIMIT = 20;
// Timeline rendering uses a mix of initial skeletons, load-more previews, and calendar placeholders.
const DIRECTION_SKELETON_COUNT = 8;
const INITIAL_FEED_PREVIEW_COUNT = 4;
const LOAD_MORE_PREVIEW_COUNT = 1;
const MIN_INITIAL_SKELETON_MS = 5;
const INITIAL_SKELETON_FADE_MS = 180;
const APPEND_SCROLL_ADJUSTMENT_RATIO = 0.002;
const TOP_OVERSCROLL_WHEEL_THRESHOLD = 72;
const TOP_OVERSCROLL_TOUCH_THRESHOLD = 54;
const CALENDAR_GRID_CELL_COUNT = 42;
const CALENDAR_WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];
const CALENDAR_PICKER_ITEM_HEIGHT = 40;
const CALENDAR_PICKER_VISIBLE_ROWS = 5;
const useIsomorphicLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

type TimelineLoadMode = "replace" | "prepend" | "append";
type CalendarPickerColumn = "year" | "month";
type ScrollAdjustment =
    | { type: "prepend"; addedIds: number[]; direction: "up" | "down"; }
    | { type: "append-anchor"; firstNewPaperId?: number; anchorTop: number; direction: "up" | "down"; }
    | undefined;

// Create stable keys for repeated timeline skeleton placeholders.
const createSkeletonKeys = (count: number, prefix: string) => (
    Array.from({ length: count }, (_, idx) => `${prefix}-${idx}`)
);

// Generate the shared shimmer style used by direction cards, feed previews, and calendar placeholders.
// Build the shared shimmer bar style used by timeline skeleton blocks.
const createPreviewBarStyle = (
    width: number | string,
    height: number,
    extraStyles: Record<string, string | number> = {},
) => ({
    display: "block",
    width,
    height,
    borderRadius: 999,
    background: "linear-gradient(90deg, #e3e9f0 0%, #edf2f7 40%, #ffffff 50%, #edf2f7 60%, #e3e9f0 100%)",
    backgroundSize: "200% 100%",
    animation: "timelinePreviewBarShimmer 1.15s ease-in-out infinite",
    position: "relative" as const,
    overflow: "hidden" as const,
    ...extraStyles,
});

const CALENDAR_HEATMAP_MAX = 20;
const CALENDAR_HEATMAP_DARK_RGB = { r: 8, g: 109, b: 177 } as const;
const CALENDAR_HEATMAP_LIGHT_RGB = { r: 255, g: 255, b: 255 } as const;
const CALENDAR_HEATMAP_MID_RGB = {
    r: Math.round(CALENDAR_HEATMAP_LIGHT_RGB.r*8 / 9 + CALENDAR_HEATMAP_DARK_RGB.r/9),
    g: Math.round(CALENDAR_HEATMAP_LIGHT_RGB.g*8 / 9 + CALENDAR_HEATMAP_DARK_RGB.g /9),
    b: Math.round(CALENDAR_HEATMAP_LIGHT_RGB.b*8 / 9 + CALENDAR_HEATMAP_DARK_RGB.b/9),
} as const;

// Clamp a numeric value into the given inclusive range.
const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

// Interpolate one RGB channel between two values.
const interpolateChannel = (start: number, end: number, ratio: number) => (
    Math.round(start + ((end - start) * ratio))
);

// Convert an RGB object into a CSS rgb(...) string.
const toRgbString = (rgb: { r: number; g: number; b: number; }) => `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`;

// Map a paper count to the background/text colors used by one calendar day cell.
const createCalendarHeatColor = (paperCount: number) => {
    // Convert paper counts into a simple light-to-dark heat scale for the calendar grid.
    if (paperCount <= 0) {
        return {
            backgroundColor: "#ffffff",
            textColor: "#1f2328",
        };
    }

    if (paperCount >= CALENDAR_HEATMAP_MAX) {
        return {
            backgroundColor: toRgbString(CALENDAR_HEATMAP_DARK_RGB),
            textColor: "#1f2328",
        };
    }

    const ratio = (paperCount - 1) / (CALENDAR_HEATMAP_MAX - 1);
    const rgb = {
        r: interpolateChannel(CALENDAR_HEATMAP_MID_RGB.r, CALENDAR_HEATMAP_DARK_RGB.r, ratio),
        g: interpolateChannel(CALENDAR_HEATMAP_MID_RGB.g, CALENDAR_HEATMAP_DARK_RGB.g, ratio),
        b: interpolateChannel(CALENDAR_HEATMAP_MID_RGB.b, CALENDAR_HEATMAP_DARK_RGB.b, ratio),
    };

    return {
        backgroundColor: toRgbString(rgb),
        textColor: "#1f2328",
    };
};

const TIMELINE_SKELETON_BLUEPRINTS = [
    {
        eyebrow: "88px",
        title: "74%",
        tags: ["54px", "72px", "62px"],
        meta: ["44%", "33%"],
        paragraph: ["100%", "96%", "84%", "58%"],
    },
    {
        eyebrow: "96px",
        title: "81%",
        tags: ["60px", "68px"],
        meta: ["48%", "29%"],
        paragraph: ["98%", "90%", "72%"],
    },
    {
        eyebrow: "78px",
        title: "69%",
        tags: ["48px", "76px", "58px"],
        meta: ["42%", "38%"],
        paragraph: ["100%", "94%", "88%", "50%"],
    },
] as const;

// Zero-pad a year/month/day fragment for ISO-style date formatting.
const padDatePart = (value: number) => String(value).padStart(2, "0");

// Parse a YYYY-MM-DD string into a noon-based Date object to reduce timezone drift.
const parseIsoDate = (value?: string) => {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        return undefined;
    }

    const [year, month, day] = value.split("-").map((item) => Number(item));
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
        return undefined;
    }

    return new Date(year, month - 1, day, 12, 0, 0, 0);
};

// Format a Date object back into the YYYY-MM-DD string used by the timeline APIs.
const formatIsoDate = (value: Date) => (
    `${value.getFullYear()}-${padDatePart(value.getMonth() + 1)}-${padDatePart(value.getDate())}`
);

// Clone a date while normalizing the time to noon to avoid timezone edge cases.
const cloneDate = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12, 0, 0, 0);

// Shift a calendar date forward or backward by a number of days.
const addCalendarDays = (value: Date, days: number) => {
    const next = cloneDate(value);
    next.setDate(next.getDate() + days);
    return next;
};

// Shift a calendar month forward or backward by a number of months.
const addCalendarMonths = (value: Date, months: number) => {
    const next = new Date(value.getFullYear(), value.getMonth(), 1, 12, 0, 0, 0);
    next.setMonth(next.getMonth() + months);
    return next;
};

// Return the first day of the given month at noon.
const startOfCalendarMonth = (value: Date) => new Date(value.getFullYear(), value.getMonth(), 1, 12, 0, 0, 0);

// Compute the first visible day in the month grid, including the leading days from the previous month.
const buildCalendarGridStart = (month: Date) => {
    const firstDay = startOfCalendarMonth(month);
    const weekday = (firstDay.getDay() + 6) % 7;
    return addCalendarDays(firstDay, -weekday);
};

// Format the visible calendar month for the panel header.
const formatCalendarMonthLabel = (value: Date) => `${value.getFullYear()} 年 ${value.getMonth() + 1} 月`;
// Format one year option for the calendar picker.
const formatCalendarYearTriggerLabel = (year: number) => `${year}年`;
// Format one month option for the calendar picker.
const formatCalendarMonthTriggerLabel = (month: number) => `${month}月`;
// Choose a fallback year label when the calendar picker has no selectable year state yet.
const formatFallbackCalendarYearTriggerLabel = (calendarMeta?: TimelineCalendarResponse) => {
    const fallbackDate = parseIsoDate(calendarMeta?.latest_date || calendarMeta?.default_date || "");
    return fallbackDate !== undefined ? formatCalendarYearTriggerLabel(fallbackDate.getFullYear()) : "年份";
};
// Choose a fallback month label when the calendar picker has no selectable month state yet.
const formatFallbackCalendarMonthTriggerLabel = (calendarMeta?: TimelineCalendarResponse) => {
    const fallbackDate = parseIsoDate(calendarMeta?.latest_date || calendarMeta?.default_date || "");
    return fallbackDate !== undefined ? formatCalendarMonthTriggerLabel(fallbackDate.getMonth() + 1) : "月份";
};

// Pick the nearest numeric option to the requested target value.
const findNearestNumericOption = (target: number, options: number[]) => {
    if (options.length === 0) {
        return undefined;
    }

    return options.reduce((best, current) => {
        const currentDistance = Math.abs(current - target);
        const bestDistance = Math.abs(best - target);
        if (currentDistance < bestDistance) {
            return current;
        }
        if (currentDistance === bestDistance && current < best) {
            return current;
        }
        return best;
    });
};

// Render the timeline page with direction switching, day-based calendar navigation, and infinite feed loading.
const TimelinePage = () => {
    const [directions, setDirections] = useState<TimelineDirectionSummary[]>([]);
    const [activeDirection, setActiveDirection] = useState("");
    const [calendarMeta, setCalendarMeta] = useState<TimelineCalendarResponse | undefined>(undefined);
    const [displayedMonth, setDisplayedMonth] = useState<Date | undefined>(undefined);
    const [selectedDate, setSelectedDate] = useState("");
    const [leadVisibleDate, setLeadVisibleDate] = useState("");
    const [isCalendarBrowsingManually, setIsCalendarBrowsingManually] = useState(false);
    const [papers, setPapers] = useState<TimelinePaper[]>([]);
    const [totalPapers, setTotalPapers] = useState(0);
    const [hasMoreBefore, setHasMoreBefore] = useState(false);
    const [hasMoreAfter, setHasMoreAfter] = useState(false);
    const [loadingDirections, setLoadingDirections] = useState(true);
    const [loadingCalendar, setLoadingCalendar] = useState(false);
    const [loadingInitial, setLoadingInitial] = useState(false);
    const [loadingPrevious, setLoadingPrevious] = useState(false);
    const [, setLoadingNext] = useState(false);
    const [hasResolvedInitialFeed, setHasResolvedInitialFeed] = useState(false);
    const [showInitialSkeleton, setShowInitialSkeleton] = useState(false);
    const [feedRevealKey, setFeedRevealKey] = useState(0);
    const [errorMessage, setErrorMessage] = useState("");
    const [isCalendarPickerOpen, setIsCalendarPickerOpen] = useState(false);
    const [calendarPickerDraftYear, setCalendarPickerDraftYear] = useState(0);
    const [calendarPickerDraftMonth, setCalendarPickerDraftMonth] = useState(1);
    const [calendarPickerActiveColumn, setCalendarPickerActiveColumn] = useState<CalendarPickerColumn>("month");
    const feedViewportRef = useRef<HTMLDivElement | undefined>(undefined);
    const paperRefs = useRef<Record<number, HTMLElement | undefined>>({});
    const papersRef = useRef<TimelinePaper[]>([]);
    const activeDirectionRef = useRef("");
    const selectedDateRef = useRef("");
    const hasMoreBeforeRef = useRef(false);
    const hasMoreAfterRef = useRef(false);
    const directionGenerationRef = useRef(0);
    const pendingScrollAdjustmentRef = useRef<ScrollAdjustment>(undefined);
    const initialSkeletonStartedAtRef = useRef(0);
    const initialSkeletonTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    const inFlightRef = useRef({
        replace: false,
        prepend: false,
        append: false,
    });
    const scrollDirectionRef = useRef<"up" | "down">("down");
    const lastFeedScrollTopRef = useRef(0);
    const skipNextScrollEventRef = useRef(false);
    const lastRealPaperBottomRef = useRef(0);
    const loadMoreThresholdConsumedRef = useRef(false);
    const topWheelPullDistanceRef = useRef(0);
    const topTouchStartYRef = useRef<number | undefined>(undefined);
    const topTouchPullDistanceRef = useRef(0);
    const topOverscrollConsumedRef = useRef(false);
    const calendarPickerAnchorRef = useRef<HTMLDivElement | undefined>(undefined);
    const calendarPickerYearWheelRef = useRef<HTMLDivElement | undefined>(undefined);
    const calendarPickerMonthWheelRef = useRef<HTMLDivElement | undefined>(undefined);

    useLayoutEffect(() => {
        // Mirror the latest papers array in a ref so scroll handlers can read it without stale closures.
        papersRef.current = papers;
    }, [papers]);

    useEffect(() => {
        activeDirectionRef.current = activeDirection;
    }, [activeDirection]);

    useEffect(() => {
        selectedDateRef.current = selectedDate;
    }, [selectedDate]);

    useEffect(() => {
        hasMoreBeforeRef.current = hasMoreBefore;
    }, [hasMoreBefore]);

    useEffect(() => {
        hasMoreAfterRef.current = hasMoreAfter;
    }, [hasMoreAfter]);

    useEffect(() => () => {
        if (initialSkeletonTimerRef.current !== undefined) {
            clearTimeout(initialSkeletonTimerRef.current);
        }
    }, []);

    // Derive a PDF URL from an arXiv abstract URL for paper link rendering.
    const buildTimelinePdfUrl = (arxivUrl?: string) => {
        // The PDF URL can be derived directly from a standard arXiv abstract link.
        if (typeof arxivUrl !== "string" || arxivUrl.trim() === "" || !arxivUrl.includes("/abs/")) {
            return "";
        }

        return arxivUrl.replace("/abs/", "/pdf/");
    };

    // Split a comma-separated subject string into normalized subject tags.
    const parseTimelineSubjects = (subjects?: string) => {
        if (typeof subjects !== "string" || subjects.trim() === "") {
            return [];
        }

        return subjects
            .split(",")
            .map((subject) => subject.trim())
            .filter((subject) => subject !== "");
    };

    // Render authors as plain text or mentor profile links depending on whether mentor ids are present.
    const renderPaperAuthors = (paper: TimelinePaper) => {
        // Mentor-linked authors become profile links; other authors remain plain text.
        const names = (paper.author_names || "").split(/[,，、]/).map((name) => name.trim()).filter(Boolean);
        const mentorIds = Array.isArray(paper.mentor_ids) ? paper.mentor_ids : [];

        if (names.length === 0) {
            return "未知";
        }

        return names.map((name, idx) => {
            const mentorId = mentorIds[idx];
            const isMentor = typeof mentorId === "number" && mentorId > 0;
            const separator = idx === names.length - 1 ? "" : "、";

            if (isMentor) {
                return (
                    <span key={`${paper.id}-${name}-${idx}`}>
                        <a
                            href={`/mentors/${mentorId}`}
                            target="_blank"
                            rel="noreferrer"
                            className="timelineMentorLink"
                        >
                            <img
                                src="/favicon_tsinghua.ico"
                                alt="清华导师"
                                className="timelineMentorIcon"
                            />
                            {name}
                        </a>
                        {separator}
                    </span>
                );
            }

            return (
                <span key={`${paper.id}-${name}-${idx}`}>
                    {name}
                    {separator}
                </span>
            );
        });
    };

    // Route a generic load mode to its matching loading state setter.
    const setLoadingFlag = (mode: TimelineLoadMode, loading: boolean) => {
        if (mode === "replace") {
            setLoadingInitial(loading);
            return;
        }

        if (mode === "prepend") {
            setLoadingPrevious(loading);
            return;
        }

        setLoadingNext(loading);
    };

    // Cancel the delayed initial-skeleton hide timer if it is still pending.
    const clearInitialSkeletonTimer = () => {
        if (initialSkeletonTimerRef.current !== undefined) {
            clearTimeout(initialSkeletonTimerRef.current);
            initialSkeletonTimerRef.current = undefined;
        }
    };

    // Begin the initial feed skeleton phase for a full direction/date replacement load.
    const startInitialSkeletonPhase = () => {
        clearInitialSkeletonTimer();
        initialSkeletonStartedAtRef.current = Date.now();
        // Direction/date switches use a dedicated feed skeleton rather than a spinner.
        setShowInitialSkeleton(true);
    };

    // Finish the initial feed skeleton phase while honoring the minimum visible duration.
    const finishInitialSkeletonPhase = (mode: TimelineLoadMode, generation: number) => {
        if (mode !== "replace") {
            return;
        }

        clearInitialSkeletonTimer();
        const elapsed = Date.now() - initialSkeletonStartedAtRef.current;
        const remaining = Math.max(MIN_INITIAL_SKELETON_MS - elapsed, 0);
        // Hide the initial skeleton only if this response still belongs to the latest direction generation.
        const finalize = () => {
            if (generation !== directionGenerationRef.current) {
                return;
            }

            setShowInitialSkeleton(false);
            setFeedRevealKey((current) => current + 1);
        };

        if (remaining === 0) {
            finalize();
            return;
        }

        initialSkeletonTimerRef.current = setTimeout(() => {
            initialSkeletonTimerRef.current = undefined;
            finalize();
        }, remaining);
    };

    // Return whether any replace/prepend/append feed request is currently in flight.
    const hasAnyFeedLoadInFlight = () => (
        inFlightRef.current.replace || inFlightRef.current.prepend || inFlightRef.current.append
    );

    // Reset all temporary state used for top-overscroll loading gestures.
    const resetTopOverscrollState = () => {
        topWheelPullDistanceRef.current = 0;
        topTouchStartYRef.current = undefined;
        topTouchPullDistanceRef.current = 0;
        topOverscrollConsumedRef.current = false;
    };

    // Reset scroll bookkeeping and restore the feed viewport to its top position.
    const resetFeedViewportState = () => {
        lastFeedScrollTopRef.current = 0;
        scrollDirectionRef.current = "down";
        skipNextScrollEventRef.current = false;
        lastRealPaperBottomRef.current = 0;
        loadMoreThresholdConsumedRef.current = false;
        resetTopOverscrollState();
        if (feedViewportRef.current !== undefined) {
            feedViewportRef.current.scrollTop = 0;
        }
    };

    // Reset feed data and scroll state before replacing the active timeline slice.
    const prepareFeedForReplace = (showSkeleton: boolean) => {
        // Reset feed-local loading, scroll, and incremental-load state before replacing the active slice.
        clearInitialSkeletonTimer();
        inFlightRef.current = {
            replace: false,
            prepend: false,
            append: false,
        };
        pendingScrollAdjustmentRef.current = undefined;
        setLoadingInitial(false);
        setLoadingPrevious(false);
        setLoadingNext(false);
        setHasResolvedInitialFeed(false);
        setShowInitialSkeleton(showSkeleton);
        setPapers([]);
        setTotalPapers(0);
        setHasMoreBefore(false);
        setHasMoreAfter(false);
        setLeadVisibleDate("");
        papersRef.current = [];
        paperRefs.current = {};
        hasMoreBeforeRef.current = false;
        hasMoreAfterRef.current = false;
        resetFeedViewportState();
    };

    // Update the date badge based on the first paper currently visible in the feed viewport.
    const updateLeadVisibleDate = () => {
        const viewport = feedViewportRef.current;
        const currentPapers = papersRef.current;
        if (viewport === undefined || currentPapers.length === 0) {
            setLeadVisibleDate("");
            return;
        }

        // The first paper whose bottom edge is below the viewport top defines the visible lead date.
        const threshold = viewport.scrollTop + 8;
        for (const paper of currentPapers) {
            const paperElement = paperRefs.current[paper.id];
            if (paperElement === undefined) {
                continue;
            }

            const paperBottom = paperElement.offsetTop + paperElement.offsetHeight;
            if (paperBottom > threshold) {
                setLeadVisibleDate(paper.publish_date || "");
                return;
            }
        }

        setLeadVisibleDate(currentPapers[0]?.publish_date || "");
    };

    // Serialize timeline query parameters into the request string expected by the proxy endpoint.
    const buildTimelineQueryString = (params: Record<string, string>) => (
        new URLSearchParams(params).toString()
    );

    // Merge a fetched timeline slice into the current feed according to the active load mode.
    const applyFeedResponse = (response: TimelinePapersResponse, mode: TimelineLoadMode) => {
        // Merge the fetched slice differently depending on replace / prepend / append mode.
        const normalizedLimit = Math.max(1, Number(response.limit) || DEFAULT_TIMELINE_LIMIT);
        const nextPapers = Array.isArray(response.papers) ? response.papers : [];
        const nextTotal = Number(response.total_papers) > 0 ? Number(response.total_papers) : 0;

        setTotalPapers(nextTotal);

        if (mode === "replace") {
            pendingScrollAdjustmentRef.current = undefined;
            setPapers(nextPapers);
            setHasMoreBefore(Boolean(response.has_newer));
            setHasMoreAfter(Boolean(response.has_older));
            return;
        }

        const currentPapers = papersRef.current;
        const existingIds = new Set(currentPapers.map((paper) => paper.id));

        if (mode === "append") {
            const uniqueIncoming = nextPapers.filter((paper) => !existingIds.has(paper.id));
            const mergedPapers = [...currentPapers, ...uniqueIncoming];

            // Remember the first appended id so the layout effect can preserve visual position after insertion.
            pendingScrollAdjustmentRef.current = uniqueIncoming.length > 0 && pendingScrollAdjustmentRef.current?.type === "append-anchor"
                ? {
                    ...pendingScrollAdjustmentRef.current,
                    firstNewPaperId: uniqueIncoming[0]?.id,
                }
                : pendingScrollAdjustmentRef.current;

            setPapers(mergedPapers);
            setHasMoreBefore(Boolean(response.has_newer) || hasMoreBeforeRef.current);
            setHasMoreAfter(Boolean(response.has_older));
            if (!response.has_older && normalizedLimit < currentPapers.length) {
                setHasMoreAfter(false);
            }
            return;
        }

        const uniqueIncoming = nextPapers.filter((paper) => !existingIds.has(paper.id));
        const mergedPapers = [...uniqueIncoming, ...currentPapers];

        pendingScrollAdjustmentRef.current = uniqueIncoming.length > 0
            ? {
                type: "prepend",
                addedIds: uniqueIncoming.map((paper) => paper.id),
                direction: "up",
            }
            : undefined;

        setPapers(mergedPapers);
        setHasMoreBefore(Boolean(response.has_newer));
        setHasMoreAfter(Boolean(response.has_older) || hasMoreAfterRef.current);
    };

    // Fetch one timeline slice for the active direction/date window and merge it into the feed.
    const fetchTimelineSlice = async (
        direction: string,
        queryParams: Record<string, string>,
        mode: TimelineLoadMode,
        generation: number,
    ) => {
        // Only one feed request runs at a time to avoid duplicate prepend/append merges.
        if (hasAnyFeedLoadInFlight()) {
            return;
        }

        inFlightRef.current[mode] = true;
        setLoadingFlag(mode, true);
        setErrorMessage("");
        if (mode === "replace") {
            startInitialSkeletonPhase();
        }

        try {
            const query = buildTimelineQueryString({
                direction,
                ...queryParams,
            });
            // The frontend uses one proxy endpoint and varies behavior through query parameters.
            const response = await request<TimelinePapersResponse>(`/api/timeline?${query}`, "GET", false);

            if (generation !== directionGenerationRef.current) {
                return;
            }

            applyFeedResponse(response, mode);
        }
        catch (err) {
            if (generation !== directionGenerationRef.current) {
                return;
            }

            if (mode === "replace") {
                setPapers([]);
                setTotalPapers(0);
                setHasMoreBefore(false);
                setHasMoreAfter(false);
                setLeadVisibleDate("");
            }

            setErrorMessage(describeRequestError(err));
        }
        finally {
            inFlightRef.current[mode] = false;
            if (generation === directionGenerationRef.current) {
                setLoadingFlag(mode, false);
                if (mode === "replace") {
                    setHasResolvedInitialFeed(true);
                }
            }
            finishInitialSkeletonPhase(mode, generation);
        }
    };

    useEffect(() => {
        // Load the available direction list and choose the initial active direction.
        const fetchDirectionOverview = async () => {
            setLoadingDirections(true);
            setHasResolvedInitialFeed(false);
            setErrorMessage("");

            try {
                // First load the available directions and the backend's preferred default direction.
                const res = await request<TimelineDirectionsResponse>("/api/timeline", "GET", false);
                const nextDirections = Array.isArray(res.directions) ? res.directions : [];

                setDirections(nextDirections);
                setActiveDirection((currentDirection) => {
                    if (currentDirection !== "" && nextDirections.some((group) => group.direction === currentDirection)) {
                        return currentDirection;
                    }

                    if (res.default_direction !== "" && nextDirections.some((group) => group.direction === res.default_direction)) {
                        return res.default_direction;
                    }

                    return nextDirections[0]?.direction || "";
                });
            }
            catch (err) {
                setDirections([]);
                setPapers([]);
                setCalendarMeta(undefined);
                setActiveDirection("");
                setSelectedDate("");
                setDisplayedMonth(undefined);
                setTotalPapers(0);
                setHasMoreBefore(false);
                setHasMoreAfter(false);
                setErrorMessage(describeRequestError(err));
            }
            finally {
                setLoadingDirections(false);
            }
        };

        void fetchDirectionOverview();
    }, []);

    useEffect(() => {
        if (activeDirection === "") {
            clearInitialSkeletonTimer();
            setShowInitialSkeleton(false);
            setCalendarMeta(undefined);
            setDisplayedMonth(undefined);
            setSelectedDate("");
            selectedDateRef.current = "";
            setLeadVisibleDate("");
            setPapers([]);
            setTotalPapers(0);
            setHasMoreBefore(false);
            setHasMoreAfter(false);
            setHasResolvedInitialFeed(false);
            setLoadingCalendar(false);
            return;
        }

        directionGenerationRef.current += 1;
        const generation = directionGenerationRef.current;
        // Every direction switch starts a new generation so stale async responses can be ignored safely.
        prepareFeedForReplace(true);
        setCalendarMeta(undefined);
        setDisplayedMonth(undefined);
        setLoadingCalendar(true);
        setErrorMessage("");

        // Load the active direction's calendar metadata and then fetch the initial feed slice.
        const fetchCalendarAndInitialFeed = async () => {
            try {
                // Load the available calendar dates first, then fetch the initial paper slice for the chosen day.
                const query = buildTimelineQueryString({
                    direction: activeDirection,
                    calendar: "1",
                });
                const response = await request<TimelineCalendarResponse>(`/api/timeline?${query}`, "GET", false);

                if (generation !== directionGenerationRef.current || activeDirectionRef.current !== activeDirection) {
                    return;
                }

                const nextAvailableDates = Array.isArray(response.available_dates) ? response.available_dates : [];
                const normalizedCalendarMeta = {
                    ...response,
                    available_dates: nextAvailableDates,
                };
                setCalendarMeta(normalizedCalendarMeta);

                const preservedDate = selectedDateRef.current !== ""
                    && nextAvailableDates.some((item) => item.date === selectedDateRef.current)
                    ? selectedDateRef.current
                    : (response.default_date || "");

                // Preserve the previously selected date when it still exists under the new direction.
                setSelectedDate(preservedDate);
                selectedDateRef.current = preservedDate;
                const monthSource = preservedDate || response.latest_date;
                setDisplayedMonth(monthSource !== "" ? parseIsoDate(monthSource) : undefined);
                setIsCalendarBrowsingManually(false);

                if (preservedDate === "") {
                    clearInitialSkeletonTimer();
                    setShowInitialSkeleton(false);
                    setHasResolvedInitialFeed(true);
                    return;
                }

                await fetchTimelineSlice(activeDirection, {
                    date: preservedDate,
                    limit: String(INITIAL_BATCH_SIZE),
                }, "replace", generation);
            }
            catch (err) {
                if (generation !== directionGenerationRef.current || activeDirectionRef.current !== activeDirection) {
                    return;
                }

                setCalendarMeta(undefined);
                setDisplayedMonth(undefined);
                setIsCalendarBrowsingManually(false);
                setSelectedDate("");
                selectedDateRef.current = "";
                setPapers([]);
                setTotalPapers(0);
                setHasMoreBefore(false);
                setHasMoreAfter(false);
                setLeadVisibleDate("");
                setHasResolvedInitialFeed(true);
                setShowInitialSkeleton(false);
                setErrorMessage(describeRequestError(err));
            }
            finally {
                if (generation === directionGenerationRef.current) {
                    setLoadingCalendar(false);
                }
            }
        };

        void fetchCalendarAndInitialFeed();
    }, [activeDirection]);

    // Resolve the full metadata record for the currently active direction.
    const activeDirectionSummary = useMemo(
        () => directions.find((group) => group.direction === activeDirection),
        [activeDirection, directions],
    );

    // Cache selectable timeline dates in a Set for fast calendar click validation.
    const availableDateSet = useMemo(
        () => new Set((calendarMeta?.available_dates || []).map((item) => item.date)),
        [calendarMeta],
    );

    // Map each available date to its paper count for calendar heatmap rendering.
    const availableDateCountMap = useMemo(
        () => new Map((calendarMeta?.available_dates || []).map((item) => [item.date, item.paper_count])),
        [calendarMeta],
    );

    // Group selectable months by year so the year/month picker can constrain valid combinations.
    const availableCalendarMonthsByYear = useMemo(() => {
        const monthsByYear = new Map<number, Set<number>>();
        for (const item of calendarMeta?.available_dates || []) {
            const parsedDate = parseIsoDate(item.date);
            if (parsedDate === undefined) {
                continue;
            }

            const year = parsedDate.getFullYear();
            const month = parsedDate.getMonth() + 1;
            const currentMonths = monthsByYear.get(year) ?? new Set<number>();
            currentMonths.add(month);
            monthsByYear.set(year, currentMonths);
        }

        return new Map(
            Array.from(monthsByYear.entries())
                .sort(([leftYear], [rightYear]) => leftYear - rightYear)
                .map(([year, months]) => [year, Array.from(months).sort((left, right) => left - right)]),
        );
    }, [calendarMeta?.available_dates]);

    // Extract the selectable calendar years in ascending order for the picker.
    const availableCalendarYears = useMemo(
        () => Array.from(availableCalendarMonthsByYear.keys()).sort((left, right) => left - right),
        [availableCalendarMonthsByYear],
    );

    const hasSelectableCalendarMonths = availableCalendarYears.length > 0;

    // Resolve the month currently shown in the right-side calendar panel.
    const currentCalendarMonth = useMemo(() => {
        if (displayedMonth !== undefined) {
            return startOfCalendarMonth(displayedMonth);
        }

        const fallbackDate = parseIsoDate(selectedDate || calendarMeta?.latest_date || "");
        return fallbackDate !== undefined ? startOfCalendarMonth(fallbackDate) : startOfCalendarMonth(new Date());
    }, [calendarMeta?.latest_date, displayedMonth, selectedDate]);

    // Build a helper that snaps a requested year/month to the nearest selectable picker values.
    const normalizeCalendarPickerDraft = useMemo(() => {
        return (targetYear: number, targetMonth: number) => {
            if (availableCalendarYears.length === 0) {
                return undefined;
            }

            const resolvedYear = availableCalendarYears.includes(targetYear)
                ? targetYear
                : findNearestNumericOption(targetYear, availableCalendarYears) ?? availableCalendarYears[0];
            const resolvedMonths = availableCalendarMonthsByYear.get(resolvedYear) ?? [];
            const resolvedMonth = resolvedMonths.includes(targetMonth)
                ? targetMonth
                : findNearestNumericOption(targetMonth, resolvedMonths) ?? resolvedMonths[0];

            if (resolvedMonth === undefined) {
                return undefined;
            }

            return {
                year: resolvedYear,
                month: resolvedMonth,
            };
        };
    }, [availableCalendarMonthsByYear, availableCalendarYears]);

    // Expose the months currently selectable for the picker draft year.
    const availableCalendarMonthsForDraftYear = useMemo(
        () => availableCalendarMonthsByYear.get(calendarPickerDraftYear) ?? [],
        [availableCalendarMonthsByYear, calendarPickerDraftYear],
    );

    // Move the calendar view one month backward or forward without selecting a specific day yet.
    const handleCalendarMonthChange = (deltaMonths: number) => {
        setIsCalendarPickerOpen(false);
        // Manual month browsing temporarily overrides auto-sync with the lead visible date.
        setIsCalendarBrowsingManually(true);
        setDisplayedMonth(addCalendarMonths(currentCalendarMonth, deltaMonths));
    };

    // Scroll a picker wheel so the chosen year or month stays centered in view.
    const scrollCalendarPickerOptionIntoView = (
        wheelRef: React.MutableRefObject<HTMLDivElement | undefined>,
        value: number,
    ) => {
        const wheel = wheelRef.current;
        if (wheel === undefined) {
            return;
        }

        const option = wheel.querySelector<HTMLElement>(`[data-picker-value="${value}"]`);
        if (!option) {
            return;
        }

        window.requestAnimationFrame(() => {
            option.scrollIntoView({
                block: "center",
                inline: "nearest",
            });
        });
    };

    // Close the year/month calendar picker overlay.
    const closeCalendarPicker = () => {
        setIsCalendarPickerOpen(false);
    };

    // Open the year/month calendar picker and seed it with the nearest selectable values.
    const openCalendarPicker = (column: CalendarPickerColumn) => {
        if (!hasSelectableCalendarMonths) {
            return;
        }

        // Open the picker snapped to the nearest selectable year/month for the currently displayed month.
        if (isCalendarPickerOpen) {
            setCalendarPickerActiveColumn(column);
            return;
        }

        const normalizedDraft = normalizeCalendarPickerDraft(
            currentCalendarMonth.getFullYear(),
            currentCalendarMonth.getMonth() + 1,
        );
        if (normalizedDraft === undefined) {
            return;
        }

        setCalendarPickerDraftYear(normalizedDraft.year);
        setCalendarPickerDraftMonth(normalizedDraft.month);
        setCalendarPickerActiveColumn(column);
        setIsCalendarPickerOpen(true);
    };

    // Change the draft year in the calendar picker and snap the month to a valid option if needed.
    const handleCalendarPickerYearDraftChange = (nextYear: number) => {
        const nextMonths = availableCalendarMonthsByYear.get(nextYear) ?? [];
        if (nextMonths.length === 0) {
            return;
        }

        setCalendarPickerDraftYear(nextYear);
        setCalendarPickerDraftMonth(
            nextMonths.includes(calendarPickerDraftMonth)
                ? calendarPickerDraftMonth
                : findNearestNumericOption(calendarPickerDraftMonth, nextMonths) ?? nextMonths[0],
        );
        setCalendarPickerActiveColumn("year");
    };

    // Change the draft month in the calendar picker.
    const handleCalendarPickerMonthDraftChange = (nextMonth: number) => {
        setCalendarPickerDraftMonth(nextMonth);
        setCalendarPickerActiveColumn("month");
    };

    // Move a calendar-picker wheel selection up or down with mouse-wheel input.
    const handleCalendarPickerWheel = (column: CalendarPickerColumn, deltaY: number) => {
        if (deltaY === 0) {
            return;
        }

        const options = column === "year"
            ? availableCalendarYears
            : availableCalendarMonthsForDraftYear;
        if (options.length <= 1) {
            return;
        }

        const currentValue = column === "year" ? calendarPickerDraftYear : calendarPickerDraftMonth;
        const currentIndex = Math.max(options.indexOf(currentValue), 0);
        const nextIndex = clamp(currentIndex + (deltaY > 0 ? 1 : -1), 0, options.length - 1);
        const nextValue = options[nextIndex];
        if (nextValue === undefined || nextValue === currentValue) {
            return;
        }

        if (column === "year") {
            handleCalendarPickerYearDraftChange(nextValue);
            return;
        }

        handleCalendarPickerMonthDraftChange(nextValue);
    };

    // Apply the draft year/month selection from the picker to the visible calendar month.
    const applyCalendarPickerSelection = () => {
        const normalizedDraft = normalizeCalendarPickerDraft(calendarPickerDraftYear, calendarPickerDraftMonth);
        if (normalizedDraft === undefined) {
            closeCalendarPicker();
            return;
        }

        // Applying the picker changes the viewed month; day selection still happens in the calendar grid.
        setIsCalendarBrowsingManually(true);
        setDisplayedMonth(new Date(normalizedDraft.year, normalizedDraft.month - 1, 1, 12, 0, 0, 0));
        closeCalendarPicker();
    };

    // Build the 6x7 calendar grid cells, including heatmap colors and clickability state.
    const calendarDayCells = useMemo(() => {
        const gridStart = buildCalendarGridStart(currentCalendarMonth);
        return Array.from({ length: CALENDAR_GRID_CELL_COUNT }, (_, idx) => {
            const value = addCalendarDays(gridStart, idx);
            const isoDate = formatIsoDate(value);
            const paperCount = availableDateCountMap.get(isoDate) || 0;
            const { backgroundColor, textColor } = createCalendarHeatColor(paperCount);
            return {
                isoDate,
                label: value.getDate(),
                inCurrentMonth: value.getMonth() === currentCalendarMonth.getMonth(),
                hasPaper: paperCount > 0,
                isInteractive: paperCount > 0,
                paperCount,
                displayCount: paperCount,
                heatLevel: clamp(paperCount, 0, CALENDAR_HEATMAP_MAX),
                backgroundColor,
                textColor,
            };
        });
    }, [availableDateCountMap, currentCalendarMonth]);

    // Summarize which sequence range of papers is currently visible for the lead date badge.
    const currentVisibleDateRange = useMemo(() => {
        const targetDate = leadVisibleDate || papers[0]?.publish_date || selectedDate;
        if (targetDate === "") {
            return undefined;
        }

        const visibleSameDayPapers = papers.filter((paper) => paper.publish_date === targetDate);
        if (visibleSameDayPapers.length === 0) {
            return undefined;
        }

        const sequences = visibleSameDayPapers
            .map((paper) => paper.day_sequence)
            .filter((value): value is number => typeof value === "number" && Number.isFinite(value));

        if (sequences.length > 0) {
            return {
                date: targetDate,
                start: Math.min(...sequences),
                end: Math.max(...sequences),
            };
        }

        return {
            date: targetDate,
            start: 1,
            end: visibleSameDayPapers.length,
        };
    }, [leadVisibleDate, papers, selectedDate]);

    useEffect(() => {
        if (leadVisibleDate === "") {
            return;
        }

        const nextLeadDate = parseIsoDate(leadVisibleDate);
        if (nextLeadDate === undefined) {
            return;
        }

        const nextLeadMonth = startOfCalendarMonth(nextLeadDate);
        if (isCalendarBrowsingManually) {
            return;
        }

        // Keep the month view synchronized with the topmost visible paper date during normal scrolling.
        if (
            currentCalendarMonth.getFullYear() === nextLeadMonth.getFullYear()
            && currentCalendarMonth.getMonth() === nextLeadMonth.getMonth()
        ) {
            return;
        }

        setDisplayedMonth(nextLeadMonth);
    }, [currentCalendarMonth, isCalendarBrowsingManually, leadVisibleDate]);

    useEffect(() => {
        if (leadVisibleDate === "") {
            return;
        }

        setIsCalendarBrowsingManually(false);
    }, [leadVisibleDate]);

    useEffect(() => {
        if (!isCalendarPickerOpen) {
            return;
        }

        // Close the picker when the user clicks outside its anchor area.
        const handleDocumentMouseDown = (event: MouseEvent) => {
            const pickerAnchor = calendarPickerAnchorRef.current;
            if (pickerAnchor !== undefined && pickerAnchor.contains(event.target as Node)) {
                return;
            }
            closeCalendarPicker();
        };

        // Close the picker from the keyboard with Escape.
        const handleDocumentKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                closeCalendarPicker();
            }
        };

        document.addEventListener("mousedown", handleDocumentMouseDown, true);
        document.addEventListener("keydown", handleDocumentKeyDown);

        return () => {
            document.removeEventListener("mousedown", handleDocumentMouseDown, true);
            document.removeEventListener("keydown", handleDocumentKeyDown);
        };
    }, [isCalendarPickerOpen]);

    useEffect(() => {
        if (!isCalendarPickerOpen) {
            return;
        }

        const activeWheel = calendarPickerActiveColumn === "year"
            ? calendarPickerYearWheelRef.current
            : calendarPickerMonthWheelRef.current;
        activeWheel?.focus();
    }, [calendarPickerActiveColumn, isCalendarPickerOpen]);

    useEffect(() => {
        if (!isCalendarPickerOpen) {
            return;
        }

        scrollCalendarPickerOptionIntoView(calendarPickerYearWheelRef, calendarPickerDraftYear);
    }, [calendarPickerDraftYear, isCalendarPickerOpen]);

    useEffect(() => {
        if (!isCalendarPickerOpen) {
            return;
        }

        scrollCalendarPickerOptionIntoView(calendarPickerMonthWheelRef, calendarPickerDraftMonth);
    }, [calendarPickerDraftMonth, isCalendarPickerOpen]);

    useEffect(() => {
        if (loadingCalendar || calendarMeta === undefined || !hasSelectableCalendarMonths) {
            closeCalendarPicker();
        }
    }, [calendarMeta, hasSelectableCalendarMonths, loadingCalendar]);

    // Measure the current bottom edge of the feed viewport in page coordinates.
    const getFeedViewportBottom = () => {
        const viewport = feedViewportRef.current;
        if (viewport === undefined) {
            return 0;
        }

        return viewport.getBoundingClientRect().bottom;
    };

    // Measure the top edge of the load-more preview sentinel card.
    const getFirstLoadMorePreviewTop = () => {
        const firstPreview = feedViewportRef.current?.querySelector<HTMLElement>("[data-load-more-preview-first='true']");
        if (!firstPreview) {
            return Number.POSITIVE_INFINITY;
        }

        return firstPreview.getBoundingClientRect().top;
    };

    // Fetch the next newer batch that should be prepended above the current feed.
    const loadPreviousBatch = () => {
        if (
            activeDirectionRef.current === ""
            || !hasMoreBeforeRef.current
            || hasAnyFeedLoadInFlight()
        ) {
            return;
        }

        const firstPaper = papersRef.current[0];
        if (firstPaper === undefined || typeof firstPaper.publish_date !== "string" || firstPaper.publish_date === "") {
            return;
        }

        // Prepending asks for newer papers than the current first visible card.
        void fetchTimelineSlice(activeDirectionRef.current, {
            after_date: firstPaper.publish_date,
            after_id: String(firstPaper.id),
            limit: String(WINDOW_BATCH_SIZE),
        }, "prepend", directionGenerationRef.current);
    };

    // Fetch the next older batch that should be appended below the current feed.
    const loadNextBatch = () => {
        if (
            activeDirectionRef.current === ""
            || !hasMoreAfterRef.current
            || hasAnyFeedLoadInFlight()
        ) {
            return;
        }

        const lastPaper = papersRef.current[papersRef.current.length - 1];
        if (lastPaper === undefined || typeof lastPaper.publish_date !== "string" || lastPaper.publish_date === "") {
            return;
        }

        // Record the current bottom anchor so appended content does not visually jump too far.
        const anchorTop = paperRefs.current[lastPaper.id]?.offsetTop || 0;
        if (anchorTop > 0) {
            pendingScrollAdjustmentRef.current = {
                type: "append-anchor",
                anchorTop,
                direction: "down",
            };
        }

        void fetchTimelineSlice(activeDirectionRef.current, {
            before_date: lastPaper.publish_date,
            before_id: String(lastPaper.id),
            limit: String(WINDOW_BATCH_SIZE),
        }, "append", directionGenerationRef.current);
    };

    // Trigger append loading when the load-more preview sentinel enters the viewport.
    const maybeLoadNextFromViewport = () => {
        if (
            !hasMoreAfterRef.current
            || hasAnyFeedLoadInFlight()
            || loadMoreThresholdConsumedRef.current
        ) {
            return;
        }

        const viewportBottom = lastRealPaperBottomRef.current || getFeedViewportBottom();
        if (viewportBottom <= 0) {
            return;
        }

        const firstPreviewTop = getFirstLoadMorePreviewTop();
        if (firstPreviewTop <= viewportBottom) {
            // Crossing the preview sentinel triggers exactly one append until new content arrives.
            loadMoreThresholdConsumedRef.current = true;
            loadNextBatch();
        }
    };

    // Trigger a prepend load after a deliberate top-overscroll gesture.
    const triggerTopOverscrollLoad = () => {
        if (
            topOverscrollConsumedRef.current
            || !hasMoreBeforeRef.current
            || hasAnyFeedLoadInFlight()
        ) {
            return;
        }

        topOverscrollConsumedRef.current = true;
        loadPreviousBatch();
    };

    // React to feed scrolling by updating direction, lead date, and append-load checks.
    const handleFeedViewportScroll = () => {
        const viewport = feedViewportRef.current;
        if (viewport === undefined) {
            return;
        }

        const currentTop = viewport.scrollTop;
        const previousTop = lastFeedScrollTopRef.current;

        if (skipNextScrollEventRef.current) {
            // Ignore the synthetic scroll event caused by our own scrollTop correction after merging data.
            skipNextScrollEventRef.current = false;
            lastFeedScrollTopRef.current = currentTop;
            updateLeadVisibleDate();
            return;
        }

        if (currentTop !== previousTop) {
            scrollDirectionRef.current = currentTop > previousTop ? "down" : "up";
        }

        lastFeedScrollTopRef.current = currentTop;

        if (currentTop > 0) {
            resetTopOverscrollState();
        }

        // A normal scroll may both reveal a new lead date and reach the load-more preview sentinel.
        maybeLoadNextFromViewport();
        updateLeadVisibleDate();
    };

    // Detect upward wheel overscroll at the top of the feed and turn it into a prepend gesture.
    const handleFeedViewportWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
        const viewport = feedViewportRef.current;
        if (viewport === undefined) {
            return;
        }

        if (viewport.scrollTop > 0 || event.deltaY >= 0) {
            if (viewport.scrollTop > 0 || event.deltaY > 0) {
                resetTopOverscrollState();
            }
            return;
        }

        if (!hasMoreBeforeRef.current || hasAnyFeedLoadInFlight()) {
            return;
        }

        // Reaching the top and continuing to scroll upward accumulates toward a "load newer" gesture.
        topWheelPullDistanceRef.current += Math.abs(event.deltaY);
        if (topWheelPullDistanceRef.current >= TOP_OVERSCROLL_WHEEL_THRESHOLD) {
            triggerTopOverscrollLoad();
        }
    };

    // Start tracking a possible mobile pull-down gesture from the top of the feed.
    const handleFeedViewportTouchStart = (event: ReactTouchEvent<HTMLDivElement>) => {
        const viewport = feedViewportRef.current;
        if (viewport === undefined || viewport.scrollTop > 0) {
            topTouchStartYRef.current = undefined;
            topTouchPullDistanceRef.current = 0;
            return;
        }

        topTouchStartYRef.current = event.touches[0]?.clientY;
        topTouchPullDistanceRef.current = 0;
    };

    // Continue tracking a mobile pull-down gesture and trigger prepend loading when it is strong enough.
    const handleFeedViewportTouchMove = (event: ReactTouchEvent<HTMLDivElement>) => {
        const viewport = feedViewportRef.current;
        if (
            viewport === undefined
            || viewport.scrollTop > 0
            || topTouchStartYRef.current === undefined
            || !hasMoreBeforeRef.current
            || hasAnyFeedLoadInFlight()
        ) {
            return;
        }

        const currentY = event.touches[0]?.clientY ?? topTouchStartYRef.current;
        const delta = currentY - topTouchStartYRef.current;
        if (delta <= 0) {
            return;
        }

        // Mobile pull-down at the top mirrors the wheel-based overscroll behavior on desktop.
        topTouchPullDistanceRef.current = Math.max(topTouchPullDistanceRef.current, delta);
        if (topTouchPullDistanceRef.current >= TOP_OVERSCROLL_TOUCH_THRESHOLD) {
            triggerTopOverscrollLoad();
        }
    };

    // Clear temporary touch-gesture state after the user releases the feed.
    const handleFeedViewportTouchEnd = () => {
        topTouchStartYRef.current = undefined;
        topTouchPullDistanceRef.current = 0;
    };

    useIsomorphicLayoutEffect(() => {
        const pendingAdjustment = pendingScrollAdjustmentRef.current;
        const viewport = feedViewportRef.current;
        if (viewport === undefined) {
            return;
        }

        if (pendingAdjustment?.type === "prepend") {
            // Offset scrollTop by the inserted card heights so prepending feels anchored to the same content.
            const addedHeight = pendingAdjustment.addedIds.reduce((sum, id) => (
                sum + (paperRefs.current[id]?.offsetHeight || 0)
            ), 0);

            if (addedHeight > 0) {
                skipNextScrollEventRef.current = true;
                viewport.scrollTop += addedHeight;
                lastFeedScrollTopRef.current = viewport.scrollTop;
                scrollDirectionRef.current = pendingAdjustment.direction;
            }
        }

        if (pendingAdjustment?.type === "append-anchor") {
            const targetId = pendingAdjustment.firstNewPaperId;
            const targetElement = targetId !== undefined ? paperRefs.current[targetId] : undefined;

            if (targetElement !== undefined) {
                // Append adjustments are intentionally tiny so the viewport feels continuous without a jump.
                const delta = targetElement.offsetTop - pendingAdjustment.anchorTop;
                const adjustedDelta = delta * APPEND_SCROLL_ADJUSTMENT_RATIO;

                if (adjustedDelta !== 0) {
                    skipNextScrollEventRef.current = true;
                    viewport.scrollTop += adjustedDelta;
                    lastFeedScrollTopRef.current = viewport.scrollTop;
                    scrollDirectionRef.current = pendingAdjustment.direction;
                }
            }
        }

        pendingScrollAdjustmentRef.current = undefined;
        lastRealPaperBottomRef.current = getFeedViewportBottom();
        loadMoreThresholdConsumedRef.current = false;
        if (viewport.scrollTop > 0) {
            resetTopOverscrollState();
        }
        updateLeadVisibleDate();
    }, [papers]);

    // Replace the current feed with the papers associated with a selected calendar day.
    const handleSelectDate = (nextDate: string) => {
        if (
            activeDirectionRef.current === ""
            || nextDate === ""
            || !availableDateSet.has(nextDate)
        ) {
            return;
        }

        directionGenerationRef.current += 1;
        const generation = directionGenerationRef.current;
        // Picking a calendar day is treated like a full feed replacement scoped to that date.
        setSelectedDate(nextDate);
        selectedDateRef.current = nextDate;
        setDisplayedMonth(parseIsoDate(nextDate));
        setIsCalendarBrowsingManually(false);
        prepareFeedForReplace(true);
        setErrorMessage("");

        void fetchTimelineSlice(activeDirectionRef.current, {
            date: nextDate,
            limit: String(INITIAL_BATCH_SIZE),
        }, "replace", generation);
    };

    // Render a stack of timeline-card skeletons for initial, prepend, or append loading states.
    const renderSkeletonStack = (count: number, position: "top" | "initial" | "bottom") => (
        <div
            className={`timelineSkeletonStack timelineSkeletonStack${position[0].toUpperCase()}${position.slice(1)}`}
            data-testid={`timeline-skeleton-${position}`}
        >
            {createSkeletonKeys(count, position).map((key, idx) => {
                const blueprint = TIMELINE_SKELETON_BLUEPRINTS[idx % TIMELINE_SKELETON_BLUEPRINTS.length];

                return (
                    <article key={key} className="timelineSkeletonCard" aria-hidden="true">
                        <div className="timelineSkeletonHeaderRow">
                            <div
                                className="timelineSkeletonBlock timelineSkeletonLine timelineSkeletonLineEyebrow"
                                style={{ width: blueprint.eyebrow }}
                            />
                            <div className="timelineSkeletonChipRow">
                                {blueprint.tags.map((width, tagIdx) => (
                                    <span
                                        key={`${key}-tag-${tagIdx}`}
                                        className="timelineSkeletonBlock timelineSkeletonTag"
                                        style={{ width }}
                                    />
                                ))}
                            </div>
                        </div>
                        <div
                            className="timelineSkeletonBlock timelineSkeletonLine timelineSkeletonLineTitle"
                            style={{ width: blueprint.title }}
                        />
                        <div className="timelineSkeletonMetaRows">
                            {blueprint.meta.map((width, metaIdx) => (
                                <div key={`${key}-meta-${metaIdx}`} className="timelineSkeletonMetaRow">
                                    <span className="timelineSkeletonBlock timelineSkeletonMetaLabel" />
                                    <span
                                        className="timelineSkeletonBlock timelineSkeletonLine timelineSkeletonLineMeta"
                                        style={{ width }}
                                    />
                                </div>
                            ))}
                        </div>
                        <div className="timelineSkeletonParagraph">
                            {blueprint.paragraph.map((width, lineIdx) => (
                                <div
                                    key={`${key}-line-${lineIdx}`}
                                    className="timelineSkeletonBlock timelineSkeletonLine timelineSkeletonLineParagraph"
                                    style={{ width }}
                                />
                            ))}
                        </div>
                    </article>
                );
            })}
        </div>
    );

    // Render loading placeholders for the direction sidebar.
    const renderDirectionSkeletonList = () => (
        <div
            className="timelineDirectionSkeletonList"
            data-testid="timeline-direction-skeletons"
            style={{
                display: "flex",
                flexDirection: "column",
                gap: 8,
                width: "100%",
            }}
        >
            {createSkeletonKeys(DIRECTION_SKELETON_COUNT, "direction").map((key) => (
                <button
                    key={key}
                    type="button"
                    className="timelineDirectionButton timelineDirectionLoadingCard"
                    aria-hidden="true"
                    tabIndex={-1}
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-start",
                        width: "100%",
                        minHeight: 98,
                        padding: "10px 12px",
                        border: "1px solid #ccc",
                        borderRadius: 6,
                        background: "#fff",
                        boxSizing: "border-box",
                        position: "relative",
                        overflow: "hidden",
                        gap: 8,
                        cursor: "default",
                        pointerEvents: "none",
                        opacity: 1,
                    }}
                >
                    <span
                        className="timelineDirectionLoadingBar timelineDirectionLoadingBarPrimary"
                        aria-hidden="true"
                        style={createPreviewBarStyle("82%", 18, {
                            marginTop: 2,
                            flex: "0 0 auto",
                            zIndex: 1,
                        })}
                    />
                    <span
                        className="timelineDirectionLoadingBar timelineDirectionLoadingBarSecondary"
                        aria-hidden="true"
                        style={createPreviewBarStyle("36%", 12, {
                            marginTop: "auto",
                            flex: "0 0 auto",
                            zIndex: 1,
                        })}
                    />
                </button>
            ))}
        </div>
    );

    // Render the loading placeholder for the main feed header.
    const renderFeedHeaderSkeleton = () => (
        <div
            className="timelineFeedHeader timelineFeedHeaderSkeleton"
            data-testid="timeline-feed-header-skeleton"
            style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 16,
                padding: "18px 20px",
                minHeight: 92,
                width: "100%",
                border: "1px solid #d8dee6",
                borderRadius: 20,
                background: "#ffffff",
                boxSizing: "border-box",
            }}
        >
            <div
                className="timelineFeedHeaderPrimarySkeleton"
                aria-hidden="true"
                style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                    flex: 1,
                    minWidth: 0,
                }}
            >
                <span
                    className="timelineFeedHeaderLoadingBar timelineFeedHeaderLoadingBarPrimary"
                    style={createPreviewBarStyle("min(360px, 62%)", 24)}
                />
                <span
                    className="timelineFeedHeaderLoadingBar timelineFeedHeaderLoadingBarSecondary"
                    style={createPreviewBarStyle("min(240px, 38%)", 14)}
                />
            </div>
            <div
                className="timelineFeedHeaderSecondarySkeleton"
                aria-hidden="true"
                style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                    alignItems: "flex-end",
                    flex: "0 0 auto",
                }}
            >
                <span
                    className="timelineFeedHeaderLoadingBar timelineFeedHeaderSkeletonStat"
                    style={createPreviewBarStyle(72, 12)}
                />
                <span
                    className="timelineFeedHeaderLoadingBar timelineFeedHeaderSkeletonStat timelineFeedHeaderSkeletonStatShort"
                    style={createPreviewBarStyle(112, 12)}
                />
            </div>
        </div>
    );

    // Render placeholder feed cards for initial load and load-more preview states.
    const renderFeedPreviewCards = ({
        count = INITIAL_FEED_PREVIEW_COUNT,
        keyPrefix = "feed-preview",
        stackClassName = "timelineFeedPreviewStack",
        testId = "timeline-feed-preview-skeletons",
    }: {
        count?: number;
        keyPrefix?: string;
        stackClassName?: string;
        testId?: string;
    } = {}) => (
        <div
            className={stackClassName}
            data-testid={testId}
            style={{
                display: "flex",
                flexDirection: "column",
                gap: 18,
                width: "100%",
            }}
        >
            {createSkeletonKeys(count, keyPrefix).map((key, idx) => (
                <article
                    key={key}
                    className="timelineFeedPreviewCard"
                    aria-hidden="true"
                    data-load-more-preview-first={keyPrefix === "feed-load-more" && idx === 0 ? "true" : undefined}
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 16,
                        minHeight: 182,
                        padding: "18px 16px 20px",
                        border: "1px solid #d8dee8",
                        borderRadius: 14,
                        background: "#fff",
                        width: "100%",
                        boxSizing: "border-box",
                    }}
                >
                    <div
                        className="timelineFeedPreviewHeaderRow"
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 12,
                        }}
                    >
                        <span
                            className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarDate"
                            style={createPreviewBarStyle(92, 14)}
                        />
                        <div
                            className="timelineFeedPreviewTagRow"
                            style={{
                                display: "inline-flex",
                                gap: 8,
                                flexWrap: "wrap",
                            }}
                        >
                            <span
                                className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarTag"
                                style={createPreviewBarStyle(56, 22, { borderRadius: 8 })}
                            />
                            <span
                                className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarTag"
                                style={createPreviewBarStyle(54, 22, { borderRadius: 8 })}
                            />
                            <span
                                className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarTag timelineFeedPreviewBarTagWide"
                                style={createPreviewBarStyle(72, 22, { borderRadius: 8 })}
                            />
                        </div>
                    </div>
                    <span
                        className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarTitle"
                        style={createPreviewBarStyle("72%", 28)}
                    />
                    <div
                        className="timelineFeedPreviewMetaRow"
                        style={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 12,
                        }}
                    >
                        <span
                            className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarLabel"
                            style={createPreviewBarStyle(44, 14, { flex: "0 0 auto" })}
                        />
                        <span
                            className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarMeta"
                            style={createPreviewBarStyle("37%", 14, { marginTop: 1 })}
                        />
                    </div>
                    <div
                        className="timelineFeedPreviewMetaRow"
                        style={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 12,
                        }}
                    >
                        <span
                            className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarLabel"
                            style={createPreviewBarStyle(44, 14, { flex: "0 0 auto" })}
                        />
                        <div
                            className="timelineFeedPreviewParagraph"
                            style={{
                                display: "flex",
                                flex: 1,
                                flexDirection: "column",
                                gap: 10,
                            }}
                        >
                            <span
                                className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarParagraph timelineFeedPreviewBarParagraphFull"
                                style={createPreviewBarStyle("100%", 14)}
                            />
                            <span
                                className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarParagraph timelineFeedPreviewBarParagraphFull"
                                style={createPreviewBarStyle("100%", 14)}
                            />
                            <span
                                className="timelineDirectionLoadingBar timelineFeedPreviewBar timelineFeedPreviewBarParagraph timelineFeedPreviewBarParagraphShort"
                                style={createPreviewBarStyle("68%", 14)}
                            />
                        </div>
                    </div>
                </article>
            ))}
        </div>
    );

    // Render the loading placeholder for the right-hand calendar panel.
    const renderCalendarPlaceholder = () => (
        <div className="timelineCalendarPlaceholder" aria-hidden="true">
            <div className="timelineCalendarPlaceholderHeader">
                <div
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 10,
                        flex: 1,
                        minWidth: 0,
                    }}
                >
                    <span className="timelineSkeletonBlock timelineCalendarPlaceholderTitle" />
                    <span
                        className="timelineFeedHeaderLoadingBar timelineCalendarPlaceholderSubtitle"
                        style={createPreviewBarStyle("min(220px, 72%)", 13)}
                    />
                </div>
                <div className="timelineCalendarPlaceholderNav">
                    <span className="timelineSkeletonBlock timelineCalendarPlaceholderNavButton" />
                    <span className="timelineSkeletonBlock timelineCalendarPlaceholderNavButton" />
                </div>
            </div>
            <div className="timelineCalendarWeekRow">
                {CALENDAR_WEEKDAY_LABELS.map((label) => (
                    <span
                        key={`calendar-placeholder-week-${label}`}
                        className="timelineFeedHeaderLoadingBar timelineCalendarPlaceholderWeekday"
                    />
                ))}
            </div>
            <div className="timelineCalendarGrid">
                {createSkeletonKeys(CALENDAR_GRID_CELL_COUNT, "calendar-cell").map((key) => (
                    <span key={key} className="timelineSkeletonBlock timelineCalendarPlaceholderCell" />
                ))}
            </div>
        </div>
    );

    const shouldRenderTimelineShell = loadingDirections || directions.length > 0;
    const shouldRenderDirectionSkeletons = loadingDirections && directions.length === 0;
    const shouldHoldInitialFeedSkeleton = activeDirection !== "" && !hasResolvedInitialFeed && papers.length === 0;
    const shouldRenderFeedHeaderSkeleton = (
        shouldRenderDirectionSkeletons
        || activeDirection === ""
        || loadingCalendar
        || shouldHoldInitialFeedSkeleton
    );
    const shouldRenderInitialFeedSkeleton = (
        shouldRenderDirectionSkeletons
        || loadingCalendar
        || showInitialSkeleton
        || shouldHoldInitialFeedSkeleton
    );
    const shouldRenderFeedPreviewSkeletons = shouldRenderInitialFeedSkeleton;
    const shouldRenderFeedStatsSkeleton = !shouldRenderFeedHeaderSkeleton && shouldRenderInitialFeedSkeleton;
    const shouldRenderResolvedFeed = !shouldRenderInitialFeedSkeleton && papers.length > 0;
    const shouldRenderEmptyFeedState = !shouldRenderInitialFeedSkeleton && !loadingInitial && hasResolvedInitialFeed && papers.length === 0;
    const shouldRenderLoadMorePreview = shouldRenderResolvedFeed && hasMoreAfter;
    const shouldRenderFeedHint = shouldRenderResolvedFeed && !hasMoreAfter;

    useEffect(() => {
        if (!shouldRenderLoadMorePreview || loadingInitial || hasAnyFeedLoadInFlight()) {
            return;
        }

        const frameId = window.requestAnimationFrame(() => {
            maybeLoadNextFromViewport();
        });

        return () => {
            window.cancelAnimationFrame(frameId);
        };
    }, [loadingInitial, papers, shouldRenderLoadMorePreview]);

    return (
        <div className="timelinePageShell">
            <div className="timelinePageHeader">
                <div>
                    <h2 style={{ margin: "0 0 8px" }}>论文时间线</h2>
                    <p style={{ margin: 0 }}>按研究方向和日期查看论文动态，右侧日历可以快速跳到任意有论文的那一天。</p>
                </div>
            </div>

            {!loadingDirections && errorMessage !== "" && (
                <div className="timelineErrorBanner">
                    {errorMessage}
                </div>
            )}

            {shouldRenderTimelineShell && (
                <div className="timelineContentLayout">
                    <aside className="timelineDirectionsPanel">
                        <h3 className="timelineDirectionsPanelTitle">研究方向</h3>
                        {shouldRenderDirectionSkeletons ? (
                            renderDirectionSkeletonList()
                        ) : (
                            <div className="timelineDirectionList" aria-label="研究方向列表">
                                {directions.map((group) => (
                                    <button
                                        key={group.direction}
                                        onClick={() => {
                                            if (group.direction === activeDirection) {
                                                if (feedViewportRef.current !== undefined) {
                                                    lastFeedScrollTopRef.current = 0;
                                                    scrollDirectionRef.current = "down";
                                                    feedViewportRef.current.scrollTop = 0;
                                                    updateLeadVisibleDate();
                                                }
                                                return;
                                            }

                                            scrollDirectionRef.current = "down";
                                            setActiveDirection(group.direction);
                                        }}
                                        className={`timelineDirectionButton${group.direction === activeDirection ? " timelineDirectionButtonActive" : ""}`}
                                    >
                                        <div style={{ fontWeight: 600 }}>{group.direction}</div>
                                        <div className="timelineDirectionCount">{group.paper_count} 篇论文</div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </aside>

                    <section className="timelineMainPanel">
                        {shouldRenderFeedHeaderSkeleton ? (
                            renderFeedHeaderSkeleton()
                        ) : (
                            <div className="timelineFeedHeader">
                                <div>
                                    <h3 style={{ margin: "0 0 6px" }}>{activeDirection || "未选择研究方向"}</h3>
                                    <p className="timelineFeedSummaryText">
                                        {activeDirectionSummary ? `${activeDirectionSummary.paper_count} 篇归档论文` : "按时间倒序浏览最新论文"}
                                    </p>
                                </div>
                                <div className="timelineFeedStats">
                                    {shouldRenderFeedStatsSkeleton ? (
                                        <div className="timelineFeedStatsSkeleton" aria-hidden="true">
                                            <span className="timelineSkeletonBlock timelineFeedStatsSkeletonLine" />
                                            <span className="timelineSkeletonBlock timelineFeedStatsSkeletonLine timelineFeedStatsSkeletonLineWide" />
                                        </div>
                                    ) : (
                                        <>
                                            <span>共 {totalPapers} 篇</span>
                                            <span>
                                                {currentVisibleDateRange
                                                    ? `当前显示 ${currentVisibleDateRange.date} 第 ${currentVisibleDateRange.start}-${currentVisibleDateRange.end} 篇`
                                                    : "等待加载"}
                                            </span>
                                        </>
                                    )}
                                </div>
                            </div>
                        )}
                        {shouldRenderFeedPreviewSkeletons && renderFeedPreviewCards()}
                        <div
                            ref={(element) => {
                                feedViewportRef.current = element ?? undefined;
                            }}
                            className="timelineFeedViewport"
                            data-testid="timeline-feed-viewport"
                            onScroll={handleFeedViewportScroll}
                            onWheel={handleFeedViewportWheel}
                            onTouchStart={handleFeedViewportTouchStart}
                            onTouchMove={handleFeedViewportTouchMove}
                            onTouchEnd={handleFeedViewportTouchEnd}
                        >
                            {!loadingInitial && loadingPrevious && renderSkeletonStack(WINDOW_BATCH_SIZE, "top")}

                            {shouldRenderResolvedFeed && (
                                <div className="timelineFeedList timelineFeedListReveal" key={feedRevealKey}>
                                    {papers.map((paper) => {
                                        const subjectTags = parseTimelineSubjects(paper.subjects);

                                        return (
                                            <article
                                                key={paper.id}
                                                ref={(element) => {
                                                    paperRefs.current[paper.id] = element ?? undefined;
                                                }}
                                                className="timelineFeedCard"
                                                data-testid={`timeline-paper-${paper.id}`}
                                            >
                                                <div className="timelinePaperHeaderRow">
                                                    <div className="timelinePaperDate">
                                                        {paper.publish_date || "未知日期"}
                                                    </div>
                                                    {paper.arxiv_url && (
                                                        <div className="timelinePaperLinks" aria-label="论文外部链接">
                                                            <span>[</span>
                                                            <a href={paper.arxiv_url} target="_blank" rel="noreferrer">
                                                                arxiv
                                                            </a>
                                                            <span>, </span>
                                                            <a href={buildTimelinePdfUrl(paper.arxiv_url)} target="_blank" rel="noreferrer">
                                                                pdf
                                                            </a>
                                                            <span>]</span>
                                                        </div>
                                                    )}
                                                    {subjectTags.length > 0 && (
                                                        <div className="timelineSubjectTags" aria-label="论文学科分类">
                                                            {subjectTags.map((subject) => (
                                                                <span key={subject} className="timelineSubjectTag">
                                                                    {subject}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                                <h4 className="timelinePaperTitle">
                                                    <LatexText text={paper.title} forceInlineMath />
                                                </h4>
                                                <div className="timelineMetaRow">
                                                    <span className="timelineMetaLabel">作者：</span>
                                                    <div className="timelineMetaContent">
                                                        {renderPaperAuthors(paper)}
                                                    </div>
                                                </div>
                                                <div className="timelineMetaRow">
                                                    <span className="timelineMetaLabel">摘要：</span>
                                                    <div className="timelineMetaContent timelineAbstractContent">
                                                        <LatexText text={paper.tldr || paper.abstract || "暂无摘要"} />
                                                    </div>
                                                </div>
                                            </article>
                                        );
                                    })}

                                    {shouldRenderLoadMorePreview && renderFeedPreviewCards({
                                        count: LOAD_MORE_PREVIEW_COUNT,
                                        keyPrefix: "feed-load-more",
                                        testId: "timeline-feed-load-more-preview",
                                        stackClassName: "timelineFeedPreviewStack timelineFeedPreviewStackLoadMore",
                                    })}
                                </div>
                            )}

                            {shouldRenderEmptyFeedState && (
                                <div className="timelineEmptyState">
                                    当前研究方向下暂无可浏览的日期论文。
                                </div>
                            )}

                            {shouldRenderFeedHint && (
                                <div className="timelineFeedHint">
                                    {hasMoreBefore
                                        ? "已到更早日期末尾；回到顶部后继续上拉，可加载更新日期的论文。"
                                        : "这个方向的论文已经浏览到底。"}
                                </div>
                            )}
                        </div>
                    </section>

                    <aside className="timelineCalendarPanel" data-testid="timeline-calendar-panel">
                        <div className="timelineCalendarPanelHeader">
                            <div>
                                <h3 className="timelineCalendarPanelTitle">日期日历</h3>
                                <p className="timelineCalendarPanelSubtitle">
                                    {selectedDate !== "" ? `已选择 ${selectedDate}` : "只可点击有论文的日期"}
                                </p>
                            </div>
                        </div>
                        {loadingCalendar || calendarMeta === undefined ? (
                            renderCalendarPlaceholder()
                        ) : (
                            <>
                                <div className="timelineCalendarMonthBar">
                                    <button
                                        type="button"
                                        className="timelineCalendarNavButton"
                                        onClick={() => handleCalendarMonthChange(-1)}
                                        aria-label="查看上个月"
                                    >
                                        ‹
                                    </button>
                                    <div
                                        className="timelineCalendarMonthPickerAnchor"
                                        ref={(element) => {
                                            calendarPickerAnchorRef.current = element ?? undefined;
                                        }}
                                    >
                                        <span className="timelineCalendarMonthLabelSrOnly">
                                            {formatCalendarMonthLabel(currentCalendarMonth)}
                                        </span>
                                        <div className="timelineCalendarMonthLabel">
                                            <button
                                                type="button"
                                                className="timelineCalendarPickerTrigger"
                                                aria-label="选择年份"
                                                aria-expanded={isCalendarPickerOpen}
                                                aria-haspopup="dialog"
                                                disabled={!hasSelectableCalendarMonths}
                                                onClick={() => openCalendarPicker("year")}
                                            >
                                                {hasSelectableCalendarMonths
                                                    ? formatCalendarYearTriggerLabel(currentCalendarMonth.getFullYear())
                                                    : formatFallbackCalendarYearTriggerLabel(calendarMeta)}
                                            </button>
                                            <span className="timelineCalendarMonthLabelDivider" aria-hidden="true">/</span>
                                            <button
                                                type="button"
                                                className="timelineCalendarPickerTrigger"
                                                aria-label="选择月份"
                                                aria-expanded={isCalendarPickerOpen}
                                                aria-haspopup="dialog"
                                                disabled={!hasSelectableCalendarMonths}
                                                onClick={() => openCalendarPicker("month")}
                                            >
                                                {hasSelectableCalendarMonths
                                                    ? formatCalendarMonthTriggerLabel(currentCalendarMonth.getMonth() + 1)
                                                    : formatFallbackCalendarMonthTriggerLabel(calendarMeta)}
                                            </button>
                                        </div>
                                        {isCalendarPickerOpen && (
                                            <div className="timelineCalendarPicker" data-testid="timeline-calendar-picker">
                                                <div className="timelineCalendarPickerColumns">
                                                    <div
                                                        className={`timelineCalendarPickerColumn${calendarPickerActiveColumn === "year" ? " timelineCalendarPickerColumnActive" : ""}`}
                                                    >
                                                        <div className="timelineCalendarPickerColumnLabel">年份</div>
                                                        <div
                                                            ref={(element) => {
                                                                calendarPickerYearWheelRef.current = element ?? undefined;
                                                            }}
                                                            className="timelineCalendarPickerWheel"
                                                            data-testid="timeline-calendar-year-wheel"
                                                            tabIndex={0}
                                                            onWheel={(event) => {
                                                                event.preventDefault();
                                                                handleCalendarPickerWheel("year", event.deltaY);
                                                            }}
                                                        >
                                                            <div className="timelineCalendarPickerWheelSpacer" aria-hidden="true" />
                                                            {availableCalendarYears.map((year) => (
                                                                <button
                                                                    key={year}
                                                                    type="button"
                                                                    data-picker-value={year}
                                                                    className={`timelineCalendarPickerOption${calendarPickerDraftYear === year ? " timelineCalendarPickerOptionActive" : ""}`}
                                                                    onClick={() => handleCalendarPickerYearDraftChange(year)}
                                                                >
                                                                    {formatCalendarYearTriggerLabel(year)}
                                                                </button>
                                                            ))}
                                                            <div className="timelineCalendarPickerWheelSpacer" aria-hidden="true" />
                                                        </div>
                                                    </div>
                                                    <div
                                                        className={`timelineCalendarPickerColumn${calendarPickerActiveColumn === "month" ? " timelineCalendarPickerColumnActive" : ""}`}
                                                    >
                                                        <div className="timelineCalendarPickerColumnLabel">月份</div>
                                                        <div
                                                            ref={(element) => {
                                                                calendarPickerMonthWheelRef.current = element ?? undefined;
                                                            }}
                                                            className="timelineCalendarPickerWheel"
                                                            data-testid="timeline-calendar-month-wheel"
                                                            tabIndex={0}
                                                            onWheel={(event) => {
                                                                event.preventDefault();
                                                                handleCalendarPickerWheel("month", event.deltaY);
                                                            }}
                                                        >
                                                            <div className="timelineCalendarPickerWheelSpacer" aria-hidden="true" />
                                                            {availableCalendarMonthsForDraftYear.map((month) => (
                                                                <button
                                                                    key={month}
                                                                    type="button"
                                                                    data-picker-value={month}
                                                                    className={`timelineCalendarPickerOption${calendarPickerDraftMonth === month ? " timelineCalendarPickerOptionActive" : ""}`}
                                                                    onClick={() => handleCalendarPickerMonthDraftChange(month)}
                                                                >
                                                                    {formatCalendarMonthTriggerLabel(month)}
                                                                </button>
                                                            ))}
                                                            <div className="timelineCalendarPickerWheelSpacer" aria-hidden="true" />
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="timelineCalendarPickerActions">
                                                    <button
                                                        type="button"
                                                        className="timelineCalendarPickerActionButton"
                                                        onClick={closeCalendarPicker}
                                                    >
                                                        取消
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="timelineCalendarPickerActionButton"
                                                        onClick={applyCalendarPickerSelection}
                                                    >
                                                        确定
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        className="timelineCalendarNavButton"
                                        onClick={() => handleCalendarMonthChange(1)}
                                        aria-label="查看下个月"
                                    >
                                        ›
                                    </button>
                                </div>
                                <div className="timelineCalendarWeekRow" aria-hidden="true">
                                    {CALENDAR_WEEKDAY_LABELS.map((label) => (
                                        <span key={`weekday-${label}`} className="timelineCalendarWeekday">
                                            {label}
                                        </span>
                                    ))}
                                </div>
                                <div className="timelineCalendarGrid">
                                    {calendarDayCells.map((cell) => {
                                        const isLeadVisible = leadVisibleDate !== "" && cell.isoDate === leadVisibleDate;
                                        const cellClassName = [
                                            "timelineCalendarDayButton",
                                            cell.inCurrentMonth ? "" : " timelineCalendarDayButtonOutside",
                                            cell.isInteractive ? "" : " timelineCalendarDayButtonDisabled",
                                            isLeadVisible ? " timelineCalendarDayButtonLead" : "",
                                        ].join("");
                                        const cellStyle = {
                                            "--timeline-calendar-cell-bg": cell.backgroundColor,
                                            "--timeline-calendar-cell-text": cell.textColor,
                                        } as React.CSSProperties;

                                        return (
                                            <button
                                                key={cell.isoDate}
                                                type="button"
                                                data-testid={`timeline-calendar-day-${cell.isoDate}`}
                                                className={cellClassName}
                                                style={cellStyle}
                                                onClick={() => {
                                                    if (!cell.isInteractive) {
                                                        return;
                                                    }
                                                    handleSelectDate(cell.isoDate);
                                                }}
                                                aria-disabled={!cell.isInteractive}
                                                aria-label={`${cell.isoDate} ${cell.displayCount} 篇论文`}
                                            >
                                                <span className="timelineCalendarDayNumber">{cell.label}</span>
                                                <span className="timelineCalendarDayMeta">
                                                    {cell.displayCount}篇
                                                </span>
                                            </button>
                                        );
                                    })}
                                </div>
                            </>
                        )}
                    </aside>
                </div>
            )}

            {!loadingDirections && errorMessage === "" && directions.length === 0 && (
                <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                    暂无时间线数据。
                </div>
            )}

            <style jsx>{`
                :global(.appMain:has(.timelinePageShell)) {
                    width: min(1544px, calc(100% - 32px));
                }

                .timelinePageShell {
                    --timeline-surface: #ffffff;
                    --timeline-surface-muted: #f6f8fb;
                    --timeline-border: #d8dee6;
                    --timeline-text-muted: #687384;
                    --timeline-accent: #0c63a6;
                    --timeline-accent-soft: #ebf5ff;
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                    width: 100%;
                    max-width: 1544px;
                    height: calc(100vh - 158px);
                    overflow: hidden;
                }

                .timelinePageHeader {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 16px;
                }

                .timelineContentLayout {
                    display: grid;
                    grid-template-columns: 240px minmax(0, 856px) 400px;
                    gap: 24px;
                    align-items: stretch;
                    flex: 1;
                    min-height: 0;
                    overflow: hidden;
                }

                .timelineDirectionsPanel,
                .timelineCalendarPanel {
                    display: flex;
                    flex-direction: column;
                    gap: 14px;
                    border: 1px solid var(--timeline-border);
                    border-radius: 20px;
                    padding: 18px 16px;
                    background: var(--timeline-surface);
                    overflow-y: auto;
                    overscroll-behavior: contain;
                    box-sizing: border-box;
                }

                .timelineCalendarPanel {
                    align-self: start;
                }

                .timelineDirectionsPanelTitle,
                .timelineCalendarPanelTitle {
                    margin: 0;
                }

                .timelineCalendarPanelHeader {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                }

                .timelineCalendarPanelSubtitle {
                    margin: 4px 0 0;
                    font-size: 13px;
                    color: var(--timeline-text-muted);
                }

                .timelineCalendarMonthBar {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 12px;
                }

                .timelineCalendarMonthPickerAnchor {
                    position: relative;
                    display: flex;
                    flex: 1;
                    justify-content: center;
                }

                .timelineCalendarMonthLabel {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    min-height: 34px;
                    font-size: 16px;
                    font-weight: 700;
                    text-align: center;
                    color: #1f2328;
                }

                .timelineCalendarMonthLabelSrOnly {
                    position: absolute;
                    width: 1px;
                    height: 1px;
                    padding: 0;
                    margin: -1px;
                    overflow: hidden;
                    clip: rect(0, 0, 0, 0);
                    white-space: nowrap;
                    border: 0;
                }

                .timelineCalendarMonthLabelDivider {
                    color: var(--timeline-text-muted);
                    font-weight: 500;
                }

                .timelineCalendarPickerTrigger {
                    border: none;
                    border-radius: 10px;
                    background: transparent;
                    color: #1f2328;
                    padding: 6px 10px;
                    font-size: 16px;
                    font-weight: 700;
                    line-height: 1;
                }

                .timelineCalendarPickerTrigger:hover:not(:disabled),
                .timelineCalendarPickerTrigger:focus-visible {
                    background: transparent;
                    color: var(--timeline-accent);
                    outline: none;
                    box-shadow: none;
                    transform: none;
                }

                .timelineCalendarPicker {
                    position: absolute;
                    top: calc(100% + 10px);
                    left: 50%;
                    z-index: 3;
                    width: min(100%, 280px);
                    min-width: 260px;
                    transform: translateX(-50%);
                    border: 1px solid var(--timeline-border);
                    border-radius: 18px;
                    background: #ffffff;
                    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.14);
                    padding: 14px;
                }

                .timelineCalendarPickerColumns {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 12px;
                }

                .timelineCalendarPickerColumn {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    min-width: 0;
                }

                .timelineCalendarPickerColumnActive .timelineCalendarPickerColumnLabel {
                    color: var(--timeline-accent);
                }

                .timelineCalendarPickerColumnLabel {
                    font-size: 12px;
                    font-weight: 700;
                    color: var(--timeline-text-muted);
                    text-align: center;
                    letter-spacing: 0.04em;
                }

                .timelineCalendarPickerWheel {
                    position: relative;
                    display: flex;
                    flex-direction: column;
                    max-height: ${CALENDAR_PICKER_ITEM_HEIGHT * CALENDAR_PICKER_VISIBLE_ROWS}px;
                    overflow-y: auto;
                    overscroll-behavior: contain;
                    scroll-snap-type: y mandatory;
                    scroll-padding-block: ${CALENDAR_PICKER_ITEM_HEIGHT * 2}px;
                    scrollbar-width: none;
                    padding: 0;
                    border-radius: 14px;
                    background: transparent;
                    outline: none;
                }

                .timelineCalendarPickerWheel::-webkit-scrollbar {
                    display: none;
                }

                .timelineCalendarPickerWheel:focus-visible {
                    box-shadow: 0 0 0 3px rgba(12, 99, 166, 0.14);
                }

                .timelineCalendarPickerWheelSpacer {
                    flex: 0 0 ${CALENDAR_PICKER_ITEM_HEIGHT * 2}px;
                }

                .timelineCalendarPickerOption {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    min-height: ${CALENDAR_PICKER_ITEM_HEIGHT}px;
                    padding: 0 10px;
                    border: none;
                    border-radius: 0;
                    background: transparent;
                    color: #1f2328;
                    font-size: 15px;
                    font-weight: 500;
                    line-height: 1;
                    scroll-snap-align: center;
                    box-shadow: none;
                    transform: none;
                }

                .timelineCalendarPickerOption:hover,
                .timelineCalendarPickerOption:focus-visible {
                    background: transparent;
                    color: var(--timeline-accent);
                    outline: none;
                    box-shadow: none;
                    transform: none;
                }

                .timelineCalendarPickerOptionActive {
                    background: transparent;
                    color: var(--timeline-accent);
                    font-weight: 700;
                }

                .timelineCalendarPickerActions {
                    display: flex;
                    justify-content: flex-end;
                    gap: 8px;
                    margin-top: 14px;
                }

                .timelineCalendarPickerActionButton {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    height: 33.77px;
                    box-sizing: border-box;
                    padding: 0 12px;
                    border-radius: 10px;
                    border: 1px solid var(--border-soft);
                    background: var(--surface-panel);
                    color: var(--ink-strong);
                    font-size: 14px;
                    font-weight: 600;
                    transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
                }

                .timelineCalendarPickerActionButton:hover:not(:disabled),
                .timelineCalendarPickerActionButton:focus-visible {
                    border-color: var(--border-strong);
                    box-shadow: var(--shadow-soft);
                    transform: translateY(-1px);
                    outline: none;
                }

                .timelineCalendarNavButton {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    width: 34px;
                    height: 34px;
                    border-radius: 10px;
                    border: 1px solid var(--timeline-border);
                    background: #fff;
                    color: #1f2328;
                    font-size: 22px;
                    line-height: 1;
                    cursor: pointer;
                }

                .timelineCalendarNavButton:hover,
                .timelineCalendarNavButton:focus-visible {
                    border-color: var(--timeline-accent);
                    outline: none;
                }

                .timelineCalendarWeekRow {
                    display: grid;
                    grid-template-columns: repeat(7, minmax(0, 1fr));
                    gap: 8px;
                }

                .timelineCalendarWeekday {
                    text-align: center;
                    font-size: 12px;
                    font-weight: 600;
                    color: var(--timeline-text-muted);
                }

                .timelineCalendarGrid {
                    display: grid;
                    grid-template-columns: repeat(7, minmax(0, 1fr));
                    gap: 4px;
                }

                .timelineCalendarDayButton {
                    --timeline-calendar-cell-bg: #ffffff;
                    --timeline-calendar-cell-text: #1f2328;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    gap: 2px;
                    width: 100%;
                    aspect-ratio: 1 / 1;
                    padding: 4px;
                    border-radius: 0;
                    border: 1px solid transparent;
                    background: var(--timeline-calendar-cell-bg);
                    color: var(--timeline-calendar-cell-text);
                    text-align: center;
                    cursor: pointer;
                    transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
                }

                .timelineCalendarDayButton:hover,
                .timelineCalendarDayButton:focus-visible {
                    border-color: var(--timeline-accent);
                    background: #ffffff;
                    color: #1f2328;
                    outline: none;
                }

                .timelineCalendarDayButtonDisabled {
                    cursor: not-allowed;
                }

                .timelineCalendarDayButtonOutside {
                    filter: saturate(0.92);
                }

                .timelineCalendarDayButtonLead {
                    border-color: var(--timeline-accent);
                    background: #ffffff;
                    color: #1f2328;
                }

                .timelineCalendarDayNumber {
                    font-size: 15px;
                    font-weight: 700;
                    color: currentColor;
                    line-height: 1;
                }

                .timelineCalendarDayMeta {
                    min-height: 10px;
                    font-size: 11px;
                    line-height: 1.1;
                    color: currentColor;
                    opacity: 0;
                    transition: opacity 0.16s ease;
                }

                .timelineCalendarDayButton:hover .timelineCalendarDayMeta,
                .timelineCalendarDayButton:focus-visible .timelineCalendarDayMeta,
                .timelineCalendarDayButtonLead .timelineCalendarDayMeta {
                    opacity: 1;
                }

                .timelineCalendarPlaceholder {
                    display: flex;
                    flex-direction: column;
                    gap: 14px;
                }

                .timelineCalendarPlaceholderHeader {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 12px;
                }

                .timelineCalendarPlaceholderTitle {
                    width: 132px;
                    height: 16px;
                    border-radius: 999px;
                }

                .timelineCalendarPlaceholderSubtitle {
                    width: min(220px, 72%);
                    height: 13px;
                    border-radius: 999px;
                }

                .timelineCalendarPlaceholderNav {
                    display: flex;
                    gap: 8px;
                }

                .timelineCalendarPlaceholderNavButton {
                    width: 34px;
                    height: 34px;
                    border-radius: 10px;
                }

                .timelineCalendarPlaceholderWeekday {
                    display: block;
                    width: 100%;
                    height: 12px;
                    border-radius: 999px;
                    justify-self: center;
                    align-self: center;
                }

                .timelineCalendarPlaceholderCell {
                    display: block;
                    width: 100%;
                    aspect-ratio: 1 / 1;
                    border-radius: 0;
                }

                .timelineDirectionList {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                }

                .timelineDirectionButton {
                    text-align: left;
                    padding: 10px 12px;
                    border-radius: 6px;
                    border: 1px solid #ccc;
                    background: #fff;
                    cursor: pointer;
                    transition: border-color 0.16s ease, background-color 0.16s ease;
                }

                .timelineDirectionButton:hover,
                .timelineDirectionButton:focus-visible {
                    border-color: #0d6efd;
                    background: #ffffff;
                    outline: none;
                }

                .timelineDirectionButtonActive {
                    border-color: #0d6efd;
                    background: #e7f1ff;
                }

                .timelineDirectionCount {
                    margin-top: 4px;
                    font-size: 12px;
                    color: #666;
                }

                .timelineMainPanel {
                    display: flex;
                    flex-direction: column;
                    gap: 14px;
                    min-height: 0;
                    height: 100%;
                    overflow: hidden;
                }

                .timelineFeedHeader {
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    gap: 16px;
                    padding: 18px 20px;
                    border: 1px solid var(--timeline-border);
                    border-radius: 20px;
                    background: #ffffff;
                }

                .timelineFeedSummaryText {
                    margin: 0;
                    color: var(--timeline-text-muted);
                    font-size: 14px;
                }

                .timelineFeedStats {
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                    align-items: flex-end;
                    color: var(--timeline-text-muted);
                    font-size: 13px;
                    white-space: nowrap;
                }

                .timelineFeedStatsSkeleton {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    align-items: flex-end;
                    min-width: 132px;
                }

                .timelineFeedStatsSkeletonLine {
                    display: block;
                    width: 72px;
                    height: 12px;
                    border-radius: 999px;
                }

                .timelineFeedStatsSkeletonLineWide {
                    width: 112px;
                }

                .timelineFeedViewport {
                    flex: 1;
                    min-height: 0;
                    overflow-y: auto;
                    overscroll-behavior: contain;
                    padding-right: 4px;
                }

                .timelineFeedList,
                .timelineSkeletonStack {
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                }

                .timelineFeedPreviewStack {
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                }

                .timelineFeedPreviewStackLoadMore {
                    width: 100%;
                }

                .timelineFeedPreviewCard {
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                    min-height: 182px;
                    padding: 18px 16px 20px;
                    border: 1px solid #d8dee8;
                    border-radius: 14px;
                    background: #fff;
                }

                .timelineFeedListReveal {
                    animation: timelineFeedFadeIn ${INITIAL_SKELETON_FADE_MS}ms ease-out;
                }

                .timelineFeedCard,
                .timelineSkeletonCard {
                    border: 1px solid #ccc;
                    border-radius: 8px;
                    padding: 16px;
                    background: #fff;
                }

                .timelinePaperTitle {
                    margin: 0 0 10px;
                    font-size: 18px;
                    line-height: 1.45;
                    color: #1f2328;
                }

                .timelinePaperHeaderRow {
                    display: flex;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 10px;
                    margin-bottom: 8px;
                    font-size: 13px;
                    color: #666;
                }

                .timelinePaperDate {
                    color: var(--timeline-text-muted);
                }

                .timelinePaperLinks {
                    color: rgb(45, 45, 45);
                    font-size: 14px;
                    line-height: 1.4;
                }

                .timelinePaperLinks a,
                :global(a.timelineMentorLink) {
                    display: inline-flex;
                    align-items: center;
                    gap: 4px;
                    height: 20px;
                    color: var(--timeline-accent);
                    text-decoration: none;
                    transition: color 0.16s ease, border-color 0.16s ease;
                    border-bottom: 1px dashed transparent;
                    line-height: 1;
                    vertical-align: middle;
                }

                .timelinePaperLinks a:hover,
                .timelinePaperLinks a:focus-visible,
                :global(a.timelineMentorLink:hover),
                :global(a.timelineMentorLink:focus-visible) {
                    color: rgb(45, 45, 45);
                    border-bottom-color: rgb(45, 45, 45);
                    outline: none;
                }

                .timelineSubjectTags {
                    display: inline-flex;
                    flex-wrap: wrap;
                    gap: 10px;
                }

                .timelineSubjectTag {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 17.5px;
                    padding: 0 8.925px;
                    border-radius: 4px;
                    background-color: rgb(8, 109, 177);
                    color: rgb(255, 255, 255);
                    font-size: 11.9px;
                    line-height: 17.85px;
                    white-space: nowrap;
                }

                :global(img.timelineMentorIcon) {
                    width: 14px;
                    height: 14px;
                    object-fit: contain;
                    display: block;
                    flex: 0 0 auto;
                }

                .timelineMetaRow {
                    font-size: 14px;
                    line-height: 1.6;
                }

                .timelineMetaLabel,
                .timelineMetaContent {
                    font-size: 14px;
                }

                .timelineMetaLabel {
                    color: #1f2328;
                    font-weight: 600;
                }

                .timelineMetaContent {
                    color: #3f4854;
                }

                .timelineSkeletonCard {
                    overflow: hidden;
                    position: relative;
                    background: #fff;
                    padding: 18px 20px;
                }

                .timelineSkeletonBlock {
                    position: relative;
                    overflow: hidden;
                    background: linear-gradient(90deg, #e3e9f0 0%, #edf2f7 40%, #ffffff 50%, #edf2f7 60%, #e3e9f0 100%);
                    background-size: 200% 100%;
                    animation: timelinePreviewBarShimmer 1.15s ease-in-out infinite;
                }

                .timelineSkeletonLine,
                .timelineSkeletonTag {
                    display: block;
                    border-radius: 999px;
                }

                .timelineSkeletonLine {
                    height: 12px;
                }

                .timelineSkeletonHeaderRow {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 12px;
                    margin-bottom: 18px;
                }

                .timelineSkeletonChipRow {
                    display: inline-flex;
                    flex-wrap: wrap;
                    justify-content: flex-end;
                    gap: 8px;
                    flex: 1;
                }

                .timelineSkeletonLineEyebrow {
                    height: 11px;
                    flex: 0 0 auto;
                }

                .timelineSkeletonLineTitle {
                    height: 22px;
                    margin-bottom: 18px;
                }

                .timelineSkeletonMetaRows {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    margin-bottom: 18px;
                }

                .timelineSkeletonMetaRow {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }

                .timelineSkeletonTag {
                    height: 22px;
                }

                .timelineSkeletonMetaLabel {
                    width: 42px;
                    height: 12px;
                    flex: 0 0 auto;
                }

                .timelineSkeletonLineMeta {
                    height: 12px;
                    flex: 0 0 auto;
                }

                .timelineSkeletonParagraph {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                }

                .timelineSkeletonLineParagraph {
                    height: 11px;
                }

                .timelineDirectionLoadingCard {
                    cursor: default;
                    pointer-events: none;
                    opacity: 1;
                }

                .timelineDirectionLoadingBar,
                .timelineFeedHeaderLoadingBar,
                .timelineFeedPreviewBar {
                    display: block;
                    border-radius: 999px;
                    position: relative;
                    overflow: hidden;
                    background: linear-gradient(90deg, #e3e9f0 0%, #edf2f7 40%, #ffffff 50%, #edf2f7 60%, #e3e9f0 100%);
                    background-size: 200% 100%;
                    animation: timelinePreviewBarShimmer 1.15s ease-in-out infinite;
                }

                .timelineEmptyState,
                .timelineErrorBanner,
                .timelineFeedHint {
                    padding: 14px 16px;
                    border-radius: 16px;
                }

                .timelineEmptyState {
                    border: 1px dashed var(--timeline-border);
                    background: var(--timeline-surface-muted);
                    color: var(--timeline-text-muted);
                }

                .timelineErrorBanner {
                    border: 1px solid #f1aeb5;
                    background-color: #f8d7da;
                }

                .timelineFeedHint {
                    text-align: center;
                    color: var(--timeline-text-muted);
                    font-size: 13px;
                    margin-top: 14px;
                }

                @keyframes timelinePreviewBarShimmer {
                    from {
                        background-position: 200% 0;
                    }

                    to {
                        background-position: -200% 0;
                    }
                }

                @keyframes timelineFeedFadeIn {
                    from {
                        opacity: 0;
                        transform: translateY(4px);
                    }

                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }

                @media (max-width: 900px) {
                    .timelinePageHeader {
                        flex-direction: column;
                        align-items: stretch;
                    }

                    .timelineContentLayout {
                        display: flex;
                        flex-direction: column;
                    }

                    .timelineDirectionsPanel,
                    .timelineCalendarPanel,
                    .timelineMainPanel {
                        min-height: 0;
                    }

                    .timelineDirectionsPanel,
                    .timelineCalendarPanel {
                        height: auto;
                        overflow-y: hidden;
                    }

                    .timelineDirectionList {
                        flex-direction: row;
                        overflow-x: auto;
                        padding-bottom: 2px;
                    }

                    .timelineDirectionButton,
                    .timelineDirectionLoadingCard {
                        flex: 0 0 220px;
                    }

                    .timelineFeedHeader {
                        flex-direction: column;
                        align-items: stretch;
                    }

                    .timelineFeedStats,
                    .timelineFeedStatsSkeleton {
                        align-items: flex-start;
                        white-space: normal;
                    }

                    .timelineFeedViewport {
                        padding-right: 0;
                    }
                }

                @media (max-width: 720px) {
                    .timelineSkeletonHeaderRow {
                        flex-direction: column;
                        align-items: flex-start;
                    }

                    .timelineSkeletonChipRow {
                        justify-content: flex-start;
                    }

                    .timelineCalendarGrid {
                        gap: 3px;
                    }

                    .timelineCalendarDayButton {
                        padding: 3px;
                    }
                }
            `}</style>
        </div>
    );
};

export default TimelinePage;
