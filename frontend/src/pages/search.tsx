import Link from "next/link";
import { CSSProperties, KeyboardEvent, MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import { useSelector } from "react-redux";

import FollowToggleButton from "../components/FollowToggleButton";
import LatexText from "../components/LatexText";
import Pagination from "../components/Pagination";
import { describeRequestError } from "../utils/errorMessage";
import { NetworkError, NetworkErrorType, request } from "../utils/network";
import { RootState } from "../redux/store";
import { INPUT_LIMITS } from "../constants/inputLimits";
import {
    buildSearchUrl,
    DEFAULT_SEARCH_QUERY_STATE,
    parseSearchQuery,
    normalizeSearchKeywordForUrl,
    SearchMatchMode,
    SearchMentorVisibility,
    SearchMode,
    SearchPaperSortMode,
    SearchQueryState,
} from "../utils/searchQuery";
import {
    clearPendingMentorSearchReturn,
    readPendingMentorSearchReturn,
    writePendingMentorSearchReturn,
} from "../utils/searchNavigation";
import { PrivateMentorResult, SearchMentorResult, SearchPaperResult } from "../utils/types";
type MentorResultFilter = SearchMentorVisibility;

// Control how much mentor detail is shown inline before the result card expands.
const PROFILE_PREVIEW_LENGTH = 100;
const PAPER_TITLES_PREVIEW_COUNT = 7;
const SEARCH_VIEW_STATE_STORAGE_PREFIX = "search-view-state:";
const INITIAL_HISTORY_ENTRY_KEY = "search-entry-initial";
const SEARCH_PAGINATION_CONTROL_HEIGHT = 33.77;
const SEARCH_SKELETON_COUNT = 4;
const MIN_SEARCH_SKELETON_MS = 5;
const SEARCH_ACTION_BUTTON_STYLE: CSSProperties = {
    flexShrink: 0,
    height: SEARCH_PAGINATION_CONTROL_HEIGHT,
    boxSizing: "border-box",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "0 12px",
    whiteSpace: "nowrap",
};

interface PrivateMentorsResponse {
    mentors?: PrivateMentorResult[];
}

interface SearchMentorsResponse {
    mentors?: SearchMentorResult[];
    page?: number;
    page_size?: number;
    total?: number;
    total_pages?: number;
    has_previous?: boolean;
    has_next?: boolean;
}

interface SearchPapersResponse {
    papers?: SearchPaperResult[];
    page?: number;
    page_size?: number;
    total?: number;
    total_pages?: number;
    has_previous?: boolean;
    has_next?: boolean;
}

interface SearchNavigationOptions {
    keyword?: string;
    mode?: SearchMode;
    searchMode?: SearchMatchMode;
    sortMode?: SearchPaperSortMode;
    page?: number;
    visibility?: MentorResultFilter;
}

interface MentorDeleteTarget {
    id: number;
    Chinese_name: string;
    English_name?: string;
    research_direction: string;
    email?: string;
}

interface PaperDeleteTarget {
    id: number;
    title: string;
    publish_date?: string;
    subjects?: string;
    mentorNames: string[];
}

interface SegmentedOption<TValue extends string> {
    label: string;
    value: TValue;
}

interface SearchHistoryViewState {
    scrollY: number;
    expandedProfileMentorIds: number[];
    expandedPaperMentorIds: number[];
    expandedMentorIds?: number[];
}

type SearchNavigationIntent = "init" | "push" | "pop" | "refresh";

// Carries pending restore context when navigation returns from the mentor detail page back to search.
let pendingSearchPopRestore:
    | {
        entryKey: string;
        transitionId: number;
    }
    | undefined;

// Read the current browser history entry key used to persist per-entry UI state.
const getWindowHistoryEntryKey = () => {
    // Next.js stores a per-entry key in history.state; use it to persist per-entry UI state.
    if (typeof window === "undefined") {
        return INITIAL_HISTORY_ENTRY_KEY;
    }

    const historyState = window.history.state as { key?: unknown } | undefined;
    const historyKey = historyState?.key;
    if (typeof historyKey === "string" && historyKey.trim() !== "") {
        return historyKey;
    }

    return INITIAL_HISTORY_ENTRY_KEY;
};

// Detect clicks that should keep native browser navigation behavior.
const isModifiedNavigationClick = (event: MouseEvent<HTMLElement>) => {
    // Modified clicks should keep native browser behavior instead of being intercepted for custom restoration.
    return event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey;
};

// Derive the PDF URL from a standard arXiv abstract URL.
const buildTimelineLikePdfUrl = (arxivUrl?: string) => {
    if (typeof arxivUrl !== "string" || arxivUrl.trim() === "" || !arxivUrl.includes("/abs/")) {
        return "";
    }

    return arxivUrl.replace("/abs/", "/pdf/");
};

// Split a comma-separated subject string into normalized subject tags.
const parseTimelineLikeSubjects = (subjects?: string) => {
    if (typeof subjects !== "string" || subjects.trim() === "") {
        return [];
    }

    return subjects
        .split(",")
        .map((subject) => subject.trim())
        .filter((subject) => subject !== "");
};

// Normalize persisted mentor ids before using them to restore expansion state.
const normalizeHistoryMentorIds = (values?: Iterable<number> | ArrayLike<number>) => {
    // Sanitize persisted ids before using them to restore expanded mentor cards.
    return Array.from(values ?? [])
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0);
};

// Build the session-storage payload used to restore scroll and expansion state for one search entry.
const buildSearchHistoryViewState = (
    scrollY: number,
    expandedProfileMentorIds: Iterable<number> | ArrayLike<number>,
    expandedPaperMentorIds: Iterable<number> | ArrayLike<number>,
) => {
    // Persist both split expansion state and the legacy combined list for backward compatibility.
    const normalizedProfileMentorIds = normalizeHistoryMentorIds(expandedProfileMentorIds);
    const normalizedPaperMentorIds = normalizeHistoryMentorIds(expandedPaperMentorIds);

    return {
        scrollY: Number.isFinite(scrollY) ? scrollY : 0,
        expandedProfileMentorIds: normalizedProfileMentorIds,
        expandedPaperMentorIds: normalizedPaperMentorIds,
        expandedMentorIds: Array.from(new Set([...normalizedProfileMentorIds, ...normalizedPaperMentorIds])),
    };
};

const SEARCH_MODE_OPTIONS: SegmentedOption<SearchMode>[] = [
    { label: "搜人", value: "mentor" },
    { label: "搜论文", value: "paper" },
];

const MATCH_MODE_OPTIONS: SegmentedOption<SearchMatchMode>[] = [
    { label: "模糊", value: "fuzzy" },
    { label: "精确", value: "exact" },
];

const PAPER_SORT_OPTIONS: SegmentedOption<SearchPaperSortMode>[] = [
    { label: "默认", value: "default" },
    { label: "最早", value: "early" },
    { label: "最晚", value: "late" },
];

const MENTOR_FILTER_OPTIONS: SegmentedOption<MentorResultFilter>[] = [
    { label: "全部", value: "all" },
    { label: "私有", value: "mine" },
    { label: "公共", value: "public" },
];

const SEARCH_SKELETON_BLUEPRINTS = [
    {
        title: "38%",
        button: "76px",
        meta: ["42%", "64%", "36%"],
        profile: ["96%", "88%", "58%"],
        papers: ["82%", "74%", "68%"],
        tags: ["56px", "68px", "48px"],
    },
    {
        title: "46%",
        button: "76px",
        meta: ["35%", "58%", "44%"],
        profile: ["92%", "80%"],
        papers: ["76%", "66%"],
        tags: ["64px", "52px"],
    },
    {
        title: "32%",
        button: "76px",
        meta: ["48%", "52%", "40%"],
        profile: ["100%", "86%", "62%"],
        papers: ["84%", "72%", "54%"],
        tags: ["50px", "72px", "60px"],
    },
] as const;

// Create stable keys for repeated search-result skeleton placeholders.
const createSearchSkeletonKeys = (count: number, prefix: string) => (
    Array.from({ length: count }, (_, idx) => `${prefix}-${idx}`)
);

// Build the follow button style used by mentor cards in search results.
const buildSearchMentorFollowButtonStyle = (followed: boolean): CSSProperties => ({
    position: "relative",
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
    whiteSpace: "nowrap",
    overflow: "hidden",
    cursor: "pointer",
    boxShadow: "none",
    transition: "none",
    appearance: "none",
    opacity: 1,
});

