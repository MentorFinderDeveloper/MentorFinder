import { fireEvent, render, screen } from "@testing-library/react";
import Pagination from "../components/Pagination";

describe("Pagination", () => {
    // Shared render helper for the pagination component.
    // Most tests only vary one or two props, so this helper provides stable
    // defaults and returns the page-change spy for assertions.
    const renderPagination = (overrides: Partial<React.ComponentProps<typeof Pagination>> = {}) => {
        const onPageChange = jest.fn();
        const utils = render(
            <Pagination
                currentPage={1}
                totalPages={10}
                loading={false}
                onPageChange={onPageChange}
                {...overrides}
            />,
        );
        return { onPageChange, ...utils };
    };

    it("renders 首页 / 上一页 / 下一页 / 尾页 / 跳转 by default", () => {
        // Tests the default control-rendering module.
        // A standard pagination bar should expose first-page, previous-page,
        // next-page, last-page, and manual jump controls.
        renderPagination({ currentPage: 5 });

        expect(screen.getByRole("button", { name: "首页" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "上一页" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "下一页" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "尾页" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "跳转" })).toBeInTheDocument();
    });

    it("renders a 5-page window centered on the current page (n-2..n+2)", () => {
        // Tests the page-window calculation module.
        // When enough pages exist, the component should render a five-page
        // window centered around the current page rather than all page numbers.
        renderPagination({ currentPage: 5, totalPages: 10 });

        ["3", "4", "5", "6", "7"].forEach((label) => {
            expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
        });
        expect(screen.queryByRole("button", { name: "2" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "8" })).not.toBeInTheDocument();
    });

    it("disables 首页 and 上一页 on the first page, enables 下一页 and 尾页", () => {
        // Tests boundary-state behavior on the first page.
        // Backward navigation should be disabled at page 1, while forward
        // navigation remains available.
        renderPagination({ currentPage: 1, totalPages: 10 });

        expect(screen.getByRole("button", { name: "首页" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "尾页" })).toBeEnabled();
    });

    it("disables 下一页 and 尾页 on the last page, enables 首页 and 上一页", () => {
        // Tests boundary-state behavior on the last page.
        // Forward navigation should be disabled at the final page, while
        // backward navigation remains available.
        renderPagination({ currentPage: 10, totalPages: 10 });

        expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "尾页" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "首页" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "上一页" })).toBeEnabled();
    });

    it("jumps to page 1 when 首页 is clicked", () => {
        // Tests first-page shortcut behavior.
        // Clicking the first-page control should emit page 1 through the
        // onPageChange callback.
        const { onPageChange } = renderPagination({ currentPage: 7, totalPages: 10 });

        fireEvent.click(screen.getByRole("button", { name: "首页" }));

        expect(onPageChange).toHaveBeenCalledWith(1);
    });

    it("jumps to the last page when 尾页 is clicked", () => {
        // Tests last-page shortcut behavior.
        // Clicking the last-page control should emit the final page number.
        const { onPageChange } = renderPagination({ currentPage: 3, totalPages: 10 });

        fireEvent.click(screen.getByRole("button", { name: "尾页" }));

        expect(onPageChange).toHaveBeenCalledWith(10);
    });

    it("jumps to entered page when 跳转 is clicked", () => {
        // Tests manual jump submission through the jump button.
        // A valid page number entered in the input should be passed to the
        // page-change callback when the jump action is clicked.
        const { onPageChange } = renderPagination({ currentPage: 1, totalPages: 10 });

        const input = screen.getByPlaceholderText("共10页");
        fireEvent.change(input, { target: { value: "6" } });
        fireEvent.click(screen.getByRole("button", { name: "跳转" }));

        expect(onPageChange).toHaveBeenCalledWith(6);
    });

    it("jumps when Enter is pressed inside the jump input", () => {
        // Tests keyboard submission for the manual jump module.
        // Pressing Enter inside the input should trigger the same page jump as
        // clicking the jump button.
        const { onPageChange } = renderPagination({ currentPage: 1, totalPages: 10 });

        const input = screen.getByPlaceholderText("共10页");
        fireEvent.change(input, { target: { value: "4" } });
        fireEvent.keyDown(input, { key: "Enter" });

        expect(onPageChange).toHaveBeenCalledWith(4);
    });

    it("ignores jump values outside [1, totalPages]", () => {
        // Tests input-range validation for manual jumps.
        // Invalid page numbers below 1 or above totalPages should not trigger
        // any page change callback.
        const { onPageChange } = renderPagination({ currentPage: 1, totalPages: 10 });

        const input = screen.getByPlaceholderText("共10页");
        fireEvent.change(input, { target: { value: "0" } });
        fireEvent.click(screen.getByRole("button", { name: "跳转" }));
        fireEvent.change(input, { target: { value: "11" } });
        fireEvent.click(screen.getByRole("button", { name: "跳转" }));

        expect(onPageChange).not.toHaveBeenCalled();
    });

    it("keeps 跳转 disabled when the input is empty", () => {
        // Tests empty-input guarding for the jump action.
        // Without a user-entered page number, the jump button should stay
        // disabled to prevent meaningless submissions.
        renderPagination({ currentPage: 1, totalPages: 10 });

        expect(screen.getByRole("button", { name: "跳转" })).toBeDisabled();
    });

    it("hides 首页 and 上一页 when showPrevious is false but still renders 下一页 and 尾页", () => {
        // Tests conditional rendering of previous-navigation controls.
        // When showPrevious is disabled, the component should hide the first
        // and previous buttons while preserving forward navigation controls.
        renderPagination({ currentPage: 1, totalPages: 10, showPrevious: false });

        expect(screen.queryByRole("button", { name: "首页" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "上一页" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "下一页" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "尾页" })).toBeInTheDocument();
    });

    it("disables every control while loading", () => {
        // Tests the loading-state module.
        // While pagination is waiting for data, all buttons and the jump input
        // should be disabled so the user cannot issue conflicting actions.
        renderPagination({ currentPage: 5, totalPages: 10, loading: true });

        ["首页", "上一页", "下一页", "尾页", "跳转"].forEach((label) => {
            expect(screen.getByRole("button", { name: label })).toBeDisabled();
        });
        expect(screen.getByPlaceholderText("共10页")).toBeDisabled();
    });

    it("treats totalPages=0 as a single page and disables next/last", () => {
        // Tests the zero-page fallback module.
        // If totalPages is reported as 0, the component should degrade
        // gracefully to a single visible page and disable forward navigation.
        renderPagination({ currentPage: 1, totalPages: 0 });

        expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "尾页" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "1" })).toBeInTheDocument();
    });
});
