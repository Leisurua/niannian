# 开发工具

统一入口：`python scripts/verify.py <lint|test|integration|android|windows> [测试路径或 Gradle 任务]`。直接在当前代码上运行，不复制源码、不生成哈希或验收报告，不自动迁移数据库。

日常选择关联测试，详见 [README](../README.md) 和 [测试说明](../tests/README.md)。演示使用客户端的 Demo 登录，再创建家庭、授权及内容；不维护引用未实现表的全项目 seed。
