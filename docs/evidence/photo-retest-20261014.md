# 照片选择修复后真机复验 — 2026-10-14

## Task

**PASS：PHOTO-SELECT-01 已修复并在指定手机复验。** 取消、超过 5 MiB、GIF、损坏图片均得到对应结果；有效 PNG 从手机系统选择器上传成功，家人端和长辈端均完整显示同一张照片。

实际选择与查看时间：2026-10-14 21:32—21:39（Asia/Shanghai）。设备：小米 12（2201123C，Android 12 / API 31）。两款 App 在同一手机分别运行，环境为 Demo、provider=mock，API/数据库/MinIO 上传与下载实际执行。图片及记忆均为虚构 fixture。

复用原失败现场的 Memory ID `01a13a7f-505d-7da2-803c-322082945402`，唯一标题 `DEMO-PHOTO-ERRORS-20261014-9FBC43C5`，内容 `Fictional photo-selection and upload-error test only.`。原失败报告仍保留：[photo-errors-20261014.md](photo-errors-20261014.md)。结构化证据：[evidence.json](photo-retest-20261014/evidence.json)，一致性核验：[verification.json](photo-retest-20261014/verification.json)。第三周整体验收仍为 **INCOMPLETE**，本次通过只覆盖该照片任务。

## Changed

- `MemoryPanel` 不再用选择器返回瞬间的 `state.familyId` 判断是否处理结果；取消也交给恢复流程。仍使用系统 `GetContent`，仍在后台清除敏感内容、照片和输入。
- `MemoryModel.resumePhotoSelection` 恢复同一家庭/用户绑定，等待重新读取完成，经鉴权 API 重读目标记忆后再处理文件。绑定已切换、权限读取失败或存在待重试请求时不开始上传。取消只恢复详情，不读取文件、不创建上传请求。
- 增加 5 项 JVM 回归，覆盖后台清空后取消、ON_START 读取未结束时返回、超限/GIF 拒绝、隔离后有效照片恢复、不同家庭/用户及权限拒绝。Gateway 明确使用确定性 mock，真实解码/隔离证据来自手机/API/数据库。
- 本地修复包与原 CI APK 签名不同，覆盖安装被拒绝；仅重装两个 Demo App，通过手机界面重新登录既有虚构账户。服务器记忆、Consent、容器和卷保留，未重新 seed 或执行迁移。
- 原始 APK、截图/XML、执行脚本和日志保存在忽略目录 `artifacts/photo-retest-20261014/`；公开证据仅包含虚构文本、ID、状态、时间和哈希。新增本报告及第三周复验索引，未修改后端源码。
- 本次生成的本地调试签名文件移至忽略目录 `artifacts/photo-retest-20261014/android-user-home/`；后续若需构建同签名包，应将 `ANDROID_USER_HOME` 指向该绝对路径。签名文件不进入提交。

## Tests

| 软件/环境检查 | 结果 | 实际证据 |
| --- | --- | --- |
| Android JVM | PASS：9 tests，0 failure/error/skip | `:feature-memory:testDebugUnitTest` 的实际 JUnit XML；包含原 4 项和新 5 项 |
| Android lint | PASS：0 errors、2 warnings | `:feature-memory:lintDebug`；既有 Lifecycle/Coroutines 依赖版本提示，未更新或屏蔽 |
| 双端 Demo 构建 | PASS | 离线 `:app-family:assembleDemoDebug :app-elder:assembleDemoDebug`，BUILD SUCCESSFUL |
| 已安装 APK 与本次源码 | PASS | 重新从手机提取双端 APK，SHA-256 与本次构建相同；3 份照片模块 Kotlin 文件哈希绑定证据 |
| 隔离运行环境 | PASS | health 200 / environment=demo、provider=mock；PostgreSQL healthy、MinIO running；既有迁移 `20261010_week3_core`，Consent GRANTED |
| 合成文件一致性 | PASS | 四份手机文件 SHA-256 与本地一致；实际解码超限 PNG、GIF 和有效 PNG，并验证损坏 PNG 解码失败 |

安装包 SHA-256：家人端 `9a5acd6f0d6f64aa0c69c599ebea9ef47456536521ef754522dc046a89be3e72`；长辈端 `03a407bf26b412544f15910e38ee0d67a792a662e573e9fd0a40087776f53456`。USB 转发为 8000→59000、59003→59003，继续使用原 loopback 隔离配置。

以下文件均从手机 `com.google.android.documentsui` 的 `NianNian-photo-test` 目录按实际文件名选择；没有用 API 上传替代手机操作。

