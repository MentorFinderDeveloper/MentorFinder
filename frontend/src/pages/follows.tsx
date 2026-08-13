import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import { useSelector } from "react-redux";

import FollowToggleButton from "../components/FollowToggleButton";
import LatexText from "../components/LatexText";
import Pagination from "../components/Pagination";
import { RootState } from "../redux/store";
import { describeRequestError } from "../utils/errorMessage";
import { request } from "../utils/network";
import { buildSearchUrl, normalizeSearchKeywordForUrl } from "../utils/searchQuery";
import { FollowUserResult, SearchMentorResult, TimelinePaper } from "../utils/types";

interface FollowedMentorsResponse {
    mentors?: SearchMentorResult[];
}

interface FollowedUsersResponse {
    users?: FollowUserResult[];
}

interface FollowersResponse {
    users?: FollowUserResult[];
}

interface FollowCountsResponse {
    mentorCount?: number;
    userCount?: number;
    subjectCount?: number;
    followerCount?: number;
}

interface FollowedSubjectSummary {
    subject: string;
    subjectName?: string;
    paperCount: number;
}

interface AvailableSubjectResult {
    subject: string;
    subjectName?: string;
    paperCount: number;
    followed: boolean;
}

interface FollowedSubjectSummariesResponse {
    subjects?: FollowedSubjectSummary[];
}

interface AvailableSubjectsResponse {
    availableSubjects?: AvailableSubjectResult[];
}

interface FollowedSubjectPapersResponse {
    subject?: string;
    recentPapers?: TimelinePaper[];
}

interface SearchUsersResponse {
    users?: FollowUserResult[];
}

interface FollowedMentorCardState extends SearchMentorResult {
    followed: boolean;
}

type FollowCategory = "mentor" | "user" | "subject";
type FollowView = "following" | "followers";

const FOLLOWED_MENTOR_CARDS_PER_PAGE = 18;
const FOLLOW_MENTOR_SKELETON_COUNT = 9;
const FOLLOW_USER_SKELETON_COUNT = 4;
const FOLLOW_SUBJECT_CHIP_SKELETON_COUNT = 8;
const FOLLOW_SUBJECT_CARD_SKELETON_COUNT = 3;
const MIN_FOLLOW_SKELETON_MS = 100;
const MAX_SEARCH_KEYWORD_LENGTH = 255;

// Create stable keys for repeated follow-page skeleton placeholders.
const createSkeletonKeys = (count: number, prefix: string) => (
    Array.from({ length: count }, (_, idx) => `${prefix}-${idx}`)
);

type FollowSkeletonSection = "mentor" | "user" | "subjectSearch" | "followedSubject" | "follower";

