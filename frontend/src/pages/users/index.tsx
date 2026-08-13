import { useEffect } from "react";
import { useRouter } from "next/router";
import { useDispatch, useSelector } from "react-redux";

import { loadAuthFromStorage, setUserId } from "../../redux/auth";
import { RootState } from "../../redux/store";
import { buildRedirectHref } from "../../utils/authRedirect";
import { request } from "../../utils/network";

interface ProfileResponse {
    userId?: number;
}

const LOGIN_REDIRECT = buildRedirectHref("/login", "/users");

/**
 * `/users` 自身没有具体用户，作为「我的主页」入口使用：
 * 解析当前登录用户后跳转到 `/users/{userId}`，未登录则回到登录页。
 * 这样从登录页携带 `redirect=/users` 跳回时不会落到 404。
 */
const UsersIndexPage = () => {
    const router = useRouter();
    const dispatch = useDispatch();
    const token = useSelector((state: RootState) => state.auth.token);
    const userId = useSelector((state: RootState) => state.auth.userId);

    useEffect(() => {
        if (userId !== undefined) {
            void router.replace(`/users/${userId}`);
            return;
        }

        if (token.trim() !== "") {
            // 已登录但本地没有缓存 userId，向后端确认后再跳转。
            request<ProfileResponse>("/api/profile/me", "GET", true)
                .then((res) => {
                    if (typeof res.userId === "number") {
                        dispatch(setUserId(res.userId));
                        void router.replace(`/users/${res.userId}`);
                    } else {
                        void router.replace(LOGIN_REDIRECT);
                    }
                })
                .catch(() => {
                    void router.replace(LOGIN_REDIRECT);
                });
            return;
        }

        // store 中没有 token：可能是尚未从 sessionStorage 注水，也可能是真的未登录。
        // 若本地存储中也没有登录信息，则确认是未登录，跳转到登录页；
        // 否则等待注水完成后本 effect 会随 token 变化重新执行。
        if (loadAuthFromStorage().token.trim() === "") {
            void router.replace(LOGIN_REDIRECT);
        }
    }, [token, userId, router, dispatch]);

    return (
        <main style={{ maxWidth: 760, margin: "0 auto" }}>
            <p>正在跳转到个人主页...</p>
        </main>
    );
};

export default UsersIndexPage;
