import { fireEvent, render, screen, within } from "@testing-library/react";
import { useRouter } from "next/router";
import { useDispatch, useSelector } from "react-redux";

import TopNav from "../components/TopNav";
import { resetAuth } from "../redux/auth";
import { buildGlobalPaperSearchUrl, normalizeSearchKeywordForUrl } from "../utils/searchQuery";

// Mock Next.js routing so the navigation component can be tested in isolation
// while still asserting which routes it tries to open.
jest.mock("next/router", () => ({
    useRouter: jest.fn(),
}));

// Mock Redux hooks because TopNav reads auth state and dispatches logout
// actions; the tests need direct control over both.
jest.mock("react-redux", () => ({
    useDispatch: jest.fn(),
    useSelector: jest.fn(),
}));

describe("TopNav", () => {
    const mockPush = jest.fn();
    const mockDispatch = jest.fn();
    const mockRouter = {
        pathname: "/",
        asPath: "/",
        query: {},
        push: mockPush,
    };
    let mockAuthState = {
        token: "",
        name: "",
        role: "",
        userId: undefined,
    };

    // Shared render helper for the top navigation component.
    const renderTopNav = () => {
        return render(<TopNav />);
    };

    beforeEach(() => {
        // Reset router/dispatch/auth state and browser helpers before each
        // navigation test so desktop/mobile/menu state does not leak.
        mockPush.mockReset();
        mockDispatch.mockReset();
        mockRouter.pathname = "/";
        mockRouter.asPath = "/";
        mockRouter.query = {};
        mockAuthState = {
            token: "",
            name: "",
            role: "",
            userId: undefined,
        };

        useRouter.mockReturnValue(mockRouter);
        useDispatch.mockReturnValue(mockDispatch);
        useSelector.mockImplementation((selector) => selector({ auth: mockAuthState }));
        globalThis.open = jest.fn();
        window.scrollTo = jest.fn();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it("shows search, Sign in and Sign up for unauthenticated users", () => {
        // Tests the unauthenticated desktop navigation module.
        // Guests should see the global search input plus sign-in/sign-up entry
        // points, but no account menu or admin controls.
        renderTopNav();

        expect(screen.getByRole("textbox", { name: "Search or jump to" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Home" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Sign up" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /alice/i })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Admin" })).not.toBeInTheDocument();
    });

    it("routes to home when clicking the logo", () => {
        // Tests logo-based home navigation.
        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: "Go to home" }));

        expect(mockPush).toHaveBeenCalledWith("/");
    });

    it("redirects unauthenticated users to login when they click follows", () => {
        // Tests protected-route redirect behavior from the top navigation.
        // Guests trying to open the follows page should be sent to login with a
        // redirect target so they can return after authentication.
        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: "Follows" }));

        expect(mockPush).toHaveBeenCalledWith("/login?redirect=%2Ffollows");
    });

    it("scrolls to the top instead of pushing again when clicking Timeline on the current timeline page", () => {
        // Tests same-route optimization for timeline navigation.
        // If the user is already on the timeline page, clicking Timeline should
        // scroll to the top rather than pushing a duplicate route.
        mockRouter.pathname = "/timeline";
        mockRouter.asPath = "/timeline";

        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: "Timeline" }));

        expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: "auto" });
        expect(mockPush).not.toHaveBeenCalled();
    });

    it("redirects unauthenticated users to login when they click profile", () => {
        // Tests protected-route redirect behavior for the profile area.
        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: "Profile" }));

        expect(mockPush).toHaveBeenCalledWith("/login?redirect=%2Fusers");
    });

    it("allows typing into the top search input", () => {
        // Tests the controlled-input module for the top global search box.
        // Typing should update the input value locally without navigating yet.
        renderTopNav();

        const searchInput = screen.getByRole("textbox", { name: "Search or jump to" });
        fireEvent.change(searchInput, { target: { value: "graph neural network" } });

        expect(searchInput).toHaveValue("graph neural network");
        expect(mockPush).not.toHaveBeenCalled();
    });

    it("truncates overly long top search keywords before opening search", () => {
        // Tests the top-nav keyword-length guard.
        // Pasted text longer than the backend limit should be truncated in the
        // controlled input and in the generated quick-search URL.
        renderTopNav();

        const searchInput = screen.getByRole("textbox", { name: "Search or jump to" });
        const longKeyword = "一".repeat(400);
        const truncatedKeyword = normalizeSearchKeywordForUrl(longKeyword);

        fireEvent.change(searchInput, { target: { value: longKeyword } });
        expect(searchInput).toHaveValue(truncatedKeyword);

        fireEvent.keyDown(searchInput, { key: "Enter" });

        expect(globalThis.open).toHaveBeenCalledWith(
            buildGlobalPaperSearchUrl(truncatedKeyword),
            "_blank",
            "noopener,noreferrer",
        );
    });

    it("opens a new tab with paper fuzzy search when pressing Enter with keyword", () => {
        // Tests the global quick-search submission module.
        // Pressing Enter with a keyword should open a new tab pointing to the
        // global paper-search URL built from that keyword.
        renderTopNav();

        const searchInput = screen.getByRole("textbox", { name: "Search or jump to" });
        fireEvent.change(searchInput, { target: { value: "graph neural network" } });
        fireEvent.keyDown(searchInput, { key: "Enter" });

        expect(globalThis.open).toHaveBeenCalledWith(
            buildGlobalPaperSearchUrl("graph neural network"),
            "_blank",
            "noopener,noreferrer",
        );
    });

    it("does not open a new tab when top search keyword is empty", () => {
        // Tests the empty-keyword guard for the top search box.
        // Pure whitespace should be treated as empty and should not trigger a
        // new search tab.
        renderTopNav();

        const searchInput = screen.getByRole("textbox", { name: "Search or jump to" });
        fireEvent.change(searchInput, { target: { value: "   " } });
        fireEvent.keyDown(searchInput, { key: "Enter" });

        expect(globalThis.open).not.toHaveBeenCalled();
    });

    it("shows avatar menu instead of auth buttons for logged-in users", () => {
        // Tests the authenticated desktop navigation module.
        // Logged-in users should see their account button/avatar menu instead
        // of guest auth buttons.
        mockAuthState = {
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
        };

        renderTopNav();

        expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Sign up" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: /alice/i })).toBeInTheDocument();
    });

    it("uses the saved avatar image in the account button", () => {
        // Tests avatar-image rendering in the authenticated account button.
        mockAuthState = {
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
            avatarUrl: "/media/avatars/user-42.png",
        };

        renderTopNav();

        expect(screen.getByRole("button", { name: /alice/i }).querySelector("img")).toHaveAttribute(
            "src",
            "/media/avatars/user-42.png",
        );
    });

    it("shows profile, follows and sign out in the avatar menu for students", () => {
        // Tests the student account-menu module.
        // Student users should get the standard personal actions, but no admin
        // entry inside the avatar dropdown.
        mockAuthState = {
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
        };

        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: /alice/i }));

        const menu = screen.getByRole("menu", { name: "Account menu" });
        expect(within(menu).getByRole("button", { name: "Profile" })).toBeInTheDocument();
        expect(within(menu).getByRole("button", { name: "Follows" })).toBeInTheDocument();
        expect(within(menu).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
        expect(within(menu).queryByRole("button", { name: "Admin" })).not.toBeInTheDocument();
    });

    it("shows admin entry in navigation and avatar menu for administrators", () => {
        // Tests the admin-navigation module.
        // Administrators should see an admin shortcut both in the main nav and
        // inside the account menu.
        mockAuthState = {
            token: "jwt-token",
            name: "ada",
            role: "admin",
            userId: 7,
        };

        renderTopNav();

        expect(screen.getByRole("button", { name: "Admin" })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /ada/i }));

        const menu = screen.getByRole("menu", { name: "Account menu" });
        expect(within(menu).getByRole("button", { name: "Admin" })).toBeInTheDocument();
    });

    it("toggles avatar menu expanded state and closes it with Escape", () => {
        // Tests avatar-menu accessibility state and keyboard dismissal.
        // The account button should reflect expanded/collapsed state through
        // aria-expanded and close when Escape is pressed.
        mockAuthState = {
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
        };

        renderTopNav();

        const avatarButton = screen.getByRole("button", { name: /alice/i });
        expect(avatarButton).toHaveAttribute("aria-expanded", "false");

        fireEvent.click(avatarButton);
        expect(avatarButton).toHaveAttribute("aria-expanded", "true");
        expect(screen.getByRole("menu", { name: "Account menu" })).toBeInTheDocument();

        fireEvent.keyDown(globalThis, { key: "Escape" });
        expect(avatarButton).toHaveAttribute("aria-expanded", "false");
        expect(screen.queryByRole("menu", { name: "Account menu" })).not.toBeInTheDocument();
    });

    it("closes avatar menu after choosing a menu item", () => {
        // Tests account-menu action handling.
        // Choosing a menu item should both navigate to the requested page and
        // close the menu afterward.
        mockAuthState = {
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
        };

        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: /alice/i }));
        const menu = screen.getByRole("menu", { name: "Account menu" });
        fireEvent.click(within(menu).getByRole("button", { name: "Profile" }));

        expect(mockPush).toHaveBeenCalledWith("/users/42");
        expect(screen.queryByRole("menu", { name: "Account menu" })).not.toBeInTheDocument();
    });

    it("dispatches resetAuth and returns home when signing out", () => {
        // Tests the sign-out module.
        // Logging out should clear auth state in Redux and route the user back
        // to the home page.
        mockAuthState = {
            token: "jwt-token",
            name: "alice",
            role: "student",
            userId: 42,
        };

        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: /alice/i }));
        fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

        expect(mockDispatch).toHaveBeenCalledWith(resetAuth());
        expect(mockPush).toHaveBeenCalledWith("/");
    });

    it("toggles mobile navigation expanded state and closes it with Escape", () => {
        // Tests the mobile-navigation drawer module.
        // The mobile menu button should manage aria-expanded correctly and the
        // drawer should close when Escape is pressed.
        renderTopNav();

        const menuToggle = screen.getByRole("button", { name: "Open navigation menu" });
        expect(menuToggle).toHaveAttribute("aria-expanded", "false");

        fireEvent.click(menuToggle);
        expect(menuToggle).toHaveAttribute("aria-expanded", "true");
        expect(screen.getByRole("navigation", { name: "Mobile primary navigation" })).toBeInTheDocument();

        fireEvent.keyDown(globalThis, { key: "Escape" });
        expect(menuToggle).toHaveAttribute("aria-expanded", "false");
        expect(screen.queryByRole("navigation", { name: "Mobile primary navigation" })).not.toBeInTheDocument();
    });

    it("opens mobile navigation and keeps restricted redirect behavior there", () => {
        // Tests protected-route handling inside the mobile navigation drawer.
        // Guest users should see the same login-redirect behavior from mobile
        // navigation that they get from desktop navigation.
        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));

        const mobileNav = screen.getByRole("navigation", { name: "Mobile primary navigation" });
        fireEvent.click(within(mobileNav).getByRole("button", { name: "Follows" }));

        expect(mockPush).toHaveBeenCalledWith("/login?redirect=%2Ffollows");
        expect(screen.queryByRole("navigation", { name: "Mobile primary navigation" })).not.toBeInTheDocument();
    });

    it("closes mobile navigation after choosing a public route", () => {
        // Tests public-route handling inside the mobile navigation drawer.
        // After choosing a normal navigation target, the drawer should close.
        renderTopNav();

        fireEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));
        const mobileNav = screen.getByRole("navigation", { name: "Mobile primary navigation" });

        fireEvent.click(within(mobileNav).getByRole("button", { name: "Search" }));

        expect(mockPush).toHaveBeenCalledWith("/search");
        expect(screen.queryByRole("navigation", { name: "Mobile primary navigation" })).not.toBeInTheDocument();
    });
});
