import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useRouter } from "next/router";

import { request } from "../utils/network";
import TimelinePage from "../pages/timeline";

// Mock Next.js routing so the timeline page can be rendered without the real
// router and any navigation side effects can be observed if needed.
jest.mock("next/router", () => ({
    useRouter: jest.fn(),
}));

// Mock the shared network helper so timeline overview, calendar metadata, and
// batched paper-feed responses can be controlled deterministically.
jest.mock("../utils/network", () => ({
    request: jest.fn(),
}));

describe("TimelinePage date mode", () => {
    const mockPush = jest.fn();

    // Builds a representative timeline paper record. Individual tests override
    // fields such as title, publish date, and per-day position to target
    // specific timeline-feed behaviors.
    const createPaper = (id, overrides = {}) => ({
        id,
        title: `Compression Paper ${id}`,
        abstract: "普通摘要。",
        tldr: "",
        arxiv_url: "https://arxiv.org/abs/1234.5678",
        publish_date: "2026-05-10",
        author_names: "Alice, Bob",
        mentor_ids: [1, 0],
        subjects: "cs.LG",
        day_sequence: id,
        day_total: 10,
        ...overrides,
    });

    // Helper for tests that need to hold requests open in order to inspect
    // loading placeholders or pending intermediate states.
    const createDeferred = () => {
        let resolve;
        let reject;
        const promise = new Promise((res, rej) => {
            resolve = res;
            reject = rej;
        });
        return { promise, resolve, reject };
    };

    // Mock payload for the timeline overview module, which defines available
    // research directions and the page-size policy.
    const mockTimelineOverview = (overrides = {}) => ({
        directions: [
            { direction: "机器学习", paper_count: 30 },
            { direction: "自然语言处理", paper_count: 8 },
        ],
        default_direction: "机器学习",
        page_size_default: 20,
        page_size_max: 100,
        ...overrides,
    });

    // Mock payload for the calendar metadata module, which determines the
    // current visible month, selectable dates, and date-range boundaries.
    const mockCalendarMeta = (overrides = {}) => ({
        direction: "机器学习",
        default_date: "2026-05-10",
        latest_date: "2026-05-10",
        earliest_date: "2026-05-08",
        available_dates: [
            { date: "2026-05-10", paper_count: 10 },
            { date: "2026-05-09", paper_count: 5 },
            { date: "2026-05-08", paper_count: 3 },
        ],
        ...overrides,
    });

    // Mock payload for a timeline feed batch. This shape is reused for the
    // initial load and for older/newer incremental loads.
    const timelineResponse = (papers, overrides = {}) => ({
        direction: "机器学习",
        limit: 6,
        total_papers: 18,
        has_newer: false,
        has_older: false,
        papers,
        ...overrides,
    });

    // Utility matcher for timeline API URLs that may vary by date/direction/
    // pagination parameters. This keeps URL assertions readable in the tests.
    const isTimelineUrl = (url, params = []) => (
        typeof url === "string"
        && url.startsWith("/api/timeline?")
        && params.every((param) => url.includes(param))
    );

    // Helper for asserting which calendar month/year the inline calendar is
    // currently showing to the user.
    const expectVisibleCalendarMonth = (yearLabel, monthLabel) => {
        const yearTrigger = screen.getByRole("button", { name: "选择年份" });
        const monthTrigger = screen.getByRole("button", { name: "选择月份" });
        expect(yearTrigger).toHaveTextContent(yearLabel);
        expect(monthTrigger).toHaveTextContent(monthLabel);
    };

    // Installs DOM geometry values for the virtual feed viewport so scrolling
    // and intersection-related logic can be tested in jsdom.
    const setupViewportGeometry = () => {
        const viewport = screen.getByTestId("timeline-feed-viewport");
        Object.defineProperty(viewport, "clientHeight", {
            configurable: true,
            value: 400,
        });
        Object.defineProperty(viewport, "scrollHeight", {
            configurable: true,
            value: 1200,
        });
        Object.defineProperty(viewport, "getBoundingClientRect", {
            configurable: true,
            value: () => ({
                top: 0,
                bottom: 400,
                left: 0,
                right: 0,
                width: 400,
                height: 400,
                x: 0,
                y: 0,
                toJSON: () => ({}),
            }),
        });
        return viewport;
    };

    // Helper for changing the mocked scrollTop of the feed viewport.
    const setViewportScrollTop = (viewport, scrollTop) => {
        Object.defineProperty(viewport, "scrollTop", {
            configurable: true,
            writable: true,
            value: scrollTop,
        });
    };

    // Helper for defining the vertical position and height of a paper card
    // within the feed, which drives "first visible paper" calculations.
    const setPaperGeometry = (paperId, offsetTop, offsetHeight = 180) => {
        const card = screen.getByTestId(`timeline-paper-${paperId}`);
        Object.defineProperty(card, "offsetTop", {
            configurable: true,
            value: offsetTop,
        });
        Object.defineProperty(card, "offsetHeight", {
            configurable: true,
            value: offsetHeight,
        });
        return card;
    };

    beforeEach(() => {
        // Reset router/network mocks and browser scrolling helpers before each
        // timeline scenario so feed state does not leak between tests.
        mockPush.mockReset();
        request.mockReset();
        window.scrollBy = jest.fn();
        window.scrollTo = jest.fn();
        Element.prototype.scrollIntoView = jest.fn();
        useRouter.mockReturnValue({
            push: mockPush,
        });
    });

    it("loads timeline overview, calendar metadata, and the default date batch", async () => {
        // Tests the initial timeline bootstrapping module.
        // On first render, the page should:
        // 1. load the overview for directions;
        // 2. load calendar metadata for the default direction;
        // 3. load the first batch of papers for the default date;
        // 4. render feed/date summary text based on that default day.
        const initialDeferred = createDeferred();
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return initialDeferred.promise;
            }
            return {};
        });

        render(<TimelinePage />);

        await waitFor(() => {
            expect(screen.getByTestId("timeline-calendar-panel")).toBeInTheDocument();
        });
        await act(async () => {
            initialDeferred.resolve(timelineResponse([
                createPaper(1, { title: "Compression Paper 1", day_sequence: 1, day_total: 6 }),
                createPaper(2, { title: "Compression Paper 2", day_sequence: 2, day_total: 6 }),
            ], {
                total_papers: 18,
                has_older: true,
            }));
        });

        await screen.findByRole("heading", { name: "Compression Paper 1" });
        expect(request).toHaveBeenCalledWith("/api/timeline", "GET", false);
        expect(request).toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&calendar=1", "GET", false);
        expect(request).toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&date=2026-05-10&limit=6", "GET", false);
        expect(screen.getByText("当前显示 2026-05-10 第 1-2 篇")).toBeInTheDocument();
        expect(screen.getByText("已选择 2026-05-10")).toBeInTheDocument();
    });

    it("keeps the feed header in skeleton state while the calendar request is still pending after overview load", async () => {
        // Tests partial-loading behavior between overview and calendar data.
        // Even after the overview loads, the feed header should remain in a
        // skeleton state until the calendar metadata request has completed.
        const calendarDeferred = createDeferred();
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return calendarDeferred.promise;
            }
            return {};
        });

        render(<TimelinePage />);

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/timeline", "GET", false);
        });

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&calendar=1", "GET", false);
        });

        expect(screen.getByTestId("timeline-feed-header-skeleton")).toBeInTheDocument();
        expect(screen.queryByText("共 0 篇")).not.toBeInTheDocument();
        expect(screen.queryByText("等待加载")).not.toBeInTheDocument();

        await act(async () => {
            calendarDeferred.resolve(mockCalendarMeta());
        });
    });

    it("renders calendar cells and disables dates without papers", async () => {
        // Tests the calendar-day rendering module.
        // Available dates should render as enabled buttons with counts and lead
        // styling, while dates with zero papers should stay disabled.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([createPaper(1)], { total_papers: 1 });
            }
            return {};
        });

        render(<TimelinePage />);

        await screen.findByRole("heading", { name: "Compression Paper 1" });
        expect(screen.getByTestId("timeline-calendar-panel")).toBeInTheDocument();
        expect(screen.queryByText("视口日期 2026-05-10")).not.toBeInTheDocument();
        expect(screen.getByTestId("timeline-calendar-day-2026-05-10")).toHaveAttribute("aria-disabled", "false");
        expect(screen.getByTestId("timeline-calendar-day-2026-05-10")).toHaveAttribute("aria-label", "2026-05-10 10 篇论文");
        expect(screen.getByTestId("timeline-calendar-day-2026-05-10")).toHaveClass("timelineCalendarDayButtonLead");
        expect(within(screen.getByTestId("timeline-calendar-day-2026-05-10")).getByText("10篇")).toBeInTheDocument();
        expect(screen.getByTestId("timeline-calendar-day-2026-05-11")).toHaveAttribute("aria-disabled", "true");
        expect(screen.getByTestId("timeline-calendar-day-2026-05-11")).toHaveAttribute("aria-label", "2026-05-11 0 篇论文");
    });

    it("switches to a clicked calendar day and reloads the feed for that exact date", async () => {
        // Tests the date-switching module driven by calendar clicks.
        // Selecting another available day should request that exact date's feed
        // batch and update the visible feed summary accordingly.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([createPaper(1, { title: "May10 Paper", day_sequence: 1, day_total: 1 })], { total_papers: 18 });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-09", "limit=6"])) {
                return timelineResponse([createPaper(2, {
                    title: "May09 Paper",
                    publish_date: "2026-05-09",
                    day_sequence: 1,
                    day_total: 1,
                })], {
                    total_papers: 18,
                    has_newer: true,
                    has_older: true,
                });
            }
            return {};
        });

        render(<TimelinePage />);

        await screen.findByRole("heading", { name: "May10 Paper" });
        fireEvent.click(screen.getByTestId("timeline-calendar-day-2026-05-09"));
        await screen.findByRole("heading", { name: "May09 Paper" });

        expect(request).toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&date=2026-05-09&limit=6", "GET", false);
        expect(screen.getByText("当前显示 2026-05-09 第 1-1 篇")).toBeInTheDocument();
    });

    it("loads older papers when the load-more preview enters the viewport", async () => {
        // Tests the incremental "load older papers" module.
        // When the load-more preview at the bottom enters the viewport, the
        // timeline should request an older batch using before_date/before_id.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([
                    createPaper(1, { day_sequence: 1, day_total: 2 }),
                    createPaper(2, { day_sequence: 2, day_total: 2 }),
                ], {
                    total_papers: 18,
                    has_older: true,
                });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "before_date=2026-05-10", "before_id=2", "limit=5"])) {
                return timelineResponse([
                    createPaper(3, {
                        title: "Older Paper 3",
                        publish_date: "2026-05-09",
                        day_sequence: 1,
                        day_total: 2,
                    }),
                    createPaper(4, {
                        title: "Older Paper 4",
                        publish_date: "2026-05-09",
                        day_sequence: 2,
                        day_total: 2,
                    }),
                ], {
                    total_papers: 18,
                    has_newer: true,
                    has_older: true,
                });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "Compression Paper 1" });

        const viewport = setupViewportGeometry();
        setViewportScrollTop(viewport, 200);
        setPaperGeometry(1, 0);
        setPaperGeometry(2, 900);

        const preview = screen.getByTestId("timeline-feed-load-more-preview");
        const firstPreviewCard = preview.querySelector("[data-load-more-preview-first='true']");
        Object.defineProperty(firstPreviewCard, "getBoundingClientRect", {
            configurable: true,
            value: () => ({
                top: 350,
                bottom: 520,
                left: 0,
                right: 0,
                width: 400,
                height: 170,
                x: 0,
                y: 350,
                toJSON: () => ({}),
            }),
        });

        act(() => {
            fireEvent.scroll(viewport);
        });

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&before_date=2026-05-10&before_id=2&limit=5", "GET", false);
        });
        expect(await screen.findByRole("heading", { name: "Older Paper 3" })).toBeInTheDocument();
    });

    it("loads newer papers only after top overscroll wheel intent at the viewport top", async () => {
        // Tests the guarded "load newer papers" module.
        // The page should not eagerly fetch newer items on any small upward
        // wheel movement. It should only do so after a strong overscroll-like
        // upward intent while already at the top of the viewport.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([
                    createPaper(9, {
                        title: "Current Day Paper",
                        publish_date: "2026-05-10",
                        day_sequence: 1,
                        day_total: 1,
                    }),
                ], {
                    total_papers: 18,
                    has_newer: true,
                    has_older: true,
                });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "after_date=2026-05-10", "after_id=9", "limit=5"])) {
                return timelineResponse([
                    createPaper(8, {
                        title: "Newer Paper 1",
                        publish_date: "2026-05-11",
                        day_sequence: 1,
                        day_total: 2,
                    }),
                    createPaper(7, {
                        title: "Newer Paper 2",
                        publish_date: "2026-05-11",
                        day_sequence: 2,
                        day_total: 2,
                    }),
                ], {
                    total_papers: 18,
                    has_newer: false,
                    has_older: true,
                });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "Current Day Paper" });

        const viewport = setupViewportGeometry();
        setViewportScrollTop(viewport, 0);
        setPaperGeometry(9, 0);

        act(() => {
            fireEvent.wheel(viewport, { deltaY: -20 });
        });
        expect(request).not.toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&after_date=2026-05-10&after_id=9&limit=5", "GET", false);

        act(() => {
            fireEvent.wheel(viewport, { deltaY: -80 });
        });

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&after_date=2026-05-10&after_id=9&limit=5", "GET", false);
        });
    });

    it("updates the visible date range based on the first visible paper in the viewport", async () => {
        // Tests the viewport-driven date summary module.
        // As the user scrolls, the header should update to reflect the date of
        // the first visible paper currently leading the viewport.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([
                    createPaper(1, { publish_date: "2026-05-10", day_sequence: 1, day_total: 2 }),
                    createPaper(2, { publish_date: "2026-05-10", day_sequence: 2, day_total: 2 }),
                    createPaper(3, { publish_date: "2026-05-09", day_sequence: 1, day_total: 1 }),
                ], {
                    total_papers: 18,
                    has_older: true,
                });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "Compression Paper 1" });

        const viewport = setupViewportGeometry();
        setPaperGeometry(1, 0, 120);
        setPaperGeometry(2, 130, 120);
        setPaperGeometry(3, 360, 120);

        expect(screen.getByText((content) => content.includes("当前显示 2026-05-10"))).toBeInTheDocument();

        setViewportScrollTop(viewport, 260);
        act(() => {
            fireEvent.scroll(viewport);
        });

        await waitFor(() => {
            expect(screen.getByText((content) => content.includes("当前显示 2026-05-09"))).toBeInTheDocument();
        });
    });

    it("auto switches the calendar month when the viewport date moves outside the current month", async () => {
        // Tests automatic calendar month synchronization with the feed viewport.
        // If scrolling makes a paper from another month become the leading
        // visible item, the calendar should automatically switch to that month.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta({
                    default_date: "2026-03-30",
                    latest_date: "2026-03-30",
                    available_dates: [
                        { date: "2026-03-30", paper_count: 3 },
                        { date: "2026-04-01", paper_count: 2 },
                    ],
                });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-03-30", "limit=6"])) {
                return timelineResponse([
                    createPaper(1, {
                        title: "March Paper",
                        publish_date: "2026-03-30",
                        day_sequence: 1,
                        day_total: 1,
                    }),
                    createPaper(2, {
                        title: "April Paper",
                        publish_date: "2026-04-01",
                        day_sequence: 1,
                        day_total: 1,
                    }),
                ], {
                    total_papers: 5,
                    has_older: true,
                });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "March Paper" });

        const viewport = setupViewportGeometry();
        setPaperGeometry(1, 0, 120);
        setPaperGeometry(2, 240, 120);
        setViewportScrollTop(viewport, 260);

        await waitFor(() => {
            expectVisibleCalendarMonth("2026年", "3月");
        });

        act(() => {
            fireEvent.scroll(viewport);
        });

        await waitFor(() => {
            expectVisibleCalendarMonth("2026年", "4月");
        });
        expect(screen.getByTestId("timeline-calendar-day-2026-04-01")).toHaveClass("timelineCalendarDayButtonLead");
    });

    it("does not snap the calendar month back immediately after manual month navigation", async () => {
        // Tests the manual-month-navigation protection module.
        // After the user explicitly switches the calendar month, the component
        // should not immediately override that choice with auto-sync behavior.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta({
                    default_date: "2026-03-30",
                    latest_date: "2026-03-30",
                    available_dates: [
                        { date: "2026-03-30", paper_count: 3 },
                        { date: "2026-04-01", paper_count: 2 },
                    ],
                });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-03-30", "limit=6"])) {
                return timelineResponse([
                    createPaper(1, {
                        title: "March Paper",
                        publish_date: "2026-03-30",
                        day_sequence: 1,
                        day_total: 1,
                    }),
                    createPaper(2, {
                        title: "April Paper",
                        publish_date: "2026-04-01",
                        day_sequence: 1,
                        day_total: 1,
                    }),
                ], {
                    total_papers: 5,
                    has_older: true,
                });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "March Paper" });

        fireEvent.click(screen.getByRole("button", { name: "查看下个月" }));

        await waitFor(() => {
            expectVisibleCalendarMonth("2026年", "4月");
        });
        expect(screen.getByRole("button", { name: "选择年份" })).toHaveTextContent("2026年");
        expect(screen.getByRole("button", { name: "选择月份" })).not.toHaveTextContent("3月");
    });

    it("opens the inline picker from year and month triggers with the current month preselected", async () => {
        // Tests the inline year/month picker opening module.
        // Clicking either trigger should open the picker and preselect the
        // currently visible year/month so the user sees the active context.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta({
                    available_dates: [
                        { date: "2025-12-01", paper_count: 2 },
                        { date: "2026-03-30", paper_count: 3 },
                        { date: "2026-04-01", paper_count: 2 },
                        { date: "2026-05-10", paper_count: 1 },
                    ],
                });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([createPaper(1)], { total_papers: 1 });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "Compression Paper 1" });

        fireEvent.click(screen.getByRole("button", { name: "选择年份" }));

        const picker = screen.getByTestId("timeline-calendar-picker");
        expect(picker).toBeInTheDocument();
        expect(within(screen.getByTestId("timeline-calendar-year-wheel")).getByRole("button", { name: "2026年" })).toHaveClass("timelineCalendarPickerOptionActive");
        expect(within(screen.getByTestId("timeline-calendar-month-wheel")).getByRole("button", { name: "5月" })).toHaveClass("timelineCalendarPickerOptionActive");

        fireEvent.click(within(picker).getByRole("button", { name: "取消" }));
        expect(screen.queryByTestId("timeline-calendar-picker")).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "选择月份" }));
        expect(screen.getByTestId("timeline-calendar-picker")).toBeInTheDocument();
    });

    it("derives year and month options from available dates and confirms month browsing without refetching papers", async () => {
        // Tests the picker option-derivation and browsing module.
        // The picker should only offer years/months that actually exist in
        // available_dates, and confirming a browsed month should update the
        // visible calendar month without re-fetching feed papers immediately.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta({
                    available_dates: [
                        { date: "2025-12-01", paper_count: 2 },
                        { date: "2026-03-30", paper_count: 3 },
                        { date: "2026-04-01", paper_count: 2 },
                        { date: "2026-05-10", paper_count: 1 },
                    ],
                });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([createPaper(1)], { total_papers: 1 });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "Compression Paper 1" });
        expect(screen.getByText("已选择 2026-05-10")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "选择年份" }));

        const yearWheel = screen.getByTestId("timeline-calendar-year-wheel");
        const monthWheel = screen.getByTestId("timeline-calendar-month-wheel");

        expect(within(yearWheel).getByRole("button", { name: "2025年" })).toBeInTheDocument();
        expect(within(yearWheel).getByRole("button", { name: "2026年" })).toBeInTheDocument();
        expect(within(monthWheel).queryByRole("button", { name: "1月" })).toBeNull();
        expect(within(monthWheel).getByRole("button", { name: "5月" })).toBeInTheDocument();

        fireEvent.click(within(yearWheel).getByRole("button", { name: "2025年" }));
        expect(within(monthWheel).getByRole("button", { name: "12月" })).toHaveClass("timelineCalendarPickerOptionActive");
        expect(within(monthWheel).queryByRole("button", { name: "5月" })).toBeNull();

        fireEvent.click(screen.getByRole("button", { name: "确定" }));

        await waitFor(() => {
            expectVisibleCalendarMonth("2025年", "12月");
        });
        expect(screen.getByText("已选择 2026-05-10")).toBeInTheDocument();
        expect(request).not.toHaveBeenCalledWith("/api/timeline?direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0&date=2025-12-01&limit=6", "GET", false);
    });

    it("closes the picker on escape and outside click without changing the visible month", async () => {
        // Tests non-destructive picker dismissal.
        // Escape and outside clicks should close the picker while preserving the
        // currently visible calendar month instead of committing changes.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta({
                    available_dates: [
                        { date: "2026-03-30", paper_count: 3 },
                        { date: "2026-04-01", paper_count: 2 },
                    ],
                });
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([createPaper(1)], { total_papers: 1 });
            }
            return {};
        });

        render(<TimelinePage />);
        await screen.findByRole("heading", { name: "Compression Paper 1" });

        fireEvent.click(screen.getByRole("button", { name: "选择月份" }));
        expect(screen.getByTestId("timeline-calendar-picker")).toBeInTheDocument();
        fireEvent.keyDown(document, { key: "Escape" });
        await waitFor(() => {
            expect(screen.queryByTestId("timeline-calendar-picker")).not.toBeInTheDocument();
        });
        expectVisibleCalendarMonth("2026年", "5月");

        fireEvent.click(screen.getByRole("button", { name: "选择月份" }));
        expect(screen.getByTestId("timeline-calendar-picker")).toBeInTheDocument();
        fireEvent.mouseDown(document.body);
        await waitFor(() => {
            expect(screen.queryByTestId("timeline-calendar-picker")).not.toBeInTheDocument();
        });
        expectVisibleCalendarMonth("2026年", "5月");
    });

    it("disables the year and month triggers when there are no selectable calendar months", async () => {
        // Tests the empty-calendar-month fallback module.
        // If no selectable months exist, the year/month picker triggers should
        // be disabled and must not open the picker dialog.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta({
                    default_date: "",
                    latest_date: "",
                    earliest_date: "",
                    available_dates: [],
                });
            }
            return {};
        });

        render(<TimelinePage />);
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "选择年份" })).toBeInTheDocument();
        });

        const yearTrigger = screen.getByRole("button", { name: "选择年份" });
        const monthTrigger = screen.getByRole("button", { name: "选择月份" });

        expect(yearTrigger).toBeDisabled();
        expect(monthTrigger).toBeDisabled();
        fireEvent.click(yearTrigger);
        expect(screen.queryByTestId("timeline-calendar-picker")).not.toBeInTheDocument();
    });

    it("renders inline LaTeX in titles and mentor links in author rows", async () => {
        // Tests paper-card content rendering inside the timeline feed.
        // This covers:
        // 1. KaTeX rendering for LaTeX inside paper titles and abstracts;
        // 2. mentor author names becoming links when mentor_ids exist;
        // 3. non-mentor authors remaining plain text.
        request.mockImplementation(async (url) => {
            if (url === "/api/timeline") {
                return mockTimelineOverview();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "calendar=1"])) {
                return mockCalendarMeta();
            }
            if (isTimelineUrl(url, ["direction=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0", "date=2026-05-10", "limit=6"])) {
                return timelineResponse([
                    createPaper(1, {
                        title: "Compression $x^2$ Paper",
                        author_names: "李四,赵云",
                        mentor_ids: [5, 0],
                        abstract: "摘要中有公式 $k$。",
                        day_sequence: 1,
                        day_total: 1,
                    }),
                ], {
                    total_papers: 1,
                });
            }
            return {};
        });

        const { container } = render(<TimelinePage />);

        await screen.findByText(/Compression/i);

        const titleHeading = container.querySelector("h4");
        expect(titleHeading?.querySelector(".katex")).not.toBeNull();
        expect(screen.queryByText(/\$x\^2\$/)).not.toBeInTheDocument();

        const mentorLink = screen.getByRole("link", { name: /李四/ });
        expect(mentorLink).toHaveAttribute("href", "/mentors/5");
        expect(within(mentorLink).getByAltText("清华导师")).toHaveAttribute("src", "/favicon_tsinghua.ico");
        expect(screen.getByText("赵云")).toBeInTheDocument();
        expect(screen.queryByRole("link", { name: "赵云" })).toBeNull();
    });
});
