/** @type {import('next').NextConfig} */
// Use the local backend in development and the deployed backend in production.
const backendBaseUrl = process.env.NODE_ENV !== "production"
    ? "http://127.0.0.1:8000"
    : (process.env.BACKEND_URL || "http://127.0.0.1:8000");
const publicSitePath = (process.env.NEXT_PUBLIC_SITE_PATH || "").trim().replace(/\/+$/, "");

const nextConfig = {
    // Emit a self-contained server bundle that can be copied into the runtime image.
    output: "standalone",
    // The public gateway serves this app below /se-projects/<PROJECT_ID>.
    basePath: publicSitePath,
    assetPrefix: publicSitePath,
    // Disabled because some existing effects are not idempotent under dev-mode double invocation.
    reactStrictMode: false,
    // swcMinify: true,

    // Proxy frontend requests to the backend so client code can call stable relative paths.
    async rewrites() {
        return [
            {
                source: "/api/:path*",
                destination: `${backendBaseUrl}/:path*`,
            },
            {
                source: "/media/:path*",
                destination: `${backendBaseUrl}/media/:path*`,
            },
        ];
    }
};

// eslint-disable-next-line no-undef
module.exports = nextConfig;
