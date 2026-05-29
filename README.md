## Django 小作业

By c7w

2026 春《软件工程》课程 Django 小作业

## API 文档

在完成本文档时，请参照 [API 文档](https://thuse-course.github.io/course-index/handout/api/).


## 环境配置

我们使用 Linux（或 WSL）环境与 `Python=3.11` 配置本次作业，推荐你使用 `conda` 创建一个新的虚拟环境：

```bash
conda create -n django_hw python=3.11 -y
conda activate django_hw
```

在此环境的基础之上，你可以运行下述命令安装依赖，注意请确保你的当前工作路径**在克隆的小作业仓库中**：

```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

!!! note "配置环境也是软件工程的一部分"

    软件工程是一门研究用工程化方法构建和维护有效的、实用的和高质量的软件的学科，而配置环境是任何工程化项目的第一步。在本次作业中，我们使用了 `conda` 作为环境管理工具，使用了 `pip` 作为依赖管理工具。这些工具的使用都是为了让你能够更加方便地配置环境，从而更加专注于实现功能。在大作业中，你也会使用到类似的工具，因此请务必熟悉这些工具的使用方法。


然后，你可以运行如下指令检查环境配置是否成功：

```bash
python3 manage.py runserver
```

这会在 `localhost:8000` 开启服务端进行监听网络请求。你可以打开浏览器，访问 http://localhost:8000/startup 来检查服务端是否正常启动。如果正常启动，你会看到含有 "Congratulations! You have successfully installed the requirements. Go ahead!" 的网页。



## 周报推送 mock 命令

后端当前提供了一个手动触发的 mock 周报命令，用于验证“构造本周新增论文列表 -> 生成周报内容 -> 渲染邮件 -> 发送邮件”的链路。

本地预览周报结果，不发送邮件：

```bash
python manage.py send_weekly_push_mock --dry-run
```

只预览某个用户的周报：

```bash
python manage.py send_weekly_push_mock --user <username> --dry-run
```

触发发送流程：

```bash
python manage.py send_weekly_push_mock --user <username>
```

使用 JSON 文件指定七天新增论文列表：

```bash
python manage.py send_weekly_push_mock --paper-file data/mock_weekly_papers.json --dry-run
```

记录某一天爬虫新增的论文 ID：

```bash
python manage.py record_weekly_push_papers --day monday --paper-ids 1,2,3
```

周报发送完成后，重置七天新增论文记录：

```bash
python manage.py reset_weekly_push_papers
```

默认邮件后端是 Django console backend，所以本地发送时邮件内容会打印到控制台，不会真正发出。若需要接入真实 SMTP，可以通过环境变量覆盖 `EMAIL_BACKEND` 和 `DEFAULT_FROM_EMAIL`。

当前每日论文爬虫在发现新增 `Paper` 后，会自动把对应 `Paper.id` 写入 `db.sqlite3` 中的周报增量表。为了避免周四中午发送周报前把新周期的周四数据混入旧周期，系统会在周四 `12:00` 之前把新增论文先写入 `next` 周期桶，待本周周报发送完成后再自动提升为新的当前周期桶。

mock 数据说明：

- 命令会从数据库最近的论文中取 `--paper-limit` 篇，默认 `20` 篇。
- 这些论文会被轮流分配到 7 个 list，模拟上周四到本周三每天爬虫发现的新论文。
- 如果传入 `--paper-file`，命令会优先使用 JSON 文件中的论文 ID 列表，而不是 `--paper-limit`。
- JSON 文件中的 ID 必须是数据库里已经存在的 `Paper.id`；如果 ID 不存在，命令会报错。
- `record_weekly_push_papers` 和 `reset_weekly_push_papers` 已经切到数据库桶实现，不再依赖 JSON 文件；其中 `--paper-file` 只在 `send_weekly_push_mock` 里作为 mock 输入使用。
- `record_weekly_push_papers` 会把当天增量论文 ID 追加到数据库中的对应周期/星期桶，并自动跳过重复 ID。
- `reset_weekly_push_papers` 会把数据库中指定周期的七天记录清空，适合在周报发送完成后开启下一周期。
- 当前逻辑会给有邮箱的用户生成周报；周报内容只包含用户关注导师和用户私有导师关联的新论文。
- `fetch_papers` 在默认情况下会自动维护数据库中的周报增量桶；如需只抓论文不记录周报增量，可传 `--disable-weekly-record`。

## JWT 配置

后端当前使用自定义 JWT 作为登录态凭证。在 GitLab CI/CD Variables 中维护 `JWT_SIGNING_KEY`，并由 CI 在构建时写入 `backend/.env`，与邮件账号等部署变量一致。

如果希望手动指定，也可以在启动前设置：

```bash
export JWT_SIGNING_KEY='replace-with-a-long-random-secret'
```

要求如下：

- `JWT_SIGNING_KEY` 必须设置，且长度至少为 32 个字符。
- 不能使用仓库中的已知开发值 `KawaiiNana`。
- CI 会在 build 阶段检查该变量是否存在；缺失时会直接失败并提示。
- 如果手动修改了 `backend/.env` 里的该值，之前签发的 token 会失效，需要重新登录。

测试环境已经预置了一个专用测试密钥；在 CI 中也会在单测前检查 `JWT_SIGNING_KEY`，避免出现“本地可跑、云端缺变量”的情况。

JSON 文件格式示例：

```json
{
  "thursday": [1, 2],
  "friday": [],
  "saturday": [3],
  "sunday": [],
  "monday": [],
  "tuesday": [],
  "wednesday": [4]
}
```

其中 7 个字段分别对应上周四、上周五、上周六、上周日、本周一、本周二、本周三。`data/mock_weekly_papers.json` 现在主要用于 `send_weekly_push_mock` 的模拟输入；正式周报链路已经切到数据库表。

当前还没有实现的内容：

- 没有使用 `Paper.discovered_at` 判定真实发现时间。
- 没有做邮箱验证。
- 没有接入真实 SMTP 配置。

## 周报定时推送

后端当前提供了一个正式的周报发送命令 `send_weekly_push`，它会读取数据库中的当前周期七天增量论文桶，向有邮箱的用户发送周报。成功发送后，会把当前周期桶归档到数据库中的 `archived` 记录，并在存在 `next` 周期桶时自动提升。

本地预览周报结果，不发送邮件也不清空记录：

```bash
python manage.py send_weekly_push --dry-run
```

只预览某个用户的周报：

```bash
python manage.py send_weekly_push --user <username> --dry-run
```

触发正式发送：

```bash
python manage.py send_weekly_push
```

后端会在 Django 应用启动时通过内置 APScheduler 注册周报邮件任务。默认配置是每周四 `12:00`（`Asia/Shanghai`）先执行 `generate_user_weekly_reports`，再执行 `send_weekly_push`。

也保留了 `run_weekly_push_scheduler` 命令，方便本地单独验证调度逻辑：

```bash
python manage.py run_weekly_push_scheduler
```

如果不希望 Django 应用启动时注册该任务，可以把 [config.yaml](/mnt/d/My_Files/TsingHua/大二下/软件工程/Project/找导师/backend/config.yaml) 中的 `startup.run_weekly_push_scheduler` 改成 `false`。

## 周报发送记录

后端当前会把正式周报的发送状态写入 `PushRecord`。你可以在 Django Admin 中查看，也可以通过管理命令查询和重试失败记录。

查看最近的周报发送记录：

```bash
python manage.py show_weekly_push_records
```

按周期查看：

```bash
python manage.py show_weekly_push_records --period-key 20260416_20260422
```

只看失败记录：

```bash
python manage.py show_weekly_push_records --period-key 20260416_20260422 --status failed
```

只预览将要重试的失败用户：

```bash
python manage.py retry_failed_weekly_push --period-key 20260416_20260422 --dry-run
```

正式重试某个周期失败的周报发送：

```bash
python manage.py retry_failed_weekly_push --period-key 20260416_20260422
```

如果需要人工补发历史某一周，也可以在正式发送命令中显式指定周期：

```bash
python manage.py send_weekly_push --user alice --period-key 20260401_20260407 --period-start 2026-04-01T00:00:00+08:00 --period-end 2026-04-07T23:59:59+08:00
```

## 爬虫定时任务

后端会在 Django 应用启动时通过内置 APScheduler 注册爬虫定时任务，默认每天 `03:15`（`Asia/Shanghai`）执行 `sync_dataset`（即先抓导师再抓论文）。

定时任务每次触发都会写入 `ScheduledTaskRun` 表，可在 Django Admin 查看任务名称、状态、开始时间、结束时间和失败信息。

也保留了 `run_daily_sync` 命令，方便本地单独验证调度逻辑：

```bash
python manage.py run_daily_sync
```

如果不希望 Django 应用启动时注册该任务，可以把 [config.yaml](/mnt/d/My_Files/TsingHua/大二下/软件工程/Project/找导师/backend/config.yaml) 中的 `startup.run_daily_sync_scheduler` 改成 `false`。

## 启动配置

后端根目录下的 [config.yaml](/mnt/d/My_Files/TsingHua/大二下/软件工程/Project/找导师/backend/config.yaml) 可以控制启动脚本是否执行启动期任务，以及 Django 应用启动时是否注册内置定时任务：

```yaml
startup:
  run_initial_sync: true
  run_daily_sync_scheduler: true
  run_weekly_push_scheduler: true
```

- `run_initial_sync`: 是否在服务启动时先执行一次 `python3 manage.py sync_dataset`
- `run_daily_sync_scheduler`: 是否在 Django 应用启动时注册每日爬虫与每周首页推送任务
- `run_weekly_push_scheduler`: 是否在 Django 应用启动时注册每周用户周报邮件任务


## 代码阅读

快速阅读提供的代码框架，试着回答以下问题：

- 本次作业的顶层项目名是什么？其下有哪些应用？
- `utils` 中的四个文件中的功能函数的输入、输出分别是什么？`CheckRequire` 装饰器的作用是什么？



!!! note "API 文档"
	下面的任务推荐你对照着 API 文档完成。


## 添加路由

在 `board/urls.py` 中：

- 为 `boards/<index>` API 添加路由到 `views.boards_index` 视图函数
    - 注意这里不要写成 `<int:index>`，因为 API 文档里规定对于不是 int 的情况也要返回合法的 JSON 请求，而非展示 Django 的默认 404 网页

- 为 `user/<userName>` API 添加路由到下面“添加视图函数”节中自定义的视图函数



## 补全模型

在 `board/models.py` 中：

- 补全 `Board` 类的成员
    - `id`，使用 BigAutoField，设置主键
    - `user`，外键连接到 `User` 类，使用级联删除
    - `board_state`，使用 CharField
    - `board_name`，使用 CharField
    - `created_time`，使用 FloatField，初始值为类创建时的时间
- 补全 `Board` 表的元数据
    - 为 `board_name` 创建索引
    - 在 `user` 和 `board_name` 上建立联合唯一约束

之后，你应该使用如下命令建库：

```bash
 python3 manage.py makemigrations board && python3 manage.py migrate
```

你需要搞明白这两个命令分别在干什么！你会在部署阶段再次遇到它们！


## 补全与添加视图函数

在 `board/views.py` 中：

- 按照所给注释补全 `login` 登录函数
- 阅读 API 文档中的对应项，然后补全 `check_for_board_data` 中的检查输入字段功能
- 按照所给注释补全 `board` 视图函数
- 阅读 API 文档中的对应项，完成 `boards_index` 的 DELETE 方法
- 阅读 API 文档中的对应项，完成 `user/<userName>` API 所对应的视图函数



## 进行单元测试

我们为你撰写的脚本 `test.sh` 包含了进行单元测试与计算覆盖率的功能。如果你只想运行单元测试，你可以运行：

```bash
python3 manage.py test
```

正确完成本次作业应该可以通过所有测试点。在小作业中你可以阅读 `board/tests.py` 中的测试逻辑对你的路由、模型与视图函数进行修改，**但请不要修改 `board/tests.py` 中的内容**。在后续的项目中 `tests.py` 将由组内负责测试与质量保证的同学进行撰写。

