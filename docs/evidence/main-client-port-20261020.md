# Windows 客户端优化移植到 main

## Task

按用户选择，保留 main 的最新功能，仅移植 PR #15 的客户端和基础设施修复；以 main 为目标创建独立 PR。

## Changed

- 两端消息列表跟随服务端游标加载后续页面，对非法或不递增的游标明确报错。
- 两端保存并取消旧的自动刷新定时器，避免开关或重新注册设备后累积刷新任务。
- 在 Tk UI 线程读取地址和优先级，后台任务使用已读取的普通值。
- MinIO 冒烟验证在传给 POSIX shell 之前规范上传、清理脚本的换行；增加 LF/CRLF 回归。
- 增加 Windows 客户端回归 CI，保留 main 已有的 Linux/Windows 兼容性 CI。

## Tests

- 客户端、CI 工具、S3 兼容性及 PowerShell 换行相关测试：**57 passed**。
- Ruff：PASS。`git diff --check`：PASS。
- main 整合副本全量 Python 回归：**437 passed / 122 skipped**；跳过包含未配置的数据库/存储与未构建 APK 的检查，不能作为通过。
- 新 PR 的 GitHub 检查结果以实际执行报告为准，不复用 MixedProgress1 分支的通过状态。

## Decisions

整合基线为 `547f34f`，已经包含 main 的第七周功能和 Linux/Windows 兼容性修复。原先直接比较 MixedProgress1 与 main 有 17 个冲突文件；本次从 main 新建分支，只移植所需修复。

保留 main 的 `backend_features`、`_check_optional_api` 和联机自检能力检查。服务端没有提供消息 API 时，客户端继续明确提示不可用，分页修复不代表服务端消息功能已实现。

main 已有第二周 CI 的测试范围修复，本次保留其脚本和工作流。没有导入 MixedProgress1 的旧后端、旧文档或额外测试数据库配置。

## Contract Changes

None。后端、Android、OpenAPI、数据库迁移、授权和家庭边界均保持 main 基线。

## Not Verified

本地没有执行真实 PostgreSQL/MinIO 或 Android 构建，这些检查由新提交的 CI 单独验证。PowerShell 单元测试明确使用 Docker/HTTP 替身；GUI、真实设备及业务投递仍未验收。

## Issues

本次保留 main 的功能缺口提示，没有补实现缺失的消息服务，也没有改变既有合同。

## Next

审阅面向 main 的新 PR。合并操作不自动执行。
