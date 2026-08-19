# MentorFinder 最终测试记录

## 1. 测试对象

- 项目：MentorFinder
- `PROJECT_ID`：`mentorfinder`
- 镜像标签：`mentorfinder:2026.08.17`
- 目标公网路径：`https://lab.cs.tsinghua.edu.cn/se-projects/mentorfinder/`

## 2. 当前验证记录（2026-08-17）

| 场景 | 结果 | 说明 |
|---|---|---|
| Next.js 子路径生产构建 | 通过 | 使用 `NEXT_PUBLIC_SITE_PATH=/se-projects/mentorfinder npm run build` |
| 前端自动化测试 | 通过 | 19 个测试套件、364 个测试全部通过 |
| Python 配置与 URL 文件语法 | 通过 | `py_compile` 通过 |
| Shell 启动脚本语法 | 通过 | `sh -n deploy/start.sh` |
| Compose YAML 基础语法 | 通过 | YAML 解析通过 |
| Git 补丁空白检查 | 通过 | `git diff --check` |
| Docker Compose 解析 | 待服务器验证 | 当前开发环境未安装 Docker CLI |
| 完整镜像构建与健康检查 | 待服务器验证 | 需 Docker 环境和依赖下载能力 |
| 公网页面、静态资源和 API | 待网关接入后验证 | 需管理员配置项目路由 |
| SQLite 与头像持久化 | 待服务器验证 | 需运行容器后重建验证 |

## 3. 服务器最终验收

部署后依次检查：

```bash
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env ps
sudo docker compose --env-file .env logs --tail=100
sudo docker network inspect web_gateway
```

然后验证：

- 公网首页和各客户端路由均保留 `/se-projects/mentorfinder`；
- `_next`、图标与背景图请求均带项目路径；
- 登录、搜索、时间线、头像上传等 `/api` 请求可达 Django；
- `/health` 返回 HTTP 200；
- 重建容器后 SQLite 数据和上传头像仍存在；
- HTTPS 页面不产生 mixed-content 请求。

服务器与公网项目全部验证后，再把对应“待验证”项更新为“通过”。