| 顺序/输入 | 实际手机结果 | API/数据库结果 | 结果 |
| --- | --- | --- | --- |
| 取消 | 返回键先退到下载目录，再退出选择器；原唯一标题/内容/已确认详情恢复，无错误和照片控件 | 双角色详情 200；FileAsset=0，无文件上传审计 | PASS |
| `01-oversize-demo.png`，7,692,327 字节 | 显示“照片需小于 5 MB。” | FileAsset=0，双角色原记忆可读，无附件 | PASS |
| `02-unsupported-demo.gif`，4,112 字节 | 显示“请选择 JPG、PNG 或 WebP 照片。” | FileAsset=0，无附件 | PASS |
| `03-corrupt-demo.png`，60 字节 | 显示“照片未通过内容检查，已隔离；请换一张照片。” | 实际 QUARANTINED 文件、FILE_QUARANTINED 审计；不进入附件；双角色 download-url 均为 404 / FILE_NOT_FOUND | PASS |
| `04-valid-demo.png`，3,404 字节 | 上传后出现“查看照片 1”；点击后家人端实际显示照片；长辈端重新登录后打开同一详情并点击，完整显示同一照片 | 实际 AVAILABLE 文件及 FILE_CONFIRMED 审计；双角色详情仅有该附件；download-url/content 均为 200，Cache-Control=no-store，下载解码像素与 fixture 相同 | PASS |

异常提示位于现有家庭记忆卡片上方；选择后滚动到该位置核对并拍摄截图，未把提示在原滚动位置自动可见作为通过依据。每次异常后点击“重新读取记忆”，再打开原详情进行下一次选择。

| 输入 | 实际 File ID | 实际状态 |
| --- | --- | --- |
| 取消、超限 PNG、GIF | 未创建 | 无状态 |
| 损坏 PNG | `01a13aa1-7a80-7a5b-b172-a95a7fe1112c` | `QUARANTINED` |
| 有效 PNG | `01a13aa2-465c-7590-90c2-b32ad827f43e` | `AVAILABLE` |

最终原记忆标题、内容、`CONFIRMED / v1` 均保持；附件从空列表变为仅包含有效照片，损坏文件没有混入附件。有效照片服务端安全副本 SHA-256 为 `81847c9393502669eba68fe4eedce16816f1980c9928434954bd9070fbaf7665`，与上传原件不同；数据库 checksum 仍表示上传原件，未把它当作安全副本哈希。

实际独立核验通过：7 阶段双角色 API/只读数据库快照、14 组截图/XML 哈希、4 份 fixture 文件、3 份 Kotlin 源码哈希及 2 张完整照片显示截图。已查看原始双端截图，蓝色边框/黄色矩形合成照片完整显示；没有仅依据“家庭记忆照片”控件存在判定通过。公开 JSON 的限定凭证/签名参数扫描为 0 命中，不替代完整隐私门禁。

## Decisions

- 修复选择器返回与后台清空的时序依赖，保留后台清理、家庭/用户隔离和服务端授权；不延长敏感缓存生命周期。
- API 查询和只读 SQL 用于独立核对 ID/状态与原字段；UI 通过唯一标题/内容关联同一记忆。文件状态取实际数据库记录及受控接口结果，不从错误文案推断。
- 两款 App 在一台手机运行。Demo/Mock 标识保留，不声称两台设备同步或真实家庭照片验收。
- 旧长辈端会话读取失败在重装后的新虚构登录中未复现；本次只确认照片现在可查看，不宣称查明或修复旧会话、Keystore 的根因。

## Contract Changes

None。

## Not Verified

- 两台手机同步、其他型号/系统、选择期间旋转或进程死亡、断网恢复和 Keystore/退出完整门禁：本任务未执行。
- 隔离文件到期后的物理清理、完整删除/撤权传播及第三周其余验收：未在本次执行，整周保持 INCOMPLETE。
- 本次仅运行照片模块 JVM/lint、双端 Demo 构建及实际照片链路；未重跑后端全量回归、全部 flavor/release 或远端 CI。UI Skills CLI 的离线路由因本地未缓存而不可用；未为此下载新依赖。

## Issues

本照片任务无剩余验收阻塞。异常提示需滚动至现有卡片顶部查看，未改动整页布局。CI 与本地调试签名差异已按 Demo 重装处理；服务器 fixture 保留。原失败报告继续作为历史证据保留。

## Next

后续周任务及其余门禁需另行指定；本次不自动执行。保留隔离服务、转发、合成文件、实际 File ID 和证据供复查，未推送或创建 PR。
