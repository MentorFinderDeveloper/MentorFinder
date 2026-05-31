from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from dataset.models import Mentor
from dataset.models import Paper
from django.utils.timezone import localtime


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    ROLE_STUDENT = "student"
    ROLE_MENTOR = "mentor"
    ROLE_ADMIN = "admin"
    ROLE_BANNED = "banned"

    ROLE_CHOICES = (
        (ROLE_STUDENT, "学生"),
        (ROLE_MENTOR, "导师"),
        (ROLE_ADMIN, "系统管理员"),
        (ROLE_BANNED, "已封禁"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    real_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="真实姓名")
    email = models.EmailField("email address", unique=True)
    jwt_token_version = models.PositiveIntegerField(default=0, verbose_name="JWT 吊销版本")
    mentor_profile = models.OneToOneField(
        Mentor,
        on_delete=models.SET_NULL,
        related_name="bound_user",
        null=True,
        blank=True,
        verbose_name="绑定公共导师",
        limit_choices_to={"owner__isnull": True},
    )
    objects = CustomUserManager()

    def revoke_jwt_tokens(self) -> None:
        self.jwt_token_version += 1

    def serialize(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "realName": self.real_name,
            "mentorProfile": self.serialize_mentor_profile(),
        }

    def serialize_mentor_profile(self):
        if self.mentor_profile is None:
            return None

        return {
            "id": self.mentor_profile.id,
            "Chinese_name": self.mentor_profile.Chinese_name,
            "English_name": self.mentor_profile.English_name,
            "research_direction": self.mentor_profile.research_direction,
            "email": self.mentor_profile.email,
        }

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"


class EmailVerificationCode(models.Model):
    email = models.EmailField(unique=True, verbose_name="邮箱")
    code = models.CharField(max_length=10, verbose_name="验证码")
    expires_at = models.DateTimeField(verbose_name="过期时间")
    created_at = models.DateTimeField(auto_now=True, verbose_name="最近一次发送时间")
    attempt_count = models.PositiveIntegerField(default=0, verbose_name="校验失败次数")

    class Meta:
        verbose_name = "邮箱验证码"
        verbose_name_plural = "邮箱验证码"

    def __str__(self) -> str:
        return f"{self.email}:{self.code}"


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    avatar_url = models.TextField(blank=True, default="", verbose_name="头像地址")
    signature = models.CharField(max_length=200, blank=True, default="", verbose_name="个性签名")
    personal_intro = models.TextField(blank=True, default="", verbose_name="个人简介")
    research_experience = models.TextField(blank=True, default="", verbose_name="科研经历")
    honors = models.TextField(blank=True, default="", verbose_name="所获荣誉")
    project_experience = models.TextField(blank=True, default="", verbose_name="项目经历")
    show_personal_intro = models.BooleanField(default=True, verbose_name="展示个人简介")
    show_research_experience = models.BooleanField(default=True, verbose_name="展示科研经历")
    show_honors = models.BooleanField(default=True, verbose_name="展示所获荣誉")
    show_project_experience = models.BooleanField(default=True, verbose_name="展示项目经历")
    updated_at = models.DateTimeField(auto_now=True)

    def serialize(self):
        return {
            "avatarUrl": self.avatar_url,
            "signature": self.signature,
            "personalIntro": self.personal_intro,
            "researchExperience": self.research_experience,
            "honors": self.honors,
            "projectExperience": self.project_experience,
            "showPersonalIntro": self.show_personal_intro,
            "showResearchExperience": self.show_research_experience,
            "showHonors": self.show_honors,
            "showProjectExperience": self.show_project_experience,
            "updatedAt": localtime(self.updated_at).isoformat(sep=' ', timespec='seconds') if self.updated_at else "",
        }

    def __str__(self):
        return f"Profile of {self.user.username}"


class MentorVerificationRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = (
        (STATUS_PENDING, "待处理"),
        (STATUS_APPROVED, "已通过"),
        (STATUS_REJECTED, "已拒绝"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mentor_verification_requests",
    )
    submitted_name = models.CharField(max_length=100, verbose_name="提交姓名")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def serialize(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "username": self.user.username,
            "userEmail": self.user.email,
            "submittedName": self.submitted_name,
            "status": self.status,
            "createdAt": localtime(self.created_at).isoformat(sep=" ", timespec="seconds") if self.created_at else "",
            "updatedAt": localtime(self.updated_at).isoformat(sep=" ", timespec="seconds") if self.updated_at else "",
        }

    def __str__(self):
        return f"Mentor verification request of {self.user.username}: {self.submitted_name}"


class MentorFollow(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mentor_follows",
    )
    mentor = models.ForeignKey(
        Mentor,
        on_delete=models.CASCADE,
        related_name="student_follows",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "mentor")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.username} follows {self.mentor.Chinese_name}"


class UserFollow(models.Model):
    follower = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="following_users",
    )
    following = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="followed_by_users",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("follower", "following")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


