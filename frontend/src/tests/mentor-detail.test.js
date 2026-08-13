import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { useRouter } from "next/router";

import authReducer from "../redux/auth";
import { request } from "../utils/network";
import MentorDetailPage from "../pages/mentors/[id]";

// Mock Next.js routing so tests can control the mentor id in the URL and
// inspect navigation behavior without depending on the real router runtime.
jest.mock("next/router", () => ({
    useRouter: jest.fn(),
}));

// Mock the shared request helper so mentor-detail data, follow state, and AI
// analysis responses can be fully controlled by the tests.
jest.mock("../utils/network", () => ({
    request: jest.fn(),
}));

describe("MentorDetailPage search return", () => {
    const mockPush = jest.fn();
    const mockBack = jest.fn();
    // Representative mentor fixture covering profile text, metadata, and both
    // linked and unlinked related-paper cases.
    const mentor = {
        id: 88,
        Chinese_name: "测试导师",
        English_name: "Test Mentor",
        research_direction: "知识工程",
        email: "test@example.com",
        profile: "教育背景\n本科毕业于测试大学\n研究概况\n长期从事知识工程研究",
        is_private: false,
        paper_ids: [{
            id: 1,
            title: "Test Paper With Link",
            author_names: "测试导师",
            arxiv_id: "1234.5678",
            arxiv_url: "https://arxiv.org/abs/1234.5678",
        }, {
            id: 2,
            title: "Test Paper Without Link",
            author_names: "测试导师",
        }],
    };

    // Shared render helper that mounts the mentor detail page with a logged-in
    // student auth state, which is required by the page's follow-related logic.
    const renderWithStore = () => {
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

        return render(
            <Provider store={store}>
                <MentorDetailPage />
            </Provider>,
        );
    };

    beforeEach(() => {
        // Reset navigation mocks, clear browser state used by "return to
        // search", and install the default mentor-detail API responses.
        mockPush.mockReset();
        mockBack.mockReset();
        request.mockReset();
        window.sessionStorage.clear();
        window.history.replaceState({ key: "mentor-entry-88" }, "", "/mentors/88");

        useRouter.mockReturnValue({
            push: mockPush,
            back: mockBack,
            query: { id: "88" },
        });

        request.mockImplementation(async (url, method) => {
            if (url === "/api/dataset/mentors/88" && method === "GET") {
                return { mentor };
            }

            if (url === "/api/follow/mentors" && method === "GET") {
                return { mentors: [] };
            }

            return {};
        });

        mockPush.mockImplementation(async () => true);
        mockBack.mockImplementation(async () => true);
    });

    it("uses router.back when returning to search with a valid search-origin marker", async () => {
        // Tests the search-return restoration module.
        // If sessionStorage contains a valid marker proving this detail page was
        // opened from the search page, the "return to search" button should use
        // router.back() to preserve the user's actual search history state.
        window.sessionStorage.setItem("search-mentor-return-marker", JSON.stringify({
            mentorId: 88,
            sourceEntryKey: "search-entry-1",
            targetEntryKey: "mentor-entry-88",
            sourcePath: "/search",
        }));

        renderWithStore();

        await screen.findByRole("heading", { name: "测试导师" });
        const sidebar = screen.getByRole("complementary", { name: "导师信息" });
        const returnButton = screen.getByRole("button", { name: "返回检索" });
        expect(returnButton.querySelector('img[src="/return_back_arrow.ico"]')).not.toBeNull();
        expect(screen.getAllByRole("button", { name: "返回检索" })).toHaveLength(1);
        expect(within(sidebar).queryByRole("button", { name: "返回检索" })).not.toBeInTheDocument();
        fireEvent.click(returnButton);

        await waitFor(() => {
            expect(mockBack).toHaveBeenCalledTimes(1);
        });
        expect(mockPush).not.toHaveBeenCalledWith("/search");
    });

    it("falls back to /search when no valid search-origin marker exists", async () => {
        // Tests the fallback navigation module for returning from mentor detail.
        // Without a valid search-origin marker, the page should push the user
        // to `/search` directly instead of trying to navigate back blindly.
        renderWithStore();

        await screen.findByRole("heading", { name: "测试导师" });
        const sidebar = screen.getByRole("complementary", { name: "导师信息" });
        const returnButton = screen.getByRole("button", { name: "返回检索" });
        expect(returnButton.querySelector('img[src="/return_back_arrow.ico"]')).not.toBeNull();
        expect(screen.getAllByRole("button", { name: "返回检索" })).toHaveLength(1);
        expect(within(sidebar).queryByRole("button", { name: "返回检索" })).not.toBeInTheDocument();
        fireEvent.click(returnButton);

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith("/search");
        });
        expect(mockBack).not.toHaveBeenCalled();
    });

    it("renders related papers with arxiv links and plain-text fallback", async () => {
        // Tests the main mentor-detail content rendering module.
        // This covers:
        // 1. the right-side mentor information sidebar;
        // 2. the left AI analysis sidebar shell;
        // 3. profile-section formatting and highlighted headings;
        // 4. related-paper rendering with arXiv links when available and
        //    plain-text fallback when links are missing.
        renderWithStore();

        await screen.findByRole("heading", { name: "测试导师" });

        const aiSidebar = screen.getByRole("complementary", { name: "AI 分析" });
        expect(within(aiSidebar).getByText("AI 分析")).toBeInTheDocument();
        expect(within(aiSidebar).getByRole("button", { name: "AI分析最近研究方向" })).toBeInTheDocument();

        const sidebar = screen.getByRole("complementary", { name: "导师信息" });
        expect(within(sidebar).getByText("导师信息")).toBeInTheDocument();
        expect(within(sidebar).getByText("英文名")).toBeInTheDocument();
        expect(within(sidebar).getByText("研究方向")).toBeInTheDocument();
        expect(within(sidebar).getByText("邮箱")).toBeInTheDocument();
        expect(within(sidebar).getByText("Test Mentor")).toBeInTheDocument();
        expect(within(sidebar).getByText("知识工程")).toBeInTheDocument();
        expect(within(sidebar).getByText("test@example.com")).toBeInTheDocument();
        expect(sidebar.querySelector('img[src="/English_Name.ico"]')).not.toBeNull();
        expect(sidebar.querySelector('img[src="/Reseach_Direction.ico"]')).not.toBeNull();
        expect(sidebar.querySelector('img[src="/Email.ico"]')).not.toBeNull();

        expect(screen.queryByText("英文名：Test Mentor")).not.toBeInTheDocument();
        expect(screen.queryByText("研究方向：知识工程")).not.toBeInTheDocument();
        expect(screen.queryByText("邮箱：test@example.com")).not.toBeInTheDocument();

        expect(screen.getByText("相关论文：")).toBeInTheDocument();
        expect(screen.queryByText("关联论文：")).not.toBeInTheDocument();
        expect(screen.getByText("导师画像")).toBeInTheDocument();
        expect(screen.queryByText("导师画像：")).not.toBeInTheDocument();
        expect(document.querySelector('img[src="/Mentor_Profile.ico"]')).not.toBeNull();
        expect(screen.getByText("本科毕业于测试大学")).toBeInTheDocument();
        expect(screen.getByText("长期从事知识工程研究")).toBeInTheDocument();
        expect(screen.getByText("教育背景")).toHaveAttribute("data-highlighted-profile-heading", "true");
        expect(screen.getByText("研究概况")).toHaveAttribute("data-highlighted-profile-heading", "true");
        expect(screen.getByText("本科毕业于测试大学")).not.toHaveAttribute("data-highlighted-profile-heading");

        const linkedPaper = screen.getByRole("link", { name: /Test Paper With Link/ });
        expect(linkedPaper).toHaveAttribute("href", "https://arxiv.org/abs/1234.5678");
        expect(linkedPaper).toHaveAttribute("target", "_blank");
        expect(linkedPaper).toHaveAttribute("rel", "noreferrer");

        const linkedPaperIcon = linkedPaper.querySelector("img");
        expect(linkedPaperIcon).not.toBeNull();
        expect(linkedPaperIcon).toHaveAttribute("src", "/arxiv.ico");

        expect(screen.getByText("Test Paper Without Link")).toBeInTheDocument();
        expect(screen.queryByRole("link", { name: /Test Paper Without Link/ })).not.toBeInTheDocument();
    });

    it("renders empty related-paper state when the mentor has no papers", async () => {
        // Tests the empty-state module for related papers.
        // If the mentor has no associated papers, the page should render the
        // explicit "no related papers" message instead of an empty list.
        request.mockImplementation(async (url, method) => {
            if (url === "/api/dataset/mentors/88" && method === "GET") {
                return {
                    mentor: {
                        ...mentor,
                        paper_ids: [],
                    },
                };
            }

            if (url === "/api/follow/mentors" && method === "GET") {
                return { mentors: [] };
            }

            return {};
        });

        renderWithStore();

        await screen.findByRole("heading", { name: "测试导师" });
        expect(screen.getByText("暂无相关论文")).toBeInTheDocument();
    });

    it("shows fallback text when the english name is missing in the sidebar", async () => {
        // Tests sidebar fallback rendering for missing mentor metadata.
        // When the English name is absent, the page should show the dedicated
        // placeholder text rather than leaving the field blank.
        request.mockImplementation(async (url, method) => {
            if (url === "/api/dataset/mentors/88" && method === "GET") {
                return {
                    mentor: {
                        ...mentor,
                        English_name: "",
                    },
                };
            }

            if (url === "/api/follow/mentors" && method === "GET") {
                return { mentors: [] };
            }

            return {};
        });

        renderWithStore();

        await screen.findByRole("heading", { name: "测试导师" });
        const sidebar = screen.getByRole("complementary", { name: "导师信息" });
        expect(within(sidebar).getByText("暂无英文名")).toBeInTheDocument();
    });

    it("renders recent direction analysis in the left ai sidebar after clicking the button", async () => {
        // Tests the AI recent-direction analysis module.
        // After the user triggers AI analysis, the left sidebar should display
        // the returned summary, metadata, and the paper list used to generate
        // that analysis.
        request.mockImplementation(async (url, method) => {
            if (url === "/api/dataset/mentors/88" && method === "GET") {
                return { mentor };
            }

            if (url === "/api/follow/mentors" && method === "GET") {
                return { mentors: [] };
            }

            if (url === "/api/dataset/mentors/88/recent-direction-analysis" && method === "POST") {
                return {
                    mentorId: 88,
                    mentorName: "测试导师",
                    paperCount: 2,
                    generatedBy: "rule",
                    analysis: "该导师近一年主要聚焦知识工程与推理建模。",
                    papers: [{
                        id: 11,
                        title: "Analysis Paper One",
                        publish_date: "2025-01-01",
                    }, {
                        id: 12,
                        title: "Analysis Paper Two",
                        publish_date: "2025-02-02",
                    }],
                };
            }

            return {};
        });

        renderWithStore();

        await screen.findByRole("heading", { name: "测试导师" });
        const aiSidebar = screen.getByRole("complementary", { name: "AI 分析" });

        fireEvent.click(within(aiSidebar).getByRole("button", { name: "AI分析最近研究方向" }));

        await waitFor(() => {
            expect(within(aiSidebar).getByText("最近研究方向分析")).toBeInTheDocument();
        });
        expect(within(aiSidebar).getByText("近一年论文数：2 ｜ 生成方式：rule")).toBeInTheDocument();
        expect(within(aiSidebar).getByText("该导师近一年主要聚焦知识工程与推理建模。")).toBeInTheDocument();
        expect(within(aiSidebar).getByText("本次分析使用的论文：")).toBeInTheDocument();
        expect(within(aiSidebar).getByText("Analysis Paper One（2025-01-01）")).toBeInTheDocument();
        expect(within(aiSidebar).getByText("Analysis Paper Two（2025-02-02）")).toBeInTheDocument();
    });

    it("shows the ai analysis loading state inside the left sidebar", async () => {
        // Tests the in-progress loading state for AI analysis.
        // While the recent-direction request is pending, the AI button should
        // become disabled and the sidebar should show status text explaining
        // that paper titles/abstracts are being processed.
        let resolveAnalysis;
        request.mockImplementation((url, method) => {
            if (url === "/api/dataset/mentors/88" && method === "GET") {
                return Promise.resolve({ mentor });
            }

            if (url === "/api/follow/mentors" && method === "GET") {
                return Promise.resolve({ mentors: [] });
            }

            if (url === "/api/dataset/mentors/88/recent-direction-analysis" && method === "POST") {
                return new Promise((resolve) => {
                    resolveAnalysis = resolve;
                });
            }

            return Promise.resolve({});
        });

        renderWithStore();

        await screen.findByRole("heading", { name: "测试导师" });
        const aiSidebar = screen.getByRole("complementary", { name: "AI 分析" });

        fireEvent.click(within(aiSidebar).getByRole("button", { name: "AI分析最近研究方向" }));

        expect(within(aiSidebar).getByRole("button", { name: "AI正在分析近一年论文，请稍候..." })).toBeDisabled();
        expect(within(aiSidebar).getByText("正在读取该导师近一年论文的题目和摘要并生成总结，请稍候...")).toBeInTheDocument();

        resolveAnalysis?.({
            mentorId: 88,
            mentorName: "测试导师",
            paperCount: 2,
            generatedBy: "rule",
            analysis: "完成分析",
            papers: [],
        });

        await waitFor(() => {
            expect(within(aiSidebar).getByText("近一年论文数：2 ｜ 生成方式：rule")).toBeInTheDocument();
        });
    });
});
