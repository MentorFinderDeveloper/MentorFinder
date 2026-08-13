import {
    readPendingMentorSearchReturn,
    writePendingMentorSearchReturn,
    clearPendingMentorSearchReturn,
} from "../utils/searchNavigation";

// The search-navigation helpers use sessionStorage to persist a return
// marker so the mentor detail page can navigate back to the correct
// search result entry. Each test starts with a clean storage slate.

beforeEach(() => {
    window.sessionStorage.clear();
});

describe("readPendingMentorSearchReturn", () => {
    // Tests the read module: returns undefined when no valid marker exists,
    // and returns the parsed marker when one is stored.

    it("returns undefined when sessionStorage is empty", () => {
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("returns undefined when the stored value is not valid JSON", () => {
        window.sessionStorage.setItem("search-mentor-return-marker", "not-json");
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("returns undefined when the stored value is missing required fields", () => {
        window.sessionStorage.setItem(
            "search-mentor-return-marker",
            JSON.stringify({ mentorId: 1 }),
        );
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("returns undefined when mentorId is not an integer", () => {
        window.sessionStorage.setItem(
            "search-mentor-return-marker",
            JSON.stringify({
                mentorId: "abc",
                sourceEntryKey: "entry-1",
                targetEntryKey: "entry-2",
                sourcePath: "/search",
            }),
        );
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("returns undefined when mentorId <= 0", () => {
        window.sessionStorage.setItem(
            "search-mentor-return-marker",
            JSON.stringify({
                mentorId: 0,
                sourceEntryKey: "entry-1",
                targetEntryKey: "entry-2",
                sourcePath: "/search",
            }),
        );
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("returns undefined when sourcePath is not /search", () => {
        window.sessionStorage.setItem(
            "search-mentor-return-marker",
            JSON.stringify({
                mentorId: 5,
                sourceEntryKey: "entry-1",
                targetEntryKey: "entry-2",
                sourcePath: "/other",
            }),
        );
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("returns undefined when sourceEntryKey is empty", () => {
        window.sessionStorage.setItem(
            "search-mentor-return-marker",
            JSON.stringify({
                mentorId: 5,
                sourceEntryKey: "",
                targetEntryKey: "entry-2",
                sourcePath: "/search",
            }),
        );
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("returns undefined when targetEntryKey is empty", () => {
        window.sessionStorage.setItem(
            "search-mentor-return-marker",
            JSON.stringify({
                mentorId: 5,
                sourceEntryKey: "entry-1",
                targetEntryKey: "",
                sourcePath: "/search",
            }),
        );
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("reads back a valid stored marker", () => {
        const marker = {
            mentorId: 42,
            sourceEntryKey: "src-key-1",
            targetEntryKey: "tgt-key-2",
            sourcePath: "/search" as const,
        };

        writePendingMentorSearchReturn(marker);
        const result = readPendingMentorSearchReturn();

        expect(result).toEqual(marker);
    });
});

describe("writePendingMentorSearchReturn", () => {
    // Tests the write module: persists a valid marker, rejects invalid ones,
    // and overwrites / clears stale data as needed.

    it("persists a valid marker to sessionStorage", () => {
        writePendingMentorSearchReturn({
            mentorId: 7,
            sourceEntryKey: "src-key",
            targetEntryKey: "tgt-key",
            sourcePath: "/search",
        });

        const raw = window.sessionStorage.getItem("search-mentor-return-marker");
        expect(raw).not.toBeNull();
        expect(JSON.parse(raw as string)).toMatchObject({
            mentorId: 7,
            sourceEntryKey: "src-key",
        });
    });

    it("clears storage when writing an invalid marker (mentorId=0)", () => {
        // writePendingMentorSearchReturn calls normalize internally; if
        // normalization fails, the function should clear the stored marker.
        writePendingMentorSearchReturn({
            mentorId: 0,
            sourceEntryKey: "src-key",
            targetEntryKey: "tgt-key",
            sourcePath: "/search",
        } as any);

        expect(window.sessionStorage.getItem("search-mentor-return-marker")).toBeNull();
    });

    it("overwrites an existing marker", () => {
        writePendingMentorSearchReturn({
            mentorId: 1,
            sourceEntryKey: "old-src",
            targetEntryKey: "old-tgt",
            sourcePath: "/search",
        });

        writePendingMentorSearchReturn({
            mentorId: 2,
            sourceEntryKey: "new-src",
            targetEntryKey: "new-tgt",
            sourcePath: "/search",
        });

        const result = readPendingMentorSearchReturn();
        expect(result?.mentorId).toBe(2);
        expect(result?.sourceEntryKey).toBe("new-src");
    });
});

describe("clearPendingMentorSearchReturn", () => {
    // Tests the clear module: removes the storage entry so subsequent
    // reads return undefined.

    it("removes the marker from sessionStorage", () => {
        writePendingMentorSearchReturn({
            mentorId: 10,
            sourceEntryKey: "src",
            targetEntryKey: "tgt",
            sourcePath: "/search",
        });

        clearPendingMentorSearchReturn();

        expect(window.sessionStorage.getItem("search-mentor-return-marker")).toBeNull();
        expect(readPendingMentorSearchReturn()).toBeUndefined();
    });

    it("is idempotent when no marker exists", () => {
        // Clearing an already-empty storage should not throw.
        expect(() => clearPendingMentorSearchReturn()).not.toThrow();
    });
});

describe("normalize validation (via write/read round-trip)", () => {
    // Tests the normalizePendingMentorSearchReturn validation rules by
    // writing values and reading them back.

    it("trims whitespace from sourceEntryKey and targetEntryKey", () => {
        writePendingMentorSearchReturn({
            mentorId: 3,
            sourceEntryKey: "  src-key  ",
            targetEntryKey: "  tgt-key  ",
            sourcePath: "/search",
        } as any);

        const result = readPendingMentorSearchReturn();
        expect(result?.sourceEntryKey).toBe("src-key");
        expect(result?.targetEntryKey).toBe("tgt-key");
    });
});
