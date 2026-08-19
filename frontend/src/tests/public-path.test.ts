type PublicPathModule = typeof import("../utils/publicPath");

const originalSitePath = process.env.NEXT_PUBLIC_SITE_PATH;

const loadPublicPathModule = (sitePath?: string): PublicPathModule => {
    if (sitePath === undefined) {
        delete process.env.NEXT_PUBLIC_SITE_PATH;
    } else {
        process.env.NEXT_PUBLIC_SITE_PATH = sitePath;
    }

    jest.resetModules();
    return require("../utils/publicPath") as PublicPathModule;
};

afterEach(() => {
    if (originalSitePath === undefined) {
        delete process.env.NEXT_PUBLIC_SITE_PATH;
    } else {
        process.env.NEXT_PUBLIC_SITE_PATH = originalSitePath;
    }
    jest.resetModules();
});

describe("public path helpers", () => {
    test("uses no prefix when the deployment path is absent or root", () => {
        expect(loadPublicPathModule().publicSitePath).toBe("");
        expect(loadPublicPathModule("/").publicSitePath).toBe("");
    });

    test("normalizes missing leading and trailing slashes", () => {
        const { publicSitePath } = loadPublicPathModule("se-projects/mentorfinder///");

        expect(publicSitePath).toBe("/se-projects/mentorfinder");
    });

    test("prefixes root-relative API, asset, and root URLs", () => {
        const { withPublicSitePath } = loadPublicPathModule("/se-projects/mentorfinder");

        expect(withPublicSitePath("/api/health")).toBe("/se-projects/mentorfinder/api/health");
        expect(withPublicSitePath("/favicon.ico")).toBe("/se-projects/mentorfinder/favicon.ico");
        expect(withPublicSitePath("/")).toBe("/se-projects/mentorfinder/");
    });

    test("does not duplicate an existing public prefix", () => {
        const { withPublicSitePath } = loadPublicPathModule("/se-projects/mentorfinder");

        expect(withPublicSitePath("/se-projects/mentorfinder")).toBe("/se-projects/mentorfinder");
        expect(withPublicSitePath("/se-projects/mentorfinder/search")).toBe("/se-projects/mentorfinder/search");
    });

    test("leaves empty, relative, external, and protocol-relative URLs unchanged", () => {
        const { withPublicSitePath } = loadPublicPathModule("/se-projects/mentorfinder");

        expect(withPublicSitePath("")).toBe("");
        expect(withPublicSitePath("search")).toBe("search");
        expect(withPublicSitePath("https://example.com/image.png")).toBe("https://example.com/image.png");
        expect(withPublicSitePath("//cdn.example.com/image.png")).toBe("//cdn.example.com/image.png");
        expect(withPublicSitePath("data:image/png;base64,abc")).toBe("data:image/png;base64,abc");
        expect(withPublicSitePath("blob:https://example.com/id")).toBe("blob:https://example.com/id");
    });
});
