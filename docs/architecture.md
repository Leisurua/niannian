# 当前系统结构

本文件说明已采用的结构。当前能力与下一步见 [roadmap](roadmap.md)，运行方式见 [deployment](deployment.md)，产品目标保留在 [需求说明](../nian-nian-requirements-design.md)。代码决定已实现行为；需求目标不代表功能已交付。

## 进程和依赖

Android / Windows → FastAPI REST / WebSocket → PostgreSQL + pgvector / 私有 S3。
独立 worker 通过同一数据库读取持久任务，调用同一套业务服务和对象存储。

| 位置 | 当前职责 |
| --- | --- |
| `backend/app/main.py`、`__main__.py` | API 路由、脱敏错误、请求编号；Windows 兼容的启动入口 |
| `backend/app/modules/auth`、`family`、`consent` | 登录会话、家庭与成员、分项授权及撤回 |
| `backend/app/modules/account` | 本人 ZIP 导出、账户删除回执、worker 文件清理、备份期限和供应商副本核验 |
| `backend/app/modules/avatar` | 本人照片制作授权、千问/豆包立绘、抠图构图、THA3 任务、预览确认和资源清理 |
| `backend/app/modules/memory` | 候选/确认、照片、检索、索引失效与清理 |
| `backend/app/modules/conversation` | 本人文字会话、WSS、受控摘要与主动邀请 |
| `backend/app/modules/reminder` | 周期/时区、执行记录、在线与离线反馈 |
| `backend/app/modules/safety`、`signal`、`notification` | 确定性规则、关注事件、授权通知与偏好 |
| `backend/app/modules/device`、`message`、`audit` | 设备注册与登录绑定、持久化家庭文字留言及回执；安全与幂等元数据审计 |
| `backend/app/platform` | 配置、数据库、公共授权、分页、S3 与 task/outbox |
| `backend/app/ai`、`integrations` | 编排和供应商无关 DTO；默认 Mock，文字 LLM 可配置 OpenAI 兼容服务 |
| `backend/app/worker` | 调度、租约、重试、索引/摘要/通知/清理任务 |

路由只处理通信和输入；服务/查询检查家庭、成员、主体、角色、授权和资源状态。跨领域调用公开服务，不能依赖其他领域的私有模型或仓储。没有实现的业务不设空模块。

## 客户端和交互

Android 采用 Kotlin、Compose、ViewModel/StateFlow。只保留 `app-elder`、`app-family`、`shared` 三个 Gradle 模块。共享库按 `data`、`core` 和各 `feature` 分包，网络、登录刷新和业务 Gateway 共用；设备权限、本地提醒调度由老人端拥有。

| 客户端 | 当前界面/交互 |
| --- | --- |
| Android 老人端 | Demo 登录、确认入家、授权/撤回、家庭记忆与照片、提醒反馈、语音/文字对话及回顾、基础 2D 数字人与播放状态联动、主动邀请设置确认；家庭留言、回复和已读 |
| Android 家属端 | 家庭/邀请/成员权限、记忆录入和确认、提醒管理、获准摘要、主动邀请设置提议、应用内通知及已读/偏好、关注事件确认/人工联系记录/误报/解决与历史、本人联系人和逐人授权；家庭留言收发与回执 |
| Windows 家属端 | 登录、建家/列表和邀请、设备注册、留言收发与回执、自动刷新、令牌续期及退出 |
| Windows 老人端 | 登录、接受邀请/选择家庭、设备注册、大字留言与快捷回复、自动接收、令牌续期及退出 |

老人端以大字、明显按钮和语音/文字输入组织对话。设备 ASR 识别后复用文字 WSS，设备 TTS 朗读回复，提供按钮打断、重播、慢速朗读和文字降级。LLM 模式由服务器握手返回；设备语音服务与 LLM 配置独立。放大文字仅改变字号，实际录音/播放状态由客户端管理，详见 [AI 说明](ai.md)。

老人端基础数字人使用共享 Compose Canvas 柿子形象，四种展示状态直接派生自 `ConversationModel`；首页和设置中的聊天入口共用同一真实会话界面。家属端 `NotificationModel` 同步授权事件及通知，详情可确认、记录联系和解决；后端 `signal` service 使用家庭锁、当前授权、独立处理权限和幂等审计完成状态更新，复用现有数据库字段。

