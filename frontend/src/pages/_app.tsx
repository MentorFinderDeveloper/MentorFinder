import Head from "next/head";
import "../styles/globals.css";
import "katex/dist/katex.min.css";
import type { AppProps } from "next/app";
import { useEffect } from "react";
import { useRouter } from "next/router";
import { Provider, useDispatch } from "react-redux";

import TopNav from "../components/TopNav";
import { hydrateAuth, loadAuthFromStorage } from "../redux/auth";
import store from "../redux/store";

// Render the global app shell, hydrate auth once, and decide whether to show the shared top navigation.
// eslint-disable-next-line @typescript-eslint/naming-convention
const App = ({ Component, pageProps }: AppProps) => {
    const dispatch = useDispatch();
    const router = useRouter();
    // Auth pages use a simplified shell without the global navigation bar.
    const isAuthPage = router.pathname === "/login" || router.pathname === "/register" || router.pathname === "/reset-password";

    useEffect(() => {
        // Rehydrate auth state from local storage once at app startup so page refreshes preserve login.
        dispatch(hydrateAuth(loadAuthFromStorage()));
    }, [dispatch]);

    return (
        <>
            <Head>
                <title>找导师</title>
            </Head>
            <div className={isAuthPage ? "appChrome appChromeAuth" : "appChrome"}>
                {!isAuthPage && <TopNav />}
                <main className={isAuthPage ? "appMain appMainAuth" : "appMain"}>
                    <Component {...pageProps} />
                </main>
            </div>
        </>
    );
};

// Wrap the custom Next.js app with the Redux provider so every page can access the shared store.
export default function AppWrapper(props: AppProps) {
    // Provide the Redux store to every page through the custom Next.js app entry point.
    return (
        <Provider store={store}>
            <App {...props} />
        </Provider>
    );
}
