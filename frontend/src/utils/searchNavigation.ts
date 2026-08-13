// Utilities for preserving and restoring search-page navigation context when
// the user leaves a search result and later returns from a mentor detail page.

export interface PendingMentorSearchReturn {
    mentorId: number;
    sourceEntryKey: string;
    targetEntryKey: string;
    sourcePath: "/search";
}

const SEARCH_RETURN_MARKER_STORAGE_KEY = "search-mentor-return-marker";

// Normalize untrusted storage data into the exact marker shape expected by the
// search-return flow. Invalid values are discarded instead of partially used.
const normalizePendingMentorSearchReturn = (
    value: Partial<PendingMentorSearchReturn> | undefined,
) => {
    const mentorId = Number(value?.mentorId);
    const sourceEntryKey = typeof value?.sourceEntryKey === "string"
        ? value.sourceEntryKey.trim()
        : "";
    const targetEntryKey = typeof value?.targetEntryKey === "string"
        ? value.targetEntryKey.trim()
        : "";

    if (
        !Number.isInteger(mentorId) ||
        mentorId <= 0 ||
        sourceEntryKey === "" ||
        targetEntryKey === "" ||
        value?.sourcePath !== "/search"
    ) {
        return undefined;
    }

    return {
        mentorId,
        sourceEntryKey,
        targetEntryKey,
        sourcePath: "/search",
    } satisfies PendingMentorSearchReturn;
};

// Read the pending mentor-return marker from sessionStorage when running in the
// browser. Invalid JSON or malformed values are treated as "no marker".
export const readPendingMentorSearchReturn = () => {
    if (typeof window === "undefined") {
        return undefined;
    }

    try {
        const rawValue = window.sessionStorage.getItem(SEARCH_RETURN_MARKER_STORAGE_KEY);
        if (typeof rawValue !== "string") {
            return undefined;
        }

        const parsedValue = JSON.parse(rawValue) as Partial<PendingMentorSearchReturn>;
        return normalizePendingMentorSearchReturn(parsedValue);
    }
    catch {
        return undefined;
    }
};

// Persist the pending mentor-return marker so the detail page knows how to
// navigate back to the originating search entry.
export const writePendingMentorSearchReturn = (value: PendingMentorSearchReturn) => {
    if (typeof window === "undefined") {
        return;
    }

    const normalizedValue = normalizePendingMentorSearchReturn(value);
    if (normalizedValue === undefined) {
        clearPendingMentorSearchReturn();
        return;
    }

    try {
        window.sessionStorage.setItem(
            SEARCH_RETURN_MARKER_STORAGE_KEY,
            JSON.stringify(normalizedValue),
        );
    }
    catch {
        // Ignore sessionStorage failures and keep navigation functional.
    }
};

// Remove any stale pending mentor-return marker after it has been consumed or
// when a new navigation flow invalidates the old one.
export const clearPendingMentorSearchReturn = () => {
    if (typeof window === "undefined") {
        return;
    }

    try {
        window.sessionStorage.removeItem(SEARCH_RETURN_MARKER_STORAGE_KEY);
    }
    catch {
        // Ignore sessionStorage failures and keep navigation functional.
    }
};