THA3 自定义形象支持手机选照片并授权，后端调用千问/豆包生成立绘，GPU worker 整理透明背景和面部位置后预生成四态角色包。任务保存到 `avatar_job`，照片、预览和角色包复用私有 `file_asset`；普通 worker 不领取生成任务。Android 的 `AvatarGenerationModel` 读取进度、下载预览、接受本人确认，`AvatarPack` 校验格式，`AvatarModel` 复验 PORTRAIT 授权，`AvatarStorage` 在本机加密保存，`CompanionAvatar` 按真实会话四态绘制图块。也保留离线制作脚本和本机 ZIP 导入；默认形象可独立使用。部署方式见 [THA3 接入](deployment.md#tha3-自定义陪伴形象)。

双端新首页复用 Activity 中的现有业务模型和 Gateway：长辈首页显示实际提醒并提交幂等反馈，家属首页按所选长辈读取提醒、执行反馈、记忆和应用内通知。首页快捷新增通过现有提醒 API 保存每日生活提醒，仅在服务端确认后提示成功；提醒的时间、内容、完成状态和删除随最新结果更新，不以本地列表追加代替同步。记忆/照片、提醒管理、文字会话、主动陪伴/摘要和通知偏好直接从首页打开；家庭邀请、成员与分项授权在家庭设置中维护。切换家庭、退到后台或授权变化会清除敏感展示，回到前台重新核对；断网时家属首页隐藏提醒及家庭记忆，现有连接状态栏显示实际状态。双端首页家人动态共用 `MessageModel`，读取实际收发箱、接收和已读回执，照片进入现有家庭记忆上传/查看；首页与留言面板共用前台生命周期，不重复注册或重置发送状态。姓名取当前账户/家庭成员，不展示虚构健康结论、时长、原声回复或默认授权。视频按钮禁用并标注尚未接入，原声消息没有播放入口。双端天气使用独立的 Open-Meteo 公共客户端，手动搜索并选择城市，显示来源和数据时间；不获取设备定位或发送登录凭证，失败/过期不回退演示天气。

Windows 用 Tk 和标准库 HTTP；`windows/src/niannian_desktop` 共用登录状态、错误解析、分页、服务器地址设置和工作线程队列。工作线程不读取 Tk 变量，结果在 UI 线程消费。可选 API 以运行服务器 `/openapi.json` 检测，不能用测试服务器的接口宣称主后端已支持。

家庭留言由 REST 前台轮询同步，不依赖 Mock 推送或 worker。发送时按当前家庭角色确定接收成员并持久化；回执按成员共享，同一成员换设备仍可补拉。客户端接收内容后确认 RECEIVED，用户点击确认后才标记 READ。不同于 AI 会话，家人主动发送的留言正文保存在数据库；访问和留存边界见 [security](security.md)。

## 已采用的重要决定

原 ADR-001～007 的有效结论统一维护于此：

- 两个原生 Android 应用，共享必要代码；不引入跨端框架或多余 Gradle 模块。
- Python 3.12、FastAPI、Pydantic v2、异步 SQLAlchemy 2、psycopg、Alembic；保持模块化单体，API 和 worker 分进程。
- PostgreSQL 是事实源，pgvector 与业务数据共享家庭/授权边界，不另建向量服务。表和迁移见 [database](database.md)。
- 二进制照片使用私有 S3/MinIO。上传短期签名；下载签名指向每次鉴权的 API 代理，不能绕过撤权。
- AI 通过 DTO、能力和固定错误边界接入，业务不使用供应商 SDK 类型。模型只提建议/候选，确定性代码决定权限和副作用，见 [ai](ai.md)。
- APScheduler + PostgreSQL task/outbox，保留幂等键、租约、有限重试和死信，不增加消息队列。

数字人、kiosk、BLE、存在检测、唤醒及未采用的设备选择仍列在路线图；当前关注通知渠道见部署说明。

## 后台任务和状态一致性

worker 每 15 秒运行一周期，同进程最多一周期，合并迟到触发；每周期最多处理 20 个任务。task/outbox 的唯一业务键去重，30 秒租约可回收，单任务 20 秒上限，最多 5 次尝试，指数退避最高 300 秒，耗尽进入 DEAD。

照片生成由同一后端的 `--avatar` worker 顺序处理，每 5 秒续租并复验授权。图像请求与本地处理各有独立超时；每任务只尝试一次，避免未知结果或进程重启自动重复付费请求。生成完成保持 READY，只有本人确认后才 ACTIVE；失败和取消复用现有文件清理任务。

API 和 worker 共享事务/领域规则。索引、摘要和通知写回须复验源记录、版本、当前授权和租约；撤回/删除先不可读，再异步清理，旧任务不能恢复内容。通知与事件同事务入队，Mock SENT 不能解释为真实送达。

数据库不实现“客户端隐藏即授权”；敏感服务、WSS 与后台派发都独立校验。权限、缓存、保留期和删除边界只在 [security](security.md) 完整维护。

关注通知复用现有 outbox/worker：Mock 保持可演示；显式启用时使用 ntfy HTTPS 推送及 Twilio SMS/Voice，详情见 [部署](deployment.md)。联系人、通知和事件处理均由确定性代码检查权限与授权。

后端 `weather` 提供 Open-Meteo 城市搜索和公共城市编号天气查询，Windows 双端复用共享面板；Android 保留现有直连天气客户端。`report` 提供授权指标采集、日期范围统计和实时固定模板周报，复用家庭、提醒和关注权限；最小轮次指标持久化，报告每次读取重新聚合。Android 双端有周报入口和本人统计开关，Windows 双端通过共享 API 读取。统计口径见 [ai](ai.md)。
