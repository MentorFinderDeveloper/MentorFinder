# MentorFinder Backend

MentorFinder 的后端服务，基于 Django 5.1 和 Django REST Framework，负责账户、导师与论文数据、搜索、关注关系、时间线、周报、邮件验证码和后台管理。

## 技术栈

- Python 3.11
- Django 5.1
- Django REST Framework
- SQLite
- APScheduler
- Gunicorn（生产环境）
- pytest、pytest-django、coverage

## 应用结构

```text
backend/
├── MFBackend/  Django 项目配置、根路由和 WSGI/ASGI 入口
├── account/    注册登录、资料、关注、邮箱验证、周报和管理接口
├── dataset/    导师、论文、时间线、爬虫和定时任务记录
├── search/     导师与论文搜索
├── utils/      JWT、请求校验、时间和调度器工具
├── config.yaml
├── manage.py
└── requirements.txt
```

## 本地开发

### 1. 创建环境

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 JWT

所有 `manage.py` 命令都要求有效的 `JWT_SIGNING_KEY`。密钥至少 32 字符，不能使用已知开发值 `KawaiiNana`。

```bash
export JWT_SIGNING_KEY='replace-with-at-least-32-random-characters'
```

也可以在 `backend/.env` 中设置；该文件已被 Git 忽略。

### 3. 初始化数据库并启动

```bash
mkdir -p data
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

检查服务：

```bash
curl http://127.0.0.1:8000/health
```

预期返回：

```text
ok
```

## 主要环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `JWT_SIGNING_KEY` | 是 | JWT 签名密钥，至少 32 字符 |
| `DJANGO_SECRET_KEY` | 生产必填 | Django 签名密钥 |
| `SQLITE_PATH` | 否 | SQLite 路径，默认 `backend/data/db.sqlite3` |
| `MEDIA_ROOT` | 否 | 上传文件目录，默认 `backend/media` |
| `PUBLIC_ORIGIN` | 生产必填 | 公网入口 |
| `PUBLIC_SITE_PATH` | 生产必填 | 公网子路径 |
| `EMAIL_HOST_USER` | 否 | SMTP 账号 |
| `EMAIL_HOST_PASSWORD` | 否 | SMTP 密码或授权码 |
| `THUCS_API_BASE_URL` | 否 | AI 周报服务地址 |
| `THUCS_API_KEY` | 否 | AI 周报服务密钥 |
| `THUCS_MODEL_NAME` | 否 | 默认 `deepseek-v4-flash` |

未配置 SMTP 凭据时使用 Django console email backend，不会发送真实邮件。

## 路由约定

后端路由在容器内部从根路径提供，例如：

- `/health`
- `/login`、`/register`、`/password-reset`
- `/profile/...`、`/follow/...`、`/management/...`
- `/search/mentors`、`/search/papers`
- `/dataset/mentors`、`/dataset/papers`
- `/dataset/weekly-push/...`
- `/timeline`
- `/admin/`
- `/media/...`

浏览器统一请求公开的 `/se-projects/mentorfinder/api/...`。外层网关移除项目子路径，容器内部 Nginx 再移除 `/api` 后转发给 Django。

## 测试

pytest 会通过 `conftest.py` 注入测试专用 JWT 密钥。

```bash
pytest
```

生成覆盖率与 JUnit 报告：

```bash
sh test.sh
```

输出目录：

- `coverage-reports/`
- `xunit-reports/`

## 数据与周报命令

同步导师和论文：

```bash
python manage.py sync_dataset
```

分别抓取：

```bash
python manage.py fetch_mentors
python manage.py fetch_papers
```

生成首页周报：

```bash
python manage.py generate_weekly_push
```

预览用户周报邮件：

```bash
python manage.py send_weekly_push --dry-run
python manage.py send_weekly_push_mock --dry-run
```

查看和重试发送记录：

```bash
python manage.py show_weekly_push_records
python manage.py retry_failed_weekly_push --period-key <period-key> --dry-run
```

## 进程内定时任务

`config.yaml` 控制定时任务：

```yaml
startup:
  run_initial_sync: false
  run_daily_sync_scheduler: true
  run_weekly_push_scheduler: true
```

当前生产 Web 进程使用 APScheduler：

- 每天 `04:00`、`12:00`、`20:00` 执行数据同步；
- 每周一 `05:00` 生成首页周报；
- 每周一 `05:00` 生成并发送用户周报；
- 时区为 `Asia/Shanghai`；
- 被部署中断的同步任务会在进程恢复后继续。

`run_initial_sync` 当前保持为 `false`，启动容器时不会立即执行全量抓取。

## 生产部署

生产部署以仓库根目录的以下文件为准：

- `Dockerfile`
- `docker-compose.yaml`
- `deploy/nginx.conf`
- `deploy/start.sh`
- `DEPLOYMENT.md`

生产容器中：

- Gunicorn 监听 `127.0.0.1:8000`；
- Next.js 监听 `127.0.0.1:3000`；
- 内部 Nginx 监听 `8080`；
- SQLite 保存到 `/app/data/db.sqlite3`；
- 上传文件保存到 `/app/data/media`；
- 启动脚本自动执行已提交的数据库迁移和 `collectstatic`；
- `GET /health` 用于 Docker Compose 健康检查。

完整的首次部署、更新、备份和回滚信息见 [根目录部署记录](../DEPLOYMENT.md)。
