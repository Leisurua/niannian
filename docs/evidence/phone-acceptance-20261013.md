# 念念手机验收阶段报告 — 2026-10-13

**整体状态：PAUSED / INCOMPLETE。** 用户要求暂时中止测试，现有结果已保留。本报告只覆盖本次实际执行的前三周软件场景，不代表完整设备、隐私或发布门禁通过。

结构化脱敏证据见 [evidence.json](phone-acceptance-20261013/evidence.json)。结果来源区分为：ADB/界面观察、操作人手动确认、只读数据库核对、独立 API 检查。操作人确认不替代尚未取得的独立证据。

## Task

在一台真实 Android 手机上安装第三周长辈端和家人端 Demo App，准备隔离后端，并检查登录、家庭绑定、家庭记忆授权、候选确认、照片和删除等已实现流程。用户手动操作手机，Codex 准备环境、观察并核对结果。

| 项目 | 本次范围 |
| --- | --- |
| 日期与时间 | 2026-10-13，Asia/Shanghai；成功设备基线约 16:30，最后删除校核约 17:57，随后按用户要求暂停 |
| 测试源码 | `a1948c2702d3117e0185abb6cf47a736d59698f1`；[第三周 PR #5](https://github.com/Leisurua/niannian/pull/5) 对应测试快照 |
| APK 来源 | [GitHub Actions run 38334535070](https://github.com/Leisurua/niannian/actions/runs/38334535070)，两个 `demoDebug` APK |
| 设备 | USB 名称 Xiaomi 15；ADB 型号 `24129PN74C`；SKU `dada` |
| 系统 | Android 16 / API 36；安全补丁 2026-08-01 |
| 数据 | 仅虚构 DEMO 身份、`DEMO-phone-20261013` 家庭及程序生成的测试 PNG |
| 环境 | Python 3.12.10、锁定的后端依赖、独立 PostgreSQL 17.11、私有 MinIO、API/worker；第三周现有迁移和 13 张业务表 |

## Changed

- 安装并核对两份 APK；手机上的文件 SHA-256 与本机下载的 CI 产物一致。
- 本次环境位于本聊天测试目录，API/存储只监听 loopback，通过 USB 映射供 Demo App 使用。
- 生成并上传一张无个人内容的 DEMO PNG；通过鉴权下载验证返回像素与该测试图一致。
- 保留设备基线、各阶段状态、API 访问结果、安装结果和日志检查记录。
- 按用户暂停指令停止本次 API、worker、MinIO、独立 PostgreSQL 和 ADB 会话。手机 App、测试数据库、测试文件及本地证据保留。
- 仓库变更仅为本报告及脱敏证据；应用代码、依赖、迁移及合同未修改。

## Tests

| ID | 检查 | 结论 | 实际证据与边界 |
| --- | --- | --- | --- |
| PHONE-01 | ENV-001 设备基线 | PASS | ADB 实读型号、SKU、Android/API/补丁；仅清单，不等同硬件通过 |
| PHONE-02 | ENV-002 双端安装与构建身份 | PASS | 两个 App 已安装、可启动，已安装 APK 哈希与 CI 下载包一致 |
| PHONE-03 | Demo / Mock 标识 | PASS | 曾实际读取两端 Demo 界面标识；不宣称真实 AI、发送或通话 |
| PHONE-04 | 隔离服务准备 | PASS | Demo health、登录、`/me`、退出及私有对象/bucket 匿名 403 均实际执行；属于本机服务检查 |
| PHONE-05 | 双端登录与家庭绑定 | PASS | 操作人完成；界面观察和数据库核对 CHILD/ELDER 均 ACTIVE |
| PHONE-06 | 加入不自动开启授权 | PASS | 绑定完成时当前虚构家庭 Consent 记录为 0 |
| PHONE-07 | 单项 FAMILY_MEMORY 授权 | PASS | 操作人确认授予；后台仅有该 scope 的授权记录 |
| PHONE-08 | 待确认候选创建 | PASS | 记录实际处于 PENDING，未记录人工确认；这是状态创建验证 |
| PHONE-09 | PENDING 在长辈已确认列表中的完整展示隔离 | NOT VERIFIED | 操作人报告不可见，但同名已确认记录及当前可见区域使独立 UI 证据不足；不据此关闭完整 RAG/展示负例门禁 |
| PHONE-10 | 人工确认 | PASS | 操作人执行；相应记录从 PENDING 变为 CONFIRMED，版本增加且存在人工确认记录 |
| PHONE-11 | 测试照片上传、选择及显示 | PASS（本次路径） | 操作人报告双端显示；FileAsset 为 AVAILABLE；虚构家人/长辈鉴权下载均为 200，像素与 DEMO 图一致。取消选择、异常 MIME/大小等未测 |
| PHONE-12 | 原照片记忆编辑后重新确认 | NOT VERIFIED | 照片关联的原记忆未出现预期编辑版本变化；新增/编辑的是其他候选。该操作没有被记成原记忆编辑通过 |
| PHONE-13 | FAMILY_MEMORY 撤回 | PASS | 正确从“我的授权”撤回后新增不可变 REVOKED 历史；家人获取照片链接 404，长辈自身读取 200；两个身份的独立请求均实际执行 |
| PHONE-14 | 记忆删除立即不可读 | PASS | 操作人删除带照片记录并确认界面不可见；记忆 DELETED，家人和长辈照片链接请求均为 404 |
| PHONE-15 | 后台文件清理 | PASS（状态记录）；物理对象独立复核 NOT VERIFIED | worker 已将关联 FileAsset 标为 DELETED；暂停前未额外用 S3 HEAD 独立证明原对象及安全副本均不存在 |
| PHONE-16 | 本次生成凭证的服务日志检查 | PASS（限定范围） | 六份本机服务日志对本次生成的数据库密码、签名密钥和存储凭证均为 0 命中；不代表完整 PRIV-002、Logcat 或系统/OEM 崩溃日志验收 |
| PHONE-17 | 断网/服务中断与恢复 | NOT_RUN | 用户暂停前未执行；暂停服务本身不被当作 App 的网络恢复验收 |
| PHONE-18 | 强制停止、冷启动与状态恢复 | NOT_RUN | 未执行对应完整手机场景 |
| PHONE-19 | 手机退出、Keystore 加密与本地擦除 | NOT VERIFIED | 本机 API 退出已测；手机退出/存储擦除和 Keystore 的完整设备验收尚未完成 |

### APK SHA-256

| App | SHA-256 |
| --- | --- |
| 长辈端 | `346c1be20311ccdc7fb28fbe3fe5b35029241b189e04d04369b5765975a4bf0a` |
| 家人端 | `fba0b7155d52ce831fe7c84ca60bcc7e330b23d1b8580bb5fdf1c2ce571e1a59` |

## Decisions

- 小米手机的 USB 安装受系统策略阻止：长辈端通过 ADB 安装，家人端最终由操作人从手机 Download 手动安装，再以文件哈希核对。
- 安全调试标志已开启，但自动点击仍被系统拒绝（`INJECT_EVENTS`）；用户选择暂不重启，改为手动操作。
- 区分“撤回这条记忆”和“我的授权 → 撤回家庭记忆”。第一次尝试只撤回了记忆，家人照片读取仍为 200；此中间结果保留，未伪装成授权撤回通过。正确撤回后的 404 结果单独记录。
- 区分“保存为新的待确认候选”和“保存编辑（需重新确认）”。未命中原照片记忆的编辑场景保留为 NOT VERIFIED。
- 停止后不继续补验未执行项；恢复测试需用户另行提出。

## Contract Changes

None。没有修改 Requirements、OpenAPI/WSS、公共状态/枚举、DB schema/迁移、Consent scope、家庭边界或 Security Boundary。

## Not Verified

- PHONE-09 的完整 UI 负例、PHONE-12 原照片记忆编辑、照片选择取消/异常输入、物理对象删除的独立 HEAD 检查。
- 手机网络恢复、进程/生命周期恢复、手机退出擦除与 Keystore 完整验收。
- kiosk/Device Owner、10 次重启、BLE、摄像头 Presence、离线唤醒、音频唯一所有者、SIM/Telecom、真实通话及性能/温度/电量门禁。
- 完整 RAG、Android 离线提醒、真实 AI/provider、通知送达，以及跨缓存/向量/导出/通知的完整删除传播。
- 本次没有重跑全量后端、Android 构建/JVM/lint、AI/security/device 套件，也没有取得这些套件针对本报告提交的新运行结果。

## Issues

1. 存在两个同名虚构家庭、多条同名或额外候选，保留原数据；本次按含 ACTIVE 长辈的家庭及照片关联记录定位证据。
2. 新建/编辑、记忆撤回/授权撤回入口在手动操作中发生混淆；已核对并纠正授权场景。编辑场景未被误记通过。这是本次观察，不直接认定为应用缺陷。
3. Windows 中文路径造成 PostgreSQL 初始化编码错误；运行文件与数据库改放到本聊天允许写入的英文路径后，现有迁移成功。该环境处理未改变业务代码。
4. 自动输入限制仍存在；没有尝试绕过、重置手机或开展未经执行的硬件测试。

## Next

仅记录续测顺序，不在本次执行：恢复隔离 Demo 环境并核对同一 APK/测试快照；重新定位原照片记忆编辑场景；补 UI 负例、异常照片选择、物理删除、网络/生命周期、退出/Keystore。硬件和后续周功能按对应实现与指定设备条件另行验收。

原始本地证据与临时凭证仍在忽略的测试目录中。公开版本仅包含本报告与脱敏 JSON，不包含 APK、数据库、照片、原始日志、验证码/邀请码、认证令牌、签名下载 URL、手机序列号或临时配置。
