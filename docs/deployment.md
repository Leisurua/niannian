# 运行与部署

## 账户生命周期运维

升级 API/worker 前，在 `backend/` 运行 `python -m alembic upgrade head`（当前头 `20261026_avatar_jobs`，包含账户生命周期迁移），随后重启二者。当前入口是 REST API，字段和凭证找回方式见 [OpenAPI](openapi.yaml)；Android/Windows 尚未增加账户管理界面。导出文件含本人资料，客户端应通过系统文件保存器交由本人选择位置；删除前先保存独立回执凭证，受理后按已有退出流程清理本地会话和缓存。

可配置 `BACKUP_RETENTION_DAYS=30`、`AUDIT_RETENTION_DAYS=90`、`TASK_RETENTION_DAYS=7`、`ACCOUNT_EXPORT_MAX_BYTES=104857600`。`BACKUP_DIRECTORY` 默认为空；只有显式指定的私有目录会启用自动备份期限清理。备份文件须命名为 `niannian-backup-YYYYMMDDTHHMMSSZ.dump`、`.sql.gz`、`.tar.gz` 或 `.zip`，时间为备份快照的 UTC 时间，不因复制而改写；写入完成后才使用该名称。清理不递归、不跟随符号链接/目录联接、不删除其他文件；目录必须仅由可信运维账号写入。此功能不自动创建备份。

Linux Compose 的 `BACKUP_DIRECTORY` 是容器内路径；启用时需通过本地 Compose override 为 worker 挂载对应私有备份目录并授予删除权限，不能只填写主机路径。默认不挂载备份，也不启用自动目录清理；可以先用下面的运维 CLI 在备份所在主机预览和清理。

```sh
# 在 backend/ 执行；先预览，--apply 才物理删除指定目录里的到期备份
python -m app.modules.account.admin prune-backups --directory /srv/niannian/backups
python -m app.modules.account.admin prune-backups --directory /srv/niannian/backups --apply
python -m app.modules.account.admin pending
# 核实全部备份/供应商副本后，用真实报告/工单文件的摘要确认对应范围
python -m app.modules.account.admin confirm-copy <deletion-id> backup --operator <operator-ref> --evidence-file <verified-report>
python -m app.modules.account.admin confirm-copy <deletion-id> provider --provider <exact-provider-from-pending> --operator <operator-ref> --evidence-file <verified-report>
```

确认命令只能在有数据库访问权限的运维环境执行，无公网管理员绕过接口。应核查服务账号、发送时间范围、供应商备份/日志及合同留存；没有完成凭据时保持待处理。升级前的 LEGACY_UNVERIFIED 必须核查历史供应商，而不是直接按当前 Mock 设置确认；若核实从未外发，也需对应库存/配置核验记录。设备系统语音服务无法核实时保留待处理。命令只保存操作人引用与证据的摘要，不保存报告中的个人正文。备份清理成功、期限到期、供应商受理工单、单条 API 记录消失均不能替代全范围核验。

