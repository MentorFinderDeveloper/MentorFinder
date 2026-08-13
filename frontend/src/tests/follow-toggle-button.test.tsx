import { fireEvent, render, screen } from "@testing-library/react";
import FollowToggleButton from "../components/FollowToggleButton";

describe("FollowToggleButton", () => {
    // Shared render helper that returns the onClick spy so tests can
    // verify click behavior without repeating setup code.
    const renderButton = (overrides: Partial<React.ComponentProps<typeof FollowToggleButton>> = {}) => {
        const onClick = jest.fn();
        const utils = render(
            <FollowToggleButton
                followed={false}
                loading={false}
                onClick={onClick}
                {...overrides}
            />,
        );
        return { onClick, ...utils };
    };

    it("renders '关注' when not followed", () => {
        // The default label for the unfollowed state should be "关注".
        renderButton({ followed: false });
        expect(screen.getByRole("button")).toHaveTextContent("关注");
    });

    it("renders '取消关注' when followed", () => {
        // The default label for the followed state should be "取消关注".
        renderButton({ followed: true });
        expect(screen.getByRole("button")).toHaveTextContent("取消关注");
    });

    it("renders custom followedLabel when followed", () => {
        // Callers can override the followed-state copy with a custom label.
        renderButton({ followed: true, followedLabel: "已关注" });
        expect(screen.getByRole("button")).toHaveTextContent("已关注");
    });

    it("does not apply custom followedLabel when not followed", () => {
        // The followedLabel prop should only affect the followed state;
        // the unfollowed default should remain "关注".
        renderButton({ followed: false, followedLabel: "已关注" });
        expect(screen.getByRole("button")).toHaveTextContent("关注");
    });

    it("is not disabled by default when loading is false and disabled is not set", () => {
        renderButton({ followed: false, loading: false });
        expect(screen.getByRole("button")).toBeEnabled();
    });

    it("is disabled while loading", () => {
        // During a follow/unfollow request the button should be disabled
        // to prevent duplicate submissions.
        renderButton({ followed: true, loading: true });
        expect(screen.getByRole("button")).toBeDisabled();
    });

    it("is disabled when disabled prop is true", () => {
        renderButton({ followed: false, loading: false, disabled: true });
        expect(screen.getByRole("button")).toBeDisabled();
    });

    it("sets aria-busy when loading", () => {
        // Assistive technology should be informed when the button is in a
        // loading state.
        renderButton({ loading: true });
        expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
    });

    it("does not set aria-busy when not loading", () => {
        renderButton({ loading: false });
        expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "false");
    });

    it("shows a loading overlay span when loading", () => {
        // The overlay span preserves button width during loading.
        renderButton({ loading: true });
        const overlays = document.querySelectorAll(".followToggleButtonOverlay");
        expect(overlays.length).toBe(1);
    });

    it("hides the loading overlay span when not loading", () => {
        renderButton({ loading: false });
        const overlays = document.querySelectorAll(".followToggleButtonOverlay");
        expect(overlays.length).toBe(0);
    });

    it("calls onClick when clicked", () => {
        const { onClick } = renderButton({ followed: false });
        fireEvent.click(screen.getByRole("button"));
        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("does not call onClick when disabled", () => {
        const { onClick } = renderButton({ disabled: true });
        fireEvent.click(screen.getByRole("button"));
        expect(onClick).not.toHaveBeenCalled();
    });

    it("does not call onClick when loading", () => {
        const { onClick } = renderButton({ loading: true });
        fireEvent.click(screen.getByRole("button"));
        expect(onClick).not.toHaveBeenCalled();
    });

    it("applies custom className", () => {
        // Callers can pass a custom class for styling.
        const { container } = renderButton({ className: "my-custom-class" });
        const button = container.querySelector("button");
        expect(button?.className).toContain("my-custom-class");
    });

    it("applies custom style", () => {
        // Callers can pass inline styles.
        renderButton({ style: { width: 200, backgroundColor: "red" } });
        const button = screen.getByRole("button");
        expect(button).toHaveStyle({ width: "200px", backgroundColor: "red" });
    });
});
