"""应用配置：在 Django 启动时进行 account 应用的初始化。

`ready()` 中会启动项目的调度器（如果有），适合注册信号或启动后台任务。
"""

from django.apps import AppConfig


class AccountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'account'

    def ready(self):
        from utils.django_scheduler import start_django_scheduler

        start_django_scheduler()
