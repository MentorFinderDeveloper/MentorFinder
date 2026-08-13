import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";

import HomeScreen, { WeeklyPushDetailCard } from "../pages/index";
import authReducer from "../redux/auth";
import { request } from "../utils/network";

// Mock the shared request helper so homepage data-loading flows can be fully
// controlled and asserted without contacting the real backend.
jest.mock("../utils/network", () => ({
    request: jest.fn(),
}));

// Helper for manually resolving asynchronous requests in loading-state tests.
// This is used when the test needs to observe the UI before and after a
// network response arrives.
const createDeferred = () => {
    let resolve;
    let reject;
    const promise = new Promise((promiseResolve, promiseReject) => {
        resolve = promiseResolve;
        reject = promiseReject;
    });

    return { promise, resolve, reject };
};

describe("HomeScreen weekly paper abstracts", () => {
    // Builds a minimal public weekly-push payload. Individual tests override
    // fields such as title, abstract, or tldr to target specific render cases.
    const buildWeeklyPush = (paperOverrides = {}, pushOverrides = {}) => ({
        weekStart: "2026-05-01",
        weekEnd: "2026-05-07",
        paperCount: 1,
        title: "本周论文速递",
        fixedSummary: "",
        aiSummary: "",
        content: "本周周报正文保持纯文本。",
        generatedBy: "rule",
        updatedAt: "2026-05-12 12:00:00",
        papers: [{
            id: 1,
            title: "Weekly Paper",
            publishDate: "2026-05-01",
            authorNames: "Alice, Bob",
            arxivUrl: "https://arxiv.org/abs/2501.00001",
            arxivId: "2501.00001",
            abstract: "默认摘要",
            tldr: "",
            ...paperOverrides,
        }],
        ...pushOverrides,
    });

    // Shared render helper for the homepage with Redux auth state.
    // Most tests in this block do not require a logged-in user, but the helper
    // keeps the setup consistent and allows auth fields to be overridden.
    const renderWithStore = (name = "", authOverrides = {}) => {
        const store = configureStore({
            reducer: {
                auth: authReducer,
            },
            preloadedState: {
                auth: {
                    name,
                    token: "",
                    role: "",
                    ...authOverrides,
                },
            },
        });

        return render(
            <Provider store={store}>
                <HomeScreen />
            </Provider>,
        );
    };

    beforeEach(() => {
        // Reset the network mock and install the default homepage data
        // responses before each test in this block.
        request.mockReset();
        request.mockImplementation(async (url) => {
            if (url === "/api/dataset/weekly-push/latest") {
                return {
                    weeklyPush: buildWeeklyPush(),
                };
            }

            if (url === "/api/dataset/weekly-push/history") {
                return {
                    history: [{
                        weekStart: "2026-05-01",
                        weekEnd: "2026-05-07",
                        title: "本周论文速递",
                        paperCount: 1,
                        generatedBy: "rule",
                        updatedAt: "2026-05-12 12:00:00",
                    }],
                };
            }

            if (url === "/api/dataset/weekly-push/latest?week_start=2026-05-01") {
                return {
                    weeklyPush: buildWeeklyPush(),
                };
            }

            return {};
        });
    });

    it("renders plain weekly paper abstracts unchanged when no LaTeX is present", async () => {
        // Tests the plain-text abstract rendering module.
        // If a weekly paper abstract contains no LaTeX syntax, the homepage
        // should render the text directly without creating KaTeX nodes.
        const { container } = renderWithStore();

        await screen.findByText("本周论文");

        expect(screen.getByText("默认摘要")).toBeInTheDocument();
        expect(container.querySelector(".homeWeeklyPaperAbstractContent")).not.toBeNull();
        expect(container.querySelector(".katex")).toBeNull();
    });

    it("renders public weekly summaries as separate overview and ai blocks", async () => {
        // Tests the public weekly-push summary split layout.
        // When the backend returns distinct fixedSummary and aiSummary fields,
        // the homepage should render them as separate front-end blocks instead
        // of displaying the composed content string with the raw marker.
        request.mockImplementation(async (url) => {
            if (url === "/api/dataset/weekly-push/latest" || url === "/api/dataset/weekly-push/latest?week_start=2026-05-01") {
                return {
                    weeklyPush: buildWeeklyPush(
                        {},
                        {
                            fixedSummary: "规则摘要：本周主要集中在多模态与智能体方向。",
                            aiSummary: "AI 摘要：研究热点进一步向推理、协作与部署效率收敛。",
                            content: "规则摘要：本周主要集中在多模态与智能体方向。\n\n【AI总结】\nAI 摘要：研究热点进一步向推理、协作与部署效率收敛。",
                        },
                    ),
                };
            }

            if (url === "/api/dataset/weekly-push/history") {
                return {
                    history: [],
                };
            }

            return {};
        });

        renderWithStore();

        expect(await screen.findByText("周概览")).toBeInTheDocument();
        expect(screen.getByText("AI总结")).toBeInTheDocument();
        expect(screen.getByText("规则摘要：本周主要集中在多模态与智能体方向。")).toBeInTheDocument();
        expect(screen.getByText("AI 摘要：研究热点进一步向推理、协作与部署效率收敛。")).toBeInTheDocument();
        expect(screen.queryByText("【AI总结】")).not.toBeInTheDocument();
    });

    it("renders inline LaTeX in weekly paper abstracts", async () => {
        // Tests inline LaTeX parsing inside paper abstracts.
        // Inline formulas should be transformed into rendered KaTeX output, and
        // the original raw `$...$` source should no longer appear in the DOM.
        request.mockImplementation(async (url) => {
            if (url === "/api/dataset/weekly-push/latest") {
                return {
                    weeklyPush: buildWeeklyPush({
                        abstract: "sequence length, but performing semantic-level compression through a specific ratio $k$}. This $O(n/k)$ path remains effective.",
                    }),
                };
            }

            if (url === "/api/dataset/weekly-push/history") {
                return {
                    history: [],
                };
            }

            return {};
        });

        const { container } = renderWithStore();

        await screen.findByRole("link", { name: "Weekly Paper" });

        expect(screen.getByText(/sequence length, but performing semantic-level compression through a specific ratio/i)).toBeInTheDocument();
        expect(screen.getByText(/This/i)).toBeInTheDocument();
        expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
        expect(screen.queryByText(/\$k\$/)).not.toBeInTheDocument();
        expect(screen.queryByText(/\$O\(n\/k\)\$/)).not.toBeInTheDocument();
    });

    it("renders LaTeX in weekly paper titles while keeping the arXiv link", async () => {
        // Tests title rendering when a paper title contains LaTeX and also has
        // an arXiv link. The title should still be clickable, and the formula
        // should render instead of remaining raw source text.
        const weeklyPushWithLatexTitle = buildWeeklyPush({
            title: "Weekly $x^2$ Paper",
        });

        request.mockImplementation(async (url) => {
            if (url === "/api/dataset/weekly-push/latest" || url === "/api/dataset/weekly-push/latest?week_start=2026-05-01") {
                return {
                    weeklyPush: weeklyPushWithLatexTitle,
                };
            }

            if (url === "/api/dataset/weekly-push/history") {
                return {
                    history: [],
                };
            }

            return {};
        });

        const { container } = renderWithStore();

        await screen.findByText(/Weekly/i);

        const titleLink = container.querySelector("a[href='https://arxiv.org/abs/2501.00001']");
        expect(titleLink).toHaveAttribute("href", "https://arxiv.org/abs/2501.00001");
        expect(container.querySelector(".katex")).not.toBeNull();
        expect(screen.queryByText(/\$x\^2\$/)).not.toBeInTheDocument();
    });

    it("renders LaTeX in weekly paper titles without arXiv links", async () => {
        // Tests title rendering when LaTeX is present but no arXiv URL exists.
        // The page should still render the formatted math in plain text mode
        // without generating an anchor tag.
        const weeklyPushWithLatexTitle = buildWeeklyPush({
            title: "Weekly $$x^2$$ Paper",
            arxivUrl: undefined,
        });

        request.mockImplementation(async (url) => {
            if (url === "/api/dataset/weekly-push/latest" || url === "/api/dataset/weekly-push/latest?week_start=2026-05-01") {
                return {
                    weeklyPush: weeklyPushWithLatexTitle,
                };
            }

            if (url === "/api/dataset/weekly-push/history") {
                return {
                    history: [],
                };
            }

            return {};
        });

        const { container } = renderWithStore();

        await screen.findByText("本周论文");

        expect(container.querySelector("a[href]")).toBeNull();
        expect(screen.getByText(/Weekly/i)).toBeInTheDocument();
        expect(container.querySelector(".katex")).not.toBeNull();
        expect(container.querySelector(".latexTextDisplay")).toBeNull();
        expect(screen.queryByText(/\$\$x\^2\$\$/)).not.toBeInTheDocument();
    });

    it("renders block LaTeX in weekly paper abstracts", async () => {
        // Tests block-level LaTeX rendering in abstracts.
        // Expressions wrapped in `$$...$$` should become display-mode KaTeX
        // blocks rather than ordinary inline text.
        request.mockImplementation(async (url) => {
            if (url === "/api/dataset/weekly-push/latest") {
                return {
                    weeklyPush: buildWeeklyPush({
                        abstract: "核心结论如下：$$E=mc^2$$并且后续仍成立。",
                    }),
                };
            }

            if (url === "/api/dataset/weekly-push/history") {
                return {
                    history: [],
                };
            }

            return {};
        });

        const { container } = renderWithStore();

        await screen.findByRole("link", { name: "Weekly Paper" });

        expect(container.querySelector(".homeWeeklyPaperAbstractContent .latexTextDisplay")).not.toBeNull();
        expect(container.querySelector(".katex-display")).not.toBeNull();
    });

    it("uses tldr before abstract in weekly paper abstracts", async () => {
        // Tests abstract source priority for weekly papers.
        // If a paper has both `tldr` and `abstract`, the shorter TLDR summary
        // should be rendered in preference to the full abstract text.
        request.mockImplementation(async (url) => {
            if (url === "/api/dataset/weekly-push/latest") {
                return {
                    weeklyPush: buildWeeklyPush({
                        abstract: "abstract $x$",
                        tldr: "tldr $y$",
                    }),
                };
            }

            if (url === "/api/dataset/weekly-push/history") {
                return {
                    history: [],
                };
            }

            return {};
        });

        const { container } = renderWithStore();

        await screen.findByRole("link", { name: "Weekly Paper" });

        expect(screen.getByText(/tldr/i)).toBeInTheDocument();
        expect(screen.queryByText(/abstract/i)).not.toBeInTheDocument();
        await waitFor(() => {
            expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(1);
        });
    });

    it("renders the public weekly push skeleton while the initial request is pending", async () => {
        // Tests the public weekly-push loading skeleton module.
        // While the latest push and history requests are unresolved, the page
        // should show placeholder skeletons and remove them only after data
        // arrives and content is ready to render.
        const latestDeferred = createDeferred();
        const historyDeferred = createDeferred();

        request.mockImplementation((url) => {
            if (url === "/api/dataset/weekly-push/latest") {
                return latestDeferred.promise;
            }

            if (url === "/api/dataset/weekly-push/history") {
                return historyDeferred.promise;
            }

            if (url === "/api/dataset/weekly-push/latest?week_start=2026-05-01") {
                return Promise.resolve({
                    weeklyPush: buildWeeklyPush(),
                });
            }

            return Promise.resolve({});
        });

        renderWithStore();

        expect(screen.getByTestId("home-weekly-push-skeleton")).toBeInTheDocument();
        expect(screen.getByTestId("home-weekly-history-skeleton")).toBeInTheDocument();

        await act(async () => {
            latestDeferred.resolve({
                weeklyPush: buildWeeklyPush(),
            });
            historyDeferred.resolve({
                history: [{
                    weekStart: "2026-05-01",
                    weekEnd: "2026-05-07",
                    title: "本周论文速递",
                    paperCount: 1,
                    generatedBy: "rule",
                    updatedAt: "2026-05-12 12:00:00",
                }],
            });
        });

        await screen.findByText("默认摘要");
        expect(screen.queryByTestId("home-weekly-push-skeleton")).not.toBeInTheDocument();
        expect(screen.queryByTestId("home-weekly-history-skeleton")).not.toBeInTheDocument();
    });
});

