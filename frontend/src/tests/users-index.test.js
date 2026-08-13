import { render, waitFor } from "@testing-library/react";
import { useRouter } from "next/router";
import { useDispatch, useSelector } from "react-redux";

import UsersIndexPage from "../pages/users/index";
import { loadAuthFromStorage, setUserId } from "../redux/auth";
import { request } from "../utils/network";

jest.mock("next/router", () => ({
    useRouter: jest.fn(),
}));

jest.mock("react-redux", () => ({
    useDispatch: jest.fn(),
    useSelector: jest.fn(),
}));

jest.mock("../redux/auth", () => ({
    loadAuthFromStorage: jest.fn(),
    setUserId: jest.fn((value) => ({ type: "auth/setUserId", payload: value })),
}));

jest.mock("../utils/network", () => ({
    request: jest.fn(),
}));

describe("UsersIndexPage", () => {
    const mockReplace = jest.fn();
    const mockDispatch = jest.fn();
    const mockRouter = { replace: mockReplace };
    let mockAuthState = { token: "", name: "", role: "", userId: undefined, avatarUrl: "" };

    beforeEach(() => {
        mockReplace.mockReset();
        mockDispatch.mockReset();
        mockAuthState = { token: "", name: "", role: "", userId: undefined, avatarUrl: "" };

        useRouter.mockReturnValue(mockRouter);
        useDispatch.mockReturnValue(mockDispatch);
        useSelector.mockImplementation((selector) => selector({ auth: mockAuthState }));
        loadAuthFromStorage.mockReturnValue({ token: "", name: "", role: "", userId: undefined, avatarUrl: "" });
        request.mockReset();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it("redirects to the user's profile when userId is already known", () => {
        mockAuthState = { token: "jwt-token", name: "alice", role: "student", userId: 42, avatarUrl: "" };

        render(<UsersIndexPage />);

        expect(mockReplace).toHaveBeenCalledWith("/users/42");
        expect(request).not.toHaveBeenCalled();
    });

    it("fetches the profile to resolve userId when logged in without a cached id", async () => {
        mockAuthState = { token: "jwt-token", name: "alice", role: "student", userId: undefined, avatarUrl: "" };
        request.mockResolvedValue({ userId: 7 });

        render(<UsersIndexPage />);

        await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/users/7"));
        expect(request).toHaveBeenCalledWith("/api/profile/me", "GET", true);
        expect(mockDispatch).toHaveBeenCalledWith(setUserId(7));
    });

    it("redirects to login when the profile lookup fails", async () => {
        mockAuthState = { token: "jwt-token", name: "alice", role: "student", userId: undefined, avatarUrl: "" };
        request.mockRejectedValue(new Error("unauthorized"));

        render(<UsersIndexPage />);

        await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login?redirect=%2Fusers"));
    });

    it("redirects to login when there is no stored session", () => {
        mockAuthState = { token: "", name: "", role: "", userId: undefined, avatarUrl: "" };
        loadAuthFromStorage.mockReturnValue({ token: "", name: "", role: "", userId: undefined, avatarUrl: "" });

        render(<UsersIndexPage />);

        expect(mockReplace).toHaveBeenCalledWith("/login?redirect=%2Fusers");
        expect(request).not.toHaveBeenCalled();
    });

    it("waits for hydration instead of bouncing a stored session to login", () => {
        mockAuthState = { token: "", name: "", role: "", userId: undefined, avatarUrl: "" };
        loadAuthFromStorage.mockReturnValue({ token: "jwt-token", name: "alice", role: "student", userId: 42, avatarUrl: "" });

        render(<UsersIndexPage />);

        expect(mockReplace).not.toHaveBeenCalled();
        expect(request).not.toHaveBeenCalled();
    });
});
