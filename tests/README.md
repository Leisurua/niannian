# 测试

后端单元测试在 `backend/tests/unit`，数据库/API/worker 测试在 `backend/tests/integration`；`tests/security` 检查脱敏与源文件隐私，Windows 测试在 `windows/tests`，Android 测试在 `android/shared/src/test`。

使用 `python scripts/verify.py test <测试路径>` 或 `windows`、`android <Gradle任务>` 选择关联范围。登录鉴权、家庭隔离、撤权、照片访问、提醒幂等和通知租约/重试检查继续保留。

集成测试统一使用 `TEST_DATABASE_URL`：显式配置 PostgreSQL/psycopg、数据库名以 `_test` 结尾、不带连接查询参数。测试会清空该库；先在该测试库执行 `alembic upgrade head`，再运行：

```powershell
python scripts/verify.py integration backend/tests/integration/test_auth_family_consent.py
python scripts/verify.py integration backend/tests/integration/test_photos.py
python scripts/verify.py integration backend/tests/integration/test_notifications.py
python scripts/verify.py integration backend/tests/integration/test_messages.py
```

照片测试默认使用明确标记的 Mock 对象存储。真实 MinIO 检查 `test_photo_storage.py` 另需 `TEST_STORAGE_CONFIG` 指向本地 JSON：`endpoint` 为 `http://127.0.0.1:59003`，`bucket` 为独立的 `niannian-test`，以及测试专用 `access_key`、`secret_key`。凭据文件不得提交；没有这些依赖时真实存储检查会跳过，不能视为通过。

