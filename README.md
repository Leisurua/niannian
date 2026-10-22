# 念念 NianNian

面向老人和家属的 AI 陪伴课程项目：Android 双端、FastAPI 单体后端、Windows 两个演示界面和 Linux 部署。

当前可运行 Demo 登录/家庭授权、家庭记忆及私有照片、文字会话与授权 RAG、提醒/离线反馈、受控摘要、主动邀请、规则警告和家属应用内通知；Android 与 Windows 共用设备注册、家庭文字留言和回执接口。语音实机、真实电话与后台消息推送仍待验证或实现；Mock 不等于真实送达或硬件验证。

## 四人团队从这里开始

| 要做什么 | 唯一主要说明 |
| --- | --- |
| 运行后端、Android、Windows 或 Linux | [部署与联调](docs/deployment.md) |
| 找模块、理解客户端与服务关系 | [当前结构](docs/architecture.md) |
| 查接口字段/状态 | [OpenAPI](docs/openapi.yaml)，运行服务的 `/docs`、`/openapi.json` |
| 查表、字段、关系和迁移 | [数据库](docs/database.md) |
| 修改 AI、RAG、摘要或风险规则 | [AI](docs/ai.md) |
| 查权限、撤权、照片、缓存和保留期 | [安全](docs/security.md) |
| 看当前进度和待开发能力 | [路线图](docs/roadmap.md) |

代码入口：`backend/app/modules/` 业务，`backend/app/ai/` 编排，`backend/app/worker/` 后台；`android/app-elder/`、`app-family/` 与 `shared/`；`windows/src/`；`infra/`。

分工与工作方式见 [AGENTS.md](AGENTS.md)，产品目标见 [需求说明](nian-nian-requirements-design.md)。日常只运行必要 lint、关联测试和相关构建，命令见 [测试说明](tests/README.md)。不新增分周文档或重复报告；旧设计与讨论查 Git 历史。

默认不保存原始音频，不提交密钥、真实家庭资料、照片或敏感全文。当前实现和目标需求分开维护，不能用接口草案、Mock 或测试数量表示功能已完成。
