# 照片选择与上传异常路径真机验收 — 2026-10-14

## Task

状态：**FAIL**。按取消选择、超过 5 MiB、不支持格式、损坏图片、有效图片恢复的顺序实际执行。取消与原测试记忆完整性通过；选择文件后未显示错误或启动上传，有效图片也未上传成功。第三周整体验收仍为 **INCOMPLETE**。

后续：同日修复后复验 **PASS**，见 [照片选择修复后真机复验](photo-retest-20261014.md)。本报告保留原失败现场结论；后续实际 File ID、状态和双端查看证据单独记录。

操作与独立复核时间为 2026-10-14 20:59—21:09（Asia/Shanghai）。设备为小米 12（2201123C，Android 12 / API 31），同一手机运行家人端和长辈端 Demo App。结构化脱敏证据见 [evidence.json](photo-errors-20261014/evidence.json)。

锁定 Memory ID：`01a13a7f-505d-7da2-803c-322082945402`。唯一标题：`DEMO-PHOTO-ERRORS-20261014-9FBC43C5`。虚构内容：`Fictional photo-selection and upload-error test only.`。基线与最终均为 `CONFIRMED / v1`，无附件。

## Changed

- 新增本轮独立报告和结构化证据，更新 PHONE-09 报告中的后续状态及第三周结果。
- Docker/API 初查均已停止；恢复原 PHONE-12 隔离容器、原卷和 Demo/Mock 配置，仅启动 API 与 worker。未清空或重建数据，未执行迁移。
- 通过现有鉴权 API 创建一条独立虚构记忆，复用既有家庭和 `FAMILY_MEMORY` 授权。初始 `CONFIRMED` 是 fixture 设置，不作为手机人工确认通过证据。
- 将四份程序生成的合成文件推送到手机专用目录 `/sdcard/Download/NianNian-photo-test`，核对手机与本地 SHA-256 一致。真实选择操作只使用这些文件。
- 原始 APK、截图、XML、脚本、运行日志和合成图片保存在忽略目录 `artifacts/photo-errors-20261014/`。公开证据只导出虚构文本 allowlist、状态、ID、时间和原始证据哈希。
- 未修改后端/Android 源码、依赖、迁移、需求或合同。

## Tests

| 环境检查 | 结果 | 实际证据 |
| --- | --- | --- |
| 隔离服务与授权 | PASS | health 200 / environment=demo，provider=mock；PostgreSQL healthy、MinIO running；既有迁移 `20261010_week3_core`；Consent GRANTED；API/worker 进程存活、WORKER_READY |
| USB 与监听 | PASS | 8000→59000、59003→59003；API/DB/MinIO 使用 loopback，未开放公网 |
| 已安装双端 APK | PASS | 从手机重新提取 APK 核对：长辈端 `346c1be20311ccdc7fb28fbe3fe5b35029241b189e04d04369b5765975a4bf0a`，家人端 `fba0b7155d52ce831fe7c84ca60bcc7e330b23d1b8580bb5fdf1c2ce571e1a59`；与原 CI 验收产物一致，未重新安装 |
| 独立记忆基线 | PASS | 创建 201；双角色独立鉴权详情 200；只读数据库同一 ID，CONFIRMED/v1、attachments=[]、FileAsset=0；家人端详情显示唯一标题、内容、已人工确认 |

以下选择操作均在家人端真实系统选择器 `com.google.android.documentsui` 执行，通过文件列表上的实际文件名选择；没有用 API 上传替代手机失败路径。

| 步骤 | 手机界面证据 | API 证据 | 数据库证据 | 结果 |
| --- | --- | --- | --- | --- |
| 取消选择 | 打开选择器后按返回；回到列表，重新打开原详情正常，无照片按钮 | 双角色详情 200，原字段与版本不变，附件为空 | FileAsset=0，无 FILE 审计 | PASS |
| 超过 5 MiB | 选择 `01-oversize-demo.png` 后返回列表；未显示“照片需小于 5 MB。”或其他错误 | 双角色原记忆可读、附件为空 | FileAsset=0，无 FILE 审计 | FAIL：明确错误提示不满足；大小校验是否到达为 NOT VERIFIED |
| 不支持格式 | 选择 `02-unsupported-demo.gif` 后返回列表；未显示“请选择 JPG、PNG 或 WebP 照片。”或其他错误 | 同上 | FileAsset=0，无 FILE 审计 | FAIL：明确错误提示不满足；MIME 校验是否到达为 NOT VERIFIED |
| 损坏图片 | 选择 `03-corrupt-demo.png` 后返回列表；未显示内容隔离错误 | 同上 | FileAsset=0，无 FILE 审计；没有实际 QUARANTINED 文件 | FAIL：选择无反馈；上传/确认/隔离分支 NOT VERIFIED |
| 有效图片恢复 | 选择 `04-valid-demo.png` 后仍返回列表；无上传成功提示、无照片按钮；重开家人端详情正常 | 双角色详情 200，附件仍为空 | FileAsset=0，无 FILE 审计；没有 AVAILABLE 文件 | FAIL：正常上传未成功；双端照片查看 NOT VERIFIED |
| 最终原测试数据 | 家人端可重开同一虚构详情；长辈端刷新显示“暂时无法读取，请检查连接或授权后重试。” | 七阶段双角色均为同一标题/内容、CONFIRMED/v1、附件为空 | 七阶段原记忆字段一致，未删除/撤回 | 原记忆完整性 PASS（API/DB及家人界面）；长辈界面 NOT VERIFIED |

