const configuredSitePath = process.env.NEXT_PUBLIC_SITE_PATH?.trim().replace(/\/+$/, "") || "";

export const publicSitePath = configuredSitePath === "" || configuredSitePath === "/"
    ? ""
    : (configuredSitePath.startsWith("/") ? configuredSitePath : `/${configuredSitePath}`);

// Prefix browser-visible root-relative URLs while leaving external/data/blob URLs untouched.
export const withPublicSitePath = (url: string): string => {
    const normalizedUrl = url.trim();
    if (
        publicSitePath === ""
        || normalizedUrl === ""
        || !normalizedUrl.startsWith("/")
        || normalizedUrl.startsWith("//")
        || normalizedUrl === publicSitePath
        || normalizedUrl.startsWith(`${publicSitePath}/`)
    ) {
        return url;
    }

    return `${publicSitePath}${normalizedUrl}`;
};

