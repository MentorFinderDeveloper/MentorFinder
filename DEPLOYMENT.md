# MentorFinder 项目部署信息记录

## 1. 项目约定

### 入口相关信息

- `web_gateway` 入口别名：`mentorfinder-entry`
- 公网入口：`https://lab.cs.tsinghua.edu.cn`
- 公网项目路径：`/se-projects/mentorfinder`

### 开发者按规则填写并提交

- 项目名称：MentorFinder
- `PROJECT_ID`：`mentorfinder`
- 容器运行 `UID:GID`：`10001:10001`

## 2. 镜像与入口

- 完整固定版本镜像：`mentorfinder:2026.08.17`（服务器本地构建）
- 支持 CPU 架构：`linux/amd64`（目标服务器架构；其他架构尚未验证）
- 容器内部 HTTP 端口：`8080`
- 应用启动命令：`/app/deploy/start.sh`
- 健康路径：`/health`
- 镜像内健康检查工具：`wget`

## 3. 环境变量与敏感配置

敏感值只保存在服务器项目目录的 `.env` 中，不填写到本文件，也不提交到 Git。

| 变量 | 必填 | 敏感 | 说明 |
|---|---|---|---|
| `APP_ENTRY_ALIAS` | 是 | 否 | 固定为 `mentorfinder-entry` |
| `PUBLIC_ORIGIN` | 是 | 否 | 固定为 `https://lab.cs.tsinghua.edu.cn` |
| `PUBLIC_SITE_PATH` | 是 | 否 | 固定为 `/se-projects/mentorfinder` |
| `PROJECT_NAME` | 是 | 否 | 固定为 `MentorFinder` |
| `PROJECT_ID` | 是 | 否 | 固定为 `mentorfinder` |
| `APP_UID_GID` | 是 | 否 | 固定为 `10001:10001` |
| `APP_IMAGE` | 是 | 否 | 固定版本镜像名，禁止使用 `latest` |
| `APP_PORT` | 是 | 否 | 固定为 `8080` |
| `APP_HEALTH_PATH` | 是 | 否 | 固定为 `/health` |
| `DJANGO_SECRET_KEY` | 是 | 是 | 在服务器 `.env` 中注入 |
| `JWT_SIGNING_KEY` | 是 | 是 | 在服务器 `.env` 中注入，至少 32 字符 |
| `DJANGO_SUPERUSER_USERNAME` | 否 | 否 | 与邮箱、密码同时填写时创建初始管理员 |
| `DJANGO_SUPERUSER_EMAIL` | 否 | 否 | 初始管理员邮箱 |
| `DJANGO_SUPERUSER_PASSWORD` | 否 | 是 | 在服务器 `.env` 中注入 |
| `EMAIL_HOST` | 否 | 否 | SMTP 主机，默认 `smtp.163.com` |
| `EMAIL_PORT` | 否 | 否 | SMTP 端口，默认 `465` |
| `EMAIL_USE_SSL` | 否 | 否 | 默认 `true` |
| `EMAIL_USE_TLS` | 否 | 否 | 默认 `false` |
| `EMAIL_HOST_USER` | 否 | 否 | SMTP 账号；留空时使用 console backend |
| `EMAIL_HOST_PASSWORD` | 否 | 是 | 在服务器 `.env` 中注入 |
| `DEFAULT_FROM_EMAIL` | 否 | 否 | 邮件发件人显示值 |
| `THUCS_API_BASE_URL` | 否 | 否 | AI 周报服务地址 |
| `THUCS_API_KEY` | 否 | 是 | 在服务器 `.env` 中注入 |
| `THUCS_MODEL_NAME` | 否 | 否 | 默认 `deepseek-v4-flash` |
| `APP_CPU_LIMIT` | 否 | 否 | 默认 `1.0` |
| `APP_MEMORY_LIMIT` | 否 | 否 | 默认 `1g` |
| `APP_PIDS_LIMIT` | 否 | 否 | 默认 `256` |

## 4. 持久化与备份

- 是否需要持久化：是
- 宿主机相对目录或命名卷：`./data`
- 容器内路径：`/app/data`
- 数据类型：SQLite 数据库 `/app/data/db.sqlite3`、上传头像 `/app/data/media`
- 备份命令或方法：停止入口容器后备份绑定目录，例如 `sudo tar -czf mentorfinder-data.tar.gz data`
- 恢复命令或方法：停止入口容器，恢复备份到 `./data`，执行 `sudo chown -R 10001:10001 data` 后重新启动

不要删除 `data`，也不要执行 `docker compose down -v`。

## 5. 初始化和迁移

- 首次启动前操作：从 `.env.project.example` 创建服务器 `.env`，填写两个必填密钥并执行 `chmod 600 .env`；创建 `data` 并设置为 `10001:10001`；确认共享网络 `web_gateway` 已存在
- 数据库初始化/迁移命令：容器启动脚本自动执行 `python manage.py migrate --noinput`；同时收集 Django 静态文件，并在三个管理员变量均已填写时创建初始管理员
- 初始化失败的处理方式：执行 `docker compose --env-file .env logs --tail=200` 查看错误；修正 `.env`、目录权限或迁移问题后重新执行 `docker compose --env-file .env up -d`，不要删除现有数据

## 6. 更新

- 获取新镜像或构建命令：`git pull --ff-only origin main && sudo docker compose --env-file .env build --pull`
- Compose 更新命令：`sudo docker compose --env-file .env up -d`
- 是否需要停机迁移：通常不需要预先停机；容器替换和数据库迁移期间会有短暂不可用
- 预计停机时间：不含镜像构建时间通常小于 1 分钟；大型迁移需另行评估

更新后执行：

```bash
sudo docker compose --env-file .env ps
sudo docker compose --env-file .env logs --tail=100
sudo docker compose --env-file .env exec -T web \
  wget -qO- http://127.0.0.1:8080/health
```

## 7. 回滚

- 上一可用镜像版本：部署前记录的上一固定镜像标签或镜像 ID；首次部署时无
- 镜像回滚步骤：检出上一已验证 Git 提交，使用原固定镜像标签重新构建，执行 `sudo docker compose --env-file .env up -d`
- 数据回滚步骤：停止入口容器，将对应时间点的备份恢复到 `./data`，重新设置 `10001:10001` 权限后启动
- 无法自动回滚的变更：不可逆 Django 数据迁移，以及部署后新增或修改的 SQLite 数据

## 8. 资源与特殊运行要求

- CPU 建议：`1.0 CPU`
- 内存建议：`1 GiB`
- 磁盘增长预估：尚未实测；主要由 SQLite 论文数据和上传头像增长，应持续监控 `./data`
- 外部数据库或第三方服务：无外部数据库；使用 SQLite；按功能访问 SMTP、arXiv/学术数据源和可选 THUCS AI API
- 特殊目录权限：宿主机 `./data` 必须允许 `10001:10001` 读写
- 其他运行要求：服务器需安装 Docker Compose；使用管理员预建的 `web_gateway`；不发布宿主机端口；时区为 `Asia/Shanghai`
