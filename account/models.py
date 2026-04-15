from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from dataset.models import Mentor
from django.utils.timezone import localtime


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = (
        ("student", "学生"),
        ("tutor", "导师"),
        ("admin", "系统管理员"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    real_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="真实姓名")
    email = models.EmailField("email address", unique=True)
    objects = CustomUserManager()

    def serialize(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "realName": self.real_name,
        }

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    research_experience = models.TextField(blank=True, default="", verbose_name="科研经历")
    honors = models.TextField(blank=True, default="", verbose_name="所获荣誉")
    project_experience = models.TextField(blank=True, default="", verbose_name="项目经历")
    updated_at = models.DateTimeField(auto_now=True)

    def serialize(self):
        return {
            "researchExperience": self.research_experience,
            "honors": self.honors,
            "projectExperience": self.project_experience,
            "updatedAt": localtime(self.updated_at).isoformat(sep=' ', timespec='seconds') if self.updated_at else "",
        }

    def __str__(self):
        return f"Profile of {self.user.username}"


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
