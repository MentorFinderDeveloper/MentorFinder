import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { useSelector } from "react-redux";

import { RootState } from "../redux/store";
import { INPUT_LIMITS } from "../constants/inputLimits";
import { describeRequestError } from "../utils/errorMessage";
import { NetworkError, NetworkErrorType, request } from "../utils/network";
import { AdminUserResult, MentorVerificationRequestResult, SearchMentorResult } from "../utils/types";

type UserRole = "student" | "mentor" | "admin" | "banned";
type UserRoleFilter = "" | UserRole;
interface AdminUsersResponse {
    users?: AdminUserResult[];
    verificationRequests?: MentorVerificationRequestResult[];
    currentUserId?: number;
}
interface SearchMentorsResponse {
    mentors?: SearchMentorResult[];
}
interface UpdateAdminUserResponse {
    user: AdminUserResult;
}

// Render the admin dashboard for user-role management and mentor verification review.
const AdminUsersPage = () => {
    const router = useRouter();
    const token = useSelector((state: RootState) => state.auth.token);
    const role = useSelector((state: RootState) => state.auth.role);
    // Gate every management action behind an authenticated admin session.
    const isAdmin = token.trim() !== "" && role === "admin";

    const [loadingUsers, setLoadingUsers] = useState(false);
    const [savingUserId, setSavingUserId] = useState<number | undefined>(undefined);
    const [errorMessage, setErrorMessage] = useState("");
    const [successMessage, setSuccessMessage] = useState("");
    const [searchKeyword, setSearchKeyword] = useState("");
    const [roleFilter, setRoleFilter] = useState<UserRoleFilter>("");
    const [users, setUsers] = useState<AdminUserResult[]>([]);
    const [verificationRequests, setVerificationRequests] = useState<MentorVerificationRequestResult[]>([]);
    const [currentUserId, setCurrentUserId] = useState<number | undefined>(undefined);
    const [mentorSearchKeyword, setMentorSearchKeyword] = useState("");
    const [mentorSearchLoading, setMentorSearchLoading] = useState(false);
    const [mentorSearchResults, setMentorSearchResults] = useState<SearchMentorResult[]>([]);
    const [reviewingRequestId, setReviewingRequestId] = useState<number | undefined>(undefined);
    const [approvalMentorIdByRequestId, setApprovalMentorIdByRequestId] = useState<Record<number, string>>({});
    const [verificationMentorSearchKeywordByRequestId, setVerificationMentorSearchKeywordByRequestId] = useState<Record<number, string>>({});
    const [verificationMentorSearchLoadingByRequestId, setVerificationMentorSearchLoadingByRequestId] = useState<Record<number, boolean>>({});
    const [verificationMentorSearchResultsByRequestId, setVerificationMentorSearchResultsByRequestId] = useState<Record<number, SearchMentorResult[]>>({});

    const [draftRoleByUserId, setDraftRoleByUserId] = useState<Record<number, UserRole>>({});
    const [draftMentorIdByUserId, setDraftMentorIdByUserId] = useState<Record<number, string>>({});

    // Convert network and authorization failures into concise admin-facing messages.
    const formatError = (err: unknown) => {
        // Normalize network-layer errors into short admin-friendly feedback strings.
        if (err instanceof NetworkError) {
            if (err.type === NetworkErrorType.UNAUTHORIZED) {
                return "请先登录管理员账号";
            }
            if (err.type === NetworkErrorType.REJECTED) {
                return "当前账号无权限执行该操作";
            }
        }
        return describeRequestError(err);
    };

    // Rebuild the editable role and mentor-binding drafts from the latest fetched user list.
    const syncDrafts = (nextUsers: AdminUserResult[]) => {
        // Keep the editable role / mentor binding controls in sync with the latest server snapshot.
        const nextRoleDrafts: Record<number, UserRole> = {};
        const nextMentorDrafts: Record<number, string> = {};
        for (const user of nextUsers) {
            nextRoleDrafts[user.id] = user.role as UserRole;
            nextMentorDrafts[user.id] = user.mentorProfile ? String(user.mentorProfile.id) : "";
        }
        setDraftRoleByUserId(nextRoleDrafts);
        setDraftMentorIdByUserId(nextMentorDrafts);
    };

    // Fetch the admin user list together with pending verification requests under the current filters.
    const fetchUsers = async (keyword?: string, nextRoleFilter?: UserRoleFilter) => {
        if (!isAdmin) {
            return;
        }

        setLoadingUsers(true);
        setErrorMessage("");

        try {
            const trimmedKeyword = (keyword ?? searchKeyword).trim();
            const resolvedRoleFilter = nextRoleFilter ?? roleFilter;
            // Build a compact query string so the page can filter users server-side.
            const queryParams = new URLSearchParams();
            if (trimmedKeyword !== "") {
                queryParams.set("keyword", trimmedKeyword);
            }
            if (resolvedRoleFilter !== "") {
                queryParams.set("role", resolvedRoleFilter);
            }
            const query = queryParams.toString() === "" ? "" : `?${queryParams.toString()}`;
            const res = await request<AdminUsersResponse>(`/api/management/users${query}`, "GET", true);
            const nextUsers = Array.isArray(res.users) ? res.users : [];
            setUsers(nextUsers);
            // Verification requests are returned with the user list so the admin has one consolidated dashboard.
            setVerificationRequests(
                Array.isArray(res.verificationRequests)
                    ? res.verificationRequests : [],
            );
            setCurrentUserId(typeof res.currentUserId === "number" ? res.currentUserId : undefined);
            syncDrafts(nextUsers);
        }
        catch (err) {
            setUsers([]);
            setVerificationRequests([]);
            setErrorMessage(formatError(err));
        }
        finally {
            setLoadingUsers(false);
        }
    };

    useEffect(() => {
        if (!isAdmin) {
            return;
        }
        // Load the unfiltered admin view on first entry.
        void fetchUsers("", "");
    }, [isAdmin]);

    // Expose only public mentor records for admin role binding and approval flows.
    // Filter the generic mentor search results down to public mentors only.
    const publicMentorSearchResults = useMemo(() => {
        // Admin role binding must point at public mentor records, never a student's private mentor.
        return mentorSearchResults.filter((mentor) => !mentor.is_private);
    }, [mentorSearchResults]);

    // Read the mentor search results associated with a specific verification request.
    // Return the public mentor candidates associated with one verification request.
    const getVerificationMentorSearchResults = (requestId: number) => {
        return (verificationMentorSearchResultsByRequestId[requestId] || []).filter((mentor) => !mentor.is_private);
    };

    // Search public mentors that admins can bind to users promoted to mentor accounts.
    const searchPublicMentors = async () => {
        const trimmedKeyword = mentorSearchKeyword.trim();
        if (trimmedKeyword === "") {
            setMentorSearchResults([]);
            return;
        }

        setMentorSearchLoading(true);
        setErrorMessage("");

        try {
            // Reuse the normal mentor search API to find a public mentor record for role binding.
            const res = await request<SearchMentorsResponse>(
                `/api/search/mentors?keyword=${encodeURIComponent(trimmedKeyword)}&search_mode=fuzzy`,
                "GET",
                true,
            );
            const nextMentors = Array.isArray(res.mentors) ? res.mentors : [];
            setMentorSearchResults(nextMentors);
        }
        catch (err) {
            setMentorSearchResults([]);
            setErrorMessage(formatError(err));
        }
        finally {
            setMentorSearchLoading(false);
        }
    };

    // Search public mentors for a single verification request before approval.
    const searchVerificationMentors = async (requestId: number) => {
        const trimmedKeyword = (verificationMentorSearchKeywordByRequestId[requestId] || "").trim();
        if (trimmedKeyword === "") {
            setVerificationMentorSearchResultsByRequestId((prev) => ({
                ...prev,
                [requestId]: [],
            }));
            return;
        }

        setVerificationMentorSearchLoadingByRequestId((prev) => ({
            ...prev,
            [requestId]: true,
        }));
        setErrorMessage("");

        try {
            // Each verification request can search independently because approvals may map to different public mentors.
            const res = await request<SearchMentorsResponse>(
                `/api/search/mentors?keyword=${encodeURIComponent(trimmedKeyword)}&search_mode=fuzzy`,
                "GET",
                true,
            );
            const nextMentors = Array.isArray(res.mentors) ? res.mentors : [];
            setVerificationMentorSearchResultsByRequestId((prev) => ({
                ...prev,
                [requestId]: nextMentors,
            }));
        }
        catch (err) {
            setVerificationMentorSearchResultsByRequestId((prev) => ({
                ...prev,
                [requestId]: [],
            }));
            setErrorMessage(formatError(err));
        }
        finally {
            setVerificationMentorSearchLoadingByRequestId((prev) => ({
                ...prev,
                [requestId]: false,
            }));
        }
    };

    // Persist the current draft role and optional mentor binding for one user.
    const saveUser = async (user: AdminUserResult) => {
        const nextRole = draftRoleByUserId[user.id] || (user.role as UserRole);
        const nextMentorId = (draftMentorIdByUserId[user.id] || "").trim();
        const payload: { role: UserRole; mentorId?: number } = {
            role: nextRole,
        };

        // Only mentor accounts need a binding to a concrete public mentor record.
        if (nextRole === "mentor" && nextMentorId !== "") {
            payload.mentorId = Number(nextMentorId);
        }

        setSavingUserId(user.id);
        setErrorMessage("");
        setSuccessMessage("");

        try {
            const res = await request<UpdateAdminUserResponse>(`/api/management/users/${user.id}`, "PUT", true, payload);
            const updatedUser = res.user;
            // Patch the edited user into the current list instead of refetching the whole page.
            const nextUsers = users.map((currentUser) => currentUser.id === user.id ? updatedUser : currentUser);
            setUsers(nextUsers);
            syncDrafts(nextUsers);
            setSuccessMessage(`已更新用户 ${updatedUser.username}`);
        }
        catch (err) {
            setErrorMessage(formatError(err));
        }
        finally {
            setSavingUserId(undefined);
        }
    };

    // Approve or reject a mentor verification request, optionally binding it to a public mentor record.
    const reviewVerificationRequest = async (
        requestId: number,
        status: "approved" | "rejected",
    ) => {
        const payload: {
            status: "approved" | "rejected";
            mentorId?: number;
        } = { status };

        if (status === "approved") {
            const mentorId = (approvalMentorIdByRequestId[requestId] || "").trim();
            if (mentorId === "") {
                setErrorMessage("审核通过前必须先搜索并选择一位公共导师");
                return;
            }
            // Approval both upgrades the user and binds the request to the selected public mentor record.
            payload.mentorId = Number(mentorId);
        }

        setReviewingRequestId(requestId);
        setErrorMessage("");
        setSuccessMessage("");

        try {
            await request(`/api/management/verification-requests/${requestId}`, "PUT", true, payload);
            // Refresh after review because both the request list and user table may change.
            await fetchUsers();
            setSuccessMessage(status === "approved" ? "认证请求已审核通过" : "认证请求已拒绝");
        } catch (err) {
            setErrorMessage(formatError(err));
        } finally {
            setReviewingRequestId(undefined);
        }
    };

    if (!isAdmin) {
        return (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
                <h2>用户管理</h2>
                <p>仅管理员可以访问该页面。</p>
                <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => router.push("/")}>返回首页</button>
                </div>
            </div>
        );
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 980 }}>
            <h2>用户管理</h2>
            <p>管理员可统一管理用户角色，并将 `mentor` 角色绑定到公共导师数据库中的导师记录。</p>

            <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => router.push("/")}>返回首页</button>
                <button onClick={() => router.push("/search")}>去检索</button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, border: "1px solid #ccc", borderRadius: 6, padding: 12 }}>
                <h3 style={{ margin: 0 }}>用户筛选</h3>
                <div style={{ display: "flex", gap: 8 }}>
                    <input
                        type="text"
                        value={searchKeyword}
                        maxLength={INPUT_LIMITS.KEYWORD}
                        placeholder="按用户名、邮箱或真实姓名搜索"
                        onChange={(e) => setSearchKeyword(e.target.value)}
                        style={{ flex: 1 }}
                    />
                    <select
                        value={roleFilter}
                        onChange={(e) => setRoleFilter(e.target.value as UserRoleFilter)}
                        style={{ width: 180 }}
                    >
                        <option value="">全部角色</option>
                        <option value="student">student</option>
                        <option value="mentor">mentor</option>
                        <option value="admin">admin</option>
                        <option value="banned">banned</option>
                    </select>
                    <button onClick={() => void fetchUsers()} disabled={loadingUsers}>
                        {loadingUsers ? "搜索中..." : "搜索用户"}
                    </button>
                </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, border: "1px solid #ccc", borderRadius: 6, padding: 12 }}>
                <h3 style={{ margin: 0 }}>公共导师检索</h3>
                <div style={{ display: "flex", gap: 8 }}>
                    <input
                        type="text"
                        value={mentorSearchKeyword}
                        maxLength={INPUT_LIMITS.KEYWORD}
                        placeholder="搜索公共导师，便于绑定 mentor 角色"
                        onChange={(e) => setMentorSearchKeyword(e.target.value)}
                        style={{ flex: 1 }}
                    />
                    <button
                        aria-label="搜索公共导师"
                        onClick={() => void searchPublicMentors()}
                        disabled={mentorSearchLoading}
                    >
                        {mentorSearchLoading ? "搜索中..." : "搜索导师"}
                    </button>
                </div>

                {publicMentorSearchResults.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {publicMentorSearchResults.map((mentor) => (
                            <div key={mentor.id} style={{ padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
                                <p style={{ margin: "0 0 4px" }}>
                                    {mentor.Chinese_name}
                                    {mentor.English_name ? ` / ${mentor.English_name}` : ""}
                                </p>
                                <p style={{ margin: 0 }}>ID: {mentor.id}，方向：{mentor.research_direction || "暂无研究方向"}</p>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, border: "1px solid #ccc", borderRadius: 6, padding: 12 }}>
                <h3 style={{ margin: 0 }}>用户认证请求列表</h3>
                {verificationRequests.length === 0 ? (
                    <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                        当前没有待查看的认证请求。
                    </div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {verificationRequests.map((requestItem) => (
                            <div key={requestItem.id} style={{ padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
                                <p style={{ margin: "0 0 4px" }}>用户：{requestItem.username}</p>
                                <p style={{ margin: "0 0 4px" }}>邮箱：{requestItem.userEmail}</p>
                                <p style={{ margin: "0 0 4px" }}>申请姓名：{requestItem.submittedName}</p>
                                <p style={{ margin: "0 0 4px" }}>状态：{requestItem.status}</p>
                                <p style={{ margin: 0 }}>提交时间：{requestItem.createdAt || "未知"}</p>
                                {requestItem.status === "pending" && (
                                    <>
                                        {/* The admin first searches a matching public mentor, then chooses approve or reject. */}
                                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                                            <input
                                                type="text"
                                                value={verificationMentorSearchKeywordByRequestId[requestItem.id] || ""}
                                                maxLength={INPUT_LIMITS.KEYWORD}
                                                placeholder="搜索并选择要绑定的公共导师"
                                                onChange={(e) => setVerificationMentorSearchKeywordByRequestId((prev) => ({
                                                    ...prev,
                                                    [requestItem.id]: e.target.value,
                                                }))}
                                                disabled={reviewingRequestId === requestItem.id}
                                                style={{ flex: 1, minWidth: 240 }}
                                            />
                                            <button
                                                aria-label={`为${requestItem.username}搜索导师`}
                                                onClick={() => void searchVerificationMentors(requestItem.id)}
                                                disabled={reviewingRequestId === requestItem.id || verificationMentorSearchLoadingByRequestId[requestItem.id]}
                                            >
                                                {verificationMentorSearchLoadingByRequestId[requestItem.id] ? "搜索中..." : "搜索导师"}
                                            </button>
                                        </div>

                                        {getVerificationMentorSearchResults(requestItem.id).length > 0 && (
                                            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                                                {getVerificationMentorSearchResults(requestItem.id).map((mentor) => (
                                                    <button
                                                        key={`${requestItem.id}-${mentor.id}`}
                                                        onClick={() => setApprovalMentorIdByRequestId((prev) => ({
                                                            ...prev,
                                                            [requestItem.id]: String(mentor.id),
                                                        }))}
                                                        disabled={reviewingRequestId === requestItem.id}
                                                        style={{
                                                            textAlign: "left",
                                                            padding: 10,
                                                            borderRadius: 6,
                                                            border: approvalMentorIdByRequestId[requestItem.id] === String(mentor.id)
                                                                ? "1px solid #0d6efd" : "1px solid #ddd",
                                                            backgroundColor: approvalMentorIdByRequestId[requestItem.id] === String(mentor.id)
                                                                ? "#e7f1ff" : "#fff",
                                                        }}
                                                    >
                                                        <div>{mentor.Chinese_name}{mentor.English_name ? ` / ${mentor.English_name}` : ""}</div>
                                                        <div style={{ fontSize: 12, color: "#666" }}>
                                                            ID: {mentor.id}，方向：{mentor.research_direction || "暂无研究方向"}
                                                        </div>
                                                    </button>
                                                ))}
                                            </div>
                                        )}

                                        {approvalMentorIdByRequestId[requestItem.id] && (
                                            <p style={{ margin: "8px 0 0" }}>
                                                已选择公共导师 ID：{approvalMentorIdByRequestId[requestItem.id]}
                                            </p>
                                        )}

                                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                                            <button
                                                aria-label={`通过${requestItem.username}的申请`}
                                                onClick={() => void reviewVerificationRequest(requestItem.id, "approved")}
                                                disabled={reviewingRequestId === requestItem.id}
                                            >
                                                {reviewingRequestId === requestItem.id ? "处理中..." : "审核通过"}
                                            </button>
                                            <button
                                                aria-label={`拒绝${requestItem.username}的申请`}
                                                onClick={() => void reviewVerificationRequest(requestItem.id, "rejected")}
                                                disabled={reviewingRequestId === requestItem.id}
                                            >
                                                {reviewingRequestId === requestItem.id ? "处理中..." : "拒绝申请"}
                                            </button>
                                        </div>
                                    </>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {errorMessage !== "" && (
                <div style={{ padding: 12, border: "1px solid #f1aeb5", backgroundColor: "#f8d7da" }}>
                    {errorMessage}
                </div>
            )}

            {successMessage !== "" && (
                <div style={{ padding: 12, border: "1px solid #badbcc", backgroundColor: "#d1e7dd" }}>
                    {successMessage}
                </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {users.map((user) => {
                    const draftRole = draftRoleByUserId[user.id] || (user.role as UserRole);
                    const draftMentorId = draftMentorIdByUserId[user.id] || "";
                    const isSaving = savingUserId === user.id;

                    return (
                        <div key={user.id} style={{ padding: 12, border: "1px solid #ccc", borderRadius: 6 }}>
                            <h3 style={{ margin: "0 0 8px" }}>
                                {user.username}
                                {currentUserId === user.id && (
                                    <span style={{ marginLeft: 8, fontSize: 12, color: "#555" }}>当前登录管理员</span>
                                )}
                            </h3>
                            <p style={{ margin: "4px 0" }}>邮箱：{user.email}</p>
                            <p style={{ margin: "4px 0" }}>当前角色：{user.role}</p>
                            <p style={{ margin: "4px 0" }}>
                                当前绑定公共导师：
                                {user.mentorProfile ? `${user.mentorProfile.Chinese_name} (ID: ${user.mentorProfile.id})` : "未绑定"}
                            </p>

                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                                <select
                                    value={draftRole}
                                    onChange={(e) => {
                                        const nextRole = e.target.value as UserRole;
                                        setDraftRoleByUserId((prev) => ({ ...prev, [user.id]: nextRole }));
                                        // Clear stale mentor bindings whenever the draft role stops being mentor.
                                        if (nextRole !== "mentor") {
                                            setDraftMentorIdByUserId((prev) => ({ ...prev, [user.id]: "" }));
                                        }
                                    }}
                                    disabled={isSaving}
                                >
                                    <option value="student">student</option>
                                    <option value="mentor">mentor</option>
                                    <option value="admin">admin</option>
                                    <option value="banned">banned</option>
                                </select>

                                <input
                                    type="number"
                                    value={draftMentorId}
                                    placeholder="公共导师 ID（mentor 必填）"
                                    onChange={(e) => setDraftMentorIdByUserId((prev) => ({ ...prev, [user.id]: e.target.value }))}
                                    disabled={isSaving || draftRole !== "mentor"}
                                    style={{ width: 220 }}
                                />

                                <button
                                    onClick={() => void saveUser(user)}
                                    disabled={isSaving || (draftRole === "mentor" && draftMentorId.trim() === "")}
                                >
                                    {isSaving ? "保存中..." : "保存角色与绑定"}
                                </button>
                            </div>
                        </div>
                    );
                })}

                {!loadingUsers && users.length === 0 && (
                    <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                        当前没有可显示的用户。
                    </div>
                )}
            </div>
        </div>
    );
};

export default AdminUsersPage;
