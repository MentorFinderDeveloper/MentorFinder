// Shared frontend data contracts used across search, mentor detail, timeline,
// follow, weekly report, and admin-management modules.
// These interfaces describe the shapes returned by backend endpoints so pages
// and components can share a consistent typed model.

// Search and mentor-related result types.
export interface SearchMentorResult {
    id: number;
    Chinese_name: string;
    English_name?: string;
    research_direction: string;
    email?: string;
    profile?: string;
    paperTitles: string[];
    is_private?: boolean;
    name?: string;
    researchDirection?: string;
}

export interface PrivateMentorPaper {
    id: number;
    title: string;
    abstract?: string;
    publish_date?: string;
    author_names: string;
    arxiv_id?: string;
    arxiv_url?: string;
}

// Detailed mentor records used in private-mentor flows and mentor detail pages.
export interface PrivateMentorResult {
    id: number;
    Chinese_name: string;
    English_name?: string;
    research_direction: string;
    email?: string;
    profile?: string;
    is_private: boolean;
    paper_ids: PrivateMentorPaper[];
}

export interface MentorDetail {
    id: number;
    Chinese_name: string;
    English_name?: string;
    research_direction: string;
    email?: string;
    profile?: string;
    is_private: boolean;
    paper_ids: PrivateMentorPaper[];
}

// AI-generated summary of a mentor's recent research direction.
export interface MentorRecentDirectionAnalysisPaper {
    id: number;
    title: string;
    publish_date: string;
}

export interface MentorRecentDirectionAnalysisResponse {
    mentorId: number;
    mentorName: string;
    paperCount: number;
    generatedBy: string;
    analysis: string;
    papers: MentorRecentDirectionAnalysisPaper[];
}

export interface SearchPaperResult {
    id: number;
    title: string;
    abstract?: string;
    publish_date?: string;
    author_names: string;
    subjects: string;
    arxiv_id?: string;
    arxiv_url?: string;
    mentorNames: string[];
    mentor_ids?: number[];
    publishDate?: string;
}

// Timeline feed data models.
export interface TimelinePaper {
    id: number;
    title: string;
    abstract?: string;
    tldr?: string;
    arxiv_url?: string;
    publish_date?: string;
    author_names: string;
    mentor_ids?: number[];
    subjects?: string;
    day_sequence?: number;
    day_total?: number;
}

export interface TimelineDirectionSummary {
    direction: string;
    paper_count: number;
}

export interface TimelineDirectionsResponse {
    directions: TimelineDirectionSummary[];
    default_direction: string;
    page_size_default: number;
    page_size_max: number;
}

export interface TimelineCalendarDateSummary {
    date: string;
    paper_count: number;
}

export interface TimelineCalendarResponse {
    direction: string;
    default_date: string;
    latest_date: string;
    earliest_date: string;
    available_dates: TimelineCalendarDateSummary[];
}

// Weekly push and personalized weekly report data models.
export interface WeeklyPushPaper {
    id: number;
    title: string;
    publishDate?: string;
    authorNames: string;
    arxivUrl?: string;
    arxivId?: string;
    abstract?: string;
    tldr?: string;
    mentorNames?: string[];
}

export interface WeeklyPushMentorGroupPaper {
    id: number;
    title: string;
    publishDate?: string;
    authorNames: string;
    mentorId: number;
    mentorName: string;
    researchDirection?: string;
    subjects: string[];
    abstractPreview?: string;
}

export interface WeeklyPushMentorGroup {
    mentorId: number;
    mentorName: string;
    mentorEnglishName?: string;
    mentorResearchDirection?: string;
    isPrivate: boolean;
    paperCount: number;
    papers: WeeklyPushMentorGroupPaper[];
}

export interface WeeklyPushSubjectGroupPaper {
    id: number;
    title: string;
    publishDate?: string;
    authorNames: string;
    subject: string;
    subjects: string[];
    abstractPreview?: string;
}

export interface WeeklyPushSubjectGroup {
    subject: string;
    paperCount: number;
    papers: WeeklyPushSubjectGroupPaper[];
}

export interface WeeklyPushSubjectDistributionItem {
    subject: string;
    count: number;
}

export interface WeeklyPushItem {
    weekStart: string;
    weekEnd: string;
    paperCount: number;
    title: string;
    fixedSummary: string;
    aiSummary: string;
    content: string;
    papers: WeeklyPushPaper[];
    generatedBy: string;
    updatedAt: string;
    mentorGroups?: WeeklyPushMentorGroup[];
    subjectGroups?: WeeklyPushSubjectGroup[];
    subjectDistribution?: WeeklyPushSubjectDistributionItem[];
    trackedMentorCount?: number;
    activeMentorCount?: number;
    trackedSubjectCount?: number;
    activeSubjectCount?: number;
}

export interface WeeklyPushResponse {
    weeklyPush?: WeeklyPushItem;
}

export interface WeeklyPushHistoryItem {
    weekStart: string;
    weekEnd: string;
    title: string;
    paperCount: number;
    generatedBy: string;
    updatedAt: string;
}

export interface WeeklyPushHistoryResponse {
    history: WeeklyPushHistoryItem[];
}

// Timeline batched response wrapper used for initial load and incremental loading.
export interface TimelinePapersResponse {
    direction: string;
    limit: number;
    total_papers: number;
    has_newer?: boolean;
    has_older?: boolean;
    offset?: number;
    has_previous?: boolean;
    has_next?: boolean;
    papers: TimelinePaper[];
}

export interface BoundMentorProfile {
    id: number;
    Chinese_name: string;
    English_name?: string;
    research_direction: string;
    email?: string;
}

// Follow-system and public-profile data models.
export interface FollowUserResult {
    id: number;
    username: string;
    realName?: string;
    role: string;
    avatarUrl?: string;
    signature?: string;
    followed: boolean;
}

export interface PublicUserProfile {
    personalIntro: string;
    researchExperience: string;
    honors: string;
    projectExperience: string;
    showPersonalIntro: boolean;
    showResearchExperience: boolean;
    showHonors: boolean;
    showProjectExperience: boolean;
    updatedAt?: string;
}

export interface PublicUserProfileResult extends FollowUserResult {
    isSelf: boolean;
    profile: PublicUserProfile;
}

// Admin management data models.
export interface AdminUserResult {
    id: number;
    username: string;
    email: string;
    role: string;
    realName?: string;
    mentorProfile?: BoundMentorProfile;
    isBoundToMentor: boolean;
}

export interface MentorVerificationRequestResult {
    id: number;
    userId: number;
    username: string;
    userEmail: string;
    submittedName: string;
    status: string;
    createdAt: string;
    updatedAt: string;
}