class SubjectFollow(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subject_follows",
    )
    subject = models.CharField(max_length=100, verbose_name="关注板块")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "subject")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} follows {self.subject}"


class WeeklyPushPaperBucket(models.Model):
    CYCLE_CURRENT = "current"
    CYCLE_NEXT = "next"
    CYCLE_ARCHIVED = "archived"

    CYCLE_CHOICES = (
        (CYCLE_CURRENT, "当前周期"),
        (CYCLE_NEXT, "下一个周期"),
        (CYCLE_ARCHIVED, "已归档周期"),
    )

    cycle = models.CharField(max_length=20, choices=CYCLE_CHOICES, verbose_name="周期类型")
    period_key = models.CharField(max_length=64, blank=True, default="", verbose_name="周期键")
    day_key = models.CharField(max_length=20, verbose_name="星期键")
    paper = models.ForeignKey(
        Paper,
        on_delete=models.CASCADE,
        related_name="weekly_push_buckets",
    )
    archive_batch = models.CharField(max_length=64, blank=True, default="", verbose_name="归档批次")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["cycle", "period_key", "day_key", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "period_key", "day_key", "paper"],
                name="unique_weekly_push_cycle_period_day_paper",
            ),
        ]

    def __str__(self) -> str:
        archive_suffix = f" [{self.archive_batch}]" if self.archive_batch else ""
        period_suffix = self.period_key or "no-period"
        return f"{self.cycle}:{period_suffix}:{self.day_key}:{self.paper_id}{archive_suffix}"


class PushRecord(models.Model):
    TYPE_WEEKLY = "weekly"

    TYPE_CHOICES = (
        (TYPE_WEEKLY, "周报"),
    )

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_PENDING, "待发送"),
        (STATUS_SENT, "发送成功"),
        (STATUS_FAILED, "发送失败"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="push_records",
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="推送类型")
    period_key = models.CharField(max_length=64, verbose_name="周期键")
    period_start = models.DateTimeField(verbose_name="周期开始时间")
    period_end = models.DateTimeField(verbose_name="周期结束时间")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    sent_at = models.DateTimeField(blank=True, null=True, verbose_name="发送时间")
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True, default="", verbose_name="失败信息")

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type", "period_key"],
                name="unique_push_record_user_type_period",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.username}:{self.type}:{self.period_key}:{self.status}"


class UserWeeklyReport(models.Model):
    GENERATED_BY_USER = "user"
    GENERATED_BY_SCHEDULED = "scheduled"

    GENERATED_BY_CHOICES = (
        (GENERATED_BY_USER, "用户手动生成"),
        (GENERATED_BY_SCHEDULED, "定时任务生成"),
    )

    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="weekly_reports",
        verbose_name="用户",
    )
    week_start = models.DateField(verbose_name="周开始日期")
    week_end = models.DateField(verbose_name="周结束日期")
    title = models.CharField(max_length=255, verbose_name="周报标题")
    payload = models.JSONField(default=dict, blank=True, verbose_name="前端展示完整结构")
    digest = models.JSONField(default=dict, blank=True, verbose_name="邮件构造用 digest")
    has_updates = models.BooleanField(default=False, verbose_name="是否有命中论文")
    total_paper_count = models.IntegerField(default=0, verbose_name="命中论文总数")
    generated_by_kind = models.CharField(
        max_length=20,
        choices=GENERATED_BY_CHOICES,
        default=GENERATED_BY_USER,
        verbose_name="生成方式",
    )
    generated_at = models.DateTimeField(auto_now=True, verbose_name="最近生成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="首次生成时间")

    class Meta:
        verbose_name = "用户专属周报"
        verbose_name_plural = verbose_name
        ordering = ["-week_start", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "week_start"],
                name="unique_user_weekly_report_user_week",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.username}:{self.week_start.isoformat()}"
