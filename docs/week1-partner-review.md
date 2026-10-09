# 第一周交付回顾与合伙人讨论

整理日期：2026-10-09。本文汇总已交付内容和可讨论事项，不修改既有需求、接口、数据库或授权契约。

## 先看结论

第一周交付的是**能够构建、测试和复现演示的工程基础**。原实现已通过 [PR #1](https://github.com/Leisurua/niannian/pull/1) 于 2026-10-02 合入 `main`。

本次 PR 只增加这份交付回顾，作为合伙人查看和讨论的入口。它不重新提交已合并的代码，也不把后续任务或未完成验收标为通过。

建议阅读顺序：本页 → [第一周验收记录](evidence/week1.md) → [开发清单](development-checklist.md) → 在本 PR 中逐项留言。

## 第一周任务与交付

| 任务 | 已交付内容 | 已有证据 | 保留的边界 |
| --- | --- | --- | --- |
| E0-T01 工程骨架 | 两个 Android Compose App、共享模块、FastAPI health、独立 worker、测试入口 | Android 构建、后端启动及包外安装检查 | App 是工程占位，不能据此宣称业务闭环已完成 |
| E0-T02 环境配置 | dev/test/demo 分离，演示与 Mock 来源明确，依赖版本锁定 | 三环境启动/配置测试 | 正式身份认证及真实供应商配置属于后续工作 |
| E0-T03 脱敏日志 | 结构化事件、请求标识、异常脱敏及隐私扫描基线 | 后端测试、源码/Git 历史/APK 扫描 | 完整设备/业务流程隐私验收仍开放；补充工作见 PR #2 |
| E0-T04 开发基础设施 | PostgreSQL、pgvector、MinIO 私有存储及 smoke | 服务健康、vector 扩展、私有桶、匿名 listing HTTP 403 | 不代表所有文件访问及删除路径已验收；已有对象 GET/清理补充见 PR #2 |
| E0-T05 迁移计划 | 22 实体创建顺序、审查清单、回滚/恢复证据计划 | [迁移计划](plan/E0-T05-alembic-initial-schema.md) | 第一周为计划；业务表迁移未由本任务执行 |
| E0-T06 接口契约 | 74 个 REST operation、9/11 种客户端/服务端 WSS 消息清单 | 冻结契约测试 | 契约清单通过不等于 74 个业务接口均已实现 |
| E0-T07 Mock 适配器 | ASR、LLM、Embedding、TTS、Avatar、WakeWord、Push、Weather 八类确定性 Mock | Adapter contract tests | Mock 不证明真实识别、生成、送达或通话能力 |
| E0-T08 演示 fixture | 虚构家庭、记忆、提醒、线索与周报等状态，固定命名空间及安全检查 | Fixture smoke；原交付记录为 24 条确定性数据 | 真实业务数据库首次写入/重复重放未验收；后续 fixture 补充见 PR #2 |
| E11-T04 CI 基线 | Backend、Android、infrastructure 三个 job；报告和 APK 产物 | 原实现及收尾提交的 CI 通过 | 当前文档 PR 的 CI 是单独一次验证，不能沿用旧 SHA 作为当前通过证据 |
| E9 设备验证启动 | 基线表、只读采集工具、责任角色、测试步骤与证据路径 | [设备启动记录](evidence/week1-device-baseline.md) | 建立记录不等于设备支持；后续设备观察按其日期、源码与 APK 指纹单独核验 |

## 可以查看的具体入口

| 合伙人关心的问题 | 阅读位置 |
| --- | --- |
| 项目总体目标与本周范围 | [开发计划](development-plan.md) 第 20 节、[需求原文](../nian-nian-requirements-design.md) |
| 双端工程与当前运行方法 | [README](../README.md)、[Android 工程说明](../android/README.md) |
| 后端/Android/基础设施如何自动检查 | [验证工具说明](evidence/week1-tooling.md)、[CI 配置](../.github/workflows/week1.yml) |
| MinIO 为什么从源码构建 | [来源、固定版本与构建说明](../infra/minio/README.md) |
| 哪些是实测、哪些仍未验证 | [第一周验收记录](evidence/week1.md)、[设备测试矩阵](device-test-matrix.md) |
| 后续还有哪些待决定事项 | [待决策清单](open-decisions.md)、[开发清单](development-checklist.md) |

## 已验证结果及证据范围

以下结果是第一周原交付的历史测量，详情和对应提交在验收记录中；不是当前所有分支的累计成绩。

- 原实现 `85d2fdd`：[CI 36539054178](https://github.com/Leisurua/niannian/actions/runs/36539054178)，三项 job 全部通过。
- 最终收尾 `5bc8db2`：[push CI](https://github.com/Leisurua/niannian/actions/runs/36730182481)、[PR CI](https://github.com/Leisurua/niannian/actions/runs/36730199543)，均通过。
- 后端：69 项通过，1 项 APK 扫描跳过；APK 检查由独立 Android job 实际执行。
- Android：两个 App 的 dev/qa/demo × debug/release 共 12 个 APK；共享模块单测 14 次执行，无失败；APK 扫描 7 项通过，无跳过。
- 基础设施：健康检查、pgvector、私有桶与匿名 listing 拒绝通过。

历史 Actions 产物采用七天保留，已超过原记录的 2026-10-06 到期日。长期参考源码中的验收记录和运行链接；需要安装包或重新核查原始报告时，应重新构建，不能把已过期产物称为仍可下载。

## 本次讨论应保留的未验证项

1. 第一周不含真实 AI/推送/天气供应商接入及真实送达、通话接通、性能结论。
2. 业务数据库 seed 重放依赖已审查的迁移。Fixture 的确定性和命名空间检查不能替代数据库重放。
3. kiosk、BLE、摄像头、离线唤醒、音频所有权、十次重启及设备隐私验收，需要指定设备和对应构建证据。
4. 数据删除传播、完整业务流程授权与隐私门禁，应按后续任务和测试矩阵验收。
5. `main` 已包含第一周工程交付，但综合 Batch 0/设备/发布门禁仍有开放项，不使用“全部验收完成”的表述。

## 与当前其他 PR 的关系

截至整理时，以下工作仍在开放 PR 中。本页只提供关联入口，不替代其审查，也不把它们计入已合并的第一周代码。

- [PR #2：补齐 E0 日志边界、虚构 fixture 与验收证据](https://github.com/Leisurua/niannian/pull/2)：日志边界、补充 fixture、对象访问与相关证据。
- [PR #3：第二周软件交付](https://github.com/Leisurua/niannian/pull/3)：登录、家庭邀请、授权和双端流程。

第一周首次记录“暂无设备”是当时的观察，不能替代后续设备记录。请按新证据的日期、型号、源码与 APK 指纹判断，而非把旧状态直接沿用到今天。

## 请合伙人重点讨论

下列问题目前是讨论议题，不是已批准的新决定。可在本 PR 的 Conversation 留整体意见，在 Files changed 针对对应条目逐行评论。

| 议题 | 希望形成的结论 | 当前依据 |
| --- | --- | --- |
| 第一周验收口径 | 是否认可以“工程基础通过，设备/真实服务/数据库重放仍待验收”作为阶段交付表述 | 开发计划第 1 周、第一周验收记录 |
| E0 补充验收 | PR #2 的证据是否足够，哪些开放门禁仍需保留 | PR #2 与安全/设备矩阵 |
| 测试设备与责任分工 | 指定平板/BLE 型号、设备操作人与证据维护人；如仍缺设备，确定补测安排 | 设备测试矩阵及后续设备记录 |
| 演示材料如何留存 | 是否保留固定版本安装包、校验值和简短演示录像；确定保管位置与责任人 | Actions 历史产物七天保留的实际限制 |
| 下一阶段交付顺序 | 先确认 E0 补充验收与第二周 PR 的依赖，再确定业务迁移和后续能力的顺序 | 开发计划、PR #2/#3 |
| 外部服务选型 | 对真实供应商的数据政策、费用、网络依赖和失败降级，先确定评估责任人与通过条件 | open-decisions 的未决项；当前继续使用 Mock |

讨论涉及接口、数据库、授权、安全边界或需求变化时，先形成 Proposal/ADR 并按既定流程审查；本回顾文档不授权实现这些变化。
