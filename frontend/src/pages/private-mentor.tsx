import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { useSelector } from "react-redux";

import { RootState } from "../redux/store";
import { INPUT_LIMITS } from "../constants/inputLimits";
import { describeRequestError } from "../utils/errorMessage";
import { NetworkError, NetworkErrorType, request } from "../utils/network";
import { PrivateMentorResult } from "../utils/types";

type PrivateMentorCategory = "all" | "withPapers" | "withoutPapers" | "withEmail";
type PrivateMentorSort = "latest" | "nameAsc" | "paperCountDesc";

interface PrivateMentorsResponse {
    mentors?: PrivateMentorResult[];
}

const PRIVATE_MENTOR_LIMIT = 10;

// Render the private mentor management page for creating, editing, filtering, and deleting user-owned mentors.
const PrivateMentorScreen = () => {
    const router = useRouter();
    const token = useSelector((state: RootState) => state.auth.token);
    const userId = useSelector((state: RootState) => state.auth.userId);
    const profileHref = userId === undefined ? "/follows" : `/users/${userId}`;
    const isLoggedIn = token.trim() !== "";

    const [privateMentorSaving, setPrivateMentorSaving] = useState(false);
    const [privateMentorLoading, setPrivateMentorLoading] = useState(false);
    const [privateMentorMessage, setPrivateMentorMessage] = useState("");
    const [privateMentorFilter, setPrivateMentorFilter] = useState("");
    const [privateMentorCategory, setPrivateMentorCategory] = useState<PrivateMentorCategory>("all");
    const [privateMentorSort, setPrivateMentorSort] = useState<PrivateMentorSort>("latest");
    const [privateMentorDeletingId, setPrivateMentorDeletingId] = useState<number | undefined>(undefined);
    const [deleteDialogTarget, setDeleteDialogTarget] = useState<PrivateMentorResult | undefined>(undefined);
    const [deleteDialogSubmitting, setDeleteDialogSubmitting] = useState(false);
    const [privateMentors, setPrivateMentors] = useState<PrivateMentorResult[]>([]);

    const [customMentorDraft, setCustomMentorDraft] = useState({
        Chinese_name: "",
        English_name: "",
        research_direction: "",
        email: "",
        profile: "",
    });

    const [editDialogTarget, setEditDialogTarget] = useState<PrivateMentorResult | undefined>(undefined);
    const [editDialogSubmitting, setEditDialogSubmitting] = useState(false);
    const [editDialogDraft, setEditDialogDraft] = useState({
        Chinese_name: "",
        English_name: "",
        research_direction: "",
        email: "",
        profile: "",
    });

    // Narrow unknown errors to the shared NetworkError class when possible.
    const isNetworkErrorInstance = (err: unknown): err is NetworkError => {
        return typeof NetworkError === "function" && err instanceof NetworkError;
    };

    // Convert backend and transport errors into private-mentor-specific user messages.
    const formatPrivateMentorError = useCallback((err: unknown) => {
        // Keep a few context-specific messages, then defer to the shared translator
        // so backend validation details surface as natural Chinese instead of raw text.
        if (isNetworkErrorInstance(err)) {
            if (err.type === NetworkErrorType.UNAUTHORIZED) {
                return "请先登录后再管理私有导师";
            }

            if (err.type === NetworkErrorType.REJECTED) {
                return "当前账号无权限创建私有导师";
            }
        }

        return describeRequestError(err);
    }, []);

    // Load the current user's private mentor list from the backend.
    const fetchMyPrivateMentors = useCallback(async () => {
        if (!isLoggedIn) {
            setPrivateMentors([]);
            setPrivateMentorMessage("登录后可添加和查看私有导师");
            return;
        }

        setPrivateMentorLoading(true);

        try {
            const res = await request<PrivateMentorsResponse>("/api/dataset/mentors/mine", "GET", true);
            const mentorList = Array.isArray(res.mentors) ? res.mentors : [];
            // Only keep records with a normalized paper_ids array so the list renderer can stay simple.
            setPrivateMentors(mentorList.filter((mentor) => Array.isArray(mentor.paper_ids)));
            setPrivateMentorMessage("");
        }
        catch (err) {
            setPrivateMentorMessage(formatPrivateMentorError(err));
        }
        finally {
            setPrivateMentorLoading(false);
        }
    }, [formatPrivateMentorError, isLoggedIn]);

    useEffect(() => {
        void fetchMyPrivateMentors();
    }, [fetchMyPrivateMentors]);

    // Derive the filtered and sorted mentor list shown in the current view.
    // Compute the currently visible private mentor list after applying filter text, category, and sort mode.
    const displayedPrivateMentors = useMemo(() => {
        const keyword = privateMentorFilter.trim().toLowerCase();

        // Apply keyword filtering, category filtering, then a client-side sort to the user's private mentor list.
        const filtered = privateMentors.filter((mentor) => {
            const matchKeyword = keyword === "" ||
                mentor.Chinese_name.toLowerCase().includes(keyword) ||
                String(mentor.English_name || "").toLowerCase().includes(keyword) ||
                String(mentor.research_direction || "").toLowerCase().includes(keyword);

            if (!matchKeyword) {
                return false;
            }

            if (privateMentorCategory === "withPapers") {
                return (mentor.paper_ids || []).length > 0;
            }

            if (privateMentorCategory === "withoutPapers") {
                return (mentor.paper_ids || []).length === 0;
            }

            if (privateMentorCategory === "withEmail") {
                return String(mentor.email || "").trim() !== "";
            }

            return true;
        });

        const sorted = [...filtered];

        if (privateMentorSort === "nameAsc") {
            sorted.sort((a, b) => {
                return a.Chinese_name.localeCompare(b.Chinese_name, "zh-CN");
            });
        }
        else if (privateMentorSort === "paperCountDesc") {
            sorted.sort((a, b) => {
                return (b.paper_ids || []).length - (a.paper_ids || []).length;
            });
        }
        else {
            sorted.sort((a, b) => {
                return b.id - a.id;
            });
        }

        return sorted;
    }, [privateMentorCategory, privateMentorFilter, privateMentorSort, privateMentors]);

    const isPrivateMentorLimitReached = privateMentors.length >= PRIVATE_MENTOR_LIMIT;

    // Create a new private mentor from the current draft fields.
    const addPrivateMentor = async () => {
        const chineseName = customMentorDraft.Chinese_name.trim();
        const englishName = customMentorDraft.English_name.trim();
        const researchDirection = customMentorDraft.research_direction.trim();
        const email = customMentorDraft.email.trim();
        const profile = customMentorDraft.profile.trim();

        if (isPrivateMentorLimitReached) {
            setPrivateMentorMessage(`私有导师最多添加 ${PRIVATE_MENTOR_LIMIT} 位，请先删除后再添加`);
            return;
        }

        if (chineseName === "" && englishName === "") {
            setPrivateMentorMessage("中文名和英文名至少填写一个");
            return;
        }

        // Creating a private mentor uses the custom mentor endpoint and refreshes the list after success.
        setPrivateMentorSaving(true);
        setPrivateMentorMessage("");

        try {
            await request("/api/dataset/mentors/custom", "POST", true, {
                Chinese_name: chineseName,
                English_name: englishName,
                research_direction: researchDirection,
                email,
                profile,
            });

            setCustomMentorDraft({
                Chinese_name: "",
                English_name: "",
                research_direction: "",
                email: "",
                profile: "",
            });
            await fetchMyPrivateMentors();
            setPrivateMentorMessage("私有导师添加成功");
        }
        catch (err) {
            setPrivateMentorMessage(formatPrivateMentorError(err));
        }
        finally {
            setPrivateMentorSaving(false);
        }
    };

    // Open the edit dialog and seed it with the selected mentor's current values.
    const openEditDialog = (mentor: PrivateMentorResult) => {
        // Seed the dialog with the current mentor snapshot so edits feel like inline modification.
        setEditDialogTarget(mentor);
        setEditDialogDraft({
            Chinese_name: mentor.Chinese_name || "",
            English_name: mentor.English_name || "",
            research_direction: mentor.research_direction === "待补充" ? "" : (mentor.research_direction || ""),
            email: mentor.email || "",
            profile: mentor.profile || "",
        });
    };

    // Close the edit dialog unless an edit request is still in flight.
    // Dismiss the edit dialog unless a save request is still running.
    const closeEditDialog = () => {
        if (editDialogSubmitting) {
            return;
        }
        setEditDialogTarget(undefined);
    };

    // Persist edits for the currently selected private mentor.
    const submitEditDialog = async () => {
        if (editDialogTarget === undefined) {
            return;
        }

        const chineseName = editDialogDraft.Chinese_name.trim();
        const englishName = editDialogDraft.English_name.trim();
        const researchDirection = editDialogDraft.research_direction.trim();
        const email = editDialogDraft.email.trim();
        const profile = editDialogDraft.profile.trim();

        if (chineseName === "" && englishName === "") {
            setPrivateMentorMessage("中文名和英文名至少填写一个");
            return;
        }

        // Update the selected private mentor and then refresh the canonical list from the server.
        setEditDialogSubmitting(true);
        setPrivateMentorMessage("");

        try {
            await request(`/api/dataset/mentors/${editDialogTarget.id}`, "PUT", true, {
                Chinese_name: chineseName,
                English_name: englishName,
                research_direction: researchDirection,
                email,
                profile,
            });

            setEditDialogTarget(undefined);
            await fetchMyPrivateMentors();
            setPrivateMentorMessage("私有导师信息已更新");
        }
        catch (err) {
            setPrivateMentorMessage(formatPrivateMentorError(err));
        }
        finally {
            setEditDialogSubmitting(false);
        }
    };

    // Open the delete confirmation dialog for the chosen private mentor.
    const openDeleteDialog = (mentor: PrivateMentorResult) => {
        setDeleteDialogTarget(mentor);
    };

    // Close the delete confirmation dialog unless deletion is still pending.
    // Dismiss the delete confirmation dialog unless deletion is still running.
    const closeDeleteDialog = () => {
        if (deleteDialogSubmitting) {
            return;
        }
        setDeleteDialogTarget(undefined);
    };

    // Permanently delete the mentor currently selected in the confirmation dialog.
    const confirmDeleteDialog = async () => {
        if (deleteDialogTarget === undefined) {
            return;
        }

        // The confirm dialog holds the deleting id so buttons elsewhere stay disabled until the request settles.
        setDeleteDialogSubmitting(true);
        setPrivateMentorDeletingId(deleteDialogTarget.id);
        setPrivateMentorMessage("");

        try {
            await request(`/api/dataset/mentors/${deleteDialogTarget.id}`, "DELETE", true);
            setDeleteDialogTarget(undefined);
            await fetchMyPrivateMentors();
            setPrivateMentorMessage("私有导师删除成功");
        }
        catch (err) {
            setPrivateMentorMessage(formatPrivateMentorError(err));
        }
        finally {
            setDeleteDialogSubmitting(false);
            setPrivateMentorDeletingId(undefined);
        }
    };

    if (!isLoggedIn) {
        return (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
                <h2>添加个人导师</h2>
                <p>请先登录后再添加个人导师。</p>
                <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => router.push("/login")}>去登录</button>
                    <button onClick={() => router.push(profileHref)}>返回个人主页</button>
                </div>
            </div>
        );
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
            {editDialogTarget !== undefined && (
                <div
                    aria-label="编辑私有导师弹窗遮罩"
                    role="presentation"
                    onClick={closeEditDialog}
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 1100,
                        background: "rgba(15, 23, 42, 0.42)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 20,
                    }}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="edit-private-mentor-dialog-title"
                        onClick={(event) => event.stopPropagation()}
                        style={{
                            width: "min(100%, 520px)",
                            borderRadius: 20,
                            background: "#ffffff",
                            border: "1px solid #d0d7de",
                            boxShadow: "0 24px 64px rgba(15, 23, 42, 0.24)",
                            padding: 24,
                            display: "flex",
                            flexDirection: "column",
                            gap: 12,
                        }}
                    >
                        <h3 id="edit-private-mentor-dialog-title" style={{ margin: 0, color: "#1f2328" }}>
                            编辑私有导师信息
                        </h3>
                        <div style={{ display: "flex", gap: 8 }}>
                            <input
                                type="text"
                                placeholder="导师中文名（可选）"
                                maxLength={INPUT_LIMITS.NAME}
                                value={editDialogDraft.Chinese_name}
                                onChange={(e) => setEditDialogDraft((prev) => ({ ...prev, Chinese_name: e.target.value }))}
                                disabled={editDialogSubmitting}
                                style={{ flex: 1 }}
                            />
                            <input
                                type="text"
                                placeholder="导师英文名（可选）"
                                maxLength={INPUT_LIMITS.NAME}
                                value={editDialogDraft.English_name}
                                onChange={(e) => setEditDialogDraft((prev) => ({ ...prev, English_name: e.target.value }))}
                                disabled={editDialogSubmitting}
                                style={{ flex: 1 }}
                            />
                        </div>
                        <input
                            type="text"
                            placeholder="研究方向（可选）"
                            maxLength={INPUT_LIMITS.RESEARCH_DIRECTION}
                            value={editDialogDraft.research_direction}
                            onChange={(e) => setEditDialogDraft((prev) => ({ ...prev, research_direction: e.target.value }))}
                            disabled={editDialogSubmitting}
                        />
                        <input
                            type="email"
                            placeholder="导师邮箱（可选）"
                            maxLength={INPUT_LIMITS.EMAIL}
                            value={editDialogDraft.email}
                            onChange={(e) => setEditDialogDraft((prev) => ({ ...prev, email: e.target.value }))}
                            disabled={editDialogSubmitting}
                        />
                        <textarea
                            placeholder="导师画像（可选）"
                            maxLength={INPUT_LIMITS.MENTOR_PROFILE}
                            value={editDialogDraft.profile}
                            onChange={(e) => setEditDialogDraft((prev) => ({ ...prev, profile: e.target.value }))}
                            disabled={editDialogSubmitting}
                            rows={4}
                            style={{ resize: "vertical", fontFamily: "inherit", fontSize: "inherit" }}
                        />
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                            <button
                                type="button"
                                onClick={() => void submitEditDialog()}
                                disabled={
                                    editDialogSubmitting ||
                                    (editDialogDraft.Chinese_name.trim() === "" && editDialogDraft.English_name.trim() === "")
                                }
                                style={{
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    fontWeight: 700,
                                }}
                            >
                                {editDialogSubmitting ? "保存中..." : "保存修改"}
                            </button>
                            <button
                                type="button"
                                onClick={closeEditDialog}
                                disabled={editDialogSubmitting}
                                style={{
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    border: "1px solid rgb(209, 217, 224)",
                                    background: "rgb(246, 248, 250)",
                                    color: "rgb(37, 41, 46)",
                                    fontWeight: 600,
                                    boxShadow: "none",
                                }}
                            >
                                取消
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {deleteDialogTarget !== undefined && (
                <div
                    aria-label="删除私有导师确认弹窗遮罩"
                    role="presentation"
                    onClick={closeDeleteDialog}
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 1100,
                        background: "rgba(15, 23, 42, 0.42)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 20,
                    }}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="delete-private-mentor-dialog-title"
                        onClick={(event) => event.stopPropagation()}
                        style={{
                            width: "min(100%, 480px)",
                            borderRadius: 20,
                            background: "#ffffff",
                            border: "1px solid #d0d7de",
                            boxShadow: "0 24px 64px rgba(15, 23, 42, 0.24)",
                            padding: 24,
                            display: "flex",
                            flexDirection: "column",
                            gap: 14,
                        }}
                    >
                        <h3 id="delete-private-mentor-dialog-title" style={{ margin: 0, color: "#1f2328" }}>
                            确认删除私有导师
                        </h3>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, color: "#1f2328" }}>
                            <p style={{ margin: 0 }}>
                                中文名：{deleteDialogTarget.Chinese_name}
                            </p>
                            <p style={{ margin: 0 }}>
                                英文名：{deleteDialogTarget.English_name?.trim() || "暂无英文名"}
                            </p>
                            <p style={{ margin: 0 }}>
                                研究方向：{deleteDialogTarget.research_direction?.trim() || "暂无研究方向"}
                            </p>
                            <p style={{ margin: 0 }}>
                                邮箱：{deleteDialogTarget.email?.trim() || "暂无邮箱"}
                            </p>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                            <button
                                type="button"
                                onClick={() => void confirmDeleteDialog()}
                                disabled={deleteDialogSubmitting}
                                style={{
                                    position: "relative",
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    border: deleteDialogSubmitting ? "none" : "1px solid #cf222e",
                                    background: deleteDialogSubmitting ? "#cf222e" : "#ffffff",
                                    color: deleteDialogSubmitting ? "#ffffff" : "#cf222e",
                                    fontWeight: 700,
                                    overflow: "hidden",
                                    transition: "background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease",
                                }}
                                onMouseEnter={(event) => {
                                    if (deleteDialogSubmitting) {
                                        return;
                                    }
                                    event.currentTarget.style.background = "#cf222e";
                                    event.currentTarget.style.color = "#ffffff";
                                    event.currentTarget.style.border = "none";
                                }}
                                onMouseLeave={(event) => {
                                    if (deleteDialogSubmitting) {
                                        return;
                                    }
                                    event.currentTarget.style.background = "#ffffff";
                                    event.currentTarget.style.color = "#cf222e";
                                    event.currentTarget.style.border = "1px solid #cf222e";
                                }}
                            >
                                <span>确认删除</span>
                                {deleteDialogSubmitting && (
                                    <span
                                        aria-hidden="true"
                                        style={{
                                            position: "absolute",
                                            inset: 0,
                                            background: "rgba(255, 255, 255, 0.55)",
                                        }}
                                    />
                                )}
                            </button>
                            <button
                                type="button"
                                onClick={closeDeleteDialog}
                                disabled={deleteDialogSubmitting}
                                style={{
                                    width: "100%",
                                    minHeight: 44,
                                    borderRadius: 12,
                                    border: "1px solid rgb(209, 217, 224)",
                                    background: "rgb(246, 248, 250)",
                                    color: "rgb(37, 41, 46)",
                                    fontWeight: 600,
                                    boxShadow: "none",
                                }}
                            >
                                取消
                            </button>
                        </div>
                    </div>
                </div>
            )}
            <h2>添加个人导师</h2>
            <p>输入中文名或英文名后，系统将自动调用爬虫抓取导师信息并保存到你的私有库。</p>
            <p style={{ margin: 0 }}>
                私有导师上限 {PRIVATE_MENTOR_LIMIT} 位，当前已添加 {privateMentors.length} 位。
            </p>
            {isPrivateMentorLimitReached && (
                <p style={{ margin: 0, color: "#cf222e", fontSize: 13 }}>
                    已达到上限，请先删除部分私有导师后再添加。
                </p>
            )}

            <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => router.push(profileHref)}>返回个人主页</button>
                <button onClick={() => router.push("/search")}>去检索</button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, border: "1px solid #ccc", borderRadius: 6, padding: 12 }}>
                {/* Filters and sort options operate entirely on the local private mentor list. */}
                <input
                    type="text"
                    placeholder="筛选我的私有导师（姓名/方向）"
                    maxLength={INPUT_LIMITS.KEYWORD}
                    value={privateMentorFilter}
                    onChange={(e) => setPrivateMentorFilter(e.target.value)}
                    disabled={privateMentorLoading || privateMentorSaving}
                />
                <div style={{ display: "flex", gap: 8 }}>
                    <select
                        id="private-mentor-category"
                        aria-label="私有导师分类"
                        value={privateMentorCategory}
                        onChange={(e) => setPrivateMentorCategory(e.target.value as PrivateMentorCategory)}
                        disabled={privateMentorLoading || privateMentorSaving}
                    >
                        <option value="all">全部导师</option>
                        <option value="withPapers">有论文</option>
                        <option value="withoutPapers">无论文</option>
                        <option value="withEmail">有邮箱</option>
                    </select>
                    <select
                        id="private-mentor-sort"
                        aria-label="私有导师排序"
                        value={privateMentorSort}
                        onChange={(e) => setPrivateMentorSort(e.target.value as PrivateMentorSort)}
                        disabled={privateMentorLoading || privateMentorSaving}
                    >
                        <option value="latest">按添加顺序</option>
                        <option value="nameAsc">按姓名</option>
                        <option value="paperCountDesc">按论文数量</option>
                    </select>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <input
                        type="text"
                        placeholder="导师中文名（可选）"
                        maxLength={INPUT_LIMITS.NAME}
                        value={customMentorDraft.Chinese_name}
                        onChange={(e) => setCustomMentorDraft((prev) => ({ ...prev, Chinese_name: e.target.value }))}
                        disabled={privateMentorSaving || privateMentorLoading}
                        style={{ flex: 1 }}
                    />
                    <input
                        type="text"
                        placeholder="导师英文名（可选）"
                        maxLength={INPUT_LIMITS.NAME}
                        value={customMentorDraft.English_name}
                        onChange={(e) => setCustomMentorDraft((prev) => ({ ...prev, English_name: e.target.value }))}
                        disabled={privateMentorSaving || privateMentorLoading}
                        style={{ flex: 1 }}
                    />
                </div>
                <input
                    type="text"
                    placeholder="研究方向（可选）"
                    maxLength={INPUT_LIMITS.RESEARCH_DIRECTION}
                    value={customMentorDraft.research_direction}
                    onChange={(e) => setCustomMentorDraft((prev) => ({ ...prev, research_direction: e.target.value }))}
                    disabled={privateMentorSaving || privateMentorLoading}
                />
                <input
                    type="email"
                    placeholder="导师邮箱（可选）"
                    maxLength={INPUT_LIMITS.EMAIL}
                    value={customMentorDraft.email}
                    onChange={(e) => setCustomMentorDraft((prev) => ({ ...prev, email: e.target.value }))}
                    disabled={privateMentorSaving || privateMentorLoading}
                />
                <textarea
                    placeholder="导师画像（可选）"
                    maxLength={INPUT_LIMITS.MENTOR_PROFILE}
                    value={customMentorDraft.profile}
                    onChange={(e) => setCustomMentorDraft((prev) => ({ ...prev, profile: e.target.value }))}
                    disabled={privateMentorSaving || privateMentorLoading}
                    rows={3}
                    style={{ resize: "vertical", fontFamily: "inherit", fontSize: "inherit" }}
                />
                <div style={{ display: "flex", gap: 8 }}>
                    <button
                        onClick={() => void addPrivateMentor()}
                        disabled={
                            privateMentorSaving ||
                            privateMentorLoading ||
                            isPrivateMentorLimitReached ||
                            (customMentorDraft.Chinese_name.trim() === "" && customMentorDraft.English_name.trim() === "")
                        }
                    >
                        {privateMentorSaving ? "添加中..." : "添加私有导师"}
                    </button>
                    <button
                        onClick={() => void fetchMyPrivateMentors()}
                        disabled={privateMentorSaving || privateMentorLoading}
                    >
                        {privateMentorLoading ? "刷新中..." : "刷新我的列表"}
                    </button>
                </div>

                {isPrivateMentorLimitReached && (
                    <p style={{ margin: 0, color: "#cf222e", fontSize: 13 }}>私有导师数量已达上限（{PRIVATE_MENTOR_LIMIT}位），请先删除部分私有导师后再添加。</p>
                )}

                {privateMentorMessage !== "" && (
                    <p
                        style={{
                            margin: 0,
                            color: privateMentorMessage.includes("成功") || privateMentorMessage.includes("已更新")
                                ? undefined
                                : "#cf222e",
                        }}
                    >
                        {privateMentorMessage}
                    </p>
                )}

                <p style={{ margin: 0 }}>
                    共 {privateMentors.length} 位私有导师，当前显示 {displayedPrivateMentors.length} 位。
                </p>

                {privateMentors.length === 0 && !privateMentorLoading && (
                    <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                        你还没有私有导师，添加后将只对你可见。
                    </div>
                )}

                {privateMentors.length > 0 && displayedPrivateMentors.length === 0 && (
                    <div style={{ padding: 12, border: "1px dashed #ccc" }}>
                        当前筛选条件下没有匹配的私有导师。
                    </div>
                )}

                {privateMentors.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {displayedPrivateMentors.map((mentor) => (
                            <div key={mentor.id} style={{ padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
                                <h4 style={{ margin: "0 0 6px" }}>
                                    {mentor.Chinese_name}
                                    <span style={{ marginLeft: 8, fontSize: 12, color: "#555" }}>
                                        {mentor.is_private ? "私有" : "公共"}
                                    </span>
                                </h4>
                                {mentor.English_name && <p style={{ margin: "4px 0" }}>英文名：{mentor.English_name}</p>}
                                <p style={{ margin: "4px 0" }}>研究方向：{mentor.research_direction || "暂无研究方向"}</p>
                                <p style={{ margin: "4px 0" }}>邮箱：{mentor.email || "暂无邮箱"}</p>
                                <p style={{ margin: "4px 0" }}>导师画像：{mentor.profile || "暂无导师画像"}</p>
                                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                                    {/* Edit and delete both route through modal dialogs to avoid accidental destructive actions. */}
                                    <button
                                        onClick={() => openEditDialog(mentor)}
                                        disabled={privateMentorSaving || privateMentorLoading || privateMentorDeletingId !== undefined}
                                    >
                                        编辑信息
                                    </button>
                                    <button
                                        onClick={() => openDeleteDialog(mentor)}
                                        disabled={privateMentorSaving || privateMentorLoading || privateMentorDeletingId !== undefined}
                                    >
                                        删除私有导师
                                    </button>
                                </div>

                                <p style={{ margin: "6px 0 4px" }}>相关论文：</p>
                                {(mentor.paper_ids || []).length === 0 ? (
                                    <p style={{ margin: 0 }}>暂无关联论文</p>
                                ) : (
                                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                                        {(mentor.paper_ids || []).map((paper) => (
                                            <li key={paper.id}>{paper.title}</li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default PrivateMentorScreen;
