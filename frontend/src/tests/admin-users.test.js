import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { useRouter } from "next/router";

import authReducer from "../redux/auth";
import { request } from "../utils/network";
import AdminUsersPage from "../pages/admin-users";

// Mock the Next.js router.
// These tests focus on the internal behavior of the admin page rather than
// real navigation, so only useRouter is kept and push is replaced with a spy.
jest.mock("next/router", () => ({
    useRouter: jest.fn(),
}));

// Mock the network layer.
// Replacing request with jest.fn() lets each test:
// 1. control what each backend endpoint returns;
// 2. assert that the page calls the expected API;
// 3. stay independent from a real backend environment.
jest.mock("../utils/network", () => ({
    request: jest.fn(),
    NetworkError: class MockNetworkError extends Error {},
    NetworkErrorType: {
        UNAUTHORIZED: 0,
        REJECTED: 1,
        CORRUPTED_RESPONSE: 2,
        UNKNOWN_ERROR: 3,
    },
}));

describe("AdminUsersPage", () => {
    const mockPush = jest.fn();

    // Shared render helper.
    // This page depends on the Redux auth state, so the helper builds a minimal
    // store with a logged-in user. The default role is admin, but other roles
    // can be injected to test permission checks.
    const renderWithStore = (role = "admin") => {
        const store = configureStore({
            reducer: {
                auth: authReducer,
            },
            preloadedState: {
                auth: {
                    name: "admin_user",
                    token: "mock-token",
                    role,
                },
            },
        });

        render(
            <Provider store={store}>
                <AdminUsersPage />
            </Provider>,
        );
    };

    beforeEach(() => {
        // Reset all spies before each test so previous calls do not pollute
        // the assertions in the current test case.
        mockPush.mockReset();
        request.mockReset();
        useRouter.mockReturnValue({
            push: mockPush,
        });

        // Provide a default set of mocked backend responses for this test file.
        // Most test cases can then focus on page behavior instead of rewriting
        // the same mock setup again and again.
        request.mockImplementation(async (url) => {
            // Admin user management endpoint:
            // returns the current user id, the user list, and pending
            // verification requests. These values support the page's initial
            // load, the user table, and the verification request section.
            if (String(url).startsWith("/api/management/users")) {
                return {
                    currentUserId: 1,
                    verificationRequests: [{
                        id: 301,
                        userId: 2,
                        username: "student_user",
                        userEmail: "student@example.com",
                        submittedName: "张老师",
                        status: "pending",
                        createdAt: "2026-04-25 13:30:00",
                        updatedAt: "2026-04-25 13:30:00",
                    }],
                    users: [{
                        id: 1,
                        username: "admin_user",
                        email: "admin@example.com",
                        role: "admin",
                        isBoundToMentor: false,
                        mentorProfile: undefined,
                    }, {
                        id: 2,
                        username: "student_user",
                        email: "student@example.com",
                        role: "student",
                        isBoundToMentor: false,
                        mentorProfile: undefined,
                    }],
                };
            }

            // Verification approval endpoint:
            // simulates a successful approval where the request becomes
            // approved and the applicant is updated to mentor.
            if (String(url).startsWith("/api/management/verification-requests/")) {
                return {
                    verificationRequest: {
                        id: 301,
                        status: "approved",
                    },
                    user: {
                        id: 2,
                        username: "student_user",
                        email: "student@example.com",
                        role: "mentor",
                        isBoundToMentor: true,
                    },
                };
            }

            // Public mentor search endpoint:
            // used when the admin looks up a mentor profile to bind during
            // the approval flow.
            if (String(url).startsWith("/api/search/mentors")) {
                return {
                    mentors: [{
                        id: 101,
                        Chinese_name: "张三",
                        English_name: "Zhang San",
                        research_direction: "机器学习",
                        email: "zhangsan@example.com",
                        profile: "公共导师",
                        paperTitles: [],
                        is_private: false,
                    }],
                };
            }

            return {};
        });
    });

    it("blocks non-admin users from viewing the page", () => {
        // Tests the permission guard.
        // If the logged-in user is not an admin, the page should not expose
        // the management UI and should show the access denied message instead.
        renderWithStore("student");

        expect(screen.getByText("仅管理员可以访问该页面。")).toBeInTheDocument();
    });

    it("loads users for admin and can search public mentors", async () => {
        // Covers two core modules:
        // 1. the initial admin-side user management data load;
        // 2. the public mentor search feature available to administrators.
        renderWithStore("admin");

        // Verify that the page requests the management data on first render.
        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/management/users", "GET", true);
        });

        // Verify that returned user data is rendered into the page.
        expect(screen.getByText("student_user")).toBeInTheDocument();

        // Simulate the admin entering a mentor keyword and submitting the
        // public mentor search form.
        fireEvent.change(screen.getByPlaceholderText("搜索公共导师，便于绑定 mentor 角色"), {
            target: { value: "张三" },
        });
        fireEvent.click(screen.getByRole("button", { name: "搜索公共导师" }));

        // Verify that the search action encodes the keyword correctly and
        // calls the mentor search endpoint with the expected query string.
        await waitFor(() => {
            expect(request).toHaveBeenCalledWith(
                "/api/search/mentors?keyword=%E5%BC%A0%E4%B8%89&search_mode=fuzzy",
                "GET",
                true,
            );
        });

        // Verify that the mentor search results and the verification request
        // section are both visible, showing that multiple admin modules are
        // rendered together from the loaded data.
        expect(screen.getByText(/ID: 101/)).toBeInTheDocument();
        expect(screen.getByText("用户认证请求列表")).toBeInTheDocument();
        expect(screen.getByText("申请姓名：张老师")).toBeInTheDocument();
    });

    it("sends keyword when searching users", async () => {
        // Tests the user search module.
        // After the admin enters a username, email, or real-name keyword, the
        // page should pass that keyword to the user management query API.
        renderWithStore("admin");

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/management/users", "GET", true);
        });

        // Simulate a user search using an email keyword.
        fireEvent.change(screen.getByPlaceholderText("按用户名、邮箱或真实姓名搜索"), {
            target: { value: "student@example.com" },
        });
        fireEvent.click(screen.getByRole("button", { name: "搜索用户" }));

        // Assert that the request URL contains the correctly encoded keyword.
        await waitFor(() => {
            expect(request).toHaveBeenCalledWith(
                "/api/management/users?keyword=student%40example.com",
                "GET",
                true,
            );
        });
    });

    it("sends role filter when filtering users", async () => {
        // Tests the role filter module.
        // When the admin changes the selected role, the page should re-query
        // the user list with the chosen role filter.
        renderWithStore("admin");

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/management/users", "GET", true);
        });

        // Simulate switching the filter from "all roles" to "banned".
        fireEvent.change(screen.getByDisplayValue("全部角色"), {
            target: { value: "banned" },
        });
        fireEvent.click(screen.getByRole("button", { name: "搜索用户" }));

        // Verify that the selected role is passed as a query parameter.
        await waitFor(() => {
            expect(request).toHaveBeenCalledWith(
                "/api/management/users?role=banned",
                "GET",
                true,
            );
        });
    });

    it("approves verification request with selected mentor id", async () => {
        // Tests the full verification approval workflow:
        // 1. search for a public mentor for the applicant;
        // 2. select a mentor candidate;
        // 3. approve the request;
        // 4. submit both the approved status and the selected mentorId.
        // This is one of the most important business flows on the admin page.
        renderWithStore("admin");

        await waitFor(() => {
            expect(request).toHaveBeenCalledWith("/api/management/users", "GET", true);
        });

        // Enter a keyword in the applicant-specific mentor search box and
        // trigger the search action.
        fireEvent.change(screen.getByPlaceholderText("搜索并选择要绑定的公共导师"), {
            target: { value: "张三" },
        });
        fireEvent.click(screen.getByRole("button", { name: "为student_user搜索导师" }));

        // Verify that the page issues the mentor search request for this flow.
        await waitFor(() => {
            expect(request).toHaveBeenCalledWith(
                "/api/search/mentors?keyword=%E5%BC%A0%E4%B8%89&search_mode=fuzzy",
                "GET",
                true,
            );
        });

        // Select a mentor first, then approve the request.
        // The order matters because the approval payload must contain the
        // final mentorId chosen by the admin.
        fireEvent.click(screen.getByRole("button", { name: /张三 \/ Zhang San/ }));
        fireEvent.click(screen.getByRole("button", { name: "通过student_user的申请" }));

        // Core assertion:
        // the approval API must receive both status=approved and mentorId=101.
        // If this passes, the page has correctly connected the whole flow:
        // search mentor -> select mentor -> submit approval.
        await waitFor(() => {
            expect(request).toHaveBeenCalledWith(
                "/api/management/verification-requests/301",
                "PUT",
                true,
                {
                    status: "approved",
                    mentorId: 101,
                },
            );
        });
    });
});
