# Generated for email verification feature on 2026-05-16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0012_userfollow"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailVerificationCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email", models.EmailField(max_length=254, unique=True, verbose_name="邮箱")),
                ("code", models.CharField(max_length=10, verbose_name="验证码")),
                ("expires_at", models.DateTimeField(verbose_name="过期时间")),
                ("created_at", models.DateTimeField(auto_now=True, verbose_name="最近一次发送时间")),
            ],
            options={
                "verbose_name": "邮箱验证码",
                "verbose_name_plural": "邮箱验证码",
            },
        ),
    ]