MinIO/S3 服务身份另需对象版本枚举和删除权限；账号文件清理失败会重试，回执保持未完成。云快照、异地复制和非管理目录备份必须另行配置相同或更短期限并核验。恢复旧备份前须停止 API/worker 外部访问，保存并比对当前删除记录，在恢复库重新执行已删除账户的清理和文件删除，再合并现有回执/供应商核验记录，确认已删除账户仍不可登录后才能开放；当前未提供自动跨备份重放工具，不能直接把旧快照当作可上线恢复结果。完整边界仅在 [security](security.md#账户级生命周期) 维护。

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

## THA3 自定义陪伴形象

手机流程为“选择照片 → 查看处理服务并授权 → 千问/豆包生成动漫立绘 → 服务端抠图、定位脸部并整理尺寸 → GPU THA3 → 下载四态预览 → 确认启用”。默认关闭，未配置时继续使用默认柿子或离线导入；只有 `APP_ENV=dev` 启用真实图像调用。生成模块由同一后端运行，API 不加载 PyTorch；GPU 依赖安装到独立环境。已使用 [THA3 官方项目](https://github.com/pkhungurn/talking-head-anime-3-demo)提交 `8946939ec7b417f443d7b0e3fcd97384313fcdb8`、Python 3.12、PyTorch 2.9.1+cu128 和 RTX 5060 Laptop 完成真实推理，源码和权重放在忽略提交的 `artifacts/` 中。

Windows 从项目根目录准备独立环境（其他显卡应选择匹配的 PyTorch 构建）：

```powershell
git clone https://github.com/pkhungurn/talking-head-anime-3-demo.git artifacts/tha3-runtime/upstream
git -C artifacts/tha3-runtime/upstream checkout 8946939ec7b417f443d7b0e3fcd97384313fcdb8
.\.venv\Scripts\python.exe -m venv --without-pip artifacts/tha3-runtime/venv
.\.venv\Scripts\python.exe -m pip --python artifacts/tha3-runtime/venv/Scripts/python.exe install torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip --python artifacts/tha3-runtime/venv/Scripts/python.exe install numpy Pillow scipy matplotlib 'rembg[cpu]==2.0.86' 'opencv-python-headless>=4.12,<5'
```

从[上游官方模型链接](https://www.dropbox.com/s/y7b8jl4n2euv8xe/talking-head-anime-3-models.zip?dl=1)下载压缩包，将其中 `separable_float/` 的 `eyebrow_decomposer.pt`、`eyebrow_morphing_combiner.pt`、`face_morpher.pt`、`two_algo_face_body_rotator.pt`、`editor.pt` 放到 `artifacts/tha3-runtime/models/separable_float/`。仅使用可信权重。

照片预处理另需 [lbpcascade_animeface](https://github.com/nagadomi/lbpcascade_animeface) 的 MIT XML 模型和 [rembg](https://github.com/danielgatis/rembg) 的 u2netp。安装时下载，实际任务不自动下载模型；OpenCV 5 已移除 CascadeClassifier，本实现使用 4.x。项目根目录执行：

```powershell
New-Item -ItemType Directory -Force artifacts/tha3-runtime/preprocess
Invoke-WebRequest https://raw.githubusercontent.com/nagadomi/lbpcascade_animeface/master/lbpcascade_animeface.xml -OutFile artifacts/tha3-runtime/preprocess/lbpcascade_animeface.xml
$env:U2NET_HOME = (Resolve-Path artifacts/tha3-runtime/preprocess).Path
.\artifacts\tha3-runtime\venv\Scripts\python.exe -c "from rembg import new_session; new_session('u2netp', providers=['CPUExecutionProvider'])"
```

根 `.env` 中配置服务和模型，密钥只放服务端。以下两个供应商选择其一，地址须与密钥地域一致；千问也可使用控制台的业务空间专属 HTTPS 域名，并保留 `/api/v1` 后缀。模型须已为当前账户开通，参见[千问图像编辑参数](https://help.aliyun.com/zh/model-studio/qwen-image-edit-api)及[豆包图像接口](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)。

```dotenv
AVATAR_GENERATION_ENABLED=true
AVATAR_IMAGE_PROVIDER=doubao
AVATAR_IMAGE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
AVATAR_IMAGE_MODEL=doubao-seedream-5-0-pro-260628
AVATAR_IMAGE_API_KEY=替换为本机密钥
# 千问替代配置：
# AVATAR_IMAGE_PROVIDER=qwen
# AVATAR_IMAGE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
# AVATAR_IMAGE_MODEL=qwen-image-2.0-pro
AVATAR_IMAGE_TIMEOUT=300
AVATAR_RENDER_TIMEOUT=300
```

当前选用 `doubao-seedream-5-0-pro-260628`，调用 `/images/generations`，上传照片为 Base64 Data URI，固定请求正方形 `2048x2048`、PNG、`response_format=b64_json`，后续仍由服务端抠图和整理到 THA3 布局。参数见 [Seedream 5.0 pro 官方说明](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)。本地未填密钥时保持 `AVATAR_GENERATION_ENABLED=false`；填入方舟 API Key 后改为 true，并重启 API 和两个 worker。不要复用聊天 LLM 的密钥，也不要把密钥发到聊天中。

2026-10-27 已用[公开 Grace Hopper 肖像](https://commons.wikimedia.org/wiki/File:Grace_Hopper.jpg)完成一次真实豆包图生图（约 85 秒），再抠图并以 GPU THA3 生成四态包；原图为 James S. Davis 摄、美国海军公开作品，结果为 AI 改编测试素材，不随 APK 分发。写实老人动漫脸使用 OpenCV 自带正面检测作为动漫检测未命中时的回退，不额外下载模型；仍拒绝多人或无脸图片。Android 真机上传、选择器返回和确认启用尚待联测。

API 和两个 worker 使用相同数据库、私有存储、签名密钥和图像配置。还需将 `.env.example` 中五个路径项设为 GPU 主机的绝对路径，分别指向 `venv/Scripts/python.exe`、`upstream/`、`models/separable_float/`、`preprocess/lbpcascade_animeface.xml`、`preprocess/`。u2netp 支持位于该目录下的 `u2netp.onnx` 或 `models/u2netp/u2netp.onnx`。保存后重启 API/worker，并执行迁移。

```powershell
# 已激活后端环境；从 backend/ 运行两个独立终端，均设置 APP_ENV=dev
python -m app.worker.main --serve          # 普通任务与文件清理
python -m app.worker.main --avatar --serve # 单 GPU 顺序处理照片任务
```

GPU worker 使用同一份后端源码与业务规则，通过配置的独立 Python 执行抠图和推理。Linux 可在 GPU 主机安装同一环境，将 Python 路径改为 `venv/bin/python`；现有普通 API/worker 容器不含 CUDA，不能直接充当 GPU worker。没有运行 `--avatar` 时制作任务保持等待。生成请求不自动重试，处理失败后由本人取消并重选；未确认任务 24 小时到期。服务端清理和外部副本边界见 [安全说明](security.md#tha3-本机形象)。

准备一张 512×512 的透明背景 RGBA PNG 动漫立绘；角色正面直立，头部按上游规范位于图片上半部中央的 128×128 区域，手不要遮挡脸部。脚本检查尺寸与透明背景，但不能自动判断立绘布局或人物还原质量。使用自己的立绘生成新角色包：

```powershell
.\artifacts\tha3-runtime\venv\Scripts\python.exe scripts/build_tha3_avatar.py `
  --tha3-root artifacts/tha3-runtime/upstream `
  --model-dir artifacts/tha3-runtime/models/separable_float `
  --image artifacts/my-character.png `
  --output artifacts/my-avatar.zip `
  --art-credit "立绘作者、来源和使用许可" `
  --preview artifacts/my-avatar-preview.png
```

默认使用 CUDA，可显式指定 `--device cpu`（速度较慢）。已有 ZIP 不会被覆盖；推理失败删除本次未完成的输出。预览从左到右为待机、倾听、思考、说话。资源包保留模型及立绘归属说明，格式为 `niannian-tha3-v1`；限四种状态、固定 256 像素图块/4 列、每种最多 16 帧，压缩包和解压读取总量均不超过 24MiB。

老人端：聊天页下方“陪伴形象 → 选择照片制作形象”，选择清晰单人照片，查看处理服务和照片后点击“同意并开始制作”。代码会检查或申请本人 PORTRAIT 授权，再上传；选择器会暂停当前聊天，回来后可重新进入查看进度。完成后切换待机、倾听、思考、说话四态检查，点击“确认并启用这个形象”才替换聊天/首页形象。切后台或断网清除照片与未确认预览，回前台查询进度，不重发生成请求。可取消任务并删除服务端资源。

离线 ZIP 导入仍在同一面板，须先在“家庭与授权设置 → 用于我与念念的交流”允许“数字人形象”。“删除本机形象并恢复默认”仅删除手机副本，服务端资源使用任务取消按钮删除。授权与本机副本处理见 [安全说明](security.md#tha3-本机形象)。

THA3 代码为 MIT，模型权重为 CC BY 4.0；上游示例角色有各自许可，其中 Lambda 角色为 CC BY-NC 4.0。本地验证用 Lambda，示例包仅作非商业评估，不随 APK 分发；正式部署换用有权使用的立绘，并填写对应的归属及许可。详情见[上游素材说明](https://github.com/pkhungurn/talking-head-anime-3-demo/blob/main/data/images/README.md)。真实模型已生成角色包，Android 文件选择器、Keystore 及完整语音交互仍需指定真机验证。

## Android

老人端点击首页柿子形象可进入真实会话并请求说话；也可在聊天页点击形象。界面显示“念念 AI 陪伴”和待机/听您说话/思考中/正在回答，只有系统 TTS 开始播放才动嘴，停止按钮始终可见。没有连接设备时，单测和 APK 构建不能替代真机收音、播音和打断验证。

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

双端首页“选择城市”接入 [Open-Meteo 城市搜索](https://open-meteo.com/en/docs/geocoding-api)与[天气接口](https://open-meteo.com/en/docs)，需设备可访问 `geocoding-api.open-meteo.com`、`api.open-meteo.com` 的 HTTPS。首次无默认城市；手动选择按本机账户/家庭/长辈分别保存，可清除，不表示长辈实时位置。页面显示城市、摄氏温度、天气、数据时间和来源，前台每 15 分钟刷新，可手动重试；退后台隐藏天气，恢复前台重新获取，超过 3 小时的数据不展示。使用公共非商业接口，商用部署需按服务方条款配置。

首页动态与留言页共用真实文字消息；“看到啦”提交已读回执，收到消息不自动算已读。照片通过“分享照片到家庭记忆”进入已有上传/授权流程。原声留言和视频通话仍无服务端能力：界面明确标注未接入，不模拟播放、拨通或家人回话。

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

升级前从 `backend/` 执行 `python -m alembic upgrade head`，再重启 API，迁移头为 `20261024_interaction_stats`。Android 双端登录并选择已确认加入的家庭后，留言卡片自动注册设备，在前台每 3 秒同步；进入后台停止轮询并清空已加载留言，返回前台重新补拉。Windows 的设备能力检测用于提示旧版后端缺少接口。

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


## 天气与周报启用

升级时在 `backend/` 执行 `python -m alembic upgrade head` 并重启 API/worker；新表仅在独立测试库验证，部署数据库仍需执行迁移。天气后端使用 [Open-Meteo 城市目录](https://open-meteo.com/en/docs/geocoding-api)和[天气服务](https://open-meteo.com/en/docs)，无需密钥，服务主机须能访问两个供应商 HTTPS 域名。Windows 双端“天气与周报”中搜索并手动选择城市，失败或超过三小时的数据不展示。Android 现有天气入口不变。公共接口的非商业使用要求仍适用。

统计默认关闭。在 Android 老人端“家庭设置”开启本人“互动统计与周报”，如需家属阅读，再单独向家庭创建者授予同项授权；非创建者还需要 REPORT_READ。实际文字或设备语音转写完成后积累记录，开启前历史不会补录。家属首页“统计周报”选择长辈、星期一及查看理由，老人端设置区可打开“我的周报”并删除本人记录；Windows 先选择家庭，再读取长辈列表、选择周和理由后生成。

报告无需定时任务或外部 LLM，查询时生成；现有 worker 负责到期清理。空报告会说明原因；提醒/关注提示还需各自授权。限定主题分类与统计口径见 [ai](ai.md)，不以空记录推断健康状态。真实设备上的周报布局与完整操作仍需真机验证。
