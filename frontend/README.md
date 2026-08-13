# MentorFinder Frontend

## Overview

This project is the frontend for MentorFinder, a mentor-discovery platform built with Next.js and React. It provides the user interface for discovering mentors, browsing papers, following mentors, managing personal profiles, and receiving personalized weekly push recommendations.

The application uses the Next.js Pages Router and integrates with a backend service through rewrite-based API proxying. It also includes authentication state persistence, shared network utilities, automated tests, and a Docker-based deployment path.

## Features

- User authentication with sign in, registration, password reset, and persisted login state
- Mentor and paper search with pagination, filtering, sorting, and search-state restoration
- Mentor follow and unfollow flows
- Personalized weekly push reports on the home page
- Timeline and mentor detail views
- Profile editing and profile settings management
- Follow list and private mentor views
- Admin user management and mentor verification workflows

Current routed pages include:

- `/` (`index`)
- `/search`
- `/login`
- `/register`
- `/reset-password`
- `/follows`
- `/timeline`
- `/private-mentor`
- `/profile`
- `/profile-settings`
- `/admin-users`

## Tech Stack

- Next.js 15.1.7 with the Pages Router
- React 19
- TypeScript
- Redux Toolkit and React Redux
- Jest, jsdom, and Testing Library
- ESLint
- pnpm

## Project Structure

```text
frontend/
├── public/          Static assets such as logos, icons, and images
├── src/components/  Reusable UI components
├── src/pages/       Route-level pages built with the Next.js Pages Router
├── src/redux/       Global auth state and Redux store setup
├── src/tests/       Jest and Testing Library test cases
├── src/utils/       Shared helpers for networking, search, redirects, and types
├── Dockerfile
├── next.config.js
└── package.json
```

## Getting Started

### Prerequisites

- Node.js
- pnpm

### Install dependencies

```bash
pnpm install
```

### Start the development server

```bash
pnpm dev
```

Then open `http://localhost:3000`.

The frontend expects the backend to be available at `http://127.0.0.1:8000` during local development unless proxy settings are changed.

## Available Scripts

- `pnpm dev` starts the local Next.js development server
- `pnpm build` creates a production build
- `pnpm start` runs the production server from the build output
- `pnpm lint` runs the Next.js ESLint checks
- `pnpm fix` applies ESLint auto-fixes to `src`
- `pnpm test` runs the Jest test suite
- `pnpm export` runs `next export`

## Backend Integration

The frontend proxies backend traffic through `next.config.js` rewrites so client code can use stable relative paths.

- `/api/:path*` is rewritten to the backend service
- `/media/:path*` is rewritten to the backend service

Environment behavior:

- In development, the default backend base URL is `http://127.0.0.1:8000`
- In production, the fallback backend URL is `https://backend-mentorfinder.app.spring26a.secoder.net`
- In production, `BACKEND_URL` can be used to override the default backend target

## Auth and State Conventions

- Authentication state is stored in Redux
- The persisted auth snapshot is saved to `localStorage` under the key `mentorfinder_auth`
- Auth state includes the token, display name, role, user id, and avatar URL
- Authenticated requests go through the shared `request(...)` helper in `src/utils/network.ts`
- The request helper injects the bearer token automatically for protected requests and normalizes backend error handling

## Testing

The project uses Jest with the Next.js Jest preset, `jsdom`, and Testing Library.

Existing tests cover areas including:

- auth flows
- search behavior
- pagination
- timeline behavior
- admin users
- mentor detail
- follow confirmation
- top navigation
- profile settings
- network utility behavior

Coverage output is written to `.coverage/`.

## Docker

A `Dockerfile` is included for containerized build and deployment workflows.

## Notes

- This project uses the Next.js Pages Router rather than the App Router
- API communication is designed around relative frontend paths and rewrite-based proxying
- Login persistence is handled on the client through Redux plus `localStorage`
- Tests and coverage artifacts already exist in the repository and can be regenerated with `pnpm test`
