# 测试

后端单元测试在 `backend/tests/unit`，数据库/API/worker 测试在 `backend/tests/integration`；`tests/security` 检查脱敏与源文件隐私，Windows 测试在 `windows/tests`，Android 测试在 `android/shared/src/test`。

使用 `python scripts/verify.py test <测试路径>` 或 `windows`、`android <Gradle任务>` 选择关联范围。登录鉴权、家庭隔离、撤权、照片访问、提醒幂等和通知租约/重试检查继续保留。

集成测试统一使用 `TEST_DATABASE_URL`：显式配置 PostgreSQL/psycopg、数据库名以 `_test` 结尾、不带连接查询参数。测试会清空该库；先在该测试库执行 `alembic upgrade head`，再运行：

```powershell
python scripts/verify.py integration backend/tests/integration/test_auth_family_consent.py
python scripts/verify.py integration backend/tests/integration/test_photos.py
python scripts/verify.py integration backend/tests/integration/test_notifications.py
```

照片测试默认使用明确标记的 Mock 对象存储。真实 MinIO 检查 `test_photo_storage.py` 另需 `TEST_STORAGE_CONFIG` 指向本地 JSON：`endpoint` 为 `http://127.0.0.1:59003`，`bucket` 为独立的 `niannian-test`，以及测试专用 `access_key`、`secret_key`。凭据文件不得提交；没有这些依赖时真实存储检查会跳过，不能视为通过。

APK 隐私检查按需执行：构建两个 Demo Debug APK 后设置 `NIANNIAN_REQUIRE_APKS=1`，运行 `python -m unittest discover -s tests/security -p test_artifact_scan.py`。不要求全部变体，不在每次 Python 测试中扫描旧 APK 或整个 Git 历史。
