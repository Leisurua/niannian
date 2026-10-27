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
