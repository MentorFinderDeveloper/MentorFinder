import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { useRouter } from "next/router";

import authReducer from "../redux/auth";
import { request } from "../utils/network";
import FollowsPage from "../pages/follows";
import MentorDetailPage from "../pages/mentors/[id]";
import { normalizeSearchKeywordForUrl } from "../utils/searchQuery";

// Mock routing so tests can control the mentor id in the URL and inspect any
// navigation side effects without using the real Next.js router.
jest.mock("next/router", () => ({
    useRouter: jest.fn(),
}));

// Mock the shared network helper so follow-related requests can be fully
// controlled and asserted without relying on a live backend.
jest.mock("../utils/network", () => ({
    request: jest.fn(),
}));

describe("follow confirmation", () => {
    const mockPush = jest.fn();
    // Representative mentor fixture used across the follows page and mentor
    // detail page tests.
    const mentor = {
        id: 7,
        Chinese_name: "张三",
        English_name: "Zhang San",
        research_direction: "机器学习",
        email: "zhangsan@example.com",
        profile: "导师画像",
        is_private: false,
        paper_ids: [],
    };
    // Fixture representing a user who follows the current user.
    const follower = {
        id: 12,
        username: "fan_user",
        realName: "粉丝用户",
        role: "student",
        signature: "关注了我",
        followed: false,
    };
    // Fixture representing a user that the current user already follows.
    const followedUser = {
        id: 21,
        username: "followed_user",
        realName: "关注用户",
        role: "student",
        signature: "我关注的人",
        followed: true,
    };
    // Fixture representing a subject already followed by the current user.
    const followedSubject = {
        subject: "cs.AI",
        subjectName: "人工智能",
        paperCount: 2,
    };
    // Fixture representing an available subject that is not yet followed.
    const availableSubject = {
        subject: "cs.LG",
        subjectName: "机器学习",
        paperCount: 5,
        followed: false,
    };

    // Helper for tests that need manual control over when an async request
    // resolves, especially for skeleton-loading and pending-button scenarios.
    const createDeferred = () => {
        let resolve;
        let reject;
        const promise = new Promise((res, rej) => {
            resolve = res;
            reject = rej;
        });
        return { promise, resolve, reject };
    };

    // Shared render helper that provides the authenticated Redux state required
    // by the follow-related pages. These tests assume a logged-in student.
    const renderWithStore = (ui) => {
        const store = configureStore({
            reducer: {
                auth: authReducer,
            },
            preloadedState: {
                auth: {
                    name: "student_user",
                    token: "mock-token",
                    role: "student",
                },
            },
        });

        render(<Provider store={store}>{ui}</Provider>);
    };

    beforeEach(() => {
        // Reset timer mode, router state, and network spies before each test so
        // every scenario starts from a clean follow-page environment.
        jest.useRealTimers();
        mockPush.mockReset();
        request.mockReset();
        useRouter.mockReturnValue({
            push: mockPush,
            query: { id: "7" },
        });
    });

    afterEach(() => {
        jest.useRealTimers();
        jest.restoreAllMocks();
    });

    // The follows page keeps skeleton placeholders visible for a short minimum
    // duration. This helper advances fake timers past that threshold.
    const finishFollowSkeleton = async () => {
        await act(async () => {
            jest.advanceTimersByTime(800);
        });
    };

    it("loads only followed mentors on initial follows page entry", async () => {
        // Tests the initial follows-page data-loading module.
        // On first entry, the page should load the default "followed mentors"
        // tab only, without eagerly fetching followed users, subjects, or fans.
        request.mockImplementation(async (url) => {
            if (url === "/api/follow/counts") {
                return {
                    mentorCount: 1,
                    userCount: 0,
                    subjectCount: 0,
                    followerCount: 0,
                };
            }
            if (url === "/api/follow/mentors") {
                return { mentors: [mentor] };
            }

            return {};
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        expect(screen.getByRole("button", { name: "用户（0）" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "板块（0）" })).toBeInTheDocument();
        expect(request).toHaveBeenCalledWith("/api/follow/counts", "GET", true);
        expect(request).toHaveBeenCalledWith("/api/follow/mentors", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/users", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/available", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/followed", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/followers", "GET", true);
    });

    it("preloads sidebar counts without eagerly fetching unopened lists", async () => {
        request.mockImplementation(async (url) => {
            if (url === "/api/follow/counts") {
                return {
                    mentorCount: 1,
                    userCount: 2,
                    subjectCount: 51,
                    followerCount: 3,
                };
            }

            if (url === "/api/follow/mentors") {
                return { mentors: [mentor] };
            }

            return {};
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        expect(screen.getByRole("button", { name: "导师（1）" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "用户（2）" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "板块（51）" })).toBeInTheDocument();
        expect(request).toHaveBeenCalledWith("/api/follow/counts", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/users", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/available", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/followed", "GET", true);
    });

    it("lazy loads followed users with a skeleton when the user tab is first opened", async () => {
        // Tests the lazy-loading module for the followed-users tab.
        // The tab should request its data only when opened for the first time,
        // show a skeleton while waiting, and replace that skeleton with real
        // content after the minimum loading duration has passed.
        jest.useFakeTimers();
        const userDeferred = createDeferred();
        request.mockImplementation((url) => {
            if (url === "/api/follow/counts") {
                return Promise.resolve({ mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 });
            }
            if (url === "/api/follow/mentors") {
                return Promise.resolve({ mentors: [mentor] });
            }

            if (url === "/api/follow/users") {
                return userDeferred.promise;
            }

            return Promise.resolve({});
        });

        renderWithStore(<FollowsPage />);

        await finishFollowSkeleton();
        await screen.findByRole("heading", { name: "张三" });
        fireEvent.click(screen.getByRole("button", { name: "用户（0）" }));

        expect(await screen.findByTestId("follow-user-skeleton")).toBeInTheDocument();
        expect(request).toHaveBeenCalledWith("/api/follow/users", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/available", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/followed", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/followers", "GET", true);

        await act(async () => {
            userDeferred.resolve({ users: [followedUser] });
        });

        expect(screen.getByTestId("follow-user-skeleton")).toBeInTheDocument();
        await finishFollowSkeleton();
        await screen.findByText("我关注的人");
        expect(screen.queryByTestId("follow-user-skeleton")).not.toBeInTheDocument();
    });

    it("truncates overly long followed-user search keywords before searching", async () => {
        // Tests the user-search keyword-length guard on the follows page.
        // Long pasted input should be truncated in the textbox and in the
        // outgoing search request.
        request.mockImplementation((url) => {
            if (url === "/api/follow/mentors") {
                return Promise.resolve({ mentors: [mentor] });
            }

            if (url === "/api/follow/users") {
                return Promise.resolve({ users: [followedUser] });
            }

            if (url.startsWith("/api/search/users?keyword=")) {
                return Promise.resolve({ users: [follower] });
            }

            return Promise.resolve({});
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        fireEvent.click(screen.getByRole("button", { name: "用户（0）" }));

        await screen.findByRole("heading", { name: "关注用户" });

        const searchInput = screen.getByPlaceholderText("搜索用户名、姓名或邮箱");
        const longKeyword = "一".repeat(400);
        const truncatedKeyword = normalizeSearchKeywordForUrl(longKeyword);

        fireEvent.change(searchInput, { target: { value: longKeyword } });
        expect(searchInput).toHaveValue(truncatedKeyword);

        fireEvent.click(screen.getByRole("button", { name: "搜索用户" }));

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith(
                `/api/search/users?keyword=${encodeURIComponent(truncatedKeyword)}`,
                "GET",
                true,
            );
        });
    });

    it("lazy loads subject sections independently when the subject tab is first opened", async () => {
        // Tests the split subject-loading module.
        // The discoverable subject list and the followed-subject summaries
        // should load in parallel with separate skeletons so one can render
        // without waiting for the other.
        jest.useFakeTimers();
        const availableDeferred = createDeferred();
        const followedDeferred = createDeferred();
        request.mockImplementation((url) => {
            if (url === "/api/follow/counts") {
                return Promise.resolve({ mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 });
            }
            if (url === "/api/follow/mentors") {
                return Promise.resolve({ mentors: [mentor] });
            }

            if (url === "/api/follow/subjects/available") {
                return availableDeferred.promise;
            }

            if (url === "/api/follow/subjects/followed") {
                return followedDeferred.promise;
            }

            return Promise.resolve({});
        });

        renderWithStore(<FollowsPage />);

        await finishFollowSkeleton();
        await screen.findByRole("heading", { name: "张三" });
        fireEvent.click(screen.getByRole("button", { name: "板块（0）" }));

        expect(await screen.findByTestId("follow-subject-search-skeleton")).toBeInTheDocument();
        expect(await screen.findByTestId("follow-followed-subject-skeleton")).toBeInTheDocument();
        expect(request).toHaveBeenCalledWith("/api/follow/subjects/available", "GET", true);
        expect(request).toHaveBeenCalledWith("/api/follow/subjects/followed", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/users", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/followers", "GET", true);

        await act(async () => {
            followedDeferred.resolve({
                subjects: [followedSubject],
            });
        });

        await finishFollowSkeleton();
        await screen.findByRole("heading", { name: "人工智能" });
        expect(screen.getByTestId("follow-subject-search-skeleton")).toBeInTheDocument();
        expect(screen.queryByTestId("follow-followed-subject-skeleton")).not.toBeInTheDocument();

        await act(async () => {
            availableDeferred.resolve({
                availableSubjects: [availableSubject],
            });
        });

        await finishFollowSkeleton();
        await screen.findByText("机器学习");
        expect(screen.queryByTestId("follow-subject-search-skeleton")).not.toBeInTheDocument();
    });

    it("loads followed-subject papers only after the user expands one subject", async () => {
        request.mockImplementation(async (url) => {
            if (url === "/api/follow/counts") {
                return { mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 };
            }
            if (url === "/api/follow/mentors") {
                return { mentors: [mentor] };
            }

            if (url === "/api/follow/subjects/available") {
                return { availableSubjects: [availableSubject] };
            }

            if (url === "/api/follow/subjects/followed") {
                return { subjects: [followedSubject] };
            }

            if (url === "/api/follow/subjects/cs.AI/papers") {
                return {
                    subject: "cs.AI",
                    recentPapers: [
                        {
                            id: 101,
                            title: "New AI paper",
                            author_names: "Author A",
                            publish_date: "2026-05-01",
                            arxiv_url: "https://arxiv.org/abs/2501.00001",
                            abstract: "abstract",
                        },
                    ],
                };
            }

            return {};
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        fireEvent.click(screen.getByRole("button", { name: "板块（0）" }));
        await screen.findByRole("heading", { name: "人工智能" });

        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/cs.AI/papers", "GET", true);

        fireEvent.click(screen.getByRole("button", { name: "展开论文" }));

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/follow/subjects/cs.AI/papers", "GET", true);
        });
        await screen.findByText("New AI paper");
        expect(screen.getByText("Author A")).toBeInTheDocument();
    });

    it("lazy loads followers with a skeleton when the fans view is first opened", async () => {
        // Tests the lazy-loading module for the "my followers" view.
        // The fans list should be fetched only after the view switch changes,
        // and a dedicated follower skeleton should be shown during loading.
        jest.useFakeTimers();
        const followerDeferred = createDeferred();
        request.mockImplementation((url) => {
            if (url === "/api/follow/counts") {
                return Promise.resolve({ mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 });
            }
            if (url === "/api/follow/mentors") {
                return Promise.resolve({ mentors: [mentor] });
            }

            if (url === "/api/follow/followers") {
                return followerDeferred.promise;
            }

            return Promise.resolve({});
        });

        renderWithStore(<FollowsPage />);

        await finishFollowSkeleton();
        await screen.findByRole("heading", { name: "张三" });
        const viewSwitch = screen.getByRole("group", { name: "关注页面切换" });
        fireEvent.click(within(viewSwitch).getByRole("button", { name: /我的粉丝/ }));

        expect(await screen.findByTestId("follow-follower-skeleton")).toBeInTheDocument();
        expect(request).toHaveBeenCalledWith("/api/follow/followers", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/users", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/available", "GET", true);
        expect(request).not.toHaveBeenCalledWith("/api/follow/subjects/followed", "GET", true);

        await act(async () => {
            followerDeferred.resolve({ users: [follower] });
        });

        expect(screen.getByTestId("follow-follower-skeleton")).toBeInTheDocument();
        await finishFollowSkeleton();
        await screen.findByRole("heading", { name: "粉丝用户" });
        expect(screen.queryByTestId("follow-follower-skeleton")).not.toBeInTheDocument();
    });

    it("does not refetch a lazily loaded tab when revisiting it", async () => {
        // Tests tab-level caching for lazily loaded follow data.
        // Once the followed-users tab has been loaded, returning to that tab
        // later should reuse the existing data instead of sending another GET.
        request.mockImplementation(async (url) => {
            if (url === "/api/follow/counts") {
                return { mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 };
            }
            if (url === "/api/follow/mentors") {
                return { mentors: [mentor] };
            }

            if (url === "/api/follow/users") {
                return { users: [followedUser] };
            }

            return {};
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        fireEvent.click(screen.getByRole("button", { name: "用户（0）" }));
        await screen.findByRole("heading", { name: "关注用户" });
        fireEvent.click(screen.getByRole("button", { name: "导师（1）" }));
        fireEvent.click(screen.getByRole("button", { name: "用户（1）" }));

        await waitFor(() => {
            const userRequests = request.mock.calls.filter(([url, method]) => (
                url === "/api/follow/users" && method === "GET"
            ));
            expect(userRequests).toHaveLength(1);
        });
    });

    it("shows direct unfollow buttons on follows page and updates card state without refetching the list", async () => {
        // Tests the direct unfollow interaction on the follows page.
        // Clicking the "already followed" button should immediately send a
        // DELETE request and update the card/count state locally, without
        // reloading the whole mentor list from the backend.
        request.mockImplementation(async (url, method) => {
            if (url === "/api/follow/counts") {
                return { mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 };
            }
            if (url === "/api/follow/mentors/7" && method === "DELETE") {
                return { followed: false };
            }

            return { mentors: [mentor] };
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        expect(screen.getByRole("button", { name: "导师（1）" })).toBeInTheDocument();
        const mentorCardHeader = screen.getByTestId("mentor-card-header-7");
        expect(within(mentorCardHeader).getByRole("heading", { name: "张三" })).toBeInTheDocument();
        expect(within(mentorCardHeader).getByRole("button", { name: "已关注" })).toBeInTheDocument();

        const followButton = screen.getByRole("button", { name: "已关注" });
        fireEvent.click(followButton);

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/follow/mentors/7", "DELETE", true);
        });
        expect(screen.getByRole("button", { name: "关注" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "导师（0）" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "张三" })).toBeInTheDocument();
    });

    it("refollows a kept mentor card on follows page without reloading layout", async () => {
        // Tests the local re-follow module on an existing mentor card.
        // After unfollowing, the same card should remain in place and support
        // re-following via POST without rebuilding the page layout.
        request.mockImplementation(async (url, method) => {
            if (url === "/api/follow/counts") {
                return { mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 };
            }
            if (url === "/api/follow/mentors/7" && method === "DELETE") {
                return { followed: false };
            }

            if (url === "/api/follow/mentors/7" && method === "POST") {
                return { followed: true };
            }

            return { mentors: [mentor] };
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        fireEvent.click(screen.getByRole("button", { name: "已关注" }));

        await waitFor(() => {
            expect(screen.getByRole("button", { name: "关注" })).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole("button", { name: "关注" }));

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/follow/mentors/7", "POST", true);
        });
        expect(screen.getByRole("button", { name: "已关注" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "导师（1）" })).toBeInTheDocument();
    });

    it("disables the follows page button and keeps its label while request is pending", async () => {
        // Tests the pending-request UI state for follow toggles on the follows
        // page. During an in-flight unfollow request, the button should become
        // disabled, keep its original label, and show the loading overlay.
        let resolveFollow;
        request.mockImplementation((url, method) => {
            if (url === "/api/follow/counts") {
                return Promise.resolve({ mentorCount: 1, userCount: 0, subjectCount: 0, followerCount: 0 });
            }
            if (url === "/api/follow/mentors/7" && method === "DELETE") {
                return new Promise((resolve) => {
                    resolveFollow = resolve;
                });
            }

            return Promise.resolve({ mentors: [mentor] });
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "张三" });
        const followButton = screen.getByRole("button", { name: "已关注" });
        fireEvent.click(followButton);

        expect(followButton).toBeDisabled();
        expect(within(followButton).getByText("已关注")).toBeInTheDocument();
        expect(followButton.querySelector(".followToggleButtonOverlay")).not.toBeNull();

        resolveFollow?.({ followed: false });

        await waitFor(() => {
            expect(screen.getByRole("button", { name: "关注" })).toBeEnabled();
        });
    });

    it("shows followers in the fans tab", async () => {
        // Tests the rendered content module for the fans view after loading.
        // Once the user switches to "my followers", the page should show the
        // followers heading, follower card content, and request the right API.
        request.mockImplementation(async (url) => {
            if (url === "/api/follow/counts") {
                return { mentorCount: 0, userCount: 0, subjectCount: 0, followerCount: 1 };
            }
            if (url === "/api/follow/mentors") {
                return { mentors: [] };
            }

            if (url === "/api/follow/users") {
                return { users: [] };
            }

            if (url === "/api/follow/followers") {
                return { users: [follower] };
            }

            return {};
        });

        renderWithStore(<FollowsPage />);

        const viewSwitch = await screen.findByRole("group", { name: "关注页面切换" });
        fireEvent.click(within(viewSwitch).getByRole("button", { name: /我的粉丝/ }));

        expect(screen.getByRole("heading", { name: "我的粉丝" })).toBeInTheDocument();
        expect(await screen.findByRole("heading", { name: "粉丝用户" })).toBeInTheDocument();
        expect(screen.getByText("关注了我")).toBeInTheDocument();
        expect(request).toHaveBeenCalledWith("/api/follow/followers", "GET", true);
    });

    it("directly unfollows from mentor detail page without confirmation", async () => {
        // Tests the mentor-detail follow toggle module.
        // On the mentor detail page, unfollowing should happen immediately
        // through the button itself, without an extra confirmation dialog.
        request.mockImplementation(async (url, method) => {
            if (url === "/api/dataset/mentors/7") {
                return { mentor };
            }

            if (url === "/api/follow/mentors" && method === "GET") {
                return { mentors: [mentor] };
            }

            if (url === "/api/follow/mentors/7" && method === "DELETE") {
                return { followed: false };
            }

            return {};
        });

        renderWithStore(<MentorDetailPage />);

        await screen.findByRole("heading", { name: "张三" });
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "已关注" })).toBeEnabled();
        });

        fireEvent.click(screen.getByRole("button", { name: "已关注" }));

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/follow/mentors/7", "DELETE", true);
        });
        expect(screen.getByRole("button", { name: "关注" })).toBeInTheDocument();
    });

    it("shows loading overlay state while follow request is pending on mentor detail page", async () => {
        // Tests the pending-request UI state for the mentor detail follow
        // button. While a follow request is unresolved, the button should be
        // disabled and show the loading overlay until the request completes.
        let resolveFollow;
        request.mockImplementation((url, method) => {
            if (url === "/api/dataset/mentors/7") {
                return Promise.resolve({ mentor });
            }

            if (url === "/api/follow/mentors" && method === "GET") {
                return Promise.resolve({ mentors: [] });
            }

            if (url === "/api/follow/mentors/7" && method === "POST") {
                return new Promise((resolve) => {
                    resolveFollow = resolve;
                });
            }

            return Promise.resolve({});
        });

        renderWithStore(<MentorDetailPage />);

        await screen.findByRole("heading", { name: "张三" });
        const followButton = await screen.findByRole("button", { name: "关注" });

        fireEvent.click(followButton);

        expect(followButton).toBeDisabled();
        expect(within(followButton).getByText("关注")).toBeInTheDocument();
        expect(followButton.querySelector(".followToggleButtonOverlay")).not.toBeNull();

        resolveFollow?.({ followed: true });

        await waitFor(() => {
            expect(screen.getByRole("button", { name: "已关注" })).toBeEnabled();
        });
    });

    it("paginates followed mentor cards at the bottom with 18 cards per page", async () => {
        // Tests the pagination module for followed mentors.
        // The follows page should render at most 18 mentor cards per page,
        // expose pagination controls, and switch to the remaining items when
        // the user navigates to the next page.
        const mentorList = Array.from({ length: 19 }, (_, index) => ({
            ...mentor,
            id: index + 1,
            Chinese_name: `导师${index + 1}`,
            English_name: `Mentor ${index + 1}`,
            email: `mentor${index + 1}@example.com`,
        }));

        request.mockImplementation(async (url) => {
            if (url === "/api/follow/mentors") {
                return { mentors: mentorList };
            }

            if (url === "/api/follow/users" || url === "/api/follow/followers") {
                return { users: [] };
            }

            return {};
        });

        renderWithStore(<FollowsPage />);

        await screen.findByRole("heading", { name: "导师1" });
        expect(screen.getAllByTestId(/mentor-card-header-/)).toHaveLength(18);
        expect(screen.queryByRole("heading", { name: "导师19" })).not.toBeInTheDocument();
        expect(screen.getAllByRole("button", { name: "跳转" })).toHaveLength(1);

        fireEvent.click(screen.getByRole("button", { name: "2" }));

        await screen.findByRole("heading", { name: "导师19" });
        expect(screen.getAllByTestId(/mentor-card-header-/)).toHaveLength(1);
        expect(screen.queryByRole("heading", { name: "导师1" })).not.toBeInTheDocument();
    });
});
