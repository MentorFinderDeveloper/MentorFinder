import {
    normalizeSearchKeywordForUrl,
    parseSearchQuery,
    buildSearchUrl,
    buildGlobalPaperSearchUrl,
    DEFAULT_SEARCH_QUERY_STATE,
} from "../utils/searchQuery";

describe("normalizeSearchKeywordForUrl", () => {
    // Tests the keyword-normalization module: trimming, empty handling, and
    // binary-search truncation when the encoded keyword exceeds the safe
    // URL length limit (511 bytes).

    it("trims leading and trailing whitespace", () => {
        expect(normalizeSearchKeywordForUrl("  hello  ")).toBe("hello");
    });

    it("returns empty string for whitespace-only input", () => {
        expect(normalizeSearchKeywordForUrl("   ")).toBe("");
    });

    it("returns empty string for empty input", () => {
        expect(normalizeSearchKeywordForUrl("")).toBe("");
    });

    it("preserves a short keyword unchanged", () => {
        const keyword = "machine learning";
        expect(normalizeSearchKeywordForUrl(keyword)).toBe(keyword);
    });

    it("preserves a keyword whose encoded length is exactly at the limit", () => {
        // Build a string whose encoded length equals MAX_SEARCH_QUERY_URL_ENCODED_LENGTH (511).
        const raw = "a".repeat(511); // ASCII chars encode to 1 byte each
        expect(normalizeSearchKeywordForUrl(raw)).toBe(raw);
    });

    it("truncates a keyword whose encoded length exceeds the limit", () => {
        // Build a string whose encoded length is well over 511.
        // CJK characters encode to 9 bytes each (%XX%YY%ZZ × 3), so
        // 60 CJK chars → 540 bytes → exceeding the limit.
        const raw = "中".repeat(60);
        const result = normalizeSearchKeywordForUrl(raw);
        // The result should be shorter than the input and less than or
        // equal to 511 bytes when URL-encoded.
        expect(result.length).toBeLessThan(raw.length);
        expect(encodeURIComponent(result).length).toBeLessThanOrEqual(511);
    });

    it("truncates a mixed ASCII and CJK keyword to fit the limit", () => {
        // Combine ASCII and CJK to exercise the binary search on a mixed
        // codepoint array.
        const raw = "hello " + "世".repeat(60);
        const result = normalizeSearchKeywordForUrl(raw);
        expect(encodeURIComponent(result).length).toBeLessThanOrEqual(511);
        expect(result).toContain("hello");
    });

    it("returns the original string even when empty after trimming and below limit", () => {
        // Regression: ensure that a string that is not empty but whose
        // trimmed form is empty still returns the trimmed empty string.
        expect(normalizeSearchKeywordForUrl("   ")).toBe("");
    });

    it("handles a single character at the limit boundary", () => {
        // A single CJK character encodes to 9 bytes (well under 511).
        expect(normalizeSearchKeywordForUrl("中")).toBe("中");
    });
});

describe("parseSearchQuery", () => {
    // Tests the query-string parser: validates and normalises raw URL query
    // parameters into a stable SearchQueryState object.

    it("parses a full valid search query", () => {
        const result = parseSearchQuery({
            keyword: "deep learning",
            mode: "paper",
            search_mode: "exact",
            sort_mode: "early",
            page: "3",
            visibility: "all",
        });

        expect(result.hasAnySearchParam).toBe(true);
        expect(result.state).toEqual({
            keyword: "deep learning",
            mode: "paper",
            searchMode: "exact",
            sortMode: "early",
            page: 3,
            visibility: "all",
        });
    });

    it("uses defaults for an empty query", () => {
        const result = parseSearchQuery({});

        expect(result.hasAnySearchParam).toBe(false);
        expect(result.state).toEqual(DEFAULT_SEARCH_QUERY_STATE);
    });

    it("falls back to default mode for an invalid mode value", () => {
        const result = parseSearchQuery({ mode: "invalid" });
        expect(result.state.mode).toBe(DEFAULT_SEARCH_QUERY_STATE.mode);
    });

    it("falls back to default search mode for an invalid search_mode value", () => {
        const result = parseSearchQuery({ search_mode: "blurry" });
        expect(result.state.searchMode).toBe(DEFAULT_SEARCH_QUERY_STATE.searchMode);
    });

    it("falls back to default sort mode for an invalid sort_mode value", () => {
        const result = parseSearchQuery({ sort_mode: "random" });
        expect(result.state.sortMode).toBe(DEFAULT_SEARCH_QUERY_STATE.sortMode);
    });

    it("falls back to page 1 for a negative page number", () => {
        const result = parseSearchQuery({ page: "-5" });
        expect(result.state.page).toBe(1);
    });

    it("falls back to page 1 for a zero page number", () => {
        const result = parseSearchQuery({ page: "0" });
        expect(result.state.page).toBe(1);
    });

    it("falls back to page 1 for a non-numeric page value", () => {
        const result = parseSearchQuery({ page: "abc" });
        expect(result.state.page).toBe(1);
    });

    it("floors a fractional page number", () => {
        const result = parseSearchQuery({ page: "4.7" });
        expect(result.state.page).toBe(4);
    });

    it("falls back to default visibility for an invalid visibility value", () => {
        const result = parseSearchQuery({ visibility: "everyone" });
        expect(result.state.visibility).toBe(DEFAULT_SEARCH_QUERY_STATE.visibility);
    });

    it("accepts all valid visibility values", () => {
        const all = parseSearchQuery({ visibility: "all" });
        expect(all.state.visibility).toBe("all");

        const mine = parseSearchQuery({ visibility: "mine" });
        expect(mine.state.visibility).toBe("mine");

        const pub = parseSearchQuery({ visibility: "public" });
        expect(pub.state.visibility).toBe("public");
    });

    it("accepts all valid sort mode values", () => {
        const def = parseSearchQuery({ sort_mode: "default" });
        expect(def.state.sortMode).toBe("default");

        const early = parseSearchQuery({ sort_mode: "early" });
        expect(early.state.sortMode).toBe("early");

        const late = parseSearchQuery({ sort_mode: "late" });
        expect(late.state.sortMode).toBe("late");
    });

    it("uses the first value from an array query parameter", () => {
        const result = parseSearchQuery({ keyword: ["first", "second"] });
        expect(result.state.keyword).toBe("first");
    });

    it("handles undefined query values gracefully", () => {
        const result = parseSearchQuery({ keyword: undefined });
        expect(result.state.keyword).toBe("");
        expect(result.state.mode).toBe(DEFAULT_SEARCH_QUERY_STATE.mode);
    });

    it("detects that search params are present even with one value", () => {
        const result = parseSearchQuery({ keyword: "test" });
        expect(result.hasAnySearchParam).toBe(true);
    });

    it("does not report hasAnySearchParam for only empty-string values", () => {
        const result = parseSearchQuery({ keyword: "", mode: "", page: "" });
        expect(result.hasAnySearchParam).toBe(false);
    });
});

