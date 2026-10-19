# 念念 Windows 子女端 0.1.0

> 与当前 main 兼容：DEMO 登录、家庭管理及邀请可使用；设备注册和跨端消息 API 尚未在 main 实现。客户端保留相关界面，调用时会提示服务端功能未交付。真实消息联机测试未完成。

这是面向课堂演示的 Windows 原生窗口客户端，直接使用 `docs/openapi.yaml` 中冻结的 HTTP 契约，不修改服务端接口。

## 已实现

- TCP 与 `/health` 分层连接诊断；
- `demo-child` 演示登录；
- 查看或创建家庭；
- 注册当前会话为 `FAMILY_MOBILE`；
- 生成一小时有效的老人端邀请令牌；
- 向家庭内 `ELDER` 角色发送普通/重要文本；
- 查看收件箱、发件箱与投递状态，发送接收/已读回执；
- 一键“虚构双端联机验收”，验证服务器介导的完整消息闭环。

访问令牌只保存在进程内存中。程序仅在 `%APPDATA%\NianNianFamily\settings.json` 保存服务器根地址，不保存账号凭证或令牌。

## 开发运行与构建

```powershell
.\run-dev.ps1
.\build.ps1
```

构建产物位于 `dist\念念-Windows子女端.exe`。源码只依赖 Python 标准库；PyInstaller 只用于生成单文件 Windows 程序。

## 怎样测试连接

1. 在 Kali 中确认服务端容器健康：`docker compose -f infra/linux/docker-compose.yml ps`。
2. 在 Windows 中先执行 `Test-NetConnection <Kali-IP> -Port 8000`。只有 `TcpTestSucceeded=True`，客户端才可能连接。
3. 打开程序，服务器地址填写 `http://<Kali-IP>:8000`，点击“测试连接”。这一步不会写业务数据。
4. 点击“一键端到端自检”。它会使用虚构账号创建临时家庭与两个设备，并检查最后一条投递是否变为 `READ`。
5. 测真实双端时，子女端创建家庭、生成邀请并注册本机；老人 Android 端接受邀请并注册后，子女端发送消息，老人端确认已读，再回到子女端刷新发件箱。

当前这台电脑此前无法访问 Kali NAT 地址 `192.168.193.128:8000`，而且 VMware 的 `VMnet8` 显示不存在。因此现阶段预计第 2 步会失败。修复方式任选一种：

- 在 VMware Virtual Network Editor 中恢复 `VMnet8` 的 Host-only adapter，然后继续用虚拟机 IP；
- 或给 NAT 配置宿主机端口转发，例如 Windows `127.0.0.1:18000` 转到 Kali `192.168.193.128:8000`，程序填写 `http://127.0.0.1:18000`；
- 或把虚拟机网卡改为桥接，让 Kali 获得与你电脑同一局域网的地址。

前两项通常需要管理员权限。不要把未配置 TLS 的 `8000` 端口直接暴露到公网。
