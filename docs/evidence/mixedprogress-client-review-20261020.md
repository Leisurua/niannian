# MixedProgress1 客户端审查与修复

## Task

审查下载目录中的代码，修复可复现的问题，并向用户指定的 `MixedProgress1` 分支提交优化 PR。本次修改集中在两套 Windows 客户端及其测试。

## Changed

| 问题 | 修复 | 回归证据 |
| --- | --- | --- |
| 两端消息列表只请求第一页，超过 100 条后新消息不可见 | 根据服务端 `page.next_cursor` 继续请求，合并所有页面；游标缺失、非法或不递增时明确报错 | INBOX/OUTBOX 多页、非法游标、重复游标测试 |
| 自动刷新关闭后仍遗留定时器，快速重新开启或再次注册老人设备会累积刷新链 | 保存并取消待执行的 `after`，设备注册复用同一刷新入口 | 两端启停、忙碌时调度测试 |
| 登录、连接检查、自检和发送任务从后台读取 Tk 变量 | 在启动任务前读取服务器地址或优先级，由闭包传入普通值 | 在模拟后台执行时禁止读取界面变量的测试 |

新增独立 Windows CI，执行两端 HTTP 客户端测试和本次回归测试，无需打开 GUI。

## Tests

- 新增回归中的前 23 项在修复前全部失败、修复后全部通过。
- 最新客户端测试：`python -m pytest -q --import-mode=importlib windows/family-client/tests windows/elder-demo/tests tests/unit/test_windows_client_reliability.py`，**35 passed**。
- PR 副本完整 Python 回归退出码为 0，进度记录为 **400 passed / 89 skipped**。该次包含最初 23 项新增测试；随后补充的 3 项由上述最新客户端测试覆盖。
- 下载目录的隔离副本应用同样修复后，完整回归为 **300 passed / 47 skipped / 1 failed**。失败是演示种子与现有数据字典不一致，详见 Issues。
- `python -m ruff check . --no-cache`：PASS。
- `git diff --check`：PASS。

## Decisions

两套 Windows 客户端在下载目录和远端基线 `9d8245fb30f9a3044d9065b1d5bccee98a0773e9` 中内容一致，已逐文件比较并忽略换行符差异。PR 从该远端基线创建，只包含此次修复。

保留两端独立打包结构；没有为少量重复分页代码引入跨应用依赖。每次刷新仍从起点读取，避免漏掉已有消息的回执更新；本次没有承诺大规模历史消息场景的性能。

## Contract Changes

None。没有修改 OpenAPI/WSS、数据库、枚举、授权或家庭边界。

## Not Verified

89 项跳过包含未提供一次性 PostgreSQL/MinIO 环境和未构建 APK 的检查，均为 NOT VERIFIED。真机、真实消息投递、GUI 人工验收和 GitHub CI 的执行结果也不能由本地单元测试代替。

## Issues

- 下载目录与远端同名分支并非同一代码快照：下载目录包含 `messaging`、`proactive_companion` 及 ADR-015/016，而远端基线具有另一套后端进度。没有把两套后端和合同文档相互覆盖。
- 用户提供的规则只认可 ADR-001 至 ADR-007；下载目录中的 ADR-015/016 标记为 Accepted。该依据冲突需要项目负责人统一，本次没有修改相关后端实现或将其认定为已批准架构。
- 下载目录的 `tests/demo/test_demo_seed.py::test_rows_match_frozen_dictionary_columns_required_fields_and_enums` 失败：`device_binding` 种子没有数据字典要求的 `family_id`、`client_kind`。这些源文件没有被本次客户端修复修改；不能声称下载目录全量测试通过。由于涉及上述合同依据冲突，暂不改变种子或合同。
- 首次测试遇到沙箱回环网络限制与系统临时目录权限问题；使用允许本机 HTTP 的执行环境和独立 `--basetemp` 后完成回归。环境错误没有通过删测或放宽断言处理。

## Next

统一下载目录与远端的后端基线及 ADR 授权记录，再单独验收消息闭环、数据库和设备。本次不执行这些后续任务。
