# MentorFinder 项目部署信息记录

## 1. 项目约定

### 入口相关信息

- `web_gateway` 入口别名：`mentorfinder-entry`
- 公网入口：`https://lab.cs.tsinghua.edu.cn`
- 公网项目路径：`/se-projects/mentorfinder`

### 项目标识

- 项目名称：MentorFinder
- `PROJECT_ID`：`mentorfinder`
- 容器运行 `UID:GID`：`10001:10001`
- 代码仓库：`https://github.com/MentorFinderDeveloper/MentorFinder.git`

## 2. 镜像与入口

- 本地固定版本镜像：`mentorfinder:2026.08.17`
- 构建文件：仓库根目录 `Dockerfile`
- 支持 CPU 架构：基础镜像支持的 `linux/amd64`、`linux/arm64`
- 容器内部 HTTP 端口：`8080`
- 应用启动命令：`/app/deploy/start.sh`
- 健康路径：`/health`
- 镜像内健康检查工具：`wget`

如果后续由镜像仓库发布，请把 `.env` 中的 `APP_IMAGE` 改为仓库内存在的完整固定标签；禁止使用 `latest`。

## 3. 运行结构和公开路径

容器内由 Nginx 监听 `8080`，并转发到：

- Next.js：`127.0.0.1:3000`；
- Django/Gunicorn：`127.0.0.1:8000`；
- `/api/...`：去掉 `/api` 后转给 Django；
- `/media/...`：转给 Django；
- `/static/...`：由 Nginx 从 `/app/static` 提供；
- `/admin/...`：转给 Django Admin；
- `/health`：转给 Django 的无需认证健康接口。

外层网关剥离 `/se-projects/mentorfinder` 后转发。Next.js 构建时使用同一路径作为 `basePath` 和 `assetPrefix`，内部 Nginx 在前端这一跳补回该路径。修改 `PUBLIC_SITE_PATH` 时必须同步修改 `deploy/nginx.conf`，然后重新构建镜像。

## 4. 环境变量与敏感配置

服务器执行 `cp .env.project.example .env` 后填写敏感项，并执行 `chmod 600 .env`。

| 变量 | 必填 | 敏感 | 说明 |
|---|---|---|---|
| `JWT_SIGNING_KEY` | 是 | 是 | 至少 32 字符，不能使用已知开发值 |
| `DJANGO_SECRET_KEY` | 是 | 是 | Django 生产签名密钥 |
| `DJANGO_SUPERUSER_USERNAME` | 否 | 否 | 与下面两项同时填写时创建管理员 |
| `DJANGO_SUPERUSER_EMAIL` | 否 | 否 | 初始管理员邮箱 |
| `DJANGO_SUPERUSER_PASSWORD` | 否 | 是 | 初始管理员密码 |
| `EMAIL_HOST_USER` | 否 | 否 | SMTP 账号；留空时使用 console backend |
| `EMAIL_HOST_PASSWORD` | 否 | 是 | SMTP 密码或授权码 |
| `THUCS_API_BASE_URL` | 否 | 否 | 周报总结服务地址 |
| `THUCS_API_KEY` | 否 | 是 | 周报总结服务密钥 |

敏感值只保存在服务器 `.env` 或受控 secrets 中，不写入仓库和镜像。

## 5. 持久化与备份

- 是否需要持久化：是；
- 宿主机目录：`./data`；
- 容器内目录：`/app/data`；
- SQLite：`/app/data/db.sqlite3`；
- 上传头像：`/app/data/media`。

首次部署：

```bash
sudo mkdir -p data
sudo chown 10001:10001 data
```

备份（在项目目录执行）：

```bash
sudo tar -czf "mentorfinder-data-$(date +%Y%m%d-%H%M%S).tar.gz" data
```

恢复时先停止入口服务，把现有 `data` 另行备份，再将备份内容恢复到 `./data` 并重新设置 `10001:10001` 所有权。不要执行 `docker compose down -v` 或删除 `data`。

## 6. 初始化与首次部署

```bash
cd <服务器分配的部署父目录>
git clone https://github.com/MentorFinderDeveloper/MentorFinder.git mentorfinder
cd mentorfinder
cp .env.project.example .env
sudo vi .env
sudo chmod 600 .env
sudo mkdir -p data
sudo chown 10001:10001 data
sudo docker network inspect web_gateway
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env build --pull
sudo docker compose --env-file .env up -d
sudo docker compose --env-file .env ps
sudo docker compose --env-file .env logs --tail=100
```

启动脚本会校验 JWT 密钥、应用已提交的数据库迁移、收集 Django 静态文件，并在三个初始管理员变量均已填写时尝试创建管理员。启动过程不会立即抓取外部数据。

## 7. 更新

```bash
cd <服务器分配的 MentorFinder 部署目录>
git pull --ff-only
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env build --pull
sudo docker compose --env-file .env up -d
sudo docker compose --env-file .env ps
sudo docker compose --env-file .env logs --tail=100
```

数据库迁移由新容器启动时自动执行。涉及不可逆迁移时，更新前必须先备份 `./data`。

## 8. 回滚

1. 更新前记录当前 Git 提交和镜像 ID，并备份 `./data`。
2. 检出上一已验证提交，或把 `.env` 中 `APP_IMAGE` 改为上一固定版本镜像。
3. 执行 `sudo docker compose --env-file .env up -d --build`。
4. 只有在数据库迁移与旧代码不兼容时，才停止服务并从对应时间点的数据备份恢复 `./data`。

数据回滚会覆盖部署后的新增数据，必须由项目负责人确认后执行。

## 9. 资源与特殊要求

- 默认 CPU 限制：`1.0`；
- 默认内存限制：`1 GiB`；
- 默认进程数限制：`256`；
- 外部服务：SMTP、arXiv/学术数据源、可选 THUCS AI API；
- 特殊权限：宿主机 `./data` 必须可由 `10001:10001` 写入；
- 共享网络：只使用管理员预建的 `web_gateway`，不发布宿主机端口。