// Render the main search page for mentors and papers, including URL-synced query state and history restoration.
const SearchScreen = () => {
    const router = useRouter();
    const authToken = useSelector((state: RootState) => state.auth.token);
    const authRole = useSelector((state: RootState) => state.auth.role);
    const isLoggedIn = authToken.trim() !== "";
    const isAdmin = authRole === "admin";
    const canFollowMentor = isLoggedIn && authRole === "student";

    const [mode, setMode] = useState<SearchMode>("mentor");
    const [matchMode, setMatchMode] = useState<SearchMatchMode>("fuzzy");
    const [paperSortMode, setPaperSortMode] = useState<SearchPaperSortMode>("default");
    const [keyword, setKeyword] = useState("");
    const [appliedKeyword, setAppliedKeyword] = useState("");
    const [loading, setLoading] = useState(false);
    const [showSearchSkeleton, setShowSearchSkeleton] = useState(false);
    const [hasSearched, setHasSearched] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");
    const [mentors, setMentors] = useState<SearchMentorResult[]>([]);
    const [papers, setPapers] = useState<SearchPaperResult[]>([]);
    const [currentPage, setCurrentPage] = useState(1);
    const [totalResults, setTotalResults] = useState(0);
    const [totalPages, setTotalPages] = useState(0);
    const [_hasPreviousPage, setHasPreviousPage] = useState(false);
    const [_hasNextPage, setHasNextPage] = useState(false);
    const [adminSaving, setAdminSaving] = useState(false);
    const [adminMessage, setAdminMessage] = useState("");
    const [mentorDeleteTarget, setMentorDeleteTarget] = useState<MentorDeleteTarget | undefined>(undefined);
    const [mentorDeleteSubmitting, setMentorDeleteSubmitting] = useState(false);
    const [paperDeleteTarget, setPaperDeleteTarget] = useState<PaperDeleteTarget | undefined>(undefined);
    const [paperDeleteSubmitting, setPaperDeleteSubmitting] = useState(false);
    const [privateMentors, setPrivateMentors] = useState<PrivateMentorResult[]>([]);
    const [followedMentorIds, setFollowedMentorIds] = useState<Set<number>>(new Set());
    const [followToggleMentorId, setFollowToggleMentorId] = useState<number | undefined>(undefined);
    const [mentorResultFilter, setMentorResultFilter] = useState<MentorResultFilter>("all");
    const [expandedProfileMentorIds, setExpandedProfileMentorIds] = useState<Set<number>>(new Set());
    const [expandedPaperMentorIds, setExpandedPaperMentorIds] = useState<Set<number>>(new Set());
    const [privateMentorSaving, setPrivateMentorSaving] = useState(false);
    const [privateMentorMsg, setPrivateMentorMsg] = useState("");
    const [customMentorChineseName, setCustomMentorChineseName] = useState("");
    const [customMentorEnglishName, setCustomMentorEnglishName] = useState("");
    const [customMentorResearchDirection, setCustomMentorResearchDirection] = useState("");
    const [customMentorEmail, setCustomMentorEmail] = useState("");
    const [customMentorProfile, setCustomMentorProfile] = useState("");
    const [showSearchLogicHelp, setShowSearchLogicHelp] = useState(false);

    const [mentorEditingId, setMentorEditingId] = useState<number | undefined>(undefined);
    const [mentorDraft, setMentorDraft] = useState({
        Chinese_name: "",
        English_name: "",
        research_direction: "",
        email: "",
        profile: "",
    });

    const [paperEditingId, setPaperEditingId] = useState<number | undefined>(undefined);
    const [paperDraft, setPaperDraft] = useState({
        title: "",
        abstract: "",
        publish_date: "",
        author_names: "",
    });
    const [activeSearchState, setActiveSearchState] = useState<SearchQueryState>(DEFAULT_SEARCH_QUERY_STATE);

    const activeSearchStateRef = useRef<SearchQueryState>(DEFAULT_SEARCH_QUERY_STATE);
    const expandedProfileMentorIdsRef = useRef<Set<number>>(new Set());
    const expandedPaperMentorIdsRef = useRef<Set<number>>(new Set());
    const navigationIntentRef = useRef<SearchNavigationIntent>("init");
    const navigationTransitionIdRef = useRef(0);
    const hasLoadedRouteStateRef = useRef(false);
    const pendingPushRestoreRef = useRef<{ transitionId?: number; targetEntryKey?: string }>({});
    const blockAutoPersistRef = useRef(false);
    const hasCheckedCrossPageRestoreRef = useRef(false);
    const searchSkeletonStartedAtRef = useRef(0);
    const searchSkeletonTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    const searchSkeletonGenerationRef = useRef(0);

    if (!hasCheckedCrossPageRestoreRef.current) {
        hasCheckedCrossPageRestoreRef.current = true;

        if (typeof window !== "undefined" && pendingSearchPopRestore === undefined) {
            const pendingMentorSearchReturn = readPendingMentorSearchReturn();
            const currentEntryKey = getWindowHistoryEntryKey();

            // If the user is returning from a mentor page, treat the next route sync as a pop-style restore.
            if (pendingMentorSearchReturn?.sourceEntryKey === currentEntryKey) {
                const transitionId = navigationTransitionIdRef.current + 1;
                navigationTransitionIdRef.current = transitionId;
                blockAutoPersistRef.current = true;
                pendingSearchPopRestore = {
                    entryKey: currentEntryKey,
                    transitionId,
                };
                navigationIntentRef.current = "pop";
            }
        }
    }

    // Clear the current result set while optionally preserving mentor expansion state.
    const resetResults = (clearExpandedMentors = true) => {
        // Reset only the current result set while leaving the query controls intact.
        setErrorMessage("");
        setMentors([]);
        setPapers([]);
        if (clearExpandedMentors) {
            setExpandedProfileMentorIds(new Set());
            setExpandedPaperMentorIds(new Set());
        }
        setCurrentPage(1);
        setTotalResults(0);
        setTotalPages(0);
        setHasPreviousPage(false);
        setHasNextPage(false);
    };

    // Cancel the delayed skeleton-hide timer for the current search load cycle.
    const clearSearchSkeletonTimer = useCallback(() => {
        if (searchSkeletonTimerRef.current !== undefined) {
            clearTimeout(searchSkeletonTimerRef.current);
            searchSkeletonTimerRef.current = undefined;
        }
    }, []);

    // Start the visible skeleton phase for a search request and return its generation id.
    const startSearchSkeletonPhase = useCallback(() => {
        clearSearchSkeletonTimer();
        const generation = searchSkeletonGenerationRef.current + 1;
        searchSkeletonGenerationRef.current = generation;
        searchSkeletonStartedAtRef.current = Date.now();
        // A generation counter prevents stale requests from hiding the newest skeleton prematurely.
        setShowSearchSkeleton(true);
        return generation;
    }, [clearSearchSkeletonTimer]);

    // Finish a search skeleton phase while honoring the minimum visible skeleton duration.
    const finishSearchSkeletonPhase = useCallback((generation: number) => {
        if (searchSkeletonGenerationRef.current !== generation) {
            return;
        }

        clearSearchSkeletonTimer();
        const elapsed = Date.now() - searchSkeletonStartedAtRef.current;
        const remaining = Math.max(MIN_SEARCH_SKELETON_MS - elapsed, 0);

        if (remaining === 0) {
            setShowSearchSkeleton(false);
            return;
        }

        searchSkeletonTimerRef.current = setTimeout(() => {
            searchSkeletonTimerRef.current = undefined;
            if (searchSkeletonGenerationRef.current === generation) {
                setShowSearchSkeleton(false);
            }
        }, remaining);
    }, [clearSearchSkeletonTimer]);

    useEffect(() => () => {
        clearSearchSkeletonTimer();
    }, [clearSearchSkeletonTimer]);

    // Normalize pagination metadata from the backend into the page's local pagination state.
    const applyPagination = (
        paginationData: {
            page?: number;
            total?: number;
            total_pages?: number;
            has_previous?: boolean;
            has_next?: boolean;
        },
        fallbackCount: number,
        requestedPage: number,
    ) => {
        // Normalize partially missing pagination metadata so mentor and paper searches render consistently.
        const resolvedPage = Number(paginationData.page);
        const normalizedPage = Number.isFinite(resolvedPage) && resolvedPage > 0
            ? resolvedPage
            : requestedPage;
        setCurrentPage(normalizedPage);

        const resolvedTotal = Number(paginationData.total);
        const normalizedTotal = Number.isFinite(resolvedTotal) && resolvedTotal >= 0
            ? resolvedTotal
            : fallbackCount;
        setTotalResults(normalizedTotal);

        const resolvedTotalPages = Number(paginationData.total_pages);
        const fallbackTotalPages = normalizedTotal > 0 ? 1 : 0;
        const normalizedTotalPages = Number.isFinite(resolvedTotalPages) && resolvedTotalPages >= 0
            ? resolvedTotalPages
            : fallbackTotalPages;
        setTotalPages(normalizedTotalPages);

        setHasPreviousPage(Boolean(paginationData.has_previous));
        setHasNextPage(Boolean(paginationData.has_next));
    };

    // Narrow unknown errors to the shared NetworkError class when possible.
    const isNetworkErrorInstance = (err: unknown): err is NetworkError => {
        return typeof NetworkError === "function" && err instanceof NetworkError;
    };

    // Return the current browser history entry key used by search-state persistence.
    const getHistoryEntryKey = () => {
        return getWindowHistoryEntryKey();
    };

    // Read the persisted scroll and expansion state for one search history entry.
    const readHistoryViewState = (entryKey: string) => {
        if (typeof window === "undefined") {
            return undefined;
        }

        try {
            const rawValue = window.sessionStorage.getItem(`${SEARCH_VIEW_STATE_STORAGE_PREFIX}${entryKey}`);
            if (typeof rawValue !== "string") {
                return undefined;
            }

            // Support both the current split expansion keys and the older combined expandedMentorIds payload.
            const parsedValue = JSON.parse(rawValue) as Partial<SearchHistoryViewState>;
            const legacyExpandedIds = Array.isArray(parsedValue.expandedMentorIds)
                ? normalizeHistoryMentorIds(parsedValue.expandedMentorIds)
                : [];
            const expandedProfileIds = Array.isArray(parsedValue.expandedProfileMentorIds)
                ? normalizeHistoryMentorIds(parsedValue.expandedProfileMentorIds)
                : legacyExpandedIds;
            const expandedPaperIds = Array.isArray(parsedValue.expandedPaperMentorIds)
                ? normalizeHistoryMentorIds(parsedValue.expandedPaperMentorIds)
                : legacyExpandedIds;

            return {
                scrollY: Number.isFinite(parsedValue.scrollY) ? Number(parsedValue.scrollY) : 0,
                expandedProfileMentorIds: expandedProfileIds,
                expandedPaperMentorIds: expandedPaperIds,
                expandedMentorIds: Array.from(new Set([...expandedProfileIds, ...expandedPaperIds])),
            } satisfies SearchHistoryViewState;
        }
        catch {
            return undefined;
        }
    };

    // Persist scroll and mentor expansion state for one search history entry.
    const writeHistoryViewState = (entryKey: string, viewState: SearchHistoryViewState) => {
        if (typeof window === "undefined") {
            return;
        }

        try {
            window.sessionStorage.setItem(
                `${SEARCH_VIEW_STATE_STORAGE_PREFIX}${entryKey}`,
                JSON.stringify(viewState),
            );
        }
        catch {
            // Ignore sessionStorage failures and keep search functional.
        }
    };

    // Save the current scroll position and expanded mentor sections into session storage.
    const persistCurrentViewState = useCallback((entryKey = getHistoryEntryKey(), force = false) => {
        if (typeof window === "undefined") {
            return;
        }

        if (!force && blockAutoPersistRef.current) {
            return;
        }

        // Save scroll position plus expanded mentor subsections so browser navigation restores reading context.
        const nextViewState = {
            scrollY: Number.isFinite(window.scrollY) ? window.scrollY : 0,
            expandedProfileMentorIds: Array.from(expandedProfileMentorIdsRef.current),
            expandedPaperMentorIds: Array.from(expandedPaperMentorIdsRef.current),
        };
        writeHistoryViewState(entryKey, buildSearchHistoryViewState(
            nextViewState.scrollY,
            nextViewState.expandedProfileMentorIds,
            nextViewState.expandedPaperMentorIds,
        ));
    }, []);

    // Restore window scroll position in a browser-safe and test-safe way.
    const scrollWindowTo = useCallback((scrollY: number) => {
        if (typeof window === "undefined") {
            return;
        }

        try {
            window.scrollTo({ left: 0, top: scrollY, behavior: "auto" });
        }
        catch {
            try {
                window.scrollTo(0, scrollY);
            }
            catch {
                // Ignore scroll failures in tests or non-browser environments.
            }
        }
    }, []);

    // Run a callback after paint so scroll restoration waits for layout-dependent content to settle.
    const scheduleAfterPaint = useCallback((callback: () => void) => {
        // Two animation frames reliably wait for layout/paint before restoring scroll-sensitive UI.
        if (typeof window === "undefined") {
            callback();
            return;
        }

        const schedule = window.requestAnimationFrame
            ? window.requestAnimationFrame.bind(window)
            : (fn: FrameRequestCallback) => window.setTimeout(() => fn(Date.now()), 16);

        schedule(() => {
            schedule(() => callback());
        });
    }, []);

    // Compare two canonical search states to decide whether a route change is actually new.
    const areSearchStatesEqual = useCallback((left: SearchQueryState, right: SearchQueryState) => {
        return left.keyword === right.keyword &&
            left.mode === right.mode &&
            left.searchMode === right.searchMode &&
            left.sortMode === right.sortMode &&
            left.page === right.page &&
            left.visibility === right.visibility;
    }, []);

    // Merge UI overrides into a canonical search state used for URL sync and requests.
    const resolveSearchState = useCallback((
        overrides: SearchNavigationOptions = {},
        baseState: SearchQueryState = activeSearchStateRef.current,
    ) => {
        // Recompute a canonical query state for URL sync and request-building.
        const nextMode = overrides.mode ?? baseState.mode;
        const nextKeyword = normalizeSearchKeywordForUrl(overrides.keyword ?? baseState.keyword);
        const nextPageRaw = overrides.page ?? baseState.page;
        const nextPage = Number.isFinite(nextPageRaw) && nextPageRaw > 0 ? Math.floor(nextPageRaw) : 1;
        const nextSortMode = overrides.sortMode ?? baseState.sortMode;
        const nextSearchMode = overrides.searchMode ?? baseState.searchMode;
        const nextVisibility = nextMode === "mentor"
            ? (overrides.visibility ?? (baseState.mode === "mentor" ? baseState.visibility : "all"))
            : "all";

        return {
            keyword: nextKeyword,
            mode: nextMode,
            searchMode: nextSearchMode,
            sortMode: nextSortMode,
            page: nextPage,
            visibility: nextVisibility,
        } satisfies SearchQueryState;
    }, []);

    // Clear all admin edit-mode state for mentor and paper management.
    const resetAdminEditorState = useCallback(() => {
        setAdminMessage("");
        setMentorEditingId(undefined);
        setMentorDraft({
            Chinese_name: "",
            English_name: "",
            research_direction: "",
            email: "",
            profile: "",
        });
        setPaperEditingId(undefined);
        setPaperDraft({
            title: "",
            abstract: "",
            publish_date: "",
            author_names: "",
        });
    }, []);

    // Clear transient dialogs and admin editors before switching to another search state.
    const resetTransientUiState = useCallback(() => {
        resetAdminEditorState();
        setMentorDeleteTarget(undefined);
        setMentorDeleteSubmitting(false);
        setPaperDeleteTarget(undefined);
        setPaperDeleteSubmitting(false);
    }, [resetAdminEditorState]);

    // Build the backend request URL for mentor search from a canonical search state.
    const buildMentorSearchRequestUrl = useCallback((state: SearchQueryState) => {
        // Mentor search supports visibility filtering in addition to keyword and match mode.
        const query = `keyword=${encodeURIComponent(normalizeSearchKeywordForUrl(state.keyword))}&search_mode=${state.searchMode}`;
        const pageQuery = state.page > 1 ? `&page=${state.page}` : "";
        const visibilityQuery = state.visibility !== "all" ? `&visibility=${state.visibility}` : "";

        return `/api/search/mentors?${query}${pageQuery}${visibilityQuery}`;
    }, []);

    // Build the backend request URL for paper search from a canonical search state.
    const buildPaperSearchRequestUrl = useCallback((state: SearchQueryState) => {
        // Paper search uses the same keyword syntax but adds a dedicated sort mode.
        const query = `keyword=${encodeURIComponent(normalizeSearchKeywordForUrl(state.keyword))}&search_mode=${state.searchMode}`;
        const pageQuery = state.page > 1 ? `&page=${state.page}` : "";

        return `/api/search/papers?${query}&sort_mode=${state.sortMode}${pageQuery}`;
    }, []);

    // Restore scroll and expansion state after a search load depending on push/pop/refresh intent.
    const applyLoadedViewState = useCallback((state: SearchQueryState, intent: SearchNavigationIntent) => {
        if (intent === "push") {
            // New navigations reset scroll and collapse mentor cards because they represent a fresh result view.
            const targetEntryKey = pendingPushRestoreRef.current.targetEntryKey ?? getHistoryEntryKey();
            const transitionId = pendingPushRestoreRef.current.transitionId ?? navigationTransitionIdRef.current;
            setExpandedProfileMentorIds(new Set());
            setExpandedPaperMentorIds(new Set());
            writeHistoryViewState(targetEntryKey, buildSearchHistoryViewState(0, [], []));
            scheduleAfterPaint(() => {
                scrollWindowTo(0);
                scheduleAfterPaint(() => {
                    if (navigationTransitionIdRef.current !== transitionId) {
                        return;
                    }
                    writeHistoryViewState(targetEntryKey, buildSearchHistoryViewState(0, [], []));
                    blockAutoPersistRef.current = false;
                    if (pendingPushRestoreRef.current.transitionId === transitionId) {
                        pendingPushRestoreRef.current = {};
                    }
                });
            });
            return;
        }

        if (intent === "pop") {
            // Back/forward restores both scroll position and expanded mentor sections from session storage.
            const entryKey = pendingSearchPopRestore?.entryKey ?? getHistoryEntryKey();
            const transitionId = pendingSearchPopRestore?.transitionId ?? navigationTransitionIdRef.current;
            const savedViewState = readHistoryViewState(entryKey);
            const restoredProfileExpandedIds = state.mode === "mentor"
                ? new Set(savedViewState?.expandedProfileMentorIds ?? [])
                : new Set<number>();
            const restoredPaperExpandedIds = state.mode === "mentor"
                ? new Set(savedViewState?.expandedPaperMentorIds ?? [])
                : new Set<number>();
            setExpandedProfileMentorIds(restoredProfileExpandedIds);
            setExpandedPaperMentorIds(restoredPaperExpandedIds);
            scheduleAfterPaint(() => {
                scrollWindowTo(savedViewState?.scrollY ?? 0);
                scheduleAfterPaint(() => {
                    if (navigationTransitionIdRef.current !== transitionId) {
                        return;
                    }
                    blockAutoPersistRef.current = false;
                    persistCurrentViewState(entryKey, true);
                    if (readPendingMentorSearchReturn()?.sourceEntryKey === entryKey) {
                        clearPendingMentorSearchReturn();
                    }
                    if (pendingSearchPopRestore?.transitionId === transitionId) {
                        pendingSearchPopRestore = undefined;
                    }
                });
            });
            return;
        }

        blockAutoPersistRef.current = false;
        if (
            state.mode !== "mentor" &&
            (expandedProfileMentorIdsRef.current.size > 0 || expandedPaperMentorIdsRef.current.size > 0)
        ) {
            setExpandedProfileMentorIds(new Set());
            setExpandedPaperMentorIds(new Set());
        }
    }, [persistCurrentViewState, scheduleAfterPaint, scrollWindowTo]);

    // Load one canonical search state into the page, including data fetch and post-load restoration.
    const loadSearchState = useCallback(async (
        state: SearchQueryState,
        intent: SearchNavigationIntent,
    ) => {
        // This is the single query-to-results pipeline: sync controls, fetch data, then restore view state.
        activeSearchStateRef.current = state;
        if (intent !== "refresh") {
            resetTransientUiState();
        }
        setActiveSearchState(state);
        setMode(state.mode);
        setMatchMode(state.searchMode);
        setPaperSortMode(state.sortMode);
        setMentorResultFilter(state.visibility);
        setKeyword(normalizeSearchKeywordForUrl(state.keyword));
        const skeletonGeneration = startSearchSkeletonPhase();
        setLoading(true);
        setHasSearched(true);
        setErrorMessage("");

        try {
            if (state.mode === "mentor") {
                const res = await request<SearchMentorsResponse>(
                    buildMentorSearchRequestUrl(state),
                    "GET",
                    isLoggedIn,
                );
                const mentorItems = Array.isArray(res.mentors) ? res.mentors : [];
                setAppliedKeyword(state.keyword);
                setMentors(mentorItems);
                setPapers([]);
                applyPagination(res, mentorItems.length, state.page);
            }
            else {
                const res = await request<SearchPapersResponse>(
                    buildPaperSearchRequestUrl(state),
                    "GET",
                    isLoggedIn,
                );
                const paperItems = Array.isArray(res.papers) ? res.papers : [];
                setAppliedKeyword(state.keyword);
                setPapers(paperItems);
                setMentors([]);
                applyPagination(res, paperItems.length, state.page);
            }
        }
        catch (err) {
            setAppliedKeyword(state.keyword);
            resetResults(intent !== "pop");
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setLoading(false);
            finishSearchSkeletonPhase(skeletonGeneration);
            applyLoadedViewState(state, intent);
            // Reset the intent after every load so later route syncs are treated normally.
            navigationIntentRef.current = "init";
        }
    }, [
        applyLoadedViewState,
        buildMentorSearchRequestUrl,
        buildPaperSearchRequestUrl,
        finishSearchSkeletonPhase,
        isLoggedIn,
        resetTransientUiState,
        startSearchSkeletonPhase,
    ]);

    // Re-run the current search state without changing the URL or history entry.
    const refreshCurrentSearch = useCallback(async (state = activeSearchStateRef.current) => {
        navigationIntentRef.current = "refresh";
        await loadSearchState(state, "refresh");
    }, [loadSearchState]);

    // Push a new shallow search URL, persist current view state, and load the next search result set.
    const navigateToSearchState = useCallback(async (nextState: SearchQueryState) => {
        const currentState = activeSearchStateRef.current;

        if (areSearchStatesEqual(nextState, currentState)) {
            await refreshCurrentSearch(nextState);
            return;
        }

        const transitionId = navigationTransitionIdRef.current + 1;
        // Save the current entry's scroll/expansion state before pushing the next shallow search URL.
        navigationTransitionIdRef.current = transitionId;
        pendingSearchPopRestore = undefined;
        expandedProfileMentorIdsRef.current = new Set(expandedProfileMentorIds);
        expandedPaperMentorIdsRef.current = new Set(expandedPaperMentorIds);
        const sourceEntryKey = getHistoryEntryKey();
        persistCurrentViewState(sourceEntryKey, true);
        blockAutoPersistRef.current = true;
        navigationIntentRef.current = "push";
        const targetUrl = buildSearchUrl(nextState);
        await router.push(
            targetUrl,
            undefined,
            { shallow: true, scroll: false },
        );
        pendingPushRestoreRef.current = {
            transitionId,
            targetEntryKey: getHistoryEntryKey(),
        };

        if (!areSearchStatesEqual(activeSearchStateRef.current, nextState)) {
            await loadSearchState(nextState, "push");
        }
    }, [
        areSearchStatesEqual,
        expandedPaperMentorIds,
        expandedProfileMentorIds,
        loadSearchState,
        persistCurrentViewState,
        refreshCurrentSearch,
        router,
    ]);

    // Switch between mentor and paper search modes and reset mode-specific transient UI.
    const switchMode = (nextMode: SearchMode) => {
        if (nextMode === mode) {
            return;
        }

        resetAdminEditorState();

        void navigateToSearchState(resolveSearchState({
            keyword,
            mode: nextMode,
            page: 1,
            visibility: "all",
        }));
    };

    // Convert admin-only dataset management errors into short UI messages.
    const formatAdminError = (err: unknown) => {
        if (isNetworkErrorInstance(err)) {
            if (err.type === NetworkErrorType.UNAUTHORIZED) {
                return "请先登录管理员账号";
            }

            if (err.type === NetworkErrorType.REJECTED) {
                return "仅管理员可以执行该操作";
            }
        }

        return describeRequestError(err);
    };

    // Load the current user's private mentors so search results can show owner-specific state.
    const fetchMyPrivateMentors = useCallback(async () => {
        if (!isLoggedIn) {
            setPrivateMentors([]);
            return;
        }

        try {
            // Search needs the user's private mentor ids so cards can show owner-specific actions and badges.
            const res = await request<PrivateMentorsResponse>("/api/dataset/mentors/mine", "GET", true);
            const mentorList = Array.isArray(res.mentors) ? res.mentors : [];
            setPrivateMentors(mentorList.filter((mentor) => Array.isArray(mentor.paper_ids)));
        }
        catch {
            setPrivateMentors([]);
        }
    }, [isLoggedIn]);

    useEffect(() => {
        void fetchMyPrivateMentors();
    }, [fetchMyPrivateMentors]);

    // Load the current student's followed mentor ids for follow-button rendering.
    const fetchFollowedMentors = useCallback(async () => {
        if (!canFollowMentor) {
            setFollowedMentorIds(new Set());
            return;
        }

        try {
            // Student users need the followed mentor set so result cards render the correct button state.
            const res = await request<{ mentors?: SearchMentorResult[] }>(
                "/api/follow/mentors",
                "GET",
                true,
            );
            const list = Array.isArray(res.mentors) ? res.mentors : [];
            setFollowedMentorIds(new Set(list.map((mentor) => mentor.id)));
        }
        catch {
            setFollowedMentorIds(new Set());
        }
    }, [canFollowMentor]);

    useEffect(() => {
        void fetchFollowedMentors();
    }, [fetchFollowedMentors]);

    // Follow or unfollow one mentor directly from the search results list.
    const toggleMentorFollow = useCallback(async (mentorId: number) => {
        if (!canFollowMentor) {
            return;
        }

        const wasFollowed = followedMentorIds.has(mentorId);
        setFollowToggleMentorId(mentorId);
        setErrorMessage("");

        try {
            const res = await request<{ followed?: boolean }>(
                `/api/follow/mentors/${mentorId}`,
                wasFollowed ? "DELETE" : "POST",
                true,
            );
            setFollowedMentorIds((prev) => {
                const next = new Set(prev);
                if (Boolean(res.followed)) {
                    next.add(mentorId);
                }
                else {
                    next.delete(mentorId);
                }
                return next;
            });
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setFollowToggleMentorId(undefined);
        }
    }, [canFollowMentor, followedMentorIds]);

    useEffect(() => {
        activeSearchStateRef.current = activeSearchState;
    }, [activeSearchState]);

    useEffect(() => {
        expandedProfileMentorIdsRef.current = expandedProfileMentorIds;
        expandedPaperMentorIdsRef.current = expandedPaperMentorIds;
    }, [expandedPaperMentorIds, expandedProfileMentorIds]);

    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }

        // Mark browser back/forward navigation so the next route sync restores the prior entry state.
        const handlePopState = () => {
            if (pendingSearchPopRestore !== undefined) {
                return;
            }

            // Browser back/forward should restore the previous search entry instead of acting like a fresh push.
            const transitionId = navigationTransitionIdRef.current + 1;
            navigationTransitionIdRef.current = transitionId;
            blockAutoPersistRef.current = true;
            pendingSearchPopRestore = {
                entryKey: getHistoryEntryKey(),
                transitionId,
            };
            navigationIntentRef.current = "pop";
        };

        const hasBeforePopState = typeof router.beforePopState === "function";
        if (hasBeforePopState) {
            router.beforePopState((state) => {
                // beforePopState exposes the upcoming history entry key earlier than raw popstate does.
                const stateLike = state as { key?: unknown; as?: unknown; url?: unknown } | undefined;
                const entryKey = typeof stateLike?.key === "string" && stateLike.key.trim() !== ""
                    ? stateLike.key
                    : getHistoryEntryKey();
                const transitionId = navigationTransitionIdRef.current + 1;
                navigationTransitionIdRef.current = transitionId;
                blockAutoPersistRef.current = true;
                pendingSearchPopRestore = {
                    entryKey,
                    transitionId,
                };
                navigationIntentRef.current = "pop";
                return true;
            });
        }

        window.addEventListener("popstate", handlePopState);
        return () => {
            if (hasBeforePopState) {
                router.beforePopState(() => true);
            }
            window.removeEventListener("popstate", handlePopState);
        };
    }, [router]);

    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }

        // Persist scroll position continuously so return navigation restores nearby results.
        const handleScroll = () => {
            persistCurrentViewState();
        };

        // Persist scroll passively so returning from detail pages lands near the same result card.
        window.addEventListener("scroll", handleScroll, { passive: true });
        return () => {
            window.removeEventListener("scroll", handleScroll);
        };
    }, [persistCurrentViewState]);

    useEffect(() => {
        persistCurrentViewState();
    }, [expandedPaperMentorIds, expandedProfileMentorIds, persistCurrentViewState]);

    // Cache the current user's private mentor ids for fast badge and action checks in result cards.
    const privateMentorIdSet = useMemo(() => {
        return new Set(privateMentors.map((mentor) => mentor.id));
    }, [privateMentors]);

    const thirdSegmentOptions = mode === "paper" ? PAPER_SORT_OPTIONS : MENTOR_FILTER_OPTIONS;
    const thirdSegmentValue = mode === "paper" ? paperSortMode : mentorResultFilter;
    const trimmedAppliedKeyword = appliedKeyword.trim();
    const isEmptySearch = trimmedAppliedKeyword === "";
    const searchHeadingText = isEmptySearch
        ? `Search in ${totalResults} entrys:`
        : `Showing ${totalResults} results for all: ${trimmedAppliedKeyword}`;

    // Create a private mentor inline from the "mine" search context and refresh the current results.
    const addPrivateMentorInSearch = useCallback(async () => {
        const chineseName = customMentorChineseName.trim();
        const englishName = customMentorEnglishName.trim();
        const researchDirection = customMentorResearchDirection.trim();
        const email = customMentorEmail.trim();
        const profile = customMentorProfile.trim();

        if (chineseName === "" && englishName === "") {
            setPrivateMentorMsg("中文名和英文名至少填写一个");
            return;
        }

        if (privateMentors.length >= 10) {
            setPrivateMentorMsg("私有导师最多添加 10 位，请先删除后再添加");
            return;
        }

        // The search page can create private mentors inline when the user is focused on "mine" results.
        setPrivateMentorSaving(true);
        setPrivateMentorMsg("");

        try {
            await request("/api/dataset/mentors/custom", "POST", true, {
                Chinese_name: chineseName,
                English_name: englishName,
                research_direction: researchDirection,
                email,
                profile,
            });
            setCustomMentorChineseName("");
            setCustomMentorEnglishName("");
            setCustomMentorResearchDirection("");
            setCustomMentorEmail("");
            setCustomMentorProfile("");
            await fetchMyPrivateMentors();
            // Refresh the current search so the newly created private mentor can appear immediately.
            await refreshCurrentSearch(resolveSearchState({ page: 1 }));
            setPrivateMentorMsg("私有导师添加成功");
        }
        catch (err) {
            if (isNetworkErrorInstance(err)) {
                const rawMsg = String(err);
                if (rawMsg.includes("Mentor already exists")) {
                    setPrivateMentorMsg("该导师已在你的私有导师列表中，请勿重复添加");
                }
                else if (rawMsg.includes("Private mentor limit reached")) {
                    setPrivateMentorMsg("私有导师数量已达上限（10位），请先删除部分私有导师后再添加");
                }
                else {
                    setPrivateMentorMsg(describeRequestError(err));
                }
            }
            else {
                setPrivateMentorMsg(describeRequestError(err));
            }
        }
        finally {
            setPrivateMentorSaving(false);
        }
    }, [customMentorChineseName, customMentorEnglishName, customMentorResearchDirection, customMentorEmail, customMentorProfile, fetchMyPrivateMentors, privateMentors.length, refreshCurrentSearch, resolveSearchState]);

    useEffect(() => {
        if (!router.isReady) {
            return;
        }

        const { hasAnySearchParam, state } = parseSearchQuery(router.query);
        const nextRouteState = hasAnySearchParam ? state : DEFAULT_SEARCH_QUERY_STATE;
        const nextIntent = pendingSearchPopRestore !== undefined
            ? "pop"
            : (hasLoadedRouteStateRef.current ? navigationIntentRef.current : "init");

        // Treat the URL as the source of truth so deep links and browser navigation remain reproducible.
        if (hasLoadedRouteStateRef.current && areSearchStatesEqual(nextRouteState, activeSearchStateRef.current)) {
            navigationIntentRef.current = "init";
            return;
        }

        hasLoadedRouteStateRef.current = true;
        void loadSearchState(nextRouteState, nextIntent);
    }, [areSearchStatesEqual, loadSearchState, router.isReady, router.query]);

    // Change paper sort mode and rerun search immediately when paper results are already active.
    const changePaperSortMode = (nextSortMode: SearchPaperSortMode) => {
        if (paperSortMode === nextSortMode) {
            return;
        }

        if (!hasSearched || mode !== "paper") {
            setPaperSortMode(nextSortMode);
            return;
        }

        void navigateToSearchState(resolveSearchState({
            keyword,
            sortMode: nextSortMode,
            page: 1,
        }));
    };

    // Change exact/fuzzy match mode and rerun search when there is already an active query.
    const changeMatchMode = (nextMatchMode: SearchMatchMode) => {
        if (matchMode === nextMatchMode) {
            return;
        }

        if (!hasSearched) {
            setMatchMode(nextMatchMode);
            return;
        }

        void navigateToSearchState(resolveSearchState({
            keyword,
            searchMode: nextMatchMode,
            page: 1,
        }));
    };

    // Submit the current query when Enter is pressed in the search input.
    const handleEnter = (event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            void navigateToSearchState(resolveSearchState({
                keyword,
                page: 1,
            }));
        }
    };

    // Clear the search box and navigate to the empty-state search URL.
    const clearKeyword = () => {
        setKeyword("");
        void navigateToSearchState(resolveSearchState({
            keyword: "",
            page: 1,
        }));
    };

    // Launch an exact paper search seeded from a clicked paper title.
    const searchPaperByTitle = (paperTitle: string) => {
        setMode("paper");
        setMatchMode("exact");
        setKeyword(normalizeSearchKeywordForUrl(paperTitle));
        setPaperSortMode("default");
        void navigateToSearchState(resolveSearchState({
            keyword: paperTitle,
            sortMode: "default",
            page: 1,
            mode: "paper",
            searchMode: "exact",
            visibility: "all",
        }, DEFAULT_SEARCH_QUERY_STATE));
    };

    // Launch an exact mentor search seeded from a clicked mentor author name.
    const searchMentorByName = (mentorName: string) => {
        setMode("mentor");
        setMatchMode("exact");
        setKeyword(normalizeSearchKeywordForUrl(mentorName));
        void navigateToSearchState(resolveSearchState({
            keyword: mentorName,
            page: 1,
            mode: "mentor",
            searchMode: "exact",
            visibility: "all",
        }, DEFAULT_SEARCH_QUERY_STATE));
    };

    // Navigate to a mentor detail page while preserving enough state to restore this search entry on return.
    const navigateToMentorHomepage = useCallback(async (mentorId: number) => {
        // Save enough context to restore this exact search entry after visiting a mentor detail page.
        expandedProfileMentorIdsRef.current = new Set(expandedProfileMentorIds);
        expandedPaperMentorIdsRef.current = new Set(expandedPaperMentorIds);
        const sourceEntryKey = getHistoryEntryKey();
        persistCurrentViewState(sourceEntryKey, true);
        writePendingMentorSearchReturn({
            mentorId,
            sourceEntryKey,
            targetEntryKey: sourceEntryKey,
            sourcePath: "/search",
        });

        try {
            await router.push(`/mentors/${mentorId}`);
            const targetEntryKey = getHistoryEntryKey();
            writePendingMentorSearchReturn({
                mentorId,
                sourceEntryKey,
                targetEntryKey,
                sourcePath: "/search",
            });
        }
        catch {
            clearPendingMentorSearchReturn();
        }
    }, [
        expandedPaperMentorIds,
        expandedProfileMentorIds,
        persistCurrentViewState,
        router,
    ]);

    // Intercept normal left-clicks on mentor links so search-state restoration data can be recorded first.
    const handleMentorHomepageLinkClick = useCallback((
        event: MouseEvent<HTMLAnchorElement>,
        mentorId: number,
    ) => {
        if (isModifiedNavigationClick(event)) {
            return;
        }

        event.preventDefault();
        void navigateToMentorHomepage(mentorId);
    }, [navigateToMentorHomepage]);

    // Expand or collapse the mentor profile text for one search result card.
    const toggleMentorProfileExpand = (mentorId: number) => {
        setExpandedProfileMentorIds((prev) => {
            const next = new Set(prev);
            if (next.has(mentorId)) {
                next.delete(mentorId);
            }
            else {
                next.add(mentorId);
            }
            expandedProfileMentorIdsRef.current = next;
            // Persist immediately so navigation away from the page preserves the just-toggled expansion state.
            writeHistoryViewState(
                getHistoryEntryKey(),
                buildSearchHistoryViewState(
                    typeof window === "undefined" || !Number.isFinite(window.scrollY) ? 0 : window.scrollY,
                    next,
                    expandedPaperMentorIdsRef.current,
                ),
            );
            return next;
        });
    };

    // Expand or collapse the related-paper title list for one mentor card.
    const toggleMentorPaperExpand = (mentorId: number) => {
        setExpandedPaperMentorIds((prev) => {
            const next = new Set(prev);
            if (next.has(mentorId)) {
                next.delete(mentorId);
            }
            else {
                next.add(mentorId);
            }
            expandedPaperMentorIdsRef.current = next;
            // Persist paper-title expansion separately from profile expansion for accurate restoration.
            writeHistoryViewState(
                getHistoryEntryKey(),
                buildSearchHistoryViewState(
                    typeof window === "undefined" || !Number.isFinite(window.scrollY) ? 0 : window.scrollY,
                    expandedProfileMentorIdsRef.current,
                    next,
                ),
            );
            return next;
        });
    };

    // Create or update a mentor record from the admin editor embedded in the search page.
    const saveMentor = async () => {
        const chineseName = mentorDraft.Chinese_name.trim();
        const researchDirection = mentorDraft.research_direction.trim();

        if (chineseName === "" || researchDirection === "") {
            setAdminMessage("导师中文名和研究方向不能为空");
            return;
        }

        setAdminSaving(true);
        setAdminMessage("");

        try {
            const method = mentorEditingId === undefined ? "POST" : "PUT";
            const url = mentorEditingId === undefined
                ? "/api/dataset/mentors"
                : `/api/dataset/mentors/${mentorEditingId}`;

            await request(url, method, true, {
                Chinese_name: chineseName,
                English_name: mentorDraft.English_name.trim(),
                research_direction: researchDirection,
                email: mentorDraft.email.trim(),
                profile: mentorDraft.profile.trim(),
            });

            setAdminMessage(mentorEditingId === undefined ? "导师新增成功" : "导师修改成功");
            setMentorEditingId(undefined);
            setMentorDraft({
                Chinese_name: "",
                English_name: "",
                research_direction: "",
                email: "",
                profile: "",
            });

            if (mode === "mentor" && hasSearched) {
                await refreshCurrentSearch();
            }
        }
        catch (err) {
            setAdminMessage(formatAdminError(err));
        }
        finally {
            setAdminSaving(false);
        }
    };

    // Populate and open the delete-confirmation dialog for a mentor.
    const openDeleteMentorDialog = (mentor: SearchMentorResult) => {
        setMentorDeleteTarget({
            id: mentor.id,
            Chinese_name: mentor.Chinese_name,
            English_name: mentor.English_name,
            research_direction: mentor.research_direction,
            email: mentor.email,
        });
    };

    // Close the mentor delete dialog unless deletion is still running.
    const closeDeleteMentorDialog = () => {
        if (mentorDeleteSubmitting) {
            return;
        }

        setMentorDeleteTarget(undefined);
    };

    // Permanently delete the mentor currently selected in the confirmation dialog.
    const confirmDeleteMentor = async () => {
        if (mentorDeleteTarget === undefined) {
            return;
        }

        setAdminSaving(true);
        setMentorDeleteSubmitting(true);
        setAdminMessage("");

        try {
            await request(`/api/dataset/mentors/${mentorDeleteTarget.id}`, "DELETE", true);
            setAdminMessage("导师删除成功");
            setMentorDeleteTarget(undefined);
            await fetchMyPrivateMentors();

            if (mode === "mentor" && hasSearched) {
                await refreshCurrentSearch();
            }
        }
        catch (err) {
            setAdminMessage(formatAdminError(err));
        }
        finally {
            setAdminSaving(false);
            setMentorDeleteSubmitting(false);
        }
    };

    // Populate and open the delete-confirmation dialog for a paper.
    const openDeletePaperDialog = (paper: SearchPaperResult) => {
        setPaperDeleteTarget({
            id: paper.id,
            title: paper.title,
            publish_date: paper.publish_date,
            subjects: paper.subjects,
            mentorNames: Array.isArray(paper.mentorNames) ? paper.mentorNames : [],
        });
    };

    // Close the paper delete dialog unless deletion is still running.
    const closeDeletePaperDialog = () => {
        if (paperDeleteSubmitting) {
            return;
        }

        setPaperDeleteTarget(undefined);
    };

    // Permanently delete the paper currently selected in the confirmation dialog.
    const confirmDeletePaper = async () => {
        if (paperDeleteTarget === undefined) {
            return;
        }

        setAdminSaving(true);
        setPaperDeleteSubmitting(true);
        setAdminMessage("");

        try {
            await request(`/api/dataset/papers/${paperDeleteTarget.id}`, "DELETE", true);
            setAdminMessage("论文删除成功");
            setPaperDeleteTarget(undefined);

            if (mode === "paper" && hasSearched) {
                await refreshCurrentSearch();
            }
        }
        catch (err) {
            setAdminMessage(formatAdminError(err));
        }
        finally {
            setAdminSaving(false);
            setPaperDeleteSubmitting(false);
        }
    };

    // Create or update a paper record from the admin editor embedded in the search page.
    const savePaper = async () => {
        const title = paperDraft.title.trim();

        if (title === "") {
            setAdminMessage("论文标题不能为空");
            return;
        }

        setAdminSaving(true);
        setAdminMessage("");

        try {
            const method = paperEditingId === undefined ? "POST" : "PUT";
            const url = paperEditingId === undefined
                ? "/api/dataset/papers"
                : `/api/dataset/papers/${paperEditingId}`;

            await request(url, method, true, {
                title,
                abstract: paperDraft.abstract.trim(),
                publish_date: paperDraft.publish_date.trim(),
                author_names: paperDraft.author_names.trim(),
            });

            setAdminMessage(paperEditingId === undefined ? "论文新增成功" : "论文修改成功");
            setPaperEditingId(undefined);
            setPaperDraft({
                title: "",
                abstract: "",
                publish_date: "",
                author_names: "",
            });

            if (mode === "paper" && hasSearched) {
                await refreshCurrentSearch();
            }
        }
        catch (err) {
            setAdminMessage(formatAdminError(err));
        }
        finally {
            setAdminSaving(false);
        }
    };

    // Load a mentor result into the admin editor for in-place modification.
    const beginEditMentor = (mentor: SearchMentorResult) => {
        setMode("mentor");
        setMentorEditingId(mentor.id);
        setMentorDraft({
            Chinese_name: mentor.Chinese_name || "",
            English_name: mentor.English_name || "",
            research_direction: mentor.research_direction || "",
            email: mentor.email || "",
            profile: mentor.profile || "",
        });
        setAdminMessage("");
    };

    // Load a paper result into the admin editor for in-place modification.
    const beginEditPaper = (paper: SearchPaperResult) => {
        setMode("paper");
        setPaperEditingId(paper.id);
        setPaperDraft({
            title: paper.title || "",
            abstract: paper.abstract || "",
            publish_date: paper.publish_date || "",
            author_names: paper.author_names || "",
        });
        setAdminMessage("");
    };

    const renderSegmentedControl = <TValue extends string>(
        label: string,
        options: SegmentedOption<TValue>[],
        activeValue: TValue,
        onSelect: (value: TValue) => void,
    ) => {
        // All segmented controls share the same animated pill UI and only differ in option set / callback.
        const activeIndex = Math.max(0, options.findIndex((option) => option.value === activeValue));
        const groupFlex = options.length;
        const groupMinWidth = options.length === 2 ? 180 : 270;

        return (
            <div
                className="searchSegmentGroup"
                role="group"
                aria-label={label}
                style={{
                    minWidth: groupMinWidth,
                    flex: `${groupFlex} 0 0`,
                    flexShrink: 0,
                }}
            >
                <div
                    className="searchSegmentTrack"
                    style={{
                        position: "relative",
                        display: "grid",
                        gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))`,
                        alignItems: "stretch",
                        width: "100%",
                        height: 25,
                        border: "1px solid #d0d7de",
                        borderRadius: 10,
                        background: "rgba(246, 248, 250, 0.96)",
                        boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.72), 0 1px 2px rgba(15, 23, 42, 0.04)",
                        overflow: "hidden",
                    }}
                >
                    <span
                        className="searchSegmentThumb"
                        aria-hidden="true"
                        style={{
                            position: "absolute",
                            top: 1,
                            bottom: 1,
                            left: 1,
                            width: `calc((100% - 2px) / ${options.length})`,
                            borderRadius: 9,
                            background: "rgb(8, 109, 177)",
                            border: "1px solid rgb(8, 109, 177)",
                            boxShadow: "0 10px 24px rgba(15, 23, 42, 0.18)",
                            transform: `translateX(${activeIndex * 100}%)`,
                            transition: "transform 240ms cubic-bezier(0.22, 1, 0.36, 1)",
                            willChange: "transform",
                        }}
                    />
                    {options.map((option) => {
                        const isActive = option.value === activeValue;

                        return (
                            <button
                                key={option.value}
                                type="button"
                                className={`searchSegmentButton${isActive ? " searchSegmentButtonActive" : ""}`}
                                aria-pressed={isActive}
                                onClick={() => onSelect(option.value)}
                                style={{
                                    position: "relative",
                                    zIndex: 1,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    minWidth: 0,
                                    minHeight: 25,
                                    border: "none",
                                    borderRadius: 10,
                                    background: "transparent",
                                    boxShadow: "none",
                                    color: isActive ? "#ffffff" : "#59636e",
                                    fontSize: 14,
                                    fontWeight: isActive ? 700 : 600,
                                    padding: "0 14px",
                                    appearance: "none",
                                    WebkitAppearance: "none",
                                    transition: "color 180ms ease",
                                }}
                            >
                                <span className="searchSegmentButtonLabel">{option.label}</span>
                            </button>
                        );
                    })}
                </div>
            </div>
        );
    };

    // Render loading placeholders for mentor search results.
    const renderMentorSkeletonList = () => (
        <div className="searchSkeletonList" aria-label="导师搜索结果加载中" data-testid="search-mentor-skeleton">
            {createSearchSkeletonKeys(SEARCH_SKELETON_COUNT, "search-mentor-skeleton").map((key, idx) => {
                const blueprint = SEARCH_SKELETON_BLUEPRINTS[idx % SEARCH_SKELETON_BLUEPRINTS.length];

                return (
                    <article key={key} className="searchSkeletonCard searchSkeletonMentorCard" aria-hidden="true">
                        <div className="searchSkeletonHeaderRow">
                            <span
                                className="searchSkeletonBlock searchSkeletonTitle"
                                style={{ width: blueprint.title }}
                            />
                            <span
                                className="searchSkeletonBlock searchSkeletonButton"
                                style={{ width: blueprint.button }}
                            />
                        </div>
                        <div className="searchSkeletonMetaStack">
                            {blueprint.meta.map((width, metaIdx) => (
                                <div key={`${key}-meta-${metaIdx}`} className="searchSkeletonMetaRow">
                                    <span className="searchSkeletonBlock searchSkeletonIcon" />
                                    <span
                                        className="searchSkeletonBlock searchSkeletonLine"
                                        style={{ width }}
                                    />
                                </div>
                            ))}
                        </div>
                        <div className="searchSkeletonMetaRow searchSkeletonProfileRow">
                            <span className="searchSkeletonBlock searchSkeletonIcon" />
                            <div className="searchSkeletonParagraph">
                                {blueprint.profile.map((width, lineIdx) => (
                                    <span
                                        key={`${key}-profile-${lineIdx}`}
                                        className="searchSkeletonBlock searchSkeletonLine"
                                        style={{ width }}
                                    />
                                ))}
                            </div>
                        </div>
                        <div className="searchSkeletonPaperPreview">
                            <span className="searchSkeletonBlock searchSkeletonSectionLabel" />
                            {blueprint.papers.map((width, paperIdx) => (
                                <span
                                    key={`${key}-paper-${paperIdx}`}
                                    className="searchSkeletonBlock searchSkeletonPaperLine"
                                    style={{ width }}
                                />
                            ))}
                        </div>
                    </article>
                );
            })}
        </div>
    );

    // Render loading placeholders for paper search results.
    const renderPaperSkeletonList = () => (
        <div className="searchSkeletonList" aria-label="论文搜索结果加载中" data-testid="search-paper-skeleton">
            {createSearchSkeletonKeys(SEARCH_SKELETON_COUNT, "search-paper-skeleton").map((key, idx) => {
                const blueprint = SEARCH_SKELETON_BLUEPRINTS[idx % SEARCH_SKELETON_BLUEPRINTS.length];

                return (
                    <article key={key} className="searchSkeletonCard searchSkeletonPaperCard" aria-hidden="true">
                        <div className="searchSkeletonPaperHeader">
                            <span className="searchSkeletonBlock searchSkeletonDate" />
                            <span className="searchSkeletonBlock searchSkeletonLinkGroup" />
                            <div className="searchSkeletonTagRow">
                                {blueprint.tags.map((width, tagIdx) => (
                                    <span
                                        key={`${key}-tag-${tagIdx}`}
                                        className="searchSkeletonBlock searchSkeletonTag"
                                        style={{ width }}
                                    />
                                ))}
                            </div>
                        </div>
                        <span
                            className="searchSkeletonBlock searchSkeletonPaperTitle"
                            style={{ width: blueprint.title === "32%" ? "68%" : "78%" }}
                        />
                        <div className="searchSkeletonTimelineMetaRow">
                            <span className="searchSkeletonBlock searchSkeletonMetaLabel" />
                            <span
                                className="searchSkeletonBlock searchSkeletonLine"
                                style={{ width: blueprint.meta[0] }}
                            />
                        </div>
                        <div className="searchSkeletonTimelineMetaRow searchSkeletonAbstractRow">
                            <span className="searchSkeletonBlock searchSkeletonMetaLabel" />
                            <div className="searchSkeletonParagraph">
                                {blueprint.profile.map((width, lineIdx) => (
                                    <span
                                        key={`${key}-abstract-${lineIdx}`}
                                        className="searchSkeletonBlock searchSkeletonLine"
                                        style={{ width }}
                                    />
                                ))}
                            </div>
                        </div>
                    </article>
                );
            })}
        </div>
    );

    // Render the full loading state, including pagination chrome and result skeleton cards.
    const renderSearchSkeletonResults = () => (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                    padding: 12,
                    flexWrap: "wrap",
                }}
            >
                <Pagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    loading={loading}
                    centered
                    controlHeight={SEARCH_PAGINATION_CONTROL_HEIGHT}
                    jumpInputWidth={120}
                    activePageHighlightColor="rgb(8, 109, 177)"
                    onPageChange={(newPage) => {
                        void navigateToSearchState(resolveSearchState({ page: newPage }));
                    }}
                />
            </div>
            {mode === "mentor" ? renderMentorSkeletonList() : renderPaperSkeletonList()}
        </div>
    );

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%", maxWidth: 794, margin: "0 auto", boxSizing: "border-box" }}>
            {mentorDeleteTarget !== undefined && (
                <div
                    aria-label="删除导师确认弹窗遮罩"
                    role="presentation"
                    onClick={closeDeleteMentorDialog}
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 1100,
                        background: "rgba(15, 23, 42, 0.42)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 20,
                    }}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="delete-mentor-dialog-title"
                        onClick={(event) => event.stopPropagation()}
                        style={{
                            width: "min(100%, 480px)",
                            borderRadius: 20,
                            background: "#ffffff",
                            border: "1px solid #d0d7de",
                            boxShadow: "0 24px 64px rgba(15, 23, 42, 0.24)",
                            padding: 24,
                            display: "flex",
                            flexDirection: "column",
                            gap: 14,
                        }}
                    >
                        <h3 id="delete-mentor-dialog-title" style={{ margin: 0, color: "#1f2328" }}>
                            确认删除导师
                        </h3>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, color: "#1f2328" }}>
                            <p style={{ margin: 0 }}>
                                中文名：{mentorDeleteTarget.Chinese_name}
                            </p>
                            <p style={{ margin: 0 }}>
                                英文名：{mentorDeleteTarget.English_name?.trim() || "暂无英文名"}
                            </p>
                            <p style={{ margin: 0 }}>
                                研究方向：{mentorDeleteTarget.research_direction?.trim() || "暂无研究方向"}
                            </p>
                            <p style={{ margin: 0 }}>
                                邮箱：{mentorDeleteTarget.email?.trim() || "暂无邮箱"}
                            </p>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                            <button
                                type="button"
                                onClick={() => void confirmDeleteMentor()}
                                disabled={mentorDeleteSubmitting}
                                style={{
                                    position: "relative",
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    border: mentorDeleteSubmitting ? "none" : "1px solid #cf222e",
                                    background: mentorDeleteSubmitting ? "#cf222e" : "#ffffff",
                                    color: mentorDeleteSubmitting ? "#ffffff" : "#cf222e",
                                    fontWeight: 700,
                                    overflow: "hidden",
                                    transition: "background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease",
                                }}
                                onMouseEnter={(event) => {
                                    if (mentorDeleteSubmitting) {
                                        return;
                                    }

                                    event.currentTarget.style.background = "#cf222e";
                                    event.currentTarget.style.color = "#ffffff";
                                    event.currentTarget.style.border = "none";
                                }}
                                onMouseLeave={(event) => {
                                    if (mentorDeleteSubmitting) {
                                        return;
                                    }

                                    event.currentTarget.style.background = "#ffffff";
                                    event.currentTarget.style.color = "#cf222e";
                                    event.currentTarget.style.border = "1px solid #cf222e";
                                }}
                            >
                                <span>确认删除</span>
                                {mentorDeleteSubmitting && (
                                    <span
                                        aria-hidden="true"
                                        style={{
                                            position: "absolute",
                                            inset: 0,
                                            background: "rgba(255, 255, 255, 0.55)",
                                        }}
                                    />
                                )}
                            </button>
                            <button
                                type="button"
                                onClick={closeDeleteMentorDialog}
                                disabled={mentorDeleteSubmitting}
                                style={{
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    border: "1px solid rgb(209, 217, 224)",
                                    background: "rgb(246, 248, 250)",
                                    color: "rgb(37, 41, 46)",
                                    fontWeight: 600,
                                    boxShadow: "none",
                                }}
                            >
                                取消
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {paperDeleteTarget !== undefined && (
                <div
                    aria-label="删除论文确认弹窗遮罩"
                    role="presentation"
                    onClick={closeDeletePaperDialog}
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 1100,
                        background: "rgba(15, 23, 42, 0.42)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 20,
                    }}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="delete-paper-dialog-title"
                        onClick={(event) => event.stopPropagation()}
                        style={{
                            width: "min(100%, 480px)",
                            borderRadius: 20,
                            background: "#ffffff",
                            border: "1px solid #d0d7de",
                            boxShadow: "0 24px 64px rgba(15, 23, 42, 0.24)",
                            padding: 24,
                            display: "flex",
                            flexDirection: "column",
                            gap: 14,
                        }}
                    >
                        <h3 id="delete-paper-dialog-title" style={{ margin: 0, color: "#1f2328" }}>
                            确认删除论文
                        </h3>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, color: "#1f2328" }}>
                            <p style={{ margin: 0 }}>
                                标题：{paperDeleteTarget.title}
                            </p>
                            <p style={{ margin: 0 }}>
                                发表日期：{paperDeleteTarget.publish_date?.trim() || "未知"}
                            </p>
                            <p style={{ margin: 0 }}>
                                导师：{paperDeleteTarget.mentorNames.length > 0 ? paperDeleteTarget.mentorNames.join("、") : "未知导师"}
                            </p>
                            <p style={{ margin: 0 }}>
                                分类：{paperDeleteTarget.subjects?.trim() || "暂无分类"}
                            </p>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                            <button
                                type="button"
                                onClick={() => void confirmDeletePaper()}
                                disabled={paperDeleteSubmitting}
                                style={{
                                    position: "relative",
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    border: paperDeleteSubmitting ? "none" : "1px solid #cf222e",
                                    background: paperDeleteSubmitting ? "#cf222e" : "#ffffff",
                                    color: paperDeleteSubmitting ? "#ffffff" : "#cf222e",
                                    fontWeight: 700,
                                    overflow: "hidden",
                                    transition: "background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease",
                                }}
                                onMouseEnter={(event) => {
                                    if (paperDeleteSubmitting) {
                                        return;
                                    }

                                    event.currentTarget.style.background = "#cf222e";
                                    event.currentTarget.style.color = "#ffffff";
                                    event.currentTarget.style.border = "none";
                                }}
                                onMouseLeave={(event) => {
                                    if (paperDeleteSubmitting) {
                                        return;
                                    }

                                    event.currentTarget.style.background = "#ffffff";
                                    event.currentTarget.style.color = "#cf222e";
                                    event.currentTarget.style.border = "1px solid #cf222e";
                                }}
                            >
                                <span>确认删除</span>
                                {paperDeleteSubmitting && (
                                    <span
                                        aria-hidden="true"
                                        style={{
                                            position: "absolute",
                                            inset: 0,
                                            background: "rgba(255, 255, 255, 0.55)",
                                        }}
                                    />
                                )}
                            </button>
                            <button
                                type="button"
                                onClick={closeDeletePaperDialog}
                                disabled={paperDeleteSubmitting}
                                style={{
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    border: "1px solid rgb(209, 217, 224)",
                                    background: "rgb(246, 248, 250)",
                                    color: "rgb(37, 41, 46)",
                                    fontWeight: 600,
                                    boxShadow: "none",
                                }}
                            >
                                取消
                            </button>
                        </div>
                    </div>
                </div>
            )}
            <h2
                title={searchHeadingText}
                style={isEmptySearch ? undefined : {
                    maxWidth: 654,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                }}
            >
                {searchHeadingText}
            </h2>

            <div style={{ position: "relative", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <div
                    style={{ position: "relative", flexShrink: 0 }}
                    onMouseEnter={() => setShowSearchLogicHelp(true)}
                    onMouseLeave={() => setShowSearchLogicHelp(false)}
                    onFocus={() => setShowSearchLogicHelp(true)}
                    onBlur={() => setShowSearchLogicHelp(false)}
                >
                    <span
                        aria-label="搜索逻辑说明"
                        tabIndex={0}
                        style={{
                            width: 20,
                            height: 20,
                            borderRadius: "50%",
                            border: "1px solid #8c959f",
                            color: "#57606a",
                            background: "#ffffff",
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 15,
                            fontWeight: 700,
                            lineHeight: 1,
                            flexShrink: 0,
                            cursor: "help",
                            userSelect: "none",
                            outline: "none",
                        }}
                    >
                        ?
                    </span>
                    {showSearchLogicHelp && (
                        <div
                            aria-hidden="true"
                            style={{
                                position: "absolute",
                                left: -20,
                                top: "100%",
                                width: "clamp(280px, 58vw, 380px)",
                                height: 12,
                                background: "transparent",
                                pointerEvents: "auto",
                                zIndex: 19,
                            }}
                        />
                    )}
                    <div
                        role="tooltip"
                        aria-hidden={!showSearchLogicHelp}
                        onMouseEnter={() => setShowSearchLogicHelp(true)}
                        onMouseLeave={() => setShowSearchLogicHelp(false)}
                        style={{
                            position: "absolute",
                            left: -20,
                            top: "calc(100% + 12px)",
                            width: "clamp(280px, 58vw, 380px)",
                            maxWidth: "calc(100vw - 24px)",
                            padding: 14,
                            borderRadius: 14,
                            border: "1px solid #d0d7de",
                            background: "#ffffff",
                            color: "#24292f",
                            boxShadow: "0 18px 42px rgba(15, 23, 42, 0.18)",
                            fontSize: 13,
                            lineHeight: 1.55,
                            zIndex: 20,
                            pointerEvents: showSearchLogicHelp ? "auto" : "none",
                            opacity: showSearchLogicHelp ? 1 : 0,
                            transform: showSearchLogicHelp ? "translateY(0)" : "translateY(4px)",
                            transition: "opacity 160ms ease, transform 160ms ease",
                            whiteSpace: "normal",
                        }}
                    >
                        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span style={{ fontSize: 13, fontWeight: 700, color: "#1f2328" }}>搜索语法提示</span>
                                <span style={{ fontSize: 12, color: "#57606a" }}>支持逻辑运算和括号组合，适合做更精确的检索。</span>
                            </div>

                            <div style={{ display: "grid", gap: 8 }}>
                                <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                    <span style={{ minWidth: 54, fontWeight: 700, color: "#0969da" }}>AND</span>
                                    <span style={{ color: "#24292f" }}>使用 <strong>&amp;&amp;</strong>、<strong>&amp;</strong> 或 <strong>且</strong>，表示“同时满足”。</span>
                                </div>
                                <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                    <span style={{ minWidth: 54, fontWeight: 700, color: "#0969da" }}>OR</span>
                                    <span style={{ color: "#24292f" }}>使用 <strong>||</strong>、<strong>|</strong> 或 <strong>或</strong>，表示“满足其一”。</span>
                                </div>
                                <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                    <span style={{ minWidth: 54, fontWeight: 700, color: "#0969da" }}>括号</span>
                                    <span style={{ color: "#24292f" }}>例如 <strong>(A || B) &amp;&amp; C</strong>，可调整优先级。</span>
                                </div>
                            </div>

                            <div style={{ padding: "10px 12px", borderRadius: 12, background: "#f6f8fa", border: "1px solid #d0d7de" }}>
                                <div style={{ fontSize: 12, fontWeight: 700, color: "#1f2328", marginBottom: 8 }}>注意</div>
                                <div style={{ display: "grid", gap: 8, color: "#57606a", fontSize: 12, lineHeight: 1.5 }}>
                                    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                        <span style={{ color: "#0969da", fontWeight: 700, minWidth: 14 }}>1.</span>
                                        <span>AND 的优先级高于 OR</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                        <span style={{ color: "#0969da", fontWeight: 700, minWidth: 14 }}>2.</span>
                                        <span>若括号不匹配，系统会将括号视作关键词的一部分处理</span>
                                    </div>
                                </div>
                                {/* <div style={{ marginTop: 8, color: "#57606a", fontSize: 12 }}>
                                    {SEARCH_LOGIC_HELP_TEXT}
                                </div> */}
                            </div>
                        </div>
                        <span
                            aria-hidden="true"
                            style={{
                                position: "absolute",
                                left: 23,
                                top: -6,
                                width: 12,
                                height: 12,
                                background: "#ffffff",
                                borderLeft: "1px solid #d0d7de",
                                borderTop: "1px solid #d0d7de",
                                transform: "rotate(45deg)",
                                boxShadow: "-3px -3px 8px rgba(15, 23, 42, 0.04)",
                            }}
                        />
                    </div>
                </div>
                <input
                    type="text"
                    value={keyword}
                    maxLength={INPUT_LIMITS.KEYWORD}
                    placeholder={mode === "mentor" ? "输入导师姓名或研究方向" : (matchMode === "fuzzy" ? "输入论文题目、导师姓名或导师研究方向" : "输入论文题目、论文分类、导师姓名或导师研究方向")}
                    onChange={(e) => setKeyword(normalizeSearchKeywordForUrl(e.target.value))}
                    onKeyDown={handleEnter}
                    style={{ flex: "1 1 260px", minWidth: 0 }}
                />
                <button
                    onClick={clearKeyword}
                    disabled={keyword.trim() === "" || loading}
                    style={SEARCH_ACTION_BUTTON_STYLE}
                >
                    清空
                </button>
                <button
                    onClick={() => {
                        void navigateToSearchState(resolveSearchState({
                            keyword,
                            page: 1,
                        }));
                    }}
                    disabled={keyword.trim() === "" || loading}
                    style={SEARCH_ACTION_BUTTON_STYLE}
                >
                    搜索
                </button>
            </div>

            <div className="searchSegmentRow" aria-label="搜索选项分段控件" style={{ flexWrap: "wrap" }}>
                {renderSegmentedControl("搜索类型", SEARCH_MODE_OPTIONS, mode, switchMode)}
                {renderSegmentedControl("匹配方式", MATCH_MODE_OPTIONS, matchMode, changeMatchMode)}
                {renderSegmentedControl(
                    mode === "paper" ? "论文排序" : "导师筛选",
                    thirdSegmentOptions,
                    thirdSegmentValue,
                    (value) => {
                        if (mode === "paper") {
                            changePaperSortMode(value as SearchPaperSortMode);
                            return;
                        }

                        const nextVisibility = value as MentorResultFilter;
                        if (!hasSearched) {
                            setMentorResultFilter(nextVisibility);
                            return;
                        }

                        void navigateToSearchState(resolveSearchState({
                            keyword,
                            visibility: nextVisibility,
                            page: 1,
                        }));
                    },
                )}
            </div>

            {isAdmin && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, border: "1px solid #ccc", borderRadius: 6, padding: 12 }}>
                    <h3 style={{ margin: 0 }}>管理员操作</h3>
                    <p style={{ margin: 0 }}>
                        当前模式：{mode === "mentor" ? "导师" : "论文"}，可执行新增、修改、删除。
                    </p>

                    {mode === "mentor" ? (
                        <>
                            <input
                                type="text"
                                placeholder="导师中文名"
                                maxLength={INPUT_LIMITS.NAME}
                                value={mentorDraft.Chinese_name}
                                onChange={(e) => setMentorDraft((prev) => ({ ...prev, Chinese_name: e.target.value }))}
                            />
                            <input
                                type="text"
                                placeholder="导师英文名（可选）"
                                maxLength={INPUT_LIMITS.NAME}
                                value={mentorDraft.English_name}
                                onChange={(e) => setMentorDraft((prev) => ({ ...prev, English_name: e.target.value }))}
                            />
                            <input
                                type="text"
                                placeholder="研究方向"
                                maxLength={INPUT_LIMITS.RESEARCH_DIRECTION}
                                value={mentorDraft.research_direction}
                                onChange={(e) => setMentorDraft((prev) => ({ ...prev, research_direction: e.target.value }))}
                            />
                            <input
                                type="text"
                                placeholder="邮箱（可选）"
                                maxLength={INPUT_LIMITS.EMAIL}
                                value={mentorDraft.email}
                                onChange={(e) => setMentorDraft((prev) => ({ ...prev, email: e.target.value }))}
                            />
                            <input
                                type="text"
                                placeholder="导师画像（可选）"
                                maxLength={INPUT_LIMITS.MENTOR_PROFILE}
                                value={mentorDraft.profile}
                                onChange={(e) => setMentorDraft((prev) => ({ ...prev, profile: e.target.value }))}
                            />
                            <div style={{ display: "flex", gap: 8 }}>
                                <button onClick={() => void saveMentor()} disabled={adminSaving}>
                                    {mentorEditingId === undefined ? "新增导师" : "保存导师修改"}
                                </button>
                                {mentorEditingId !== undefined && (
                                    <button
                                        onClick={() => {
                                            setMentorEditingId(undefined);
                                            setMentorDraft({
                                                Chinese_name: "",
                                                English_name: "",
                                                research_direction: "",
                                                email: "",
                                                profile: "",
                                            });
                                        }}
                                        disabled={adminSaving}
                                    >
                                        取消编辑
                                    </button>
                                )}
                            </div>
                        </>
                    ) : (
                        <>
                            <input
                                type="text"
                                placeholder="论文标题"
                                maxLength={INPUT_LIMITS.PAPER_TITLE}
                                value={paperDraft.title}
                                onChange={(e) => setPaperDraft((prev) => ({ ...prev, title: e.target.value }))}
                            />
                            <input
                                type="date"
                                value={paperDraft.publish_date}
                                onChange={(e) => setPaperDraft((prev) => ({ ...prev, publish_date: e.target.value }))}
                            />
                            <input
                                type="text"
                                placeholder="作者名单（逗号分隔）"
                                maxLength={INPUT_LIMITS.AUTHOR_NAMES}
                                value={paperDraft.author_names}
                                onChange={(e) => setPaperDraft((prev) => ({ ...prev, author_names: e.target.value }))}
                            />
                            <textarea
                                placeholder="摘要（可选）"
                                maxLength={INPUT_LIMITS.PAPER_ABSTRACT}
                                value={paperDraft.abstract}
                                onChange={(e) => setPaperDraft((prev) => ({ ...prev, abstract: e.target.value }))}
                                style={{ minHeight: 80 }}
                            />
                            <div style={{ display: "flex", gap: 8 }}>
                                <button onClick={() => void savePaper()} disabled={adminSaving}>
                                    {paperEditingId === undefined ? "新增论文" : "保存论文修改"}
                                </button>
                                {paperEditingId !== undefined && (
                                    <button
                                        onClick={() => {
                                            setPaperEditingId(undefined);
                                            setPaperDraft({
                                                title: "",
                                                abstract: "",
                                                publish_date: "",
                                                author_names: "",
                                            });
                                        }}
                                        disabled={adminSaving}
                                    >
                                        取消编辑
                                    </button>
                                )}
                            </div>
                        </>
                    )}

                    {adminMessage !== "" && (
                        <p style={{ margin: 0 }}>{adminMessage}</p>
                    )}
                </div>
            )}

            {errorMessage !== "" && (
                <div style={{ padding: 12, border: "1px solid #f1aeb5", backgroundColor: "#f8d7da" }}>
                    {errorMessage}
                </div>
            )}

            {mode === "mentor" && mentorResultFilter === "mine" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, border: "1px solid #ccc", borderRadius: 6, padding: 12 }}>
                    {!isLoggedIn ? (
                        <span>仅登录用户才能添加私有导师</span>
                    ) : (
                        <>
                            <div style={{ display: "flex", gap: 8 }}>
                                <input
                                    type="text"
                                    placeholder="导师中文名（可选）"
                                    maxLength={INPUT_LIMITS.NAME}
                                    value={customMentorChineseName}
                                    onChange={(e) => setCustomMentorChineseName(e.target.value)}
                                    disabled={privateMentorSaving}
                                    style={{ flex: 1 }}
                                />
                                <input
                                    type="text"
                                    placeholder="导师英文名（可选）"
                                    maxLength={INPUT_LIMITS.NAME}
                                    value={customMentorEnglishName}
                                    onChange={(e) => setCustomMentorEnglishName(e.target.value)}
                                    disabled={privateMentorSaving}
                                    style={{ flex: 1 }}
                                />
                            </div>
                            <input
                                type="text"
                                placeholder="研究方向（可选）"
                                maxLength={INPUT_LIMITS.RESEARCH_DIRECTION}
                                value={customMentorResearchDirection}
                                onChange={(e) => setCustomMentorResearchDirection(e.target.value)}
                                disabled={privateMentorSaving}
                            />
                            <input
                                type="email"
                                placeholder="导师邮箱（可选）"
                                maxLength={INPUT_LIMITS.EMAIL}
                                value={customMentorEmail}
                                onChange={(e) => setCustomMentorEmail(e.target.value)}
                                disabled={privateMentorSaving}
                            />
                            <textarea
                                placeholder="导师画像（可选）"
                                maxLength={INPUT_LIMITS.MENTOR_PROFILE}
                                value={customMentorProfile}
                                onChange={(e) => setCustomMentorProfile(e.target.value)}
                                disabled={privateMentorSaving}
                                rows={3}
                                style={{ resize: "vertical", fontFamily: "inherit", fontSize: "inherit" }}
                            />
                            <div style={{ display: "flex", gap: 8 }}>
                                <button
                                    onClick={() => void addPrivateMentorInSearch()}
                                    disabled={
                                        privateMentorSaving ||
                                        privateMentors.length >= 10 ||
                                        (customMentorChineseName.trim() === "" && customMentorEnglishName.trim() === "")
                                    }
                                >
                                    {privateMentorSaving ? "添加中..." : "添加私有导师"}
                                </button>
                            </div>
                            {privateMentors.length >= 10 && (
                                <p style={{ margin: 0, color: "#cf222e", fontSize: 13 }}>私有导师数量已达上限（10位），请先删除部分私有导师后再添加。</p>
                            )}
                            {privateMentorMsg !== "" && (
                                <p
                                    style={{
                                        margin: 0,
                                        fontSize: 13,
                                        color: privateMentorMsg === "私有导师添加成功" ? undefined : "#cf222e",
                                    }}
                                >
                                    {privateMentorMsg}
                                </p>
                            )}
                        </>
                    )}
                </div>
            )}

            {showSearchSkeleton && renderSearchSkeletonResults()}

            {!showSearchSkeleton && mode === "mentor" && mentors.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 8,
                            padding: 12,
                            flexWrap: "wrap",
                        }}
                    >
                        <Pagination
                            currentPage={currentPage}
                            totalPages={totalPages}
                            loading={loading}
                            centered
                            controlHeight={SEARCH_PAGINATION_CONTROL_HEIGHT}
                            jumpInputWidth={120}
                            activePageHighlightColor="rgb(8, 109, 177)"
                            onPageChange={(newPage) => {
                                void navigateToSearchState(resolveSearchState({ page: newPage }));
                            }}
                        />
                    </div>

                    {mentors.length === 0 && (
                        <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                            当前筛选条件下没有导师结果。
                        </div>
                    )}

                    {mentors.map((mentor) => {
                        const isProfileExpanded = expandedProfileMentorIds.has(mentor.id);
                        const isPaperExpanded = expandedPaperMentorIds.has(mentor.id);
                        const profileText = mentor.profile || "暂无导师画像";
                        const profilePreview = profileText.length > PROFILE_PREVIEW_LENGTH
                            ? `${profileText.slice(0, PROFILE_PREVIEW_LENGTH)}...`
                            : profileText;
                        const visiblePaperTitles = isPaperExpanded
                            ? mentor.paperTitles
                            : mentor.paperTitles.slice(0, PAPER_TITLES_PREVIEW_COUNT);
                        const hasProfileMore = profileText.length > PROFILE_PREVIEW_LENGTH;
                        const hasPaperMore = mentor.paperTitles.length > PAPER_TITLES_PREVIEW_COUNT;

                        const isFollowed = followedMentorIds.has(mentor.id);

                        return (
                        <div
                            key={mentor.id}
                            style={{ position: "relative", padding: 12, border: "1px solid #ccc", borderRadius: 6 }}
                        >
                            {/* Students can follow mentors; owners of private mentors can also delete them inline. */}
                            {(canFollowMentor || (isLoggedIn && privateMentorIdSet.has(mentor.id))) && (
                                <div
                                    style={{
                                        position: "absolute",
                                        top: 8,
                                        right: 8,
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 8,
                                        zIndex: 1,
                                    }}
                                >
                                    {canFollowMentor && (
                                        <FollowToggleButton
                                            className="searchMentorFollowButton"
                                            followed={isFollowed}
                                            followedLabel="已关注"
                                            loading={followToggleMentorId === mentor.id}
                                            onClick={() => void toggleMentorFollow(mentor.id)}
                                            style={buildSearchMentorFollowButtonStyle(isFollowed)}
                                        />
                                    )}
                                    {isLoggedIn && privateMentorIdSet.has(mentor.id) && (
                                        <button
                                            onClick={() => openDeleteMentorDialog(mentor)}
                                            disabled={adminSaving}
                                            style={{
                                                border: "1px solid #cf222e",
                                                borderRadius: 8,
                                                background: "#ffffff",
                                                color: "#cf222e",
                                                fontWeight: 600,
                                                padding: "4px 12px",
                                            }}
                                        >
                                            删除
                                        </button>
                                    )}
                                </div>
                            )}
                            <h3 style={{ margin: "0 0 8px", fontSize: "20px" }}>
                                <Link
                                    href={`/mentors/${mentor.id}`}
                                    className="searchMentorNameLink"
                                    onClick={(event) => handleMentorHomepageLinkClick(event, mentor.id)}
                                >
                                    {mentor.Chinese_name}
                                </Link>
                                {privateMentorIdSet.has(mentor.id) && (
                                    <span aria-hidden="true" style={{ marginLeft: 8, fontSize: 12, color: "#555" }}>我的私有导师</span>
                                )}
                            </h3>
                            {mentor.English_name && (
                                <p className="searchMentorMetaRow">
                                    <img
                                        src="/English_Name.ico"
                                        alt=""
                                        aria-hidden="true"
                                        className="searchMentorMetaIcon"
                                    />
                                    <span className="searchMentorMetaSrOnly">英文名</span>
                                    <span className="searchMentorMetaText">{mentor.English_name}</span>
                                </p>
                            )}
                            <p className="searchMentorMetaRow">
                                <img
                                    src="/Reseach_Direction.ico"
                                    alt=""
                                    aria-hidden="true"
                                    className="searchMentorMetaIcon"
                                />
                                <span className="searchMentorMetaSrOnly">研究方向</span>
                                <span className="searchMentorMetaText">{mentor.research_direction || "暂无研究方向"}</span>
                            </p>
                            <p className="searchMentorMetaRow">
                                <img
                                    src="/Email.ico"
                                    alt=""
                                    aria-hidden="true"
                                    className="searchMentorMetaIcon"
                                />
                                <span className="searchMentorMetaSrOnly">邮箱</span>
                                <span className="searchMentorMetaText">{mentor.email || "暂无邮箱"}</span>
                            </p>
                            <p className="searchMentorMetaRow">
                                <img
                                    src="/Mentor_Profile.ico"
                                    alt=""
                                    aria-hidden="true"
                                    className="searchMentorMetaIcon"
                                />
                                <span className="searchMentorMetaSrOnly">导师画像</span>
                                {isProfileExpanded ? (
                                    <span className="searchMentorMetaText searchMentorMetaTextExpanded">
                                        <span className="searchMentorProfileFullText">{profileText}</span>
                                        {hasProfileMore && (
                                            <button
                                                type="button"
                                                onClick={() => toggleMentorProfileExpand(mentor.id)}
                                                className="searchMentorInlineLinkButton searchMentorInlineLinkButtonBlock"
                                                data-testid={`mentor-profile-toggle-${mentor.id}`}
                                            >
                                                收起
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            onClick={() => void navigateToMentorHomepage(mentor.id)}
                                            className="searchMentorInlineLinkButton searchMentorInlineLinkButtonSpaced"
                                            data-testid={`mentor-homepage-button-${mentor.id}`}
                                        >
                                            前往主页
                                        </button>
                                    </span>
                                ) : (
                                    <span className="searchMentorMetaText">
                                        {profilePreview}
                                        {hasProfileMore && (
                                            <>
                                                {" "}
                                                <button
                                                    type="button"
                                                    onClick={() => toggleMentorProfileExpand(mentor.id)}
                                                    className="searchMentorInlineLinkButton"
                                                    data-testid={`mentor-profile-toggle-${mentor.id}`}
                                                >
                                                    展开
                                                </button>
                                            </>
                                        )}
                                        {" "}
                                        <button
                                            type="button"
                                            onClick={() => void navigateToMentorHomepage(mentor.id)}
                                            className={`searchMentorInlineLinkButton${hasProfileMore ? " searchMentorInlineLinkButtonSpaced" : ""}`}
                                            data-testid={`mentor-homepage-button-${mentor.id}`}
                                        >
                                            前往主页
                                        </button>
                                    </span>
                                )}
                            </p>
                            <p style={{ margin: "8px 0 4px", fontSize: "14px" }}>相关论文：</p>
                            <ul style={{ margin: 0, paddingLeft: 0, fontSize: "14px", listStyle: "none" }}>
                                {visiblePaperTitles.map((title) => (
                                    <li key={title}>
                                        <button
                                            type="button"
                                            onClick={() => searchPaperByTitle(title)}
                                            className="searchMentorPaperLinkButton"
                                        >
                                            <img
                                                src="/arxiv.ico"
                                                alt=""
                                                aria-hidden="true"
                                                className="searchMentorPaperLinkIcon"
                                            />
                                            <span className="searchMentorPaperLinkText">
                                                <LatexText text={title} forceInlineMath />
                                            </span>
                                        </button>
                                    </li>
                                ))}
                                {hasPaperMore && (
                                    <li className="searchMentorPaperFooter">
                                        <button
                                            type="button"
                                            onClick={() => toggleMentorPaperExpand(mentor.id)}
                                            className="searchMentorInlineLinkButton searchMentorInlineLinkButtonPaperFooter"
                                            data-testid={`mentor-paper-toggle-${mentor.id}`}
                                        >
                                            {isPaperExpanded ? "收起" : "展开"}
                                        </button>
                                    </li>
                                )}
                            </ul>
                            {isAdmin && (
                                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                                    <button onClick={() => beginEditMentor(mentor)} disabled={adminSaving}>修改导师</button>
                                    <button onClick={() => openDeleteMentorDialog(mentor)} disabled={adminSaving}>删除导师</button>
                                </div>
                            )}
                        </div>
                        );
                    })}

                    <Pagination
                        currentPage={currentPage}
                        totalPages={totalPages}
                        loading={loading}
                        centered
                        controlHeight={SEARCH_PAGINATION_CONTROL_HEIGHT}
                        jumpInputWidth={120}
                        activePageHighlightColor="rgb(8, 109, 177)"
                        onPageChange={(newPage) => {
                            void navigateToSearchState(resolveSearchState({ page: newPage }));
                        }}
                    />
                </div>
            )}

            {!showSearchSkeleton && mode === "paper" && papers.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 8,
                            padding: 12,
                            flexWrap: "wrap",
                        }}
                    >
                        <Pagination
                            currentPage={currentPage}
                            totalPages={totalPages}
                            loading={loading}
                            centered
                            controlHeight={SEARCH_PAGINATION_CONTROL_HEIGHT}
                            jumpInputWidth={120}
                            activePageHighlightColor="rgb(8, 109, 177)"
                            onPageChange={(newPage) => {
                                void navigateToSearchState(resolveSearchState({ page: newPage }));
                            }}
                        />
                    </div>

                    {papers.map((paper) => {
                        const subjectTags = parseTimelineLikeSubjects(paper.subjects);

                        return (
                            <article
                                key={paper.id}
                                style={{
                                    position: "relative",
                                    padding: 16,
                                    border: "1px solid #ccc",
                                    borderRadius: 8,
                                    backgroundColor: "#fff",
                                }}
                            >
                                <div className="searchTimelinePaperHeaderRow">
                                    <div className="searchTimelinePaperDate">
                                        {paper.publish_date || "未知日期"}
                                    </div>
                                    {paper.arxiv_url && (
                                        <div className="searchTimelinePaperLinks" aria-label="论文外部链接">
                                            <span>[</span>
                                            <a href={paper.arxiv_url} target="_blank" rel="noreferrer">
                                                arxiv
                                            </a>
                                            <span>, </span>
                                            <a href={buildTimelineLikePdfUrl(paper.arxiv_url)} target="_blank" rel="noreferrer">
                                                pdf
                                            </a>
                                            <span>]</span>
                                        </div>
                                    )}
                                    {subjectTags.length > 0 && (
                                        <div className="searchTimelineSubjectTags" aria-label="论文学科分类">
                                            {subjectTags.map((subject) => (
                                                <span key={subject} className="searchTimelineSubjectTag">
                                                    {subject}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                <h3 style={{ margin: "0 0 8px", fontSize: "17.5px" }}>
                                    <LatexText text={paper.title} forceInlineMath />
                                </h3>
                                <div className="timelineMetaRow">
                                    <span className="timelineMetaLabel">作者：</span>
                                    <div className="timelineMetaContent">
                                        {(() => {
                                            const names = (paper.author_names || "").split(/[,，、]/).map((s) => s.trim()).filter(Boolean);
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
                                                        <span key={`${name}-${idx}`}>
                                                            <button
                                                                type="button"
                                                                onClick={() => searchMentorByName(name)}
                                                                className="searchTimelineMentorButton"
                                                            >
                                                                <img
                                                                    src="/favicon_tsinghua.ico"
                                                                    alt="清华导师"
                                                                    className="searchTimelineMentorIcon"
                                                                />
                                                                {name}
                                                            </button>
                                                            {separator}
                                                        </span>
                                                    );
                                                }

                                                return (
                                                    <span key={`${name}-${idx}`}>
                                                        {name}
                                                        {separator}
                                                    </span>
                                                );
                                            });
                                        })()}
                                    </div>
                                </div>
                                <div className="timelineMetaRow">
                                    <span className="timelineMetaLabel">摘要：</span>
                                    <div className="timelineMetaContent timelineAbstractContent searchPaperAbstractContent">
                                        <LatexText text={paper.abstract || "暂无摘要"} />
                                    </div>
                                </div>
                                {isAdmin && (
                                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                                        <button onClick={() => beginEditPaper(paper)} disabled={adminSaving}>修改论文</button>
                                        <button onClick={() => openDeletePaperDialog(paper)} disabled={adminSaving}>删除论文</button>
                                    </div>
                                )}
                            </article>
                        );
                    })}

                    <Pagination
                        currentPage={currentPage}
                        totalPages={totalPages}
                        loading={loading}
                        centered
                        controlHeight={SEARCH_PAGINATION_CONTROL_HEIGHT}
                        jumpInputWidth={120}
                        activePageHighlightColor="rgb(8, 109, 177)"
                        onPageChange={(newPage) => {
                            void navigateToSearchState(resolveSearchState({ page: newPage }));
                        }}
                    />
                </div>
            )}

            {hasSearched && !loading && !showSearchSkeleton && errorMessage === "" && mode === "mentor" && mentors.length === 0 && (
                <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                    未找到匹配的导师结果（当前为{matchMode === "exact" ? "精确" : "模糊"}搜索）。
                </div>
            )}

            {hasSearched && !loading && !showSearchSkeleton && errorMessage === "" && mode === "paper" && papers.length === 0 && (
                <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                    未找到匹配的论文结果（当前为{matchMode === "exact" ? "精确" : "模糊"}搜索）。
                </div>
            )}

            <style jsx>{`
                .searchSegmentRow {
                    display: flex;
                    gap: 12px;
                    width: 100%;
                    overflow-x: auto;
                    padding: 4px 2px 8px;
                    scrollbar-width: thin;
                    -webkit-overflow-scrolling: touch;
                }

                .searchSegmentGroup {
                    min-width: 0;
                }

                .searchSegmentButton {
                    transform: none;
                }

                .searchSegmentButton:focus-visible {
                    outline: 2px solid rgba(47, 129, 247, 0.35);
                    outline-offset: -2px;
                }

                .searchSegmentButtonLabel {
                    display: block;
                    width: 100%;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }

                :global(a.searchMentorNameLink) {
                    color: #000000;
                    text-decoration: none;
                    transition: color 0.16s ease;
                }

                :global(a.searchMentorNameLink:hover),
                :global(a.searchMentorNameLink:focus-visible) {
                    color: rgb(8, 109, 177);
                    text-decoration: none;
                    outline: none;
                }

                .searchMentorMetaRow {
                    display: flex;
                    align-items: flex-start;
                    gap: 6px;
                    margin: 4px 0;
                    font-size: 14px;
                }

                .searchMentorMetaIcon {
                    width: 16px;
                    height: 16px;
                    object-fit: contain;
                    display: block;
                    flex: 0 0 auto;
                    margin-top: 1px;
                }

                .searchMentorMetaText {
                    min-width: 0;
                    white-space: normal;
                    word-break: break-word;
                }

                .searchMentorMetaTextExpanded {
                    display: inline;
                }

                .searchMentorProfileFullText {
                    display: block;
                }

                .searchMentorInlineLinkButton {
                    display: inline;
                    margin: 0;
                    padding: 0;
                    border: 0;
                    background: transparent;
                    appearance: none;
                    -webkit-appearance: none;
                    color: rgb(8, 109, 177);
                    font: inherit;
                    text-decoration: none;
                    cursor: pointer;
                }

                .searchMentorInlineLinkButton:hover,
                .searchMentorInlineLinkButton:focus-visible {
                    color: rgb(8, 109, 177);
                    text-decoration: none;
                    outline: none;
                }

                .searchMentorInlineLinkButtonBlock {
                    display: inline-block;
                    margin-top: 0;
                }

                .searchMentorInlineLinkButtonSpaced {
                    margin-left: 8px;
                }

                .searchMentorInlineLinkButtonPaperFooter {
                    display: inline-block;
                    margin-top: 6px;
                    margin-left: 0;
                }

                :global(button.searchMentorFollowButton:hover:not(:disabled)),
                :global(button.searchMentorFollowButton:focus-visible) {
                    transform: none;
                    box-shadow: none;
                }

                :global(button.searchMentorFollowButton:focus-visible) {
                    outline: 2px solid rgba(8, 109, 177, 0.35);
                    outline-offset: 2px;
                }

                :global(button.searchMentorFollowButton:disabled) {
                    opacity: 1;
                    cursor: not-allowed;
                }

                :global(.searchSkeletonList) {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    width: 100%;
                }

                :global(.searchSkeletonCard) {
                    box-sizing: border-box;
                    position: relative;
                    overflow: hidden;
                    width: 100%;
                    padding: 16px;
                    border: 1px solid #ccc;
                    border-radius: 8px;
                    background: #ffffff;
                }

                :global(.searchSkeletonMentorCard) {
                    padding: 14px 12px 16px;
                }

                :global(.searchSkeletonPaperCard) {
                    padding: 16px;
                }

                :global(.searchSkeletonBlock) {
                    display: block;
                    position: relative;
                    overflow: hidden;
                    background: linear-gradient(90deg, #e3e9f0 0%, #edf2f7 40%, #ffffff 50%, #edf2f7 60%, #e3e9f0 100%);
                    background-size: 200% 100%;
                    animation: searchSkeletonShimmer 1.15s ease-in-out infinite;
                }

                :global(.searchSkeletonHeaderRow) {
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    gap: 16px;
                    margin-bottom: 14px;
                    padding-right: 2px;
                }

                :global(.searchSkeletonTitle) {
                    height: 24px;
                    border-radius: 999px;
                    flex: 0 1 auto;
                    max-width: calc(100% - 92px);
                }

                :global(.searchSkeletonButton) {
                    height: 28px;
                    border-radius: 6px;
                    flex: 0 0 auto;
                }

                :global(.searchSkeletonMetaStack) {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                }

                :global(.searchSkeletonMetaRow),
                :global(.searchSkeletonTimelineMetaRow) {
                    display: flex;
                    align-items: flex-start;
                    gap: 8px;
                    min-width: 0;
                }

                :global(.searchSkeletonIcon) {
                    width: 16px;
                    height: 16px;
                    border-radius: 4px;
                    flex: 0 0 auto;
                    margin-top: 1px;
                }

                :global(.searchSkeletonLine) {
                    height: 12px;
                    border-radius: 999px;
                    max-width: 100%;
                }

                :global(.searchSkeletonProfileRow) {
                    margin-top: 8px;
                }

                :global(.searchSkeletonParagraph) {
                    display: flex;
                    flex: 1;
                    min-width: 0;
                    flex-direction: column;
                    gap: 10px;
                    padding-top: 2px;
                }

                :global(.searchSkeletonPaperPreview) {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    margin-top: 14px;
                    padding-left: 0;
                }

                :global(.searchSkeletonSectionLabel) {
                    width: 72px;
                    height: 14px;
                    border-radius: 999px;
                    margin-bottom: 2px;
                }

                :global(.searchSkeletonPaperLine) {
                    height: 14px;
                    border-radius: 999px;
                    max-width: 100%;
                }

                :global(.searchSkeletonPaperHeader) {
                    display: flex;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 10px;
                    margin-bottom: 12px;
                }

                :global(.searchSkeletonDate) {
                    width: 86px;
                    height: 13px;
                    border-radius: 999px;
                }

                :global(.searchSkeletonLinkGroup) {
                    width: 54px;
                    height: 14px;
                    border-radius: 999px;
                }

                :global(.searchSkeletonTagRow) {
                    display: inline-flex;
                    flex: 1;
                    flex-wrap: wrap;
                    gap: 10px;
                    min-width: 160px;
                }

                :global(.searchSkeletonTag) {
                    height: 18px;
                    border-radius: 4px;
                }

                :global(.searchSkeletonPaperTitle) {
                    height: 22px;
                    max-width: 100%;
                    border-radius: 999px;
                    margin-bottom: 14px;
                }

                :global(.searchSkeletonMetaLabel) {
                    width: 42px;
                    height: 14px;
                    border-radius: 999px;
                    flex: 0 0 auto;
                    margin-top: 3px;
                }

                :global(.searchSkeletonAbstractRow) {
                    margin-top: 12px;
                }

                .searchMentorPaperFooter {
                    padding-left: 0;
                    margin-top: 0;
                }

                .searchMentorMetaSrOnly {
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

                .searchTimelinePaperHeaderRow {
                    display: flex;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 10px;
                    margin-bottom: 8px;
                    font-size: 13px;
                    color: #666;
                }

                .searchTimelinePaperDate {
                    color: #666;
                }

                .searchTimelinePaperLinks {
                    color: rgb(45, 45, 45);
                    font-size: 14px;
                    line-height: 1.4;
                }

                .searchTimelinePaperLinks a {
                    display: inline-flex;
                    align-items: center;
                    gap: 4px;
                    height: 20px;
                    color: rgb(8, 109, 177);
                    text-decoration: none;
                    transition: color 0.16s ease, border-color 0.16s ease;
                    border-bottom: 1px dashed transparent;
                    line-height: 1;
                    vertical-align: middle;
                }

                .searchTimelinePaperLinks a:hover,
                .searchTimelinePaperLinks a:focus-visible,
                :global(button.searchTimelineMentorButton:hover),
                :global(button.searchTimelineMentorButton:focus-visible) {
                    color: rgb(45, 45, 45);
                    border-bottom-color: rgb(45, 45, 45);
                    outline: none;
                }

                .searchTimelineSubjectTags {
                    display: inline-flex;
                    flex-wrap: wrap;
                    gap: 10px;
                }

                .searchTimelineSubjectTag {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    box-sizing: border-box;
                    min-height: 17.5px;
                    padding: 0 8.925px;
                    border-radius: 4px;
                    background-color: rgb(8, 109, 177);
                    color: rgb(255, 255, 255);
                    font-size: 11.9px;
                    font-style: normal;
                    font-weight: 400;
                    line-height: 17.85px;
                    text-rendering: optimizelegibility;
                    white-space: nowrap;
                }

                :global(.timelineMetaRow) {
                    font-size: 14px;
                }

                :global(.timelineMetaLabel),
                :global(.timelineMetaContent) {
                    font-size: 14px;
                }

                :global(button.searchTimelineMentorButton) {
                    display: inline-flex;
                    align-items: center;
                    gap: 4px;
                    height: 20px;
                    border: none;
                    background: transparent;
                    padding: 0;
                    color: rgb(8, 109, 177);
                    text-decoration: none;
                    transition: color 0.16s ease, border-color 0.16s ease;
                    border-bottom: 1px dashed transparent;
                    line-height: 1;
                    vertical-align: middle;
                    cursor: pointer;
                    font: inherit;
                }

                :global(img.searchTimelineMentorIcon) {
                    width: 14px;
                    height: 14px;
                    object-fit: contain;
                    display: block;
                    flex: 0 0 auto;
                }

                @keyframes searchSkeletonShimmer {
                    from {
                        background-position: 200% 0;
                    }

                    to {
                        background-position: -200% 0;
                    }
                }

                @media (max-width: 820px) {
                    .searchSegmentRow {
                        width: calc(100% + 4px);
                    }

                    :global(.searchSkeletonCard) {
                        padding: 14px 12px 16px;
                    }

                    :global(.searchSkeletonHeaderRow) {
                        gap: 12px;
                    }

                    :global(.searchSkeletonTitle) {
                        max-width: calc(100% - 88px);
                    }

                    :global(.searchSkeletonPaperHeader) {
                        align-items: flex-start;
                    }

                    :global(.searchSkeletonTagRow) {
                        flex-basis: 100%;
                        min-width: 0;
                    }
                }
            `}</style>
        </div>
    );
};

export default SearchScreen;