| 测试文件 | 实际字节数 | 本地实际解码核对 | 实际 File ID / 状态 |
| --- | --- | --- | --- |
| `01-oversize-demo.png` | 7,692,327（>5,242,880） | 可解码 PNG，1600×1600 | 未创建 / 无状态 |
| `02-unsupported-demo.gif` | 4,112 | 可解码 GIF，不在 JPG/PNG/WebP 白名单 | 未创建 / 无状态 |
| `03-corrupt-demo.png` | 60 | 有 PNG 开头，截断后解码失败 | 未创建 / 无状态 |
| `04-valid-demo.png` | 3,404 | 可解码 PNG，480×320 | 未创建 / 无状态 |

“无异常照片可查看”仅表示本次没有附件和文件记录；**不构成上传校验或隔离成功**。没有虚构 File ID，也没有将零记录称为 QUARANTINED。公开 JSON 中 `file_id`、`file_status` 均为 null。

证据一致性校验实际通过：14 组 UI XML/截图哈希一致；四份合成文件大小、格式、解码/损坏特征及手机哈希一致；七阶段 API/DB 原记忆字段一致、FileAsset 和 FILE 审计均为空。公开文件与本轮四份 API/worker 日志的限定凭证/签名参数扫描为 0 命中；这不替代完整隐私门禁。未因文档验收重新构建或重跑全量回归。

## Decisions

- 手机、API、数据库证据分别记录；UI 不展示 Memory/File ID，使用唯一标题/内容关联独立 API 与只读数据库 ID。
- 无错误提示与正常上传失败是已经观察到的 **FAIL**；没有到达的具体校验、隔离和照片查看分支标为 **NOT VERIFIED**。
- 保留失败现场及测试记忆，不通过修改 APK、绕过选择器、补 API 上传或直接写 DB 制造通过结果。
- 两款 App 在同一手机分别运行，不声称两台手机同步通过。Demo/Mock 标识保持，合成图片不代表真实家庭照片。

## Contract Changes

None。

## Not Verified

- 超限/格式本地错误处理的实际进入、损坏图片经手机上传后的 QUARANTINED/下载拒绝、有效照片 AVAILABLE 和双端查看：选择返回后没有文件记录，相关下游分支未到达。
- 长辈端最终测试记忆详情：刷新实际显示通用读取错误；独立长辈鉴权 API 200 不替代手机界面通过。未归因于网络、凭证或 Keystore。
- 选择器问题的确切根因：未插桩。源码中 `MemoryPanel` 的 ON_STOP 清空、ON_START bind，以及 ActivityResult 对 `state.familyId` 的外层判断是待核查线索，不能据此宣布根因已证实。
- 本轮未验证物理删除、断网恢复、退出/Keystore、进程恢复、其他硬件或后续周任务；未重跑后端全量、Android 构建/JVM/lint。

## Issues

**PHOTO-SELECT-01：选择文件后没有上传或明确反馈。** 在安装哈希已核对的家人端，三类异常文件和有效 PNG 各按指定顺序实际选择一次，均回到已确认列表；原详情选择消失，没有错误或成功提示。独立 API 和只读数据库未发现关联文件/文件审计。正常上传入口因此不能通过本轮验收。

长辈端最终读取失败单独保留证据，不扩大本轮为登录、Keystore 或断网恢复排查。初始服务停止已在验收前恢复；ADB 沙箱不能连接宿主 daemon，获准使用宿主 ADB 后连接正常。

## Next

另行指定任务核查并修复 PHOTO-SELECT-01，再复验本轮未达到的分支；长辈端读取问题另行核查。本轮不执行修复、物理删除、断网恢复或退出/Keystore。保留隔离服务、USB 映射、合成 fixture 和失败现场供复查。