// Build the follow button style used by mentor cards on the follows page.
const buildSearchLikeMentorFollowButtonStyle = (followed: boolean): CSSProperties => ({
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

// Format tab counts into a compact display string for the page-level segmented control.
const formatViewSwitchCount = (value: number) => {
    // Compact larger counts so the segmented controls stay readable on narrower screens.
    const safeValue = Math.max(0, Math.floor(value));

    if (safeValue < 1000) {
        return String(safeValue);
    }

    if (safeValue >= 99950) {
        return "99.9k";
    }

    return `${(safeValue / 1000).toFixed(1)}k`;
};

// Render the follows dashboard for mentors, users, subjects, and follower relationships.
const FollowsPage = () => {
    const router = useRouter();
    const authToken = useSelector((state: RootState) => state.auth.token);
    const isLoggedIn = authToken.trim() !== "";

    const [mentors, setMentors] = useState<FollowedMentorCardState[]>([]);
    const [users, setUsers] = useState<FollowUserResult[]>([]);
    const [followers, setFollowers] = useState<FollowUserResult[]>([]);
    const [subjects, setSubjects] = useState<FollowedSubjectSummary[]>([]);
    const [availableSubjects, setAvailableSubjects] = useState<AvailableSubjectResult[]>([]);
    const [subjectPapersByCode, setSubjectPapersByCode] = useState<Record<string, TimelinePaper[]>>({});
    const [subjectPaperErrors, setSubjectPaperErrors] = useState<Record<string, string>>({});
    const [subjectSearchKeyword, setSubjectSearchKeyword] = useState("");
    const [expandedSubjects, setExpandedSubjects] = useState<Set<string>>(new Set());
    const [userSearchKeyword, setUserSearchKeyword] = useState("");
    const [userSearchResults, setUserSearchResults] = useState<FollowUserResult[]>([]);
    const [userSearchLoading, setUserSearchLoading] = useState(false);
    const [activeView, setActiveView] = useState<FollowView>("following");
    const [activeCategory, setActiveCategory] = useState<FollowCategory>("mentor");
    const [mentorCurrentPage, setMentorCurrentPage] = useState(1);
    const [mentorLoading, setMentorLoading] = useState(false);
    const [userLoading, setUserLoading] = useState(false);
    const [availableSubjectLoading, setAvailableSubjectLoading] = useState(false);
    const [followedSubjectLoading, setFollowedSubjectLoading] = useState(false);
    const [followerLoading, setFollowerLoading] = useState(false);
    const [hasLoadedMentors, setHasLoadedMentors] = useState(false);
    const [hasLoadedUsers, setHasLoadedUsers] = useState(false);
    const [hasLoadedAvailableSubjects, setHasLoadedAvailableSubjects] = useState(false);
    const [hasLoadedFollowedSubjects, setHasLoadedFollowedSubjects] = useState(false);
    const [hasLoadedFollowers, setHasLoadedFollowers] = useState(false);
    const [sidebarCounts, setSidebarCounts] = useState({
        mentorCount: 0,
        userCount: 0,
        subjectCount: 0,
        followerCount: 0,
    });
    const [actionMentorId, setActionMentorId] = useState<number | undefined>(undefined);
    const [actionUserId, setActionUserId] = useState<number | undefined>(undefined);
    const [actionSubject, setActionSubject] = useState<string | undefined>(undefined);
    const [subjectPaperLoadingCodes, setSubjectPaperLoadingCodes] = useState<Set<string>>(new Set());
    const [errorMessage, setErrorMessage] = useState("");
    const skeletonStartedAtRef = useRef<Record<FollowSkeletonSection, number>>({
        mentor: 0,
        user: 0,
        subjectSearch: 0,
        followedSubject: 0,
        follower: 0,
    });
    const skeletonTimerRef = useRef<Record<FollowSkeletonSection, ReturnType<typeof setTimeout> | undefined>>({
        mentor: undefined,
        user: undefined,
        subjectSearch: undefined,
        followedSubject: undefined,
        follower: undefined,
    });

    // Route a generic section key to the matching loading state setter.
    const setSectionLoading = useCallback((section: FollowSkeletonSection, loading: boolean) => {
        // Route a generic section key to the matching loading flag.
        if (section === "mentor") {
            setMentorLoading(loading);
            return;
        }
        if (section === "user") {
            setUserLoading(loading);
            return;
        }
        if (section === "subjectSearch") {
            setAvailableSubjectLoading(loading);
            return;
        }
        if (section === "followedSubject") {
            setFollowedSubjectLoading(loading);
            return;
        }
        setFollowerLoading(loading);
    }, []);

    // Cancel the delayed skeleton-hide timer for one section.
    const clearSkeletonTimer = useCallback((section: FollowSkeletonSection) => {
        const timer = skeletonTimerRef.current[section];
        if (timer !== undefined) {
            clearTimeout(timer);
            skeletonTimerRef.current[section] = undefined;
        }
    }, []);

    // Start the loading skeleton timing window for one follow section.
    const startSkeletonPhase = useCallback((section: FollowSkeletonSection) => {
        clearSkeletonTimer(section);
        skeletonStartedAtRef.current[section] = Date.now();
        // Each section enforces its own minimum skeleton duration to avoid flash-of-loaded-content.
        setSectionLoading(section, true);
    }, [clearSkeletonTimer, setSectionLoading]);

    // Finish a section's skeleton phase while honoring the minimum visible skeleton duration.
    const finishSkeletonPhase = useCallback((section: FollowSkeletonSection) => {
        clearSkeletonTimer(section);
        const elapsed = Date.now() - skeletonStartedAtRef.current[section];
        const remaining = Math.max(MIN_FOLLOW_SKELETON_MS - elapsed, 0);
        if (remaining === 0) {
            setSectionLoading(section, false);
            return;
        }

        skeletonTimerRef.current[section] = setTimeout(() => {
            skeletonTimerRef.current[section] = undefined;
            setSectionLoading(section, false);
        }, remaining);
    }, [clearSkeletonTimer, setSectionLoading]);

    useEffect(() => () => {
        (Object.keys(skeletonTimerRef.current) as FollowSkeletonSection[]).forEach((section) => {
            clearSkeletonTimer(section);
        });
    }, [clearSkeletonTimer]);

    // Clear every cached tab/list when the page needs a full auth-aware reset.
    const resetFollowData = useCallback(() => {
        // Clear every tab's cached data when auth disappears or the page needs a full reset.
        setMentors([]);
        setUsers([]);
        setFollowers([]);
        setSubjects([]);
        setAvailableSubjects([]);
        setSubjectPapersByCode({});
        setSubjectPaperErrors({});
        setExpandedSubjects(new Set());
        setSubjectPaperLoadingCodes(new Set());
        setHasLoadedMentors(false);
        setHasLoadedUsers(false);
        setHasLoadedAvailableSubjects(false);
        setHasLoadedFollowedSubjects(false);
        setHasLoadedFollowers(false);
        setSidebarCounts({
            mentorCount: 0,
            userCount: 0,
            subjectCount: 0,
            followerCount: 0,
        });
    }, []);

    // Load lightweight sidebar counts immediately so unopened tabs can still show real counts.
    const fetchFollowCounts = useCallback(async () => {
        if (!isLoggedIn) {
            resetFollowData();
            return;
        }

        try {
            const countRes = await request<FollowCountsResponse>("/api/follow/counts", "GET", true);
            setSidebarCounts({
                mentorCount: Number(countRes.mentorCount) || 0,
                userCount: Number(countRes.userCount) || 0,
                subjectCount: Number(countRes.subjectCount) || 0,
                followerCount: Number(countRes.followerCount) || 0,
            });
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
    }, [isLoggedIn, resetFollowData]);

    // Load the current user's followed mentor list.
    const fetchMentors = useCallback(async () => {
        if (!isLoggedIn) {
            resetFollowData();
            return;
        }

        startSkeletonPhase("mentor");
        setErrorMessage("");

        try {
            const mentorRes = await request<FollowedMentorsResponse>("/api/follow/mentors", "GET", true);
            // Store followed=true directly on mentor cards so the shared toggle button can render from local state.
            setMentors(
                Array.isArray(mentorRes.mentors)
                    ? mentorRes.mentors.map((mentor) => ({
                        ...mentor,
                        followed: true,
                    }))
                    : [],
            );
            setSidebarCounts((currentCounts) => ({
                ...currentCounts,
                mentorCount: Array.isArray(mentorRes.mentors) ? mentorRes.mentors.length : 0,
            }));
            setHasLoadedMentors(true);
        }
        catch (err) {
            setHasLoadedMentors(false);
            setErrorMessage(describeRequestError(err));
        }
        finally {
            finishSkeletonPhase("mentor");
        }
    }, [finishSkeletonPhase, isLoggedIn, resetFollowData, startSkeletonPhase]);

    // Load the current user's followed user list.
    const fetchUsers = useCallback(async () => {
        if (!isLoggedIn) {
            resetFollowData();
            return;
        }

        startSkeletonPhase("user");
        setErrorMessage("");

        try {
            const userRes = await request<FollowedUsersResponse>("/api/follow/users", "GET", true);
            setUsers(Array.isArray(userRes.users) ? userRes.users : []);
            setSidebarCounts((currentCounts) => ({
                ...currentCounts,
                userCount: Array.isArray(userRes.users)
                    ? userRes.users.filter((user) => user.followed).length
                    : 0,
            }));
            setHasLoadedUsers(true);
        }
        catch (err) {
            setHasLoadedUsers(false);
            setErrorMessage(describeRequestError(err));
        }
        finally {
            finishSkeletonPhase("user");
        }
    }, [finishSkeletonPhase, isLoggedIn, resetFollowData, startSkeletonPhase]);

    // Load the discoverable subject list independently so it cannot block the followed-subject cards.
    const fetchAvailableSubjects = useCallback(async () => {
        if (!isLoggedIn) {
            resetFollowData();
            return;
        }

        startSkeletonPhase("subjectSearch");
        setErrorMessage("");

        try {
            const subjectRes = await request<AvailableSubjectsResponse>("/api/follow/subjects/available", "GET", true);
            setAvailableSubjects(Array.isArray(subjectRes.availableSubjects) ? subjectRes.availableSubjects : []);
            setHasLoadedAvailableSubjects(true);
        }
        catch (err) {
            setHasLoadedAvailableSubjects(false);
            setErrorMessage(describeRequestError(err));
        }
        finally {
            finishSkeletonPhase("subjectSearch");
        }
    }, [finishSkeletonPhase, isLoggedIn, resetFollowData, startSkeletonPhase]);

    // Load lightweight followed-subject summaries without prefetching each subject's paper list.
    const fetchFollowedSubjects = useCallback(async () => {
        if (!isLoggedIn) {
            resetFollowData();
            return;
        }

        startSkeletonPhase("followedSubject");
        setErrorMessage("");

        try {
            const subjectRes = await request<FollowedSubjectSummariesResponse>("/api/follow/subjects/followed", "GET", true);
            setSubjects(Array.isArray(subjectRes.subjects) ? subjectRes.subjects : []);
            setSidebarCounts((currentCounts) => ({
                ...currentCounts,
                subjectCount: Array.isArray(subjectRes.subjects) ? subjectRes.subjects.length : 0,
            }));
            setHasLoadedFollowedSubjects(true);
        }
        catch (err) {
            setHasLoadedFollowedSubjects(false);
            setErrorMessage(describeRequestError(err));
        }
        finally {
            finishSkeletonPhase("followedSubject");
        }
    }, [finishSkeletonPhase, isLoggedIn, resetFollowData, startSkeletonPhase]);

    // Lazily load recent papers only after the user expands a specific followed subject.
    const fetchSubjectPapers = useCallback(async (subject: string) => {
        setSubjectPaperLoadingCodes((currentCodes) => new Set(currentCodes).add(subject));
        setSubjectPaperErrors((currentErrors) => {
            const nextErrors = { ...currentErrors };
            delete nextErrors[subject];
            return nextErrors;
        });

        try {
            const res = await request<FollowedSubjectPapersResponse>(
                `/api/follow/subjects/${encodeURIComponent(subject)}/papers`,
                "GET",
                true,
            );
            setSubjectPapersByCode((currentPapers) => ({
                ...currentPapers,
                [subject]: Array.isArray(res.recentPapers) ? res.recentPapers : [],
            }));
        }
        catch (err) {
            setSubjectPaperErrors((currentErrors) => ({
                ...currentErrors,
                [subject]: describeRequestError(err),
            }));
        }
        finally {
            setSubjectPaperLoadingCodes((currentCodes) => {
                const nextCodes = new Set(currentCodes);
                nextCodes.delete(subject);
                return nextCodes;
            });
        }
    }, []);

    // Load the users who currently follow the authenticated user.
    const fetchFollowers = useCallback(async () => {
        if (!isLoggedIn) {
            resetFollowData();
            return;
        }

        startSkeletonPhase("follower");
        setErrorMessage("");

        try {
            const followerRes = await request<FollowersResponse>("/api/follow/followers", "GET", true);
            setFollowers(Array.isArray(followerRes.users) ? followerRes.users : []);
            setSidebarCounts((currentCounts) => ({
                ...currentCounts,
                followerCount: Array.isArray(followerRes.users) ? followerRes.users.length : 0,
            }));
            setHasLoadedFollowers(true);
        }
        catch (err) {
            setHasLoadedFollowers(false);
            setErrorMessage(describeRequestError(err));
        }
        finally {
            finishSkeletonPhase("follower");
        }
    }, [finishSkeletonPhase, isLoggedIn, resetFollowData, startSkeletonPhase]);

    // Follow or unfollow one mentor directly from the mentor tab.
    const toggleFollow = async (mentor: FollowedMentorCardState) => {
        const mentorId = mentor.id;
        setActionMentorId(mentorId);
        setErrorMessage("");

        try {
            const res = await request<{ followed?: boolean }>(
                `/api/follow/mentors/${mentorId}`,
                mentor.followed ? "DELETE" : "POST",
                true,
            );
            setMentors((currentMentors) => currentMentors.map((item) => (
                item.id === mentorId
                    ? {
                        ...item,
                        followed: Boolean(res.followed),
                    }
                    : item
            )));
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setActionMentorId(undefined);
        }
    };

    // Follow or unfollow one user and reflect the result across every user list on the page.
    const toggleUserFollow = async (targetUser: FollowUserResult) => {
        const targetUserId = targetUser.id;
        setActionUserId(targetUserId);
        setErrorMessage("");

        try {
            const res = await request<{ followed?: boolean }>(
                `/api/follow/users/${targetUserId}`,
                targetUser.followed ? "DELETE" : "POST",
                true,
            );
            const followed = Boolean(res.followed);
            const updateUser = (item: FollowUserResult) => (
                item.id === targetUserId ? { ...item, followed } : item
            );
            // Reflect follow changes across the followed list, follower list, and search results simultaneously.
            setUsers((currentUsers) => {
                const updatedUsers = currentUsers.map(updateUser);
                if (updatedUsers.some((item) => item.id === targetUserId)) {
                    return updatedUsers;
                }
                return followed ? [{ ...targetUser, followed }, ...updatedUsers] : updatedUsers;
            });
            setSidebarCounts((currentCounts) => ({
                ...currentCounts,
                userCount: Math.max(currentCounts.userCount + (followed ? 1 : -1), 0),
            }));
            setUserSearchResults((currentUsers) => currentUsers.map(updateUser));
            setFollowers((currentUsers) => currentUsers.map(updateUser));
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setActionUserId(undefined);
        }
    };

    // Follow or unfollow one subject and update both the available and followed subject lists.
    const toggleSubjectFollow = async (targetSubject: string, followed: boolean) => {
        setActionSubject(targetSubject);
        setErrorMessage("");

        try {
            const res = await request<{ followed?: boolean; subject?: FollowedSubjectSummary | string }>(
                `/api/follow/subjects/${encodeURIComponent(targetSubject)}`,
                followed ? "DELETE" : "POST",
                true,
            );
            const nextFollowed = Boolean(res.followed);

            setAvailableSubjects((currentSubjects) => currentSubjects.map((item) => (
                item.subject === targetSubject ? { ...item, followed: nextFollowed } : item
            )));

            if (nextFollowed && typeof res.subject === "object" && Boolean(res.subject)) {
                // Insert a newly followed subject immediately when the backend returns its summary payload.
                setSubjects((currentSubjects) => {
                    if (currentSubjects.some((item) => item.subject === targetSubject)) {
                        return currentSubjects;
                    }
                    return [res.subject as FollowedSubjectSummary, ...currentSubjects];
                });
                setSidebarCounts((currentCounts) => ({
                    ...currentCounts,
                    subjectCount: currentCounts.subjectCount + 1,
                }));
                setHasLoadedFollowedSubjects(true);
            }
            else {
                setSubjects((currentSubjects) => currentSubjects.filter((item) => item.subject !== targetSubject));
                setExpandedSubjects((currentSubjects) => {
                    const nextSubjects = new Set(currentSubjects);
                    nextSubjects.delete(targetSubject);
                    return nextSubjects;
                });
                setSubjectPapersByCode((currentPapers) => {
                    const nextPapers = { ...currentPapers };
                    delete nextPapers[targetSubject];
                    return nextPapers;
                });
                setSubjectPaperErrors((currentErrors) => {
                    const nextErrors = { ...currentErrors };
                    delete nextErrors[targetSubject];
                    return nextErrors;
                });
                setSidebarCounts((currentCounts) => ({
                    ...currentCounts,
                    subjectCount: Math.max(currentCounts.subjectCount - 1, 0),
                }));
            }
        }
        catch (err) {
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setActionSubject(undefined);
        }
    };

    // Search users that can be followed from the user tab.
    const searchUsers = async () => {
        const keyword = normalizeSearchKeywordForUrl(userSearchKeyword);
        if (keyword === "") {
            setUserSearchResults([]);
            return;
        }

        setUserSearchLoading(true);
        setErrorMessage("");

        try {
            const res = await request<SearchUsersResponse>(
                `/api/search/users?keyword=${encodeURIComponent(keyword)}`,
                "GET",
                true,
            );
            setUserSearchResults(Array.isArray(res.users) ? res.users : []);
        }
        catch (err) {
            setUserSearchResults([]);
            setErrorMessage(describeRequestError(err));
        }
        finally {
            setUserSearchLoading(false);
        }
    };

    // Navigate to a public user profile from any user card on the page.
    const openUserProfile = (userId: number) => {
        void router.push(`/users/${userId}`);
    };

    // Derive the PDF URL from an arXiv abstract link for subject-paper previews.
    const buildPaperPdfUrl = (arxivUrl?: string) => {
        // Mirror the search/timeline behavior by deriving the PDF link from the arXiv abstract URL.
        if (typeof arxivUrl !== "string" || arxivUrl.trim() === "" || !arxivUrl.includes("/abs/")) {
            return "";
        }

        return arxivUrl.replace("/abs/", "/pdf/");
    };

    // Expand or collapse the recent paper list for one followed subject.
    const toggleSubjectExpand = async (subject: string) => {
        const isExpanded = expandedSubjects.has(subject);
        if (isExpanded) {
            setExpandedSubjects((currentSubjects) => {
                const nextSubjects = new Set(currentSubjects);
                nextSubjects.delete(subject);
                return nextSubjects;
            });
            return;
        }

        setExpandedSubjects((currentSubjects) => new Set(currentSubjects).add(subject));
        if (subjectPapersByCode[subject] !== undefined || subjectPaperLoadingCodes.has(subject)) {
            return;
        }
        await fetchSubjectPapers(subject);
    };

    // Jump into the search page with an exact paper search seeded from a subject code.
    const navigateToSubjectSearch = (subjectCode: string) => {
        // Reuse the search page for exact subject-code paper search from the follows dashboard.
        const url = buildSearchUrl({
            keyword: subjectCode,
            mode: "paper",
            searchMode: "exact",
            sortMode: "default",
            page: 1,
            visibility: "all",
        });
        void router.push(url);
    };

    // Render one user card shared by the search, following, and follower lists.
    const renderUserCard = (user: FollowUserResult, keyPrefix: string) => (
        <div
            className="userCard"
            key={`${keyPrefix}-${user.id}`}
            role="button"
            tabIndex={0}
            aria-label={`进入${user.realName || user.username}用户主页`}
            onClick={() => openUserProfile(user.id)}
            onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openUserProfile(user.id);
                }
            }}
        >
            <div className="userCardProfile">
                <div className="userAvatar" aria-hidden="true">
                    {user.avatarUrl ? (
                        <img src={user.avatarUrl} alt="" />
                    ) : (
                        <span>{user.username.slice(0, 1).toUpperCase()}</span>
                    )}
                </div>
                <div className="userText">
                    <h4>{user.realName || user.username}</h4>
                    <p>{user.username} · {user.role}</p>
                    <p>{user.signature || "暂无签名"}</p>
                </div>
            </div>
            <div className="userFollowButtonShell" onClick={(event) => event.stopPropagation()}>
                {/* Prevent follow clicks from also triggering navigation into the user profile. */}
                <FollowToggleButton
                    className="followToggleButton"
                    followed={user.followed}
                    loading={actionUserId === user.id}
                    onClick={() => void toggleUserFollow(user)}
                />
            </div>
        </div>
    );

    // Render loading placeholders for the mentor tab.
    const renderMentorSkeletonGrid = () => (
        <div className="followSkeletonMentorGrid" aria-label="导师关注加载中" data-testid="follow-mentor-skeleton">
            {createSkeletonKeys(FOLLOW_MENTOR_SKELETON_COUNT, "mentor-skeleton").map((key) => (
                <div className="followSkeletonMentorCard" key={key} aria-hidden="true">
                    <div className="followSkeletonMentorHeader">
                        <span className="followSkeletonBlock followSkeletonMentorTitle" />
                        <span className="followSkeletonBlock followSkeletonMentorButton" />
                    </div>
                    <span className="followSkeletonBlock followSkeletonMentorMeta followSkeletonMentorMetaShort" />
                    <span className="followSkeletonBlock followSkeletonMentorMeta" />
                    <span className="followSkeletonBlock followSkeletonMentorMeta followSkeletonMentorMetaWide" />
                </div>
            ))}
        </div>
    );

    // Render loading placeholders for user-card lists.
    const renderUserSkeletonList = (testId = "follow-user-skeleton") => (
        <div className="userList" aria-label="用户关注加载中" data-testid={testId}>
            {createSkeletonKeys(FOLLOW_USER_SKELETON_COUNT, `${testId}-item`).map((key) => (
                <div className="userCard followSkeletonUserCard" key={key} aria-hidden="true">
                    <div className="userCardProfile">
                        <span className="followSkeletonBlock followSkeletonAvatar" />
                        <div className="userText followSkeletonUserText">
                            <span className="followSkeletonBlock followSkeletonUserName" />
                            <span className="followSkeletonBlock followSkeletonUserMeta" />
                            <span className="followSkeletonBlock followSkeletonUserSignature" />
                        </div>
                    </div>
                    <span className="followSkeletonBlock followSkeletonUserButton" />
                </div>
            ))}
        </div>
    );

    // Render loading placeholders for the discoverable subject list.
    const renderAvailableSubjectSkeleton = () => (
        <section className="subjectSearchSection" aria-label="搜索关注板块加载中" data-testid="follow-subject-search-skeleton">
            <div className="sectionHeader">
                <h3>关注板块</h3>
            </div>
            <span className="followSkeletonBlock followSkeletonSearchInput" aria-hidden="true" />
            <div className="subjectChipGrid" aria-hidden="true">
                {createSkeletonKeys(FOLLOW_SUBJECT_CHIP_SKELETON_COUNT, "subject-chip-skeleton").map((key) => (
                    <span className="followSkeletonBlock followSkeletonSubjectChip" key={key} />
                ))}
            </div>
        </section>
    );

    // Render loading placeholders for the followed-subject summary list.
    const renderFollowedSubjectSkeleton = () => (
        <section className="followedSubjectSection" aria-label="已关注板块加载中" data-testid="follow-followed-subject-skeleton">
            <div className="sectionHeader">
                <h3>已关注板块</h3>
                <span>0</span>
            </div>
            <div className="subjectList" aria-hidden="true">
                {createSkeletonKeys(FOLLOW_SUBJECT_CARD_SKELETON_COUNT, "subject-card-skeleton").map((key) => (
                    <article className="subjectCard followSkeletonSubjectCard" key={key}>
                        <div className="subjectCardHeader">
                            <div className="followSkeletonSubjectTitleGroup">
                                <span className="followSkeletonBlock followSkeletonSubjectTitle" />
                                <span className="followSkeletonBlock followSkeletonSubjectMeta" />
                            </div>
                            <div className="subjectActionGroup">
                                <span className="followSkeletonBlock followSkeletonSubjectAction" />
                                <span className="followSkeletonBlock followSkeletonSubjectAction" />
                                <span className="followSkeletonBlock followSkeletonSubjectAction" />
                            </div>
                        </div>
                    </article>
                ))}
            </div>
        </section>
    );

    // Switch between the "following" and "followers" top-level views.
    const handleViewChange = (nextView: FollowView) => {
        setActiveView(nextView);
        // Followers are loaded lazily because many sessions never leave the default "following" tab.
        if (nextView === "followers" && !hasLoadedFollowers && !followerLoading) {
            void fetchFollowers();
        }
    };

    // Switch between mentor, user, and subject tabs inside the "following" view.
    const handleCategoryChange = (nextCategory: FollowCategory) => {
        setActiveCategory(nextCategory);
        // User and subject tabs are also lazy-loaded to keep the initial mentor view responsive.
        if (nextCategory === "user" && !hasLoadedUsers && !userLoading) {
            void fetchUsers();
        }
        if (nextCategory === "subject") {
            if (!hasLoadedAvailableSubjects && !availableSubjectLoading) {
                void fetchAvailableSubjects();
            }
            if (!hasLoadedFollowedSubjects && !followedSubjectLoading) {
                void fetchFollowedSubjects();
            }
        }
    };

    const followedUserIds = new Set(
        users.filter((user) => user.followed).map((user) => user.id),
    );
    const followedSubjectSet = useMemo(
        () => new Set(subjects.map((subject) => subject.subject)),
        [subjects],
    );
    const filteredAvailableSubjects = useMemo(() => {
        const keyword = subjectSearchKeyword.trim().toLowerCase();
        // Hide subjects that are already followed from the discovery chip list.
        return availableSubjects.filter((subject) => {
            if (subject.followed || followedSubjectSet.has(subject.subject)) {
                return false;
            }
            if (keyword === "") {
                return true;
            }
            return subject.subject.toLowerCase().includes(keyword)
                || (subject.subjectName || subject.subject).toLowerCase().includes(keyword);
        });
    }, [availableSubjects, followedSubjectSet, subjectSearchKeyword]);
    const mentorCount = hasLoadedMentors
        ? mentors.filter((mentor) => mentor.followed).length
        : sidebarCounts.mentorCount;
    const userCount = hasLoadedUsers
        ? users.filter((user) => user.followed).length
        : sidebarCounts.userCount;
    const subjectCount = hasLoadedFollowedSubjects
        ? subjects.length
        : sidebarCounts.subjectCount;
    const followerCount = hasLoadedFollowers
        ? followers.length
        : sidebarCounts.followerCount;
    const followingCount = mentorCount + userCount + subjectCount;
    const visibleUserSearchResults = userSearchResults.filter((user) => (
        !user.followed && !followedUserIds.has(user.id)
    ));
    const mentorTotalPages = Math.max(1, Math.ceil(mentors.length / FOLLOWED_MENTOR_CARDS_PER_PAGE));
    const safeMentorCurrentPage = Math.min(mentorCurrentPage, mentorTotalPages);
    const mentorPageStartIndex = (safeMentorCurrentPage - 1) * FOLLOWED_MENTOR_CARDS_PER_PAGE;
    const paginatedMentors = mentors.slice(
        mentorPageStartIndex,
        mentorPageStartIndex + FOLLOWED_MENTOR_CARDS_PER_PAGE,
    );

    useEffect(() => {
        // The page opens by loading followed mentors first.
        void fetchFollowCounts();
        void fetchMentors();
    }, [fetchFollowCounts, fetchMentors]);

    useEffect(() => {
        if (mentorCurrentPage > mentorTotalPages) {
            setMentorCurrentPage(mentorTotalPages);
        }
    }, [mentorCurrentPage, mentorTotalPages]);

    if (!isLoggedIn) {
        return (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 960 }}>
                <p>请先登录后查看关注列表。</p>
            </div>
        );
    }

        return (
            <div className="followsPage">
                <div className="pageHeader">
                    <div className="pageTitleGroup">
                        <h2 className="pageTitle">{activeView === "following" ? "我的关注" : "我的粉丝"}</h2>
                    </div>
                    <div className="pageHeaderActions">
                        <button
                            type="button"
                            className="addPrivateMentorButton"
                            onClick={() => router.push("/private-mentor")}
                        >
                            添加个人导师
                        </button>
                        <div className="viewSwitchGroup" role="group" aria-label="关注页面切换">
                            <div className="viewSwitch">
                                <span
                                    className={activeView === "following" ? "viewSwitchThumb" : "viewSwitchThumb viewSwitchThumbFollowers"}
                                    aria-hidden="true"
                                />
                                <button
                                    className={activeView === "following" ? "searchSegmentButton viewSwitchButton viewSwitchButtonActive" : "searchSegmentButton viewSwitchButton"}
                                    type="button"
                                    aria-pressed={activeView === "following"}
                                    onClick={() => handleViewChange("following")}
                                >
                                    <span className="viewSwitchButtonLabel">我的关注</span>
                                    <span className="viewSwitchButtonCount" aria-hidden="true">
                                        {formatViewSwitchCount(followingCount)}
                                    </span>
                                </button>
                                <button
                                    className={activeView === "followers" ? "searchSegmentButton viewSwitchButton viewSwitchButtonActive" : "searchSegmentButton viewSwitchButton"}
                                    type="button"
                                    aria-pressed={activeView === "followers"}
                                    onClick={() => handleViewChange("followers")}
                                >
                                    <span className="viewSwitchButtonLabel">我的粉丝</span>
                                    <span className="viewSwitchButtonCount" aria-hidden="true">
                                        {formatViewSwitchCount(followerCount)}
                                    </span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

            {activeView === "following" ? (
            <div className="content">
                <aside className="sidebar" aria-label="关注筛选">
                    <div className="categorySwitchGroup" role="group" aria-label="关注类型切换">
                        <div className="categorySwitch">
                            <span
                                className={[
                                    "categorySwitchThumb",
                                    activeCategory === "user" ? "categorySwitchThumbUser" : "",
                                    activeCategory === "subject" ? "categorySwitchThumbSubject" : "",
                                ].filter(Boolean).join(" ")}
                                aria-hidden="true"
                            />
                            <button
                                className={activeCategory === "mentor" ? "searchSegmentButton categorySwitchButton categorySwitchButtonActive" : "searchSegmentButton categorySwitchButton"}
                                type="button"
                                aria-pressed={activeCategory === "mentor"}
                                aria-label={`导师（${formatViewSwitchCount(mentorCount)}）`}
                                onClick={() => handleCategoryChange("mentor")}
                            >
                                <span className="categorySwitchButtonLabel">导师</span>
                                <span className="categorySwitchButtonCount" aria-hidden="true">
                                    {formatViewSwitchCount(mentorCount)}
                                </span>
                            </button>
                            <button
                                className={activeCategory === "user" ? "searchSegmentButton categorySwitchButton categorySwitchButtonActive" : "searchSegmentButton categorySwitchButton"}
                                type="button"
                                aria-pressed={activeCategory === "user"}
                                aria-label={`用户（${formatViewSwitchCount(userCount)}）`}
                                onClick={() => handleCategoryChange("user")}
                            >
                                <span className="categorySwitchButtonLabel">用户</span>
                                <span className="categorySwitchButtonCount" aria-hidden="true">
                                    {formatViewSwitchCount(userCount)}
                                </span>
                            </button>
                            <button
                                className={activeCategory === "subject" ? "searchSegmentButton categorySwitchButton categorySwitchButtonActive" : "searchSegmentButton categorySwitchButton"}
                                type="button"
                                aria-pressed={activeCategory === "subject"}
                                aria-label={`板块（${formatViewSwitchCount(subjectCount)}）`}
                                onClick={() => handleCategoryChange("subject")}
                            >
                                <span className="categorySwitchButtonLabel">板块</span>
                                <span className="categorySwitchButtonCount" aria-hidden="true">
                                    {formatViewSwitchCount(subjectCount)}
                                </span>
                            </button>
                        </div>
                    </div>
                </aside>

                <main className="main">
                    {errorMessage !== "" && <p style={{ color: "#c62828" }}>{errorMessage}</p>}

                    {activeCategory === "mentor" && !mentorLoading && hasLoadedMentors && mentors.length === 0 && errorMessage === "" && (
                        <p>暂无关注导师</p>
                    )}

                    {activeCategory === "mentor" && (
                        <div className="mentorSection">
                            {mentorLoading ? (
                                renderMentorSkeletonGrid()
                            ) : (
                                <div className="mentorGrid">
                                    {paginatedMentors.map((mentor) => (
                                        <div
                                            key={mentor.id}
                                            className="mentorCard"
                                            role="button"
                                            tabIndex={0}
                                            aria-label={`进入${mentor.Chinese_name}导师主页`}
                                            onClick={() => router.push(`/mentors/${mentor.id}`)}
                                            onKeyDown={(event) => {
                                                if (event.key === "Enter" || event.key === " ") {
                                                    event.preventDefault();
                                                    void router.push(`/mentors/${mentor.id}`);
                                                }
                                            }}
                                        >
                                            <div className="mentorCardHeader" data-testid={`mentor-card-header-${mentor.id}`}>
                                                <h3 className="mentorName">
                                                    {mentor.Chinese_name}
                                                    {mentor.is_private && (
                                                        <span className="privateBadge">我的私有导师</span>
                                                    )}
                                                </h3>
                                                <div className="followButtonShell" onClick={(event) => event.stopPropagation()}>
                                                    <FollowToggleButton
                                                        className="followToggleButton"
                                                        followed={mentor.followed}
                                                        followedLabel="已关注"
                                                        loading={actionMentorId === mentor.id}
                                                        onClick={() => void toggleFollow(mentor)}
                                                        style={buildSearchLikeMentorFollowButtonStyle(mentor.followed)}
                                                    />
                                                </div>
                                            </div>
                                            {mentor.English_name && (
                                                <p className="mentorMeta">英文名：{mentor.English_name}</p>
                                            )}
                                            <p className="mentorMeta">研究方向：{mentor.research_direction || "暂无研究方向"}</p>
                                            <p className="mentorMeta">邮箱：{mentor.email || "暂无邮箱"}</p>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {mentors.length > 0 && (
                                <div className="mentorPagination">
                                    <Pagination
                                        currentPage={safeMentorCurrentPage}
                                        totalPages={mentorTotalPages}
                                        loading={mentorLoading}
                                        centered
                                        controlHeight={33.77}
                                        jumpInputWidth={120}
                                        activePageHighlightColor="rgb(8, 109, 177)"
                                        onPageChange={(newPage) => setMentorCurrentPage(newPage)}
                                    />
                                </div>
                            )}
                        </div>
                    )}

                    {activeCategory === "user" && (
                    <section className="userFollowSection" aria-label="关注用户">
                        <section className="userSearchSection" aria-label="搜索关注用户">
                            <div className="sectionHeader">
                                <h3>关注用户</h3>
                            </div>

                            <div className="userSearch">
                                <input
                                    type="text"
                                    value={userSearchKeyword}
                                    placeholder="搜索用户名、姓名或邮箱"
                                    maxLength={MAX_SEARCH_KEYWORD_LENGTH}
                                    onChange={(event) => setUserSearchKeyword(normalizeSearchKeywordForUrl(event.target.value))}
                                    onKeyDown={(event) => {
                                        if (event.key === "Enter") {
                                            void searchUsers();
                                        }
                                    }}
                                />
                                <button type="button" onClick={() => void searchUsers()} disabled={userSearchLoading}>
                                    {userSearchLoading ? "搜索中..." : "搜索用户"}
                                </button>
                            </div>

                            {visibleUserSearchResults.length > 0 && (
                                <div className="userList" aria-label="用户搜索结果">
                                    {visibleUserSearchResults.map((user) => renderUserCard(user, "search"))}
                                </div>
                            )}
                        </section>

                        <section className="followedUserSection" aria-label="已关注用户区块">
                            <div className="sectionHeader">
                                <h3>已关注用户</h3>
                                <span>{users.filter((user) => user.followed).length}</span>
                            </div>

                            {userLoading ? (
                                renderUserSkeletonList()
                            ) : hasLoadedUsers && users.length === 0 ? (
                                <p>暂无关注用户</p>
                            ) : (
                                <div className="userList" aria-label="已关注用户">
                                    {users.map((user) => renderUserCard(user, "followed"))}
                                </div>
                            )}
                        </section>
                    </section>
                    )}

                    {activeCategory === "subject" && (
                    <section className="subjectFollowSection" aria-label="关注板块">
                        {availableSubjectLoading ? (
                            renderAvailableSubjectSkeleton()
                        ) : (
                            <section className="subjectSearchSection" aria-label="搜索关注板块">
                                <div className="sectionHeader">
                                    <h3>关注板块</h3>
                                </div>

                                <div className="userSearch">
                                    <input
                                        type="text"
                                        value={subjectSearchKeyword}
                                        placeholder="搜索板块名称或代码，例如 人工智能 / cs.AI"
                                        onChange={(event) => setSubjectSearchKeyword(event.target.value)}
                                    />
                                </div>

                                {filteredAvailableSubjects.length > 0 && (
                                    <div className="subjectChipGrid" aria-label="可关注板块">
                                        {filteredAvailableSubjects.map((subject) => (
                                            <button
                                                key={subject.subject}
                                                className="subjectChip"
                                                type="button"
                                                disabled={actionSubject === subject.subject}
                                                onClick={() => void toggleSubjectFollow(subject.subject, false)}
                                            >
                                                <span className="subjectChipLabel">{subject.subjectName || subject.subject}</span>
                                                <small>{subject.paperCount} 篇</small>
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {hasLoadedAvailableSubjects && filteredAvailableSubjects.length === 0 && (
                                    <p>暂无可关注板块</p>
                                )}
                            </section>
                        )}

                        {followedSubjectLoading ? (
                            renderFollowedSubjectSkeleton()
                        ) : (
                            <section className="followedSubjectSection" aria-label="已关注板块区块">
                                <div className="sectionHeader">
                                    <h3>已关注板块</h3>
                                    <span>{subjects.length}</span>
                                </div>

                                {hasLoadedFollowedSubjects && subjects.length === 0 ? (
                                    <p>暂无关注板块</p>
                                ) : (
                                    <div className="subjectList" aria-label="已关注板块">
                                        {subjects.map((subject) => {
                                            const subjectPapers = subjectPapersByCode[subject.subject] || [];
                                            const subjectPaperError = subjectPaperErrors[subject.subject];
                                            const subjectPaperLoading = subjectPaperLoadingCodes.has(subject.subject);
                                            return (
                                                <article className="subjectCard" key={subject.subject}>
                                                    <div className="subjectCardHeader">
                                                        <div>
                                                            <h4>{subject.subjectName || subject.subject}</h4>
                                                            <p>{subject.paperCount} 篇论文</p>
                                                        </div>
                                                        <div className="subjectActionGroup">
                                                            <button
                                                                className="subjectExpandButton"
                                                                type="button"
                                                                onClick={() => void toggleSubjectExpand(subject.subject)}
                                                            >
                                                                {expandedSubjects.has(subject.subject) ? "收起论文" : "展开论文"}
                                                            </button>
                                                            <button
                                                                className="subjectSearchButton"
                                                                type="button"
                                                                onClick={() => navigateToSubjectSearch(subject.subject)}
                                                            >
                                                                前往检索
                                                            </button>
                                                            <button
                                                                className="subjectUnfollowButton"
                                                                type="button"
                                                                disabled={actionSubject === subject.subject}
                                                                onClick={() => void toggleSubjectFollow(subject.subject, true)}
                                                            >
                                                                {actionSubject === subject.subject ? "处理中..." : "取消关注"}
                                                            </button>
                                                        </div>
                                                    </div>

                                                    {expandedSubjects.has(subject.subject) && subjectPaperLoading && (
                                                        <p className="subjectEmptyText">论文加载中...</p>
                                                    )}

                                                    {expandedSubjects.has(subject.subject) && !subjectPaperLoading && subjectPaperError && (
                                                        <p className="subjectEmptyText">{subjectPaperError}</p>
                                                    )}

                                                    {expandedSubjects.has(subject.subject) && !subjectPaperLoading && !subjectPaperError && subjectPapers.length === 0 && (
                                                        <p className="subjectEmptyText">该板块暂无论文。</p>
                                                    )}

                                                    {expandedSubjects.has(subject.subject) && !subjectPaperLoading && subjectPapers.length > 0 && (
                                                        <div className="subjectPaperList">
                                                            {subjectPapers.map((paper) => {
                                                                const pdfUrl = buildPaperPdfUrl(paper.arxiv_url);
                                                                return (
                                                                    <div className="subjectPaperItem" key={paper.id}>
                                                                        <div className="subjectPaperTitle">
                                                                            <LatexText text={paper.title} forceInlineMath />
                                                                        </div>
                                                                        <div className="subjectPaperMeta">
                                                                            <span>{paper.publish_date || "未知日期"}</span>
                                                                            <span>{paper.author_names || "未知作者"}</span>
                                                                            {paper.arxiv_url && (
                                                                                <a href={paper.arxiv_url} target="_blank" rel="noreferrer">
                                                                                    arXiv
                                                                                </a>
                                                                            )}
                                                                            {pdfUrl !== "" && (
                                                                                <a href={pdfUrl} target="_blank" rel="noreferrer">
                                                                                    PDF
                                                                                </a>
                                                                            )}
                                                                        </div>
                                                                        <p className="subjectPaperAbstract">
                                                                            {paper.tldr || paper.abstract || "暂无摘要"}
                                                                        </p>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    )}
                                                </article>
                                            );
                                        })}
                                    </div>
                                )}
                            </section>
                        )}
                    </section>
                    )}
                </main>
            </div>
            ) : (
                <main className="followersMain" aria-label="我的粉丝">
                    {errorMessage !== "" && <p style={{ color: "#c62828" }}>{errorMessage}</p>}

                    {followerLoading ? (
                        renderUserSkeletonList("follow-follower-skeleton")
                    ) : hasLoadedFollowers && followers.length === 0 && errorMessage === "" ? (
                        <p>暂无粉丝</p>
                    ) : (
                        <div className="userList" aria-label="关注自己的用户">
                            {followers.map((user) => renderUserCard(user, "follower"))}
                        </div>
                    )}
                </main>
            )}

            <style jsx>{`
                :global(.appMain:has(.followsPage)) {
                    width: min(1510px, calc(100% - 32px));
                }

                .followsPage {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    width: 100%;
                    max-width: 1477px;
                }

                .pageHeader {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 16px;
                }

                .pageTitle {
                    margin: 0;
                }

                .pageTitleGroup {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }

                .pageHeaderActions {
                    display: flex;
                    align-items: center;
                    justify-content: flex-end;
                    gap: 12px;
                    flex-wrap: wrap;
                }

                .addPrivateMentorButton {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 36px;
                    padding: 0 14px;
                    border: 1px solid #d0d7de;
                    border-radius: 12px;
                    background: rgba(246, 248, 250, 0.96);
                    color: rgb(37, 41, 46);
                    font-size: 14px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
                }

                .addPrivateMentorButton:hover {
                    background: rgb(8, 109, 177);
                    border-color: rgb(8, 109, 177);
                    color: #ffffff;
                }

                .viewSwitchGroup {
                    min-width: 260px;
                }

                .categorySwitchGroup {
                    width: 100%;
                }

                .viewSwitch {
                    position: relative;
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    align-items: stretch;
                    width: 100%;
                    height: 44px;
                    border: 1px solid #d0d7de;
                    border-radius: 16px;
                    background: rgba(246, 248, 250, 0.96);
                    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72), 0 1px 2px rgba(15, 23, 42, 0.04);
                    overflow: hidden;
                }

                .viewSwitchThumb {
                    position: absolute;
                    top: 2px;
                    bottom: 2px;
                    left: 2px;
                    width: calc((100% - 4px) / 2);
                    border-radius: 14px;
                    background: rgb(8, 109, 177);
                    border: 1px solid rgb(8, 109, 177);
                    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
                    transform: translateX(0);
                    transition: transform 240ms cubic-bezier(0.22, 1, 0.36, 1);
                    will-change: transform;
                }

                .viewSwitchThumbFollowers {
                    transform: translateX(100%);
                }

                .viewSwitchButton {
                    position: relative;
                    z-index: 1;
                    display: inline-flex;
                    min-height: 44px;
                    align-items: center;
                    justify-content: center;
                    gap: 6px;
                    border: 0;
                    border-radius: 16px;
                    background: transparent;
                    box-shadow: none;
                    color: #59636e;
                    padding: 0 16px;
                    font-size: 16px;
                    font-weight: 600;
                    appearance: none;
                    -webkit-appearance: none;
                    transition: color 180ms ease;
                }

                .viewSwitchButtonLabel,
                .viewSwitchButtonCount {
                    color: inherit;
                }

                .viewSwitchButtonCount {
                    display: inline-flex;
                    min-width: 5ch;
                    justify-content: flex-end;
                    font-size: 14px;
                    font-weight: 700;
                    font-variant-numeric: tabular-nums;
                }

                .viewSwitchButtonActive {
                    font-weight: 700;
                    color: #fff;
                }

                .viewSwitchButton:hover,
                .viewSwitchButton:focus-visible {
                    box-shadow: none;
                    transform: none;
                }

                .viewSwitchButton:focus-visible {
                    outline: 2px solid rgba(8, 109, 177, 0.35);
                    outline-offset: 2px;
                }

                .content {
                    display: grid;
                    grid-template-columns: 160px 1fr;
                    gap: 18px;
                    align-items: start;
                }

                .sidebar {
                    min-width: 0;
                }

                .categorySwitch {
                    position: relative;
                    display: grid;
                    grid-template-rows: repeat(3, minmax(0, 1fr));
                    gap: 0;
                    width: 100%;
                    padding: 2px;
                    border: 1px solid #d0d7de;
                    border-radius: 16px;
                    background: rgba(246, 248, 250, 0.96);
                    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72), 0 1px 2px rgba(15, 23, 42, 0.04);
                    overflow: hidden;
                }

                .categorySwitchThumb {
                    position: absolute;
                    top: 2px;
                    left: 2px;
                    right: 2px;
                    height: calc((100% - 4px) / 3);
                    border-radius: 14px;
                    background: rgb(8, 109, 177);
                    border: 1px solid rgb(8, 109, 177);
                    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
                    transform: translateY(0);
                    transition: transform 240ms cubic-bezier(0.22, 1, 0.36, 1);
                    will-change: transform;
                }

                .categorySwitchThumbUser {
                    transform: translateY(100%);
                }

                .categorySwitchThumbSubject {
                    transform: translateY(200%);
                }

                .categorySwitchButton {
                    position: relative;
                    z-index: 1;
                    display: inline-flex;
                    min-height: 54px;
                    align-items: center;
                    justify-content: space-between;
                    gap: 8px;
                    border: 0;
                    border-radius: 14px;
                    background: transparent;
                    box-shadow: none;
                    color: #59636e;
                    padding: 0 16px;
                    font-size: 16px;
                    font-weight: 600;
                    appearance: none;
                    -webkit-appearance: none;
                    transition: color 180ms ease;
                    text-align: left;
                }

                .categorySwitchButtonLabel,
                .categorySwitchButtonCount {
                    color: inherit;
                }

                .categorySwitchButtonCount {
                    display: inline-flex;
                    min-width: 4ch;
                    justify-content: flex-end;
                    font-size: 14px;
                    font-weight: 700;
                    font-variant-numeric: tabular-nums;
                }

                .categorySwitchButtonActive {
                    font-weight: 700;
                    color: #fff;
                }

                .categorySwitchButton:hover,
                .categorySwitchButton:focus-visible {
                    box-shadow: none;
                    transform: none;
                }

                .categorySwitchButton:focus-visible {
                    outline: 2px solid rgba(8, 109, 177, 0.35);
                    outline-offset: 2px;
                }

                .main {
                    min-width: 0;
                }

                .followersMain {
                    min-width: 0;
                }

                .mentorSection {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }

                .mentorGrid {
                    display: grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap: 12px;
                }

                .mentorPagination {
                    display: flex;
                    justify-content: center;
                }

                :global(.followSkeletonBlock) {
                    display: block;
                    position: relative;
                    overflow: hidden;
                    border-radius: 999px;
                    background: linear-gradient(90deg, #e3e9f0 0%, #edf2f7 40%, #ffffff 50%, #edf2f7 60%, #e3e9f0 100%);
                    background-size: 200% 100%;
                    animation: followSkeletonShimmer 1.15s ease-in-out infinite;
                }

                :global(.followSkeletonMentorGrid) {
                    display: grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap: 12px;
                }

                :global(.followSkeletonMentorCard) {
                    min-height: 158px;
                    padding: 14px;
                    border: 1px solid #ccc;
                    border-radius: 8px;
                    background: #fff;
                    cursor: default;
                    pointer-events: none;
                }

                :global(.followSkeletonMentorHeader) {
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    gap: 12px;
                    margin-bottom: 8px;
                }

                :global(.followSkeletonUserCard),
                :global(.followSkeletonSubjectCard) {
                    cursor: default;
                    pointer-events: none;
                }

                :global(.followSkeletonMentorTitle) {
                    width: min(168px, 58%);
                    height: 23px;
                }

                :global(.followSkeletonMentorButton),
                :global(.followSkeletonUserButton) {
                    flex: 0 0 auto;
                    width: 72px;
                    height: 28px;
                    border-radius: 6px;
                }

                :global(.followSkeletonMentorMeta) {
                    width: 82%;
                    height: 14px;
                    margin-top: 12px;
                }

                :global(.followSkeletonMentorMetaShort) {
                    width: 52%;
                }

                :global(.followSkeletonMentorMetaWide) {
                    width: 92%;
                }

                :global(.followSkeletonAvatar) {
                    width: 44px;
                    height: 44px;
                    border-radius: 50%;
                }

                :global(.followSkeletonUserText) {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    width: 100%;
                }

                :global(.followSkeletonUserName) {
                    width: min(180px, 46%);
                    height: 17px;
                }

                :global(.followSkeletonUserMeta) {
                    width: min(240px, 62%);
                    height: 13px;
                }

                :global(.followSkeletonUserSignature) {
                    width: min(360px, 82%);
                    height: 13px;
                }

                :global(.followSkeletonSearchInput) {
                    width: 100%;
                    height: 42px;
                    border-radius: 6px;
                }

                :global(.followSkeletonSubjectChip) {
                    min-height: 54px;
                    border-radius: 8px;
                }

                :global(.followSkeletonSubjectTitleGroup) {
                    display: flex;
                    flex: 1 1 auto;
                    flex-direction: column;
                    gap: 10px;
                    min-width: 0;
                }

                :global(.followSkeletonSubjectTitle) {
                    width: min(220px, 58%);
                    height: 20px;
                }

                :global(.followSkeletonSubjectMeta) {
                    width: 96px;
                    height: 13px;
                }

                :global(.followSkeletonSubjectAction) {
                    width: 76px;
                    height: 34px;
                    border-radius: 6px;
                }

                :global(.userFollowSection) {
                    display: flex;
                    flex-direction: column;
                    gap: 18px;
                }

                :global(.subjectFollowSection) {
                    display: flex;
                    flex-direction: column;
                    gap: 18px;
                }

                :global(.userSearchSection),
                :global(.followedUserSection),
                :global(.subjectSearchSection),
                :global(.followedSubjectSection) {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }

                :global(.followedUserSection),
                :global(.followedSubjectSection) {
                    border-top: 1px solid #d0d7de;
                    padding-top: 16px;
                }

                :global(.sectionHeader) {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 12px;
                }

                :global(.sectionHeader h3) {
                    margin: 0;
                    font-size: 18px;
                }

                :global(.sectionHeader span) {
                    border: 1px solid #d0d7de;
                    border-radius: 999px;
                    padding: 4px 10px;
                    color: #57606a;
                    font-size: 13px;
                    font-weight: 700;
                }

                :global(.userSearch) {
                    display: flex;
                    gap: 8px;
                    align-items: stretch;
                }

                :global(.userSearch input) {
                    min-width: 0;
                    flex: 1;
                    border: 1px solid #d0d7de;
                    border-radius: 6px;
                    padding: 10px 12px;
                }

                :global(.userSearch button) {
                    flex: 0 0 auto;
                    border: 1px solid #222;
                    border-radius: 6px;
                    background: #fff;
                    padding: 10px 14px;
                    font-weight: 700;
                }

                :global(.userList) {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                }

                :global(.subjectChipGrid) {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(176px, 1fr));
                    gap: 8px;
                    width: 100%;
                    max-height: 360px;
                    overflow: auto;
                    padding-right: 8px;
                    box-sizing: border-box;
                }

                :global(.subjectChip) {
                    display: grid;
                    grid-template-columns: minmax(0, 1fr) auto;
                    min-height: 54px;
                    align-items: center;
                    gap: 8px;
                    border: 1px solid #d0d7de;
                    border-radius: 8px;
                    background: #fff;
                    padding: 10px 12px;
                    color: #1f2328;
                    font-weight: 700;
                    text-align: left;
                }

                :global(.subjectChipLabel) {
                    min-width: 0;
                    overflow-wrap: anywhere;
                    line-height: 1.35;
                }

                :global(.subjectChip small) {
                    flex: 0 0 auto;
                    color: #57606a;
                    font-size: 12px;
                    font-weight: 600;
                    white-space: nowrap;
                    align-self: center;
                }

                :global(.subjectChip:hover:not(:disabled)),
                :global(.subjectChip:focus-visible) {
                    border-color: #0969da;
                    color: #0969da;
                    outline: none;
                }

                :global(.subjectList) {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }

                :global(.subjectCard) {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    border: 1px solid #d0d7de;
                    border-radius: 8px;
                    background: #fff;
                    padding: 14px;
                }

                :global(.subjectCardHeader) {
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    gap: 12px;
                }

                :global(.subjectActionGroup) {
                    display: inline-flex;
                    flex: 0 0 auto;
                    gap: 8px;
                    align-items: center;
                    flex-wrap: wrap;
                    justify-content: flex-end;
                }

                :global(.subjectCardHeader h4),
                :global(.subjectCardHeader p) {
                    margin: 0;
                }

                :global(.subjectCardHeader h4) {
                    font-size: 18px;
                }

                :global(.subjectCardHeader p) {
                    margin-top: 4px;
                    color: #57606a;
                    font-size: 13px;
                }

                :global(.subjectSearchButton) {
                    border: 1px solid #0969da;
                    background: #eef6ff;
                    color: #0969da;
                    padding: 8px 10px;
                    border-radius: 6px;
                    font-weight: 700;
                    cursor: pointer;
                }

                :global(.subjectExpandButton),
                :global(.subjectUnfollowButton) {
                    border: 1px solid #d0d7de;
                    border-radius: 6px;
                    background: #f6f8fa;
                    padding: 8px 10px;
                    color: #1f2328;
                    font-weight: 700;
                }

                :global(.subjectExpandButton) {
                    border-color: rgb(8, 109, 177);
                    background: #fff;
                    color: rgb(8, 109, 177);
                }

                :global(.subjectPaperList) {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                }

                :global(.subjectPaperItem) {
                    border-top: 1px solid #d8dee4;
                    padding-top: 10px;
                }

                :global(.subjectPaperTitle) {
                    color: #1f2328;
                    font-weight: 700;
                    line-height: 1.45;
                }

                :global(.subjectPaperMeta) {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 8px;
                    margin-top: 4px;
                    color: #57606a;
                    font-size: 13px;
                }

                :global(.subjectPaperMeta a) {
                    color: rgb(8, 109, 177);
                    text-decoration: none;
                }

                :global(.subjectPaperAbstract),
                :global(.subjectEmptyText) {
                    margin: 6px 0 0;
                    color: #3f4650;
                    line-height: 1.55;
                }

                :global(.subjectPaperAbstract) {
                    display: -webkit-box;
                    overflow: hidden;
                    -webkit-box-orient: vertical;
                    -webkit-line-clamp: 3;
                }

                :global(.userCard) {
                    display: flex;
                    gap: 12px;
                    align-items: center;
                    justify-content: space-between;
                    border: 1px solid #d0d7de;
                    border-radius: 8px;
                    padding: 12px;
                    background: #fff;
                    cursor: pointer;
                    transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
                }

                :global(.userCard:hover),
                :global(.userCard:focus) {
                    border-color: #8c959f;
                    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
                    outline: none;
                    transform: translateY(-1px);
                }

                :global(.userCardProfile) {
                    display: grid;
                    grid-template-columns: 44px minmax(0, 1fr);
                    gap: 12px;
                    align-items: center;
                    min-width: 0;
                    flex: 1 1 auto;
                }

                :global(.userAvatar),
                :global(.userAvatar img) {
                    width: 44px;
                    height: 44px;
                    border-radius: 50%;
                }

                :global(.userAvatar) {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    overflow: hidden;
                    background: #eef6ff;
                    color: #0969da;
                    font-weight: 800;
                }

                :global(.userAvatar img) {
                    display: block;
                    object-fit: cover;
                }

                :global(.userText) {
                    min-width: 0;
                }

                :global(.userText h4),
                :global(.userText p) {
                    overflow: hidden;
                    margin: 0;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }

                :global(.userText h4) {
                    font-size: 16px;
                }

                :global(.userText p) {
                    color: #57606a;
                    font-size: 13px;
                }

                :global(.userFollowButtonShell) {
                    display: flex;
                    flex: 0 0 auto;
                    justify-self: end;
                }

                .mentorCard {
                    min-height: 158px;
                    padding: 14px;
                    border: 1px solid #ccc;
                    border-radius: 8px;
                    cursor: pointer;
                    background: #fff;
                    transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
                }

                .mentorCard:hover,
                .mentorCard:focus {
                    border-color: #666;
                    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
                    outline: none;
                    transform: translateY(-1px);
                }

                .mentorCardHeader {
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    gap: 12px;
                    margin-bottom: 8px;
                }

                .followButtonShell {
                    flex-shrink: 0;
                }

                .followToggleButton {
                    position: relative;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    min-width: 72px;
                    min-height: 28px;
                    border: 0 solid transparent;
                    border-radius: 6px;
                    background: rgb(8, 109, 177);
                    color: #ffffff;
                    padding: 0 12px;
                    font-size: 14px;
                    font-weight: 500;
                    line-height: 1;
                    white-space: nowrap;
                    overflow: hidden;
                    cursor: pointer;
                    box-shadow: none;
                    transition: none;
                    appearance: none;
                    opacity: 1;
                }

                .followToggleButton span {
                    color: inherit;
                }

                .followToggleButton:hover:not(:disabled),
                .followToggleButton:focus-visible {
                    transform: none;
                    box-shadow: none;
                }

                .followToggleButton:focus-visible {
                    outline: 2px solid rgba(8, 109, 177, 0.35);
                    outline-offset: 2px;
                }

                .followToggleButton:disabled {
                    opacity: 1;
                    cursor: not-allowed;
                }

                :global(.followToggleButtonOverlay) {
                    position: absolute;
                    inset: 0;
                    background: rgba(255, 255, 255, 0.55);
                }

                .mentorName {
                    margin: 0;
                    font-size: 18px;
                    line-height: 1.35;
                }

                .privateBadge {
                    margin-left: 8px;
                    font-size: 12px;
                    color: #555;
                    font-weight: 400;
                }

                .mentorMeta {
                    margin: 4px 0 0;
                    color: #333;
                    line-height: 1.45;
                    overflow-wrap: anywhere;
                    word-break: break-word;
                }

                @keyframes followSkeletonShimmer {
                    0% {
                        background-position: 200% 0;
                    }

                    100% {
                        background-position: -200% 0;
                    }
                }

                @media (max-width: 720px) {
                    .pageHeader {
                        align-items: stretch;
                        flex-direction: column;
                    }

                    .viewSwitch {
                        width: 100%;
                        min-width: 0;
                    }

                    .content {
                        grid-template-columns: 1fr;
                    }

                    .mentorGrid {
                        grid-template-columns: 1fr;
                    }

                    :global(.userSearch) {
                        flex-direction: column;
                    }

                    :global(.userSearch button) {
                        width: 100%;
                    }

                    :global(.userCard) {
                        align-items: flex-start;
                        flex-direction: column;
                    }

                    :global(.userCardProfile) {
                        grid-template-columns: 40px minmax(0, 1fr);
                        width: 100%;
                    }

                    :global(.userAvatar),
                    :global(.userAvatar img) {
                        width: 40px;
                        height: 40px;
                    }

                    :global(.userFollowButtonShell) {
                        justify-content: flex-start;
                        width: 100%;
                    }
                }
            `}</style>
        </div>
    );
};

export default FollowsPage;
