"""应用配置：`dataset` 模块的 Django AppConfig。"""

from django.apps import AppConfig


class DatasetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dataset'
