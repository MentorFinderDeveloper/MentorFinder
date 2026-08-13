import { KeyboardEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { useDispatch, useSelector } from "react-redux";

import { resetAuth, setUserId } from "../redux/auth";
import { RootState } from "../redux/store";
import { request } from "../utils/network";
import { buildRedirectHref, isSafeRelativeRedirect } from "../utils/authRedirect";
import { buildGlobalPaperSearchUrl, normalizeSearchKeywordForUrl } from "../utils/searchQuery";
import { INPUT_LIMITS } from "../constants/inputLimits";

interface NavItem {
    label: string;
    href: string;
    requiresAuth?: boolean;
    adminOnly?: boolean;
    activeMatch: (pathname: string) => boolean;
}

// Centralize top-level navigation rules so desktop and mobile menus stay consistent.
const NAV_ITEMS: NavItem[] = [
    {
        label: "Search",
        href: "/search",
        activeMatch: (pathname) => pathname === "/search" || pathname.startsWith("/mentors/"),
    },
    {
        label: "Timeline",
        href: "/timeline",
        activeMatch: (pathname) => pathname === "/timeline",
    },
    {
        label: "Follows",
        href: "/follows",
        requiresAuth: true,
        activeMatch: (pathname) => pathname === "/follows",
    },
    {
        label: "Profile",
        href: "/users",
        requiresAuth: true,
        activeMatch: (pathname) => pathname.startsWith("/users/") || pathname === "/profile" || pathname === "/profile-settings" || pathname === "/private-mentor",
    },
    {
        label: "Admin",
        href: "/admin-users",
        requiresAuth: true,
        adminOnly: true,
        activeMatch: (pathname) => pathname === "/admin-users",
    },
];

const TopNav = () => {
    const router = useRouter();
    const dispatch = useDispatch();
    const auth = useSelector((state: RootState) => state.auth);

    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
    const [searchKeyword, setSearchKeyword] = useState("");

    const isLoggedIn = auth.token.trim() !== "";
    const isAdmin = auth.role === "admin";
    const currentPath = typeof router.asPath === "string" && router.asPath !== "" ? router.asPath : "/";
    const currentRedirect = typeof router.query.redirect === "string" ? router.query.redirect : "";

    const visibleNavItems = useMemo(() => {
        // Non-admin users should never see admin-only navigation entries.
        return NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);
    }, [isAdmin]);

    useEffect(() => {
        // Collapse any open menu after route changes so stale panels do not remain visible.
        setMobileMenuOpen(false);
        setAvatarMenuOpen(false);
    }, [currentPath]);

    useEffect(() => {
        // Let keyboard users dismiss both menus with Escape.
        const handleEscape = (event: globalThis.KeyboardEvent) => {
            if (event.key === "Escape") {
                setMobileMenuOpen(false);
                setAvatarMenuOpen(false);
            }
        };

        window.addEventListener("keydown", handleEscape);
        return () => window.removeEventListener("keydown", handleEscape);
    }, []);

    const goto = (href: string, requiresAuth = false) => {
        // Preserve the intended destination when redirecting unauthenticated users to login.
        const targetHref = requiresAuth && !isLoggedIn
            ? buildRedirectHref("/login", href)
            : href;

        setMobileMenuOpen(false);
        setAvatarMenuOpen(false);

        if (href === "/timeline" && router.pathname === href) {
            // Re-clicking the current timeline tab should reset the feed viewport instead of remounting.
            window.scrollTo({ top: 0, left: 0, behavior: "auto" });
            return;
        }

        void router.push(targetHref);
    };

    const gotoProfile = async () => {
        if (!isLoggedIn) {
            goto("/users", true);
            return;
        }

        if (auth.userId !== undefined) {
            // Reuse the cached user id from Redux when it is already known.
            goto(`/users/${auth.userId}`, true);
            return;
        }

        setMobileMenuOpen(false);
        setAvatarMenuOpen(false);

        try {
            // Resolve the current user's profile id lazily so the nav can link to /users/:id.
            const res = await request<{ userId?: number }>("/api/profile/me", "GET", true);
            if (typeof res.userId === "number") {
                dispatch(setUserId(res.userId));
                void router.push(`/users/${res.userId}`);
            }
        }
        catch {
            // If auth is stale, fall back to login and keep the profile page as the redirect target.
            void router.push("/login?redirect=%2Fusers");
        }
    };

    const gotoAuthPage = (basePath: "/login" | "/register") => {
        // Only forward safe in-app redirect targets to avoid open redirect behavior.
        const nextHref = isSafeRelativeRedirect(currentRedirect)
            ? buildRedirectHref(basePath, currentRedirect)
            : basePath;

        setMobileMenuOpen(false);
        setAvatarMenuOpen(false);
        void router.push(nextHref);
    };

    const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            event.preventDefault();
            const trimmedKeyword = normalizeSearchKeywordForUrl(searchKeyword);
            if (trimmedKeyword === "") {
                return;
            }

            // The top-nav search opens the global paper search in a new tab without disturbing the current page.
            window.open(
                buildGlobalPaperSearchUrl(trimmedKeyword),
                "_blank",
                "noopener,noreferrer",
            );
        }
    };

    const handleSignOut = () => {
        // Clear local auth state immediately before returning to the landing page.
        dispatch(resetAuth());
        setMobileMenuOpen(false);
        setAvatarMenuOpen(false);
        void router.push("/");
    };

    // Fall back to an initial when the user has no avatar image.
    const avatarLabel = auth.name.trim() === ""
        ? "U"
        : auth.name.trim().slice(0, 1).toUpperCase();
    const avatarUrl = typeof auth.avatarUrl === "string" ? auth.avatarUrl.trim() : "";

    return (
        <header className="topNav">
            <div className="topNavInner">
                <div className="topNavLeft">
                    <button
                        type="button"
                        className="topNavBrand"
                        onClick={() => goto("/")}
                        aria-label="Go to home"
                    >
                        <span className="topNavBrandLogoFrame" aria-hidden="true">
                            <img
                                src="/mentorfinder-logo-1.svg"
                                alt=""
                                className="topNavBrandLogo"
                            />
                        </span>
                    </button>

                    <nav className="topNavLinks" aria-label="Primary">
                        {visibleNavItems.map((item) => (
                            <button
                                key={item.href}
                                type="button"
                                className={item.activeMatch(router.pathname) ? "topNavLink topNavLinkActive" : "topNavLink"}
                                onClick={() => {
                                    if (item.label === "Profile") {
                                        void gotoProfile();
                                        return;
                                    }
                                    goto(item.href, Boolean(item.requiresAuth));
                                }}
                            >
                                {item.label}
                            </button>
                        ))}
                    </nav>
                </div>

                <div className="topNavRight">
                    <div className="topNavSearchShell">
                        <span className="topNavSearchIcon" aria-hidden="true">
                            <svg
                                data-component="Octicon"
                                focusable="false"
                                className="octicon octicon-search"
                                viewBox="0 0 16 16"
                                width="16"
                                height="16"
                                fill="currentColor"
                                display="inline-block"
                                overflow="visible"
                                style={{ verticalAlign: "text-bottom" }}
                            >
                                <path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.499 4.499 0 1 0-8.997 0A4.499 4.499 0 0 0 11.5 7Z" />
                            </svg>
                        </span>
                        <input
                            type="text"
                            className="topNavSearch"
                            placeholder="Search or jump to..."
                            aria-label="Search or jump to"
                            maxLength={INPUT_LIMITS.KEYWORD}
                            value={searchKeyword}
                            onChange={(event) => setSearchKeyword(normalizeSearchKeywordForUrl(event.target.value))}
                            onKeyDown={handleSearchKeyDown}
                        />
                    </div>

                    {!isLoggedIn ? (
                        <div className="topNavDesktopAuth">
                            <button type="button" className="topNavAuthLink" onClick={() => gotoAuthPage("/login")}>
                                Sign in
                            </button>
                            <button type="button" className="topNavAuthPrimary" onClick={() => gotoAuthPage("/register")}>
                                Sign up
                            </button>
                        </div>
                    ) : (
                        <div className="topNavAvatarArea">
                            <button
                                type="button"
                                className="topNavAvatarButton"
                                aria-haspopup="menu"
                                aria-expanded={avatarMenuOpen}
                                onClick={() => setAvatarMenuOpen((open) => !open)}
                            >
                                {avatarUrl === "" ? (
                                    <span className="topNavAvatarCircle" aria-hidden="true">{avatarLabel}</span>
                                ) : (
                                    <img
                                        className="topNavAvatarCircle topNavAvatarImage"
                                        src={avatarUrl}
                                        alt=""
                                        aria-hidden="true"
                                    />
                                )}
                                <span className="topNavAvatarName">{auth.name || "Account"}</span>
                            </button>

                            {avatarMenuOpen && (
                                <div className="topNavAvatarMenu" role="menu" aria-label="Account menu">
                                    <button type="button" className="topNavMenuItem" onClick={() => void gotoProfile()}>
                                        Profile
                                    </button>
                                    <button type="button" className="topNavMenuItem" onClick={() => goto("/follows", true)}>
                                        Follows
                                    </button>
                                    {isAdmin && (
                                        <button type="button" className="topNavMenuItem" onClick={() => goto("/admin-users", true)}>
                                            Admin
                                        </button>
                                    )}
                                    <button type="button" className="topNavMenuItem topNavMenuItemDanger" onClick={handleSignOut}>
                                        Sign out
                                    </button>
                                </div>
                            )}
                        </div>
                    )}

                    <button
                        type="button"
                        className="topNavMobileToggle"
                        aria-label="Open navigation menu"
                        aria-expanded={mobileMenuOpen}
                        onClick={() => setMobileMenuOpen((open) => !open)}
                    >
                        <span />
                        <span />
                        <span />
                    </button>
                </div>
            </div>

            {mobileMenuOpen && (
                <div className="topNavMobilePanel">
                    <nav className="topNavMobileLinks" aria-label="Mobile primary navigation">
                        {visibleNavItems.map((item) => (
                            <button
                                key={`mobile-${item.href}`}
                                type="button"
                                className={item.activeMatch(router.pathname) ? "topNavMobileLink topNavMobileLinkActive" : "topNavMobileLink"}
                                onClick={() => {
                                    if (item.label === "Profile") {
                                        void gotoProfile();
                                        return;
                                    }
                                    goto(item.href, Boolean(item.requiresAuth));
                                }}
                            >
                                {item.label}
                            </button>
                        ))}
                    </nav>

                    {!isLoggedIn ? (
                        <div className="topNavMobileAuth">
                            <button type="button" className="topNavMobileLink" onClick={() => gotoAuthPage("/login")}>
                                Sign in
                            </button>
                            <button type="button" className="topNavMobileLink topNavMobileLinkPrimary" onClick={() => gotoAuthPage("/register")}>
                                Sign up
                            </button>
                        </div>
                    ) : (
                        <div className="topNavMobileAccount">
                            <div className="topNavMobileAccountLabel">
                                Signed in as <strong>{auth.name || "Account"}</strong>
                            </div>
                            <button type="button" className="topNavMobileLink" onClick={() => void gotoProfile()}>
                                Profile
                            </button>
                            <button type="button" className="topNavMobileLink" onClick={() => goto("/follows", true)}>
                                Follows
                            </button>
                            {isAdmin && (
                                <button type="button" className="topNavMobileLink" onClick={() => goto("/admin-users", true)}>
                                    Admin
                                </button>
                            )}
                            <button type="button" className="topNavMobileLink topNavMobileLinkDanger" onClick={handleSignOut}>
                                Sign out
                            </button>
                        </div>
                    )}
                </div>
            )}
        </header>
    );
};

export default TopNav;