describe("HomeScreen loading skeletons", () => {
    // Public weekly-push fixture used when the logged-in homepage also needs to
    // render the shared public weekly report sections.
    const buildWeeklyPush = () => ({
        weekStart: "2026-05-01",
        weekEnd: "2026-05-07",
        paperCount: 1,
        title: "本周论文速递",
        fixedSummary: "",
        aiSummary: "",
        content: "公共周报正文",
        generatedBy: "rule",
        updatedAt: "2026-05-12 12:00:00",
        papers: [{
            id: 1,
            title: "Weekly Paper",
            publishDate: "2026-05-01",
            authorNames: "Alice",
            arxivUrl: "https://arxiv.org/abs/2501.00001",
            arxivId: "2501.00001",
            abstract: "公共摘要",
            tldr: "",
        }],
    });

    // Personalized weekly-push fixture used to test logged-in homepage states.
    // This payload includes mentor/subject tracking metadata in addition to the
    // papers and summaries shown in the personalized report.
    const buildPersonalizedWeeklyPush = () => ({
        weekStart: "2026-05-01",
        weekEnd: "2026-05-07",
        paperCount: 1,
        title: "个性周报",
        fixedSummary: "规则摘要",
        aiSummary: "AI 摘要",
        content: "个性周报正文",
        generatedBy: "thucs-openai",
        updatedAt: "2026-05-12 12:00:00",
        papers: [{
            id: 11,
            title: "Mentor weekly paper",
            publishDate: "2026-05-01",
            authorNames: "Alice",
            abstract: "导师论文摘要",
            tldr: "",
            mentorNames: ["张老师"],
        }],
        mentorGroups: [],
        subjectGroups: [],
        trackedMentorCount: 1,
        activeMentorCount: 1,
        trackedSubjectCount: 2,
        activeSubjectCount: 1,
    });

    // Render helper for the logged-in homepage state, where personalized
    // weekly-push modules become available.
    const renderLoggedInHome = () => {
        const store = configureStore({
            reducer: {
                auth: authReducer,
            },
            preloadedState: {
                auth: {
                    name: "Alice",
                    token: "token",
                    role: "",
                },
            },
        });

        return render(
            <Provider store={store}>
                <HomeScreen />
            </Provider>,
        );
    };

    // Shared mock branch for the public weekly-push endpoints. Tests in this
    // block add personalized endpoints on top of these baseline responses.
    const mockResolvedPublicWeeklyPush = (url) => {
        if (url === "/api/dataset/weekly-push/latest" || url === "/api/dataset/weekly-push/latest?week_start=2026-05-01") {
            return Promise.resolve({
                weeklyPush: buildWeeklyPush(),
            });
        }

        if (url === "/api/dataset/weekly-push/history") {
            return Promise.resolve({
                history: [{
                    weekStart: "2026-05-01",
                    weekEnd: "2026-05-07",
                    title: "本周论文速递",
                    paperCount: 1,
                    generatedBy: "rule",
                    updatedAt: "2026-05-12 12:00:00",
                }],
            });
        }

        return undefined;
    };

    beforeEach(() => {
        request.mockReset();
    });

    it("renders the personalized weekly push skeleton while stored data is pending", async () => {
        // Tests the loading skeleton module for personalized weekly reports.
        // When a logged-in user's personalized push and history are still
        // loading, the page should show dedicated personalized skeletons and
        // replace them with the finished report content afterward.
        const personalizedDeferred = createDeferred();
        const personalizedHistoryDeferred = createDeferred();

        request.mockImplementation((url) => {
            const publicResult = mockResolvedPublicWeeklyPush(url);
            if (publicResult !== undefined) {
                return publicResult;
            }

            if (url === "/api/dataset/weekly-push/personalized") {
                return personalizedDeferred.promise;
            }

            if (url === "/api/dataset/weekly-push/personalized/history") {
                return personalizedHistoryDeferred.promise;
            }

            if (url === "/api/dataset/weekly-push/personalized?week_start=2026-05-01") {
                return Promise.resolve({
                    weeklyPush: buildPersonalizedWeeklyPush(),
                });
            }

            return Promise.resolve({});
        });

        renderLoggedInHome();

        expect(await screen.findByTestId("home-personalized-push-skeleton")).toBeInTheDocument();
        expect(screen.getByTestId("home-personalized-history-skeleton")).toBeInTheDocument();

        await act(async () => {
            personalizedDeferred.resolve({
                weeklyPush: buildPersonalizedWeeklyPush(),
            });
            personalizedHistoryDeferred.resolve({
                history: [{
                    weekStart: "2026-05-01",
                    weekEnd: "2026-05-07",
                    title: "个性周报",
                    paperCount: 1,
                    generatedBy: "thucs-openai",
                    updatedAt: "2026-05-12 12:00:00",
                }],
            });
        });

        await screen.findByText("导师论文摘要");
        expect(screen.getByText("关注导师")).toBeInTheDocument();
        expect(screen.queryByTestId("home-personalized-push-skeleton")).not.toBeInTheDocument();
        expect(screen.queryByTestId("home-personalized-history-skeleton")).not.toBeInTheDocument();
    });

    it("keeps the generation status text instead of showing the personalized read skeleton", async () => {
        // Tests the in-progress generation status module.
        // If the user actively triggers personalized report generation, the UI
        // should keep the explicit generation-status text visible rather than
        // switching back to the generic "read" skeleton placeholder.
        const generateDeferred = createDeferred();

        request.mockImplementation((url, method) => {
            const publicResult = mockResolvedPublicWeeklyPush(url);
            if (publicResult !== undefined) {
                return publicResult;
            }

            if (url === "/api/dataset/weekly-push/personalized" && method === "POST") {
                return generateDeferred.promise;
            }

            if (url === "/api/dataset/weekly-push/personalized") {
                return Promise.resolve({
                    weeklyPush: undefined,
                });
            }

            if (url === "/api/dataset/weekly-push/personalized/history") {
                return Promise.resolve({
                    history: [],
                });
            }

            return Promise.resolve({});
        });

        const user = userEvent.setup();
        renderLoggedInHome();

        await screen.findByText("点击上方按钮后，会按你当前关注的导师和板块即时生成一份专属周报。");
        await user.click(screen.getByRole("button", { name: "生成个性周报" }));

        expect(screen.getByText("正在整理你关注导师和板块本周的新增论文，并生成 AI 总结，请稍候。")).toBeInTheDocument();
        expect(screen.queryByTestId("home-personalized-push-skeleton")).not.toBeInTheDocument();

        await act(async () => {
            generateDeferred.resolve({
                weeklyPush: buildPersonalizedWeeklyPush(),
            });
        });
    });
});

