import { KeyboardEvent, useMemo, useState } from "react";

interface PaginationProps {
    currentPage: number;
    totalPages: number;
    loading: boolean;
    onPageChange: (page: number) => void;
    showPrevious?: boolean;
    nextLabel?: string;
    centered?: boolean;
    controlHeight?: number;
    jumpInputWidth?: number;
    activePageHighlightColor?: string;
}

const Pagination = ({
    currentPage,
    totalPages,
    loading,
    onPageChange,
    showPrevious = true,
    nextLabel = "下一页",
    centered = false,
    controlHeight,
    jumpInputWidth,
    activePageHighlightColor,
}: PaginationProps) => {
    const [jumpInput, setJumpInput] = useState("");

    // Treat empty datasets as a single virtual page so the controls stay in a stable shape.
    const safeTotal = Math.max(totalPages, 1);
    const controlStyle = controlHeight === undefined
        ? undefined
        : {
            height: controlHeight,
            boxSizing: "border-box" as const,
        };
    const buttonStyle = controlHeight === undefined
        ? undefined
        : {
            ...controlStyle,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 12px",
        };
    const inputStyle = {
        ...controlStyle,
        ...(jumpInputWidth === undefined ? undefined : { width: jumpInputWidth }),
    };

    const pageNumbers = useMemo(() => {
        const pages: number[] = [];
        // Keep the visible page window compact and centered around the current page when possible.
        const windowSize = Math.min(5, safeTotal);
        const halfWindow = Math.floor(windowSize / 2);
        const start = Math.max(1, Math.min(currentPage - halfWindow, safeTotal - windowSize + 1));
        const end = start + windowSize - 1;
        for (let i = start; i <= end; i++) {
            pages.push(i);
        }
        return pages;
    }, [currentPage, safeTotal]);

    const handleJump = () => {
        // Ignore invalid input instead of forcing a page change or showing an alert.
        const num = Number(jumpInput);
        if (Number.isFinite(num) && num >= 1 && num <= safeTotal) {
            onPageChange(num);
            setJumpInput("");
        }
    };

    const handleJumpKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            handleJump();
        }
    };

    return (
        <div
            style={{
                display: "flex",
                alignItems: "center",
                justifyContent: centered ? "center" : undefined,
                gap: 6,
                flexWrap: "wrap",
                width: centered ? "100%" : undefined,
            }}
        >
            {showPrevious && (
                <>
                    <button
                        onClick={() => onPageChange(1)}
                        disabled={loading || currentPage <= 1}
                        style={buttonStyle}
                    >
                        首页
                    </button>
                    <button
                        onClick={() => onPageChange(Math.max(1, currentPage - 1))}
                        disabled={loading || currentPage <= 1}
                        style={buttonStyle}
                    >
                        上一页
                    </button>
                </>
            )}

            {pageNumbers.map((num) => (
                <button
                    key={num}
                    onClick={() => {
                        // Avoid redundant fetches when the current page button is pressed again.
                        if (num !== currentPage) {
                            onPageChange(num);
                        }
                    }}
                    disabled={loading}
                    aria-current={num === currentPage ? "page" : undefined}
                    style={{
                        ...buttonStyle,
                        fontWeight: num === currentPage ? 700 : 400,
                        width: controlHeight ?? 32,
                        minWidth: controlHeight ?? 32,
                        padding: 0,
                        backgroundColor: num === currentPage && activePageHighlightColor !== undefined
                            ? activePageHighlightColor
                            : undefined,
                        borderColor: num === currentPage && activePageHighlightColor !== undefined
                            ? activePageHighlightColor
                            : undefined,
                        color: num === currentPage && activePageHighlightColor !== undefined
                            ? "#ffffff"
                            : undefined,
                    }}
                >
                    {num}
                </button>
            ))}

            <button
                onClick={() => onPageChange(currentPage + 1)}
                disabled={loading || totalPages === 0 || currentPage >= safeTotal}
                style={buttonStyle}
            >
                {nextLabel}
            </button>

            <button
                onClick={() => onPageChange(safeTotal)}
                disabled={loading || totalPages === 0 || currentPage >= safeTotal}
                style={buttonStyle}
            >
                尾页
            </button>

            <input
                type="number"
                value={jumpInput}
                onChange={(e) => setJumpInput(e.target.value)}
                onKeyDown={handleJumpKeyDown}
                placeholder={`共${safeTotal}页`}
                disabled={loading}
                className="paginationJumpInput"
                min={1}
                max={safeTotal}
                style={inputStyle}
            />
            <button
                onClick={handleJump}
                disabled={loading || jumpInput.trim() === ""}
                style={buttonStyle}
            >
                跳转
            </button>
        </div>
    );
};

export default Pagination;
