from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dataset", "0010_scheduledtaskrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledtaskrun",
            name="progress_message",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="当前进度"),
        ),
        migrations.AddField(
            model_name="scheduledtaskrun",
            name="progress_current",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="当前进度值"),
        ),
        migrations.AddField(
            model_name="scheduledtaskrun",
            name="progress_total",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="总进度值"),
        ),
        migrations.AddField(
            model_name="scheduledtaskrun",
            name="progress_log",
            field=models.TextField(blank=True, default="", verbose_name="进度日志"),
        ),
        migrations.AddField(
            model_name="scheduledtaskrun",
            name="last_heartbeat_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="最近进度更新时间"),
        ),
    ]