describe("HomeScreen subject group interactions", () => {
    // Personalized weekly-push fixture focused on followed subject groups.
    // These tests target the subject card list and the modal used to inspect
    // papers inside a selected subject group.
    const buildPersonalizedWeeklyPush = () => ({
        weekStart: "2026-05-01",
        weekEnd: "2026-05-07",
        paperCount: 2,
        title: "个性周报",
        fixedSummary: "规则摘要",
        aiSummary: "AI 摘要",
        content: "个性周报正文",
        generatedBy: "thucs-openai",
        updatedAt: "2026-05-12 12:00:00",
        papers: [{
            id: 11,
            title: "Mentor weekly paper",
            publishDate: "2026-05-01",
            authorNames: "Alice",
            abstract: "导师论文摘要",
            tldr: "",
            mentorNames: ["张老师"],
        }],
        mentorGroups: [],
        subjectGroups: [
            {
                subject: "cs.AI",
                paperCount: 2,
                papers: [
                    {
                        id: 101,
                        title: "AI Paper One",
                        publishDate: "2026-05-03",
                        authorNames: "Alice, Bob",
                        subject: "cs.AI",
                        subjects: ["cs.AI", "cs.LG"],
                        abstractPreview: "AI Paper One 摘要预览",
                    },
                    {
                        id: 102,
                        title: "AI Paper Two",
                        publishDate: "2026-05-04",
                        authorNames: "Carol",
                        subject: "cs.AI",
                        subjects: ["cs.AI"],
                        abstractPreview: "AI Paper Two 摘要预览",
                    },
                ],
            },
            {
                subject: "cs.CL",
                paperCount: 1,
                papers: [
                    {
                        id: 103,
                        title: "CL Paper One",
                        publishDate: "2026-05-05",
                        authorNames: "Dave",
                        subject: "cs.CL",
                        subjects: ["cs.CL"],
                        abstractPreview: "CL Paper One 摘要预览",
                    },
                ],
            },
        ],
        subjectDistribution: [{ subject: "cs.AI", count: 2 }, { subject: "cs.CL", count: 1 }],
        trackedMentorCount: 1,
        activeMentorCount: 1,
        trackedSubjectCount: 2,
        activeSubjectCount: 2,
    });

    // Render helper for the reusable weekly-push detail card, allowing the
    // tests to focus on subject-group interactions without mounting the whole
    // homepage shell.
    const renderSubjectGroups = (pushOverrides = {}) => render(
        <WeeklyPushDetailCard
            push={{
                ...buildPersonalizedWeeklyPush(),
                ...pushOverrides,
            }}
            emptyPaperText="你关注的导师本周暂无新增论文明细。"
            showMentorNames
            showPersonalizedSummary
            metaItems={[]}
        />,
    );

    it("renders horizontal subject cards and opens the selected subject modal", async () => {
        // Tests the subject-group card module and its modal-opening behavior.
        // The personalized report should show horizontal cards for followed
        // subject groups, and clicking one should open a detail dialog with the
        // subject metadata, paper list, previews, and scroll locking.
        const user = userEvent.setup();
        renderSubjectGroups();

        const aiCardButton = await screen.findByRole("button", { name: "查看板块 cs.AI 的 2 篇论文" });
        expect(aiCardButton).toBeInTheDocument();
        expect(within(aiCardButton).getByText("cs.AI")).toBeInTheDocument();
        expect(within(aiCardButton).getByText("人工智能 (Artificial Intelligence)")).toBeInTheDocument();
        expect(within(aiCardButton).getByText("2篇")).toBeInTheDocument();
        expect(screen.queryByText("AI Paper One 摘要预览")).not.toBeInTheDocument();
        expect(screen.queryByText("AI Paper One")).not.toBeInTheDocument();

        await user.click(aiCardButton);

        const dialog = await screen.findByRole("dialog", { name: "人工智能 (Artificial Intelligence)" });
        expect(dialog).toBeInTheDocument();
        expect(within(dialog).getByText("cs.AI")).toBeInTheDocument();
        expect(within(dialog).getByText("人工智能 (Artificial Intelligence)")).toBeInTheDocument();
        expect(within(dialog).getByText("AI Paper One")).toBeInTheDocument();
        expect(within(dialog).getByText("AI Paper Two")).toBeInTheDocument();
        expect(within(dialog).getByText("AI Paper One 摘要预览")).toBeInTheDocument();
        expect(within(dialog).getByText(/作者：Alice, Bob/)).toBeInTheDocument();
        expect(document.body.style.overflow).toBe("hidden");

        await user.click(screen.getByRole("button", { name: "关闭 cs.AI 板块详情" }));
        await waitFor(() => {
            expect(screen.queryByRole("dialog", { name: "人工智能 (Artificial Intelligence)" })).not.toBeInTheDocument();
        });
        expect(document.body.style.overflow).toBe("");
    });

    it("closes the subject modal via overlay click and Escape key", async () => {
        // Tests modal dismissal behavior for subject-group details.
        // The subject dialog should support both overlay-click closing and
        // keyboard closing via Escape, while also restoring page scrolling.
        const user = userEvent.setup();
        renderSubjectGroups();

        await user.click(await screen.findByRole("button", { name: "查看板块 cs.CL 的 1 篇论文" }));

        const dialog = await screen.findByRole("dialog", { name: "自然语言处理 (NLP)" });
        const overlay = dialog.parentElement;
        expect(overlay).not.toBeNull();

        fireEvent.click(overlay);
        await waitFor(() => {
            expect(screen.queryByRole("dialog", { name: "自然语言处理 (NLP)" })).not.toBeInTheDocument();
        });

        await user.click(await screen.findByRole("button", { name: "查看板块 cs.CL 的 1 篇论文" }));
        await screen.findByRole("dialog", { name: "自然语言处理 (NLP)" });

        fireEvent.keyDown(window, { key: "Escape" });
        await waitFor(() => {
            expect(screen.queryByRole("dialog", { name: "自然语言处理 (NLP)" })).not.toBeInTheDocument();
        });
        expect(document.body.style.overflow).toBe("");
    });

    it("keeps the empty placeholder when there are no followed subject updates", async () => {
        // Tests the empty-state module for personalized followed subjects.
        // If no followed subject groups have updates this week, the component
        // should keep the explicit placeholder text and render no subject cards.
        renderSubjectGroups({
            subjectGroups: [],
            trackedSubjectCount: 0,
            activeSubjectCount: 0,
        });

        expect(await screen.findByText("你关注的板块本周暂无新增论文。")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /查看板块/ })).not.toBeInTheDocument();
    });
});
