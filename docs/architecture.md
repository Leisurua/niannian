# 当前系统结构

本文件说明已采用的结构。当前能力与下一步见 [roadmap](roadmap.md)，运行方式见 [deployment](deployment.md)，产品目标保留在 [需求说明](../nian-nian-requirements-design.md)。代码决定已实现行为；需求目标不代表功能已交付。

## 进程和依赖

Android / Windows → FastAPI REST / WebSocket → PostgreSQL + pgvector / 私有 S3。
独立 worker 通过同一数据库读取持久任务，调用同一套业务服务和对象存储。

| 位置 | 当前职责 |
| --- | --- |
| `backend/app/main.py`、`__main__.py` | API 路由、脱敏错误、请求编号；Windows 兼容的启动入口 |
| `backend/app/modules/auth`、`family`、`consent` | 登录会话、家庭与成员、分项授权及撤回 |
| `backend/app/modules/memory` | 候选/确认、照片、检索、索引失效与清理 |
| `backend/app/modules/conversation` | 本人文字会话、WSS、受控摘要与主动邀请 |
| `backend/app/modules/reminder` | 周期/时区、执行记录、在线与离线反馈 |
| `backend/app/modules/safety`、`signal`、`notification` | 确定性规则、关注事件、授权通知与偏好 |
| `backend/app/modules/device`、`audit` | 登录设备绑定的内部服务；安全与幂等元数据审计 |
| `backend/app/platform` | 配置、数据库、公共授权、分页、S3 与 task/outbox |
| `backend/app/ai`、`integrations` | 编排和供应商无关 DTO；默认 Mock，文字 LLM 可配置 OpenAI 兼容服务 |
| `backend/app/worker` | 调度、租约、重试、索引/摘要/通知/清理任务 |

路由只处理通信和输入；服务/查询检查家庭、成员、主体、角色、授权和资源状态。跨领域调用公开服务，不能依赖其他领域的私有模型或仓储。没有实现的业务不设空模块。

## 客户端和交互

Android 采用 Kotlin、Compose、ViewModel/StateFlow。只保留 `app-elder`、`app-family`、`shared` 三个 Gradle 模块。共享库按 `data`、`core` 和各 `feature` 分包，网络、登录刷新和业务 Gateway 共用；设备权限、本地提醒调度由老人端拥有。

| 客户端 | 当前界面/交互 |
| --- | --- |
| Android 老人端 | Demo 登录、确认入家、授权/撤回、家庭记忆与照片、提醒反馈、文字对话及回顾、主动邀请设置确认 |
| Android 家属端 | 家庭/邀请/成员权限、记忆录入和确认、提醒管理、获准摘要、主动邀请设置提议、应用内通知及已读/偏好 |
| Windows 家属端 | 登录、建家/列表和邀请；保留设备和留言界面，但服务器尚无对应 API |
| Windows 老人端 | 登录、接受邀请/选择家庭；保留大字留言与快捷回复界面，消息后端尚未实现 |

老人端以大字、明显按钮和直接文字输入组织对话，显示临时消息列表、等待、停止、重新编辑和重连状态。LLM 模式由服务器握手返回；录音和播音尚未启用，放大文字仅改变字号。

Windows 用 Tk 和标准库 HTTP；`windows/src/niannian_desktop` 共用登录状态、错误解析、分页、服务器地址设置和工作线程队列。工作线程不读取 Tk 变量，结果在 UI 线程消费。可选 API 以运行服务器 `/openapi.json` 检测，不能用测试服务器的接口宣称主后端已支持。

## 已采用的重要决定

原 ADR-001～007 的有效结论统一维护于此：

- 两个原生 Android 应用，共享必要代码；不引入跨端框架或多余 Gradle 模块。
- Python 3.12、FastAPI、Pydantic v2、异步 SQLAlchemy 2、psycopg、Alembic；保持模块化单体，API 和 worker 分进程。
- PostgreSQL 是事实源，pgvector 与业务数据共享家庭/授权边界，不另建向量服务。表和迁移见 [database](database.md)。
- 二进制照片使用私有 S3/MinIO。上传短期签名；下载签名指向每次鉴权的 API 代理，不能绕过撤权。
- AI 通过 DTO、能力和固定错误边界接入，业务不使用供应商 SDK 类型。模型只提建议/候选，确定性代码决定权限和副作用，见 [ai](ai.md)。
- APScheduler + PostgreSQL task/outbox，保留幂等键、租约、有限重试和死信，不增加消息队列。

原推送、数字人、kiosk、BLE、存在检测、唤醒和电话 ADR 尚未采用的供应商/设备选择仅列在路线图，不把讨论方案当作现状。

## 后台任务和状态一致性

worker 每 15 秒运行一周期，同进程最多一周期，合并迟到触发；每周期最多处理 20 个任务。task/outbox 的唯一业务键去重，30 秒租约可回收，单任务 20 秒上限，最多 5 次尝试，指数退避最高 300 秒，耗尽进入 DEAD。

API 和 worker 共享事务/领域规则。索引、摘要和通知写回须复验源记录、版本、当前授权和租约；撤回/删除先不可读，再异步清理，旧任务不能恢复内容。通知与事件同事务入队，Mock SENT 不能解释为真实送达。

数据库不实现“客户端隐藏即授权”；敏感服务、WSS 与后台派发都独立校验。权限、缓存、保留期和删除边界只在 [security](security.md) 完整维护。