describe("buildSearchUrl", () => {
    // Tests the URL-building module: generates the canonical `/search?...`
    // URL from a SearchQueryState, with mode-specific parameters.

    it("builds a basic mentor search URL", () => {
        const url = buildSearchUrl({
            keyword: "math",
            mode: "mentor",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 1,
            visibility: "all",
        });

        expect(url).toBe("/search?keyword=math&mode=mentor&search_mode=fuzzy");
    });

    it("includes sort_mode for paper mode", () => {
        const url = buildSearchUrl({
            keyword: "ML",
            mode: "paper",
            searchMode: "exact",
            sortMode: "early",
            page: 1,
            visibility: "all",
        });

        expect(url).toContain("sort_mode=early");
        expect(url).toContain("mode=paper");
    });

    it("includes visibility when not 'all' for mentor mode", () => {
        const url = buildSearchUrl({
            keyword: "physics",
            mode: "mentor",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 1,
            visibility: "mine",
        });

        expect(url).toContain("visibility=mine");
    });

    it("does not include visibility when it is 'all' for mentor mode", () => {
        const url = buildSearchUrl({
            keyword: "physics",
            mode: "mentor",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 1,
            visibility: "all",
        });

        expect(url).not.toContain("visibility");
    });

    it("includes page parameter when page > 1", () => {
        const url = buildSearchUrl({
            keyword: "cs",
            mode: "paper",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 3,
            visibility: "all",
        });

        expect(url).toContain("page=3");
    });

    it("omits page parameter when page is 1", () => {
        const url = buildSearchUrl({
            keyword: "cs",
            mode: "mentor",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 1,
            visibility: "all",
        });

        expect(url).not.toContain("page=");
    });

    it("encodes special characters in the keyword", () => {
        const url = buildSearchUrl({
            keyword: "c++",
            mode: "mentor",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 1,
            visibility: "all",
        });

        expect(url).toContain("keyword=c%2B%2B");
    });

    it("omits visibility for paper mode even when set", () => {
        // Paper mode does not use the visibility parameter.
        const url = buildSearchUrl({
            keyword: "AI",
            mode: "paper",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 1,
            visibility: "mine",
        });

        expect(url).not.toContain("visibility");
    });

    it("handles an empty keyword", () => {
        const url = buildSearchUrl({
            keyword: "",
            mode: "mentor",
            searchMode: "fuzzy",
            sortMode: "default",
            page: 1,
            visibility: "all",
        });

        expect(url).toBe("/search?keyword=&mode=mentor&search_mode=fuzzy");
    });
});

describe("buildGlobalPaperSearchUrl", () => {
    // Tests the global search-box convenience helper: always opens a fuzzy
    // paper search with default parameters.

    it("builds a fuzzy paper search URL for the given keyword", () => {
        const url = buildGlobalPaperSearchUrl("transformer");
        expect(url).toContain("keyword=transformer");
        expect(url).toContain("mode=paper");
        expect(url).toContain("search_mode=fuzzy");
        expect(url).toContain("sort_mode=default");
        expect(url).not.toContain("visibility=");
        expect(url).not.toContain("page=");
    });

    it("trims and encodes the keyword", () => {
        const url = buildGlobalPaperSearchUrl("  neural net  ");
        expect(url).toContain("keyword=neural+net");
    });

    it("handles an empty keyword", () => {
        const url = buildGlobalPaperSearchUrl("");
        expect(url).toBe("/search?keyword=&mode=paper&search_mode=fuzzy&sort_mode=default");
    });
});
