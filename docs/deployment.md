# 运行与部署

## 本地后端

需要 CPython 3.12、Docker Compose v2；Android 构建另需 JDK 17、SDK 35 / Build Tools 35.0.0。从仓库根目录（以下 Python 环境命令使用 PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.lock -r requirements-ci.txt
docker compose -f infra/docker-compose.yml up -d
$env:APP_ENV = "demo"
```

按 [.env.example](../.env.example) 创建根目录 `.env`，填入本机配置：

```dotenv
DATABASE_URL=postgresql+psycopg://nianian:nianian-dev-only@127.0.0.1:5432/nianian
PUBLIC_BASE_URL=http://127.0.0.1:8000
S3_ENDPOINT=http://127.0.0.1:9000
S3_BUCKET=nianian-private
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=nianian-dev-only
```

另用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成本机值，写为 `.env` 中的 AUTH_SIGNING_KEY。该文件不提交。API 与 worker 使用相同签名密钥、APP_ENV 和数据库/存储配置。上述数据库与存储默认凭据只用于本机演示。

```powershell
cd backend
python -m alembic upgrade head
python -m app --reload
# 另一个已激活环境的终端，同样设置 APP_ENV=demo，在 backend/ 中运行：
python -m app.worker.main --serve
```

API 根地址 `http://127.0.0.1:8000`；`/docs`、`/openapi.json` 查看当前运行接口。`/health` 只检查 API 活性，不证明数据库、存储或 worker 正常。摘要、通知和索引需要 worker 实际运行，`--once` 可执行一次周期。Demo 登录支持 demo-child、demo-elder、demo-caregiver、demo-other；通过正常客户端/API 建家并授权，不运行依赖未实现表的 seed。

APP_ENV 从进程环境选择 dev/test/demo，应用读取 `backend/config/<环境>.env`，再加载忽略提交的根 `.env`；环境变量优先。demo 要求 demo_data=true 且 provider_mode=mock，test 也只允许 Mock。填入供应商密钥不会自动启用真实 AI。

## 真实 LLM 文字联调

先沿用上述数据库、迁移、签名密钥配置。在 API 和 worker 进程设置 `$env:APP_ENV = "dev"`，根目录 `.env` 增加：

```dotenv
PROVIDER_MODE=mock
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_THINKING=disabled
LLM_API_KEY=替换为本机密钥
LLM_TIMEOUT_SECONDS=20
```