真实语义检索检查 `test_semantic_memory.py` 另需 `TEST_EMBEDDING_MODEL_PATH` 指向已下载的 BGE 模型目录；模型准备见 [部署说明](../docs/deployment.md#本地家庭记忆语义检索)。该测试使用实际 CPU 推理和 pgvector，检查医院陪同同义问法、无匹配、Mock/旧模型索引补建、推理中撤权及家庭隔离。未提供模型时明确跳过，不用 Mock 向量代替通过结果。

APK 隐私检查按需执行：构建两个 Demo Debug APK 后设置 `NIANNIAN_REQUIRE_APKS=1`，运行 `python -m unittest discover -s tests/security -p test_artifact_scan.py`。不要求全部变体，不在每次 Python 测试中扫描旧 APK 或整个 Git 历史。

## Android 核心业务实机验证（2026-10-20）

使用 Android 12 / MIUI 真机、老人端与家属端独立 Demo Debug 测试包，连接本地 API、worker、PostgreSQL 和真实 MinIO；账户、记忆及图片均为虚构测试数据，原有应用与数据保留。

- 登录与家庭：双端 Demo 登录、家属创建家庭、生成长辈邀请、长辈核对并确认加入；加入家庭不会自动开启数据授权。
- 提醒闭环：家属端创建一次性喝水提醒，长辈端读取并反馈完成，家属端查看反馈；三条测试提醒最终各只有一条已完成执行记录，重复同步未产生重复记录。
- 离线与重启：移除 USB API 转发模拟断网，长辈端保存完成反馈；结束进程并在断网状态重启后记录仍在，恢复转发后成功同步到服务端。
- 本机通知：测试应用后台运行被系统禁止时，闹钟进入阻止队列；经用户授权放行该独立测试包后，在家属端前台、长辈端后台时观察到真实提醒通知，点击可进入长辈端并完成反馈。
- 家庭记忆：通过 API 预置待确认候选，家属端在获得授权后读取、人工确认并从已确认列表打开；候选不会自动进入默认事实列表。
- 私有照片：合成图片经真实 MinIO 上传、确认及鉴权下载；家属端系统文件选择器上传和照片显示通过。
- 授权与隔离：以测试长辈身份通过 API 授予、撤回家庭记忆授权；未授权家属及非家庭成员读取记忆、申请照片下载均返回 404；撤回后旧照片链接失效，家属端刷新清除已加载内容。

实机发现并修复 Android 12 对带 `+00:00` 时间戳的解析兼容问题，恢复提醒缓存更新及完成反馈同步；本机提醒改为按实际待提醒时间与缓存到期时间调度，避免每分钟后台轮询。共享模块 87 项单元测试通过，双端 Demo Debug 构建成功。

本轮未验证真实 LLM/ASR/TTS、真实语音或跨 Android 版本兼容；当前对话仍为 Mock。后台通知依赖系统权限和非精确闹钟，不保证准点送达；运行要求见 [部署说明](../docs/deployment.md#android)。截图、设备标识、本机配置、令牌和调试日志不随本次提交上传。

## 主线与压缩包整合验证（2026-11-01）

远端主线基线为 `2fe77d0`，上一周对比基线为 `8041bf9`。收到的压缩包最接近 `2dd17f7`，本次仅整合主动求助及 Linux TLS 增量，保留后续主线的家人音色、语义关注和后台通知实现；旧 Gradle 锁、本机 SDK 路径和缓存不合并。代码在独立集成分支验证，原工作区未提交修改保留。

- 压缩包：Python/Windows/源码检查 414 项通过、1 项按配置跳过；数据库集成 168 项通过、6 项跳过；Android 共享模块 133 项通过，双端 Demo Debug 构建成功。
- 集成版本：Python/Windows/源码检查 492 项通过、1 项按配置跳过；数据库集成 194 项通过、7 项跳过。修复无会话来源的主动求助被定期清理后，通知集成专项 60 项重新通过，包含并发幂等、家属处理、无授权接收人及维护后事件保留。迁移头为 `20261101_elder_help_requests`。
- Android 共享模块 151 项通过，双端独立测试包构建成功；显式开启 APK 检查后 6 项隐私扫描通过。静态检查、TLS Compose 合并配置及 Linux 脚本语法检查通过；未做真实 Linux TLS 上线验收。
- 集成跳过项为本地 BGE 模型与真实 MinIO 检查；模型和存储服务未配置，不能视为真实模型/存储验证通过。APK 的默认跳过项已通过单独显式扫描补测。
- Android 12 / MIUI 真机：用户开启 USB 安装后，双端独立包安装成功。通过 USB 连接隔离 Mock 后端及虚构家庭，实际完成老人按钮求助 → 家属应用内读取 → 确认关注 → 人工标记解决 → 老人查看解决状态及处理历史；强行停止并重开老人端后家庭连接恢复，数据库对应按钮事件仅一条。测试家庭关系和授权由 API 预置，不重复宣称本轮完成建家 UI 验收。
- 撤回虚构测试授权后，老人再次求助显示无授权接收人和改用电话/当面联系提示；家属端重新进入后旧事件清空。修复真机发现的失败状态误显示“待确认关注”问题，重新构建安装后显示“通知未成功，请另行联系”。原有应用与数据保留。
- 本轮验证为 USB 联机、应用内通知及人工处理状态，不含锁屏后台送达、真实 LLM/ASR/TTS、家人音色供应商或电话接通验收，也不代表两台独立设备或 Wi-Fi 联机通过。

相较上一周的功能进展与剩余边界集中见 [路线图](../docs/roadmap.md#相比上一周的进度2026-11-01)。

## 在线主动陪伴增量（2026-11-01）

主动邀请已脱离 Mock 模式限制，Android/Windows 静默展示三种明确操作；接受后复用当前模型和已有语音设置，拒绝不调用模型，暂停写入现有当日设置。生产仍采用至少 30 分钟间隔和每日最多 3 次；邀请限当前聊天连接、5 分钟及单次响应，不支持后台唤醒或自动收音，无数据库迁移。

Python/Windows 与源码检查 496 项通过、1 项按配置跳过，Windows 专项 40 项通过；主动邀请、会话、取消及家人音色相关集成 39 项通过，最终六类邀请响应（含新增五分钟到期场景）专项重新通过，覆盖未接受不调用模型、过期/重复/设置改版拒绝及暂停。Android 共享模块 152 项通过，双端构建及 6 项 APK 隐私检查通过。修复 Android 12 对 API `+00:00` 到期时间的兼容解析。

真机使用隔离虚构家庭及 Mock 后端；仅测试进程临时将空闲间隔缩为 20 秒以触发邀请，产品规则未修改。已验证邀请静默展示与接受后普通回复、拒绝后关闭邀请，以及“今天少打扰我”持久化当天暂停；验证后恢复测试服务的正常 30 分钟间隔。真实供应商连续语音及 Windows 实际界面操作仍待分别验证。
