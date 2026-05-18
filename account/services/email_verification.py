"""邮箱验证码相关业务逻辑：生成、发送、校验、冷却控制。"""
import random
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from account.models import EmailVerificationCode


CODE_LENGTH = 6


def email_matches_bypass(email: str) -> bool:
    prefix = getattr(settings, "EMAIL_VERIFICATION_BYPASS_PREFIX", "bypass")
    if not prefix:
        return False
    return email.strip().lower().startswith(prefix.lower())


def generate_verification_code() -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(CODE_LENGTH))


def _ttl_seconds() -> int:
    return int(getattr(settings, "EMAIL_VERIFICATION_CODE_TTL_SECONDS", 600))


def _cooldown_seconds() -> int:
    return int(getattr(settings, "EMAIL_VERIFICATION_CODE_RESEND_COOLDOWN", 60))


def get_remaining_cooldown(email: str) -> int:
    """返回该邮箱距离可以再次发送验证码还剩多少秒；0 表示无冷却。"""
    record = EmailVerificationCode.objects.filter(email=email).first()
    if record is None:
        return 0
    cooldown = _cooldown_seconds()
    elapsed = (timezone.now() - record.created_at).total_seconds()
    remaining = int(cooldown - elapsed)
    return max(remaining, 0)


def issue_verification_code(email: str) -> tuple[str, EmailVerificationCode]:
    """生成或刷新验证码并落库，返回(code, record)。"""
    code = generate_verification_code()
    expires_at = timezone.now() + timedelta(seconds=_ttl_seconds())
    record, _ = EmailVerificationCode.objects.update_or_create(
        email=email,
        defaults={
            "code": code,
            "expires_at": expires_at,
        },
    )
    return code, record


def send_verification_email(email: str, code: str) -> None:
    subject = "[MentorFinder] 注册邮箱验证码"
    ttl_minutes = max(1, _ttl_seconds() // 60)
    body = (
        f"您好，\n\n"
        f"您正在注册 MentorFinder 账号，本次邮箱验证码为：{code}\n"
        f"验证码 {ttl_minutes} 分钟内有效，请尽快在注册页面完成校验。\n"
        f"如非本人操作，请忽略此邮件。\n\n"
        f"— MentorFinder 团队"
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=False,
    )


def send_password_reset_email(email: str, code: str) -> None:
    subject = "[MentorFinder] 修改密码邮箱验证码"
    ttl_minutes = max(1, _ttl_seconds() // 60)
    body = (
        f"您好，\n\n"
        f"您正在通过邮箱验证码修改 MentorFinder 账号密码，本次验证码为：{code}\n"
        f"验证码 {ttl_minutes} 分钟内有效，请尽快在修改密码页面完成校验。\n"
        f"如非本人操作，请忽略此邮件，并确认账号安全。\n\n"
        f"— MentorFinder 团队"
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=False,
    )


def verify_code(email: str, code: str) -> bool:
    """校验通过返回 True，并消费掉该验证码（删除记录）。"""
    record = EmailVerificationCode.objects.filter(email=email).first()
    if record is None:
        return False
    if record.expires_at < timezone.now():
        record.delete()
        return False
    if record.code != code.strip():
        return False
    record.delete()
    return True