当前接入 DeepSeek 官方 V4.1 Flash；截至 2026-10-20，官方 API 模型名为 `deepseek-flash`（指向 V4.1-Flash-1017），不是 `deepseek-v4.1-flash`。URL 是 API 基址，程序自动追加 `/chat/completions`。`LLM_THINKING=disabled` 会发送 `thinking: {"type":"disabled"}`，关闭默认深度思考以减少日常聊天等待；回复保持 JSON 模式。[官方模型说明](https://api-docs.deepseek.com/quick_start/pricing/)、[请求参数](https://api-docs.deepseek.com/api/create-chat-completion/)。

密钥仅放在后端忽略提交的 `.env` 或环境变量，不能放进 Android。保存后重启 API/worker，使缓存的配置重新加载；配置缺项时拒绝启动，不静默回退到 Mock。切换其他兼容供应商时修改 URL/模型，并移除不受其支持的 `LLM_THINKING`；保持 HTTPS、Bearer 鉴权及 `response_format={"type":"json_object"}` 支持。

`LLM_PROVIDER` 只控制聊天；`PROVIDER_MODE=mock` 继续允许虚构 Demo 登录，Embedding、语音和推送不会随 LLM 升级。demo/test 环境禁止真实 LLM。当前已用隔离 PostgreSQL 库的虚构账户验证登录、家庭关系、WebSocket 两轮真实回复、上下文衔接和结束会话，不持久化逐字稿；这不代表 Android 真机或正式部署验收。真实敏感数据使用前仍需确认供应商留存与训练策略。

Android 以 demo-elder 登录并加入家庭，点击“开始聊天”，输入文字后发送。连接后的聊天卡片显示“AI 对话”或“Mock 演示”；成功回复后可继续第二轮，停止会取消等待，失败可重新编辑上一条。断线不会自动重发，重连后需重新说明话题；回顾仍需单独授权。

语音在老人端使用手机已安装的中文语音识别与 TTS 服务，无须配置后端 ASR/TTS 密钥。在“用于我与念念的交流”中允许语音处理（与授予家属分开），再点“点击说话”并允许麦克风，说完等自动识别或点“说完了”，识别文字自动提交现有 LLM，回复显示并朗读。“停止”取消当前识别、请求或播放；“打断并说话”停播后开始新输入。支持“再说一遍”“说慢一点”“关闭朗读”，音量使用手机音量键。当前为按钮打断，无自动人声打断或后台唤醒。设备没有识别服务、中文语音数据或麦克风权限时会提示并保留文字入口；语音服务可能联网，数据边界见 [安全说明](security.md)。真机收音、扬声器输出和设备引擎兼容性尚待验证。

## Android


家属端在“家人关注事件”中确认关注、人工记录已联系、标记误报或解决。误报可以直接关闭待确认事件；解决需先确认关注。详情展示处理时间线，误报/解决立即取消待发通知，已发布记录保留至原期限。当前家庭创建者或同时有 `SIGNAL_READ`、`SIGNAL_WRITE` 的子女、照护人、紧急联系人可以处理，仍需长辈的 `NOTIFICATION_TO_FAMILY` 授权，身体不适另需 `HEALTH_MEDICATION`。

双方在家庭设置的“我的联系方式与紧急联系”登记本人号码（E.164，如带 +86 国家区号），可单独允许号码分享、登记为紧急联系人或删除。号码加密保存；退出/移除成员时删除。长辈可在此处逐人授予或撤回关注通知、健康信息授权。管理员可邀请紧急联系人并授予处理权限。事件中的拨号、短信入口使用当前获准分享的号码，打开系统拨号/短信编辑器，由用户完成发送；不会据此标记联系成功。号码为本人声明，尚未做运营商验证。

### 外部关注通知（默认关闭）

API 和 worker 同时配置 `CONTACT_ENCRYPTION_KEY`（用 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成并仅保存到本地 `.env`），才能保存号码/推送主题。升级数据库后可使用联系人功能，无须开启外发。密钥丢失会导致已存号码无法解密；不要使用登录签名密钥替代。

外发需显式设置 `APP_ENV=dev`、`NOTIFICATION_EXTERNAL_ENABLED=true`。ntfy 推送设置 `NOTIFICATION_PUSH_PROVIDER=ntfy`、`NTFY_BASE_URL`（HTTPS 私有服务）、`PUSH_API_KEY`，接收者在联系人设置填写本人主题，并在 ntfy 手机客户端订阅；服务端必须为主题配置访问控制。此实现通过 ntfy 客户端接收后台推送，念念 APK 尚未内置厂商推送 SDK。[ntfy 官方发送接口](https://docs.ntfy.sh/publish/)。

短信和自动语音电话配置 `TWILIO_ACCOUNT_SID`、`TWILIO_AUTH_TOKEN`、`TWILIO_FROM_NUMBER`。接收者登记本人号码并在对应长辈通知偏好中主动开启 SMS/PHONE，遵守免打扰；服务商账号、号码、地区发送权限与费用由部署方配置。发送内容仅为“念念 AI 提醒，请到应用查看授权详情”，不外发逐字稿、健康线索、家庭名称或事件标识。语音为 AI 自动播报，不是接通长辈本人。[短信 API](https://www.twilio.com/docs/messaging/api/message-resource)、[语音 API](https://www.twilio.com/docs/voice/api/call-resource)。

`GET /v1/notification-capabilities` 返回实际配置状态；外发关闭、缺少配置或接收地址会保留明确失败记录，不回退为成功。供应商受理仅标记 SENT；worker 查询 Twilio 回执，短信 delivered 才记送达，电话 busy/no-answer/failed 显示失败，completed 仅表示呼叫结束（可能是语音信箱），不会自动确认、联系或解决事件。外部发送超时、丢失回包或进程在发送中崩溃时标记 DELIVERY_UNKNOWN 并停止自动重发，避免重复呼叫；需人工核实。Mock 推送仍仅为模拟，不证明设备送达。尚未使用真实账号、号码或设备验证外部渠道。

`android/local.properties` 配置本机 `sdk.dir`，不要提交。两个应用共享 `shared`；日常只构建所改应用或一个 Demo 变体：

```bash
cd android
./gradlew :shared:testDebugUnitTest
./gradlew :app-elder:assembleDemoDebug :app-family:assembleDemoDebug
```

Windows 使用 `gradlew.bat`；按需运行 `:shared:lintDebug`。APK 位于各 `app-*/build/outputs/apk/demo/debug/`。dev、qa、demo 的应用 ID 和原有 Room 数据库身份保持不变，不要求全部变体构建。

模拟器连接 `http://10.0.2.2:8000`。真机 API 用 HTTPS；USB Debug 可执行 `adb reverse tcp:8000 tcp:8000` 后填 `http://127.0.0.1:8000`。照片上传直接访问 S3_PUBLIC_ENDPOINT，下载通过 PUBLIC_BASE_URL 表示的 API；这些地址都需从设备可达。必要时为 USB 联调转发存储端口，或设置设备可访问的存储地址。不能把任意局域网 HTTP 地址当作 Android 已允许的 API。

长辈端按下一条未提示提醒（含稍后提醒）、免打扰结束或缓存到期时间注册本机闹钟，不进行每分钟后台轮询。当前使用非精确闹钟，Android/OEM 省电和频率限制仍可能造成延迟，不保证准点送达。实机需开启此应用的系统通知并允许后台运行；禁止后台运行时，MIUI 等系统可直接阻止闹钟。服务端生成执行记录不代表手机已收到通知。

## Windows

需要带 Tk 的 CPython 3.12。在已激活环境、仓库根目录：

```powershell
python -m pip install -e windows
niannian-family-client
niannian-elder-demo
```

也可执行 `windows/run.ps1 -Client family` 或 `-Client elder`。两端设置只保存服务器地址；令牌在内存中。选择家庭后点击注册/启用本机，即可与连接同一后端、加入同一家庭的 Android 或 Windows 家人收发文字留言。默认每 3 秒刷新，可关闭自动刷新；令牌过期自动轮换续期。退出登录或关闭窗口会停止轮询，等待正在执行的请求结束后撤销当前会话并清空界面；断网退出会明确提示服务端撤销未确认。

升级前从 `backend/` 执行 `python -m alembic upgrade head`，再重启 API，迁移头为 `20261023_attention_contacts`。Android 双端登录并选择已确认加入的家庭后，留言卡片自动注册设备，在前台每 3 秒同步；进入后台停止轮询并清空已加载留言，返回前台重新补拉。Windows 的设备能力检测用于提示旧版后端缺少接口。

首次联调：家属建家并生成邀请 → 长辈接受并确认加入 → Windows 注册本机/Android 打开留言卡片 → 家属发文字 → 长辈收到并点击“我已读完这条” → 回复 → 家属查看回执。接收方暂未注册或离线时仍保存给该成员，稍后可补收；回执表示这个成员的客户端已接收或本人已确认，不表示所有设备均在线。留言发送失败后用原内容重试，客户端复用幂等键；不会自动重复发送。当前没有后台消息推送。

需要 exe 时在当前环境安装 pyinstaller，再运行 `windows/build.ps1 -Client family` 或 `-Client elder`，输出在 `windows/dist/`。打包不是每次编辑的前置条件。

## Linux 服务端

主机准备 Docker Engine、Compose v2、curl、openssl 或 od；用户需有 Docker 权限。在仓库根目录：

```bash
bash infra/linux/deploy.sh --host <局域网IP或DNS>
```

首次生成权限 600 的 `infra/linux/.env` 和随机本机凭据，构建后端及固定版本 MinIO/mc，先迁移，再启动 API、worker、PostgreSQL/pgvector 和私有桶。更新时再次运行脚本即可；已有 `.env` 不覆盖，换地址时编辑 NIANNIAN_HOST。

默认 API 为 8000、S3 为 9000；PostgreSQL 不映射主机端口，MinIO 控制台 9001 只绑定回环。端口可在该 `.env` 修改。默认 HTTP/WS 供可信内网 Windows 演示；Android 局域网连接需另外配置 HTTPS API。公网部署还需 TLS 和访问限制，不直接暴露演示凭据或管理端口。

```bash
docker compose --env-file infra/linux/.env -f infra/linux/docker-compose.yml ps
docker compose --env-file infra/linux/.env -f infra/linux/docker-compose.yml logs -f api worker
# 停止服务但保留数据库/照片卷：
docker compose --env-file infra/linux/.env -f infra/linux/docker-compose.yml down
```

不要给已有数据随意执行 `down --volumes`。按需用 `bash infra/linux/smoke.sh` 检查部署状态；构建 MinIO 需要访问上游，首次构建耗时取决于网络和 CPU。

## 常见问题与开发检查

- 登录不可用：检查 APP_ENV、Mock/Demo 配置和签名密钥；API 与 worker 必须使用同一配置。
- 文字正常而照片失败：检查 S3_ENDPOINT、客户端可达的 S3_PUBLIC_ENDPOINT、私有桶凭据及 PUBLIC_BASE_URL。
- 索引/摘要/通知不更新：检查 worker 和 task_outbox；失败会重试或进入 DEAD，不能只看 `/health`。
- Linux API 未启动：先查看 migrate、api 日志；Android 连不上时先核对 HTTPS/回环限制和端口可达性。

开发验证统一用 `scripts/verify.py`，只运行关联范围；测试库及真实 MinIO 参数见 [测试说明](../tests/README.md)。没有执行的真机、供应商或部署检查如实写未验证，不新建多份报告。
