"""MFBackend URL 配置（中文注释）

此模块定义项目根级 URL 路由，并将不同子应用（`account`, `search`, `dataset`）
包含进来。`urlpatterns` 列表将 URL 路径映射到对应视图或子路由模块。

当部署静态/媒体文件时，`serve_media` 为开发/简单部署场景提供了一个
基于 `django.views.static.serve` 的媒体文件服务回退处理（在生产环境中
应使用专门的静态文件服务器或 CDN）。

参考文档：https://docs.djangoproject.com/en/4.1/topics/http/urls/
"""
from django.contrib import admin
from django.conf import settings
from django.urls import path, include, re_path
from django.http import HttpResponseNotFound
from django.http import Http404
from django.views.static import serve


def serve_media(req, path):
    """提供对 `MEDIA_ROOT` 下文件的简单访问，供开发或本地调试使用。

    参数:
    - `req`: Django 请求对象
    - `path`: 媒体文件相对路径

    返回 HTTP 响应或 404（当文件不存在时）。生产环境中请改用更高效
    的静态文件/媒体托管方案。
    """

    try:
        return serve(req, path, document_root=settings.MEDIA_ROOT)
    except Http404:
        return HttpResponseNotFound()


urlpatterns = [
    path('admin/', admin.site.urls), 
    path('', include("account.urls")),
    path('', include("search.urls")),
    path('', include("dataset.urls")),
    re_path(r"^media/(?P<path>.*)$", serve_media),
]
