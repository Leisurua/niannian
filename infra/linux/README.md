# Kali Linux 服务端部署

这是现有 FastAPI 模块化单体的 Linux 运行包装，不是另一套业务代码。Compose 同时运行 API、后台 worker、Alembic 迁移、PostgreSQL/pgvector 和私有 MinIO。当前使用 `demo + mock` 配置，不会伪装成真实 AI、短信或推送服务。

## 1. Kali 准备

建议使用 64 位 Kali，至少 4 GB 内存和 12 GB 可用空间。安装 Docker Engine、Compose v2、`curl` 和 `openssl`：

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 curl openssl
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

退出并重新登录 Kali，然后确认 `docker run --rm hello-world` 可执行。若 Kali 当前软件源没有 `docker-compose-v2`，请按 Docker 官方说明安装 Compose plugin；本项目不支持旧的 Python `docker-compose` v1。

## 2. 首次启动

在仓库根目录执行：

```bash
bash infra/linux/deploy.sh --host 192.168.1.50
```

将 `192.168.1.50` 换成 Kali 在手机同一局域网内的 IPv4 地址。不传 `--host` 时脚本会选择 `hostname -I` 返回的第一个地址。脚本会：

1. 生成权限为 `600` 的 `infra/linux/.env`，其中是本机随机密钥；
2. 构建固定版本的 Python 后端与 MinIO 镜像；
3. 先运行 Alembic，成功后再启动 API 和 worker；
4. 执行健康、迁移版本、worker 与存储隐私自检。

首次构建 MinIO 需从上游源码编译，耗时取决于网络和 CPU。不要将生成的 `.env` 提交到 Git。
Linux Compose 构建 Alpine 包时使用清华镜像，Go 依赖使用 `goproxy.cn`，GitHub 传输使用 `gh-proxy.com`；MinIO 和 `mc` 仍必须通过 Dockerfile 中的精确 Git 提交校验才会继构建。普通 Windows 基础设施 Compose 不传这些参数，仍使用官方默认源。

## 3. 与 Android 联调

部署成功后脚本会打印 API、WebSocket 和照片上传地址。手机需要与 Kali 互通，并允许访问：

- TCP `8000`：REST API 和 WebSocket；
- TCP `9000`：仅用于 MinIO 预签名照片上传。

PostgreSQL 没有映射到主机；MinIO 管理端口 `9001` 只绑定 `127.0.0.1`。如果启用了 UFW，可只允许当前局域网网段，例如：

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 9000 proto tcp
```

这个版本用于课设内网联调，使用明文 HTTP/WS。不要直接暴露到公网；公网部署必须再加 TLS 反向代理、域名、防火墙和备份策略。

## 4. 日常命令

```bash
# 重新验收
bash infra/linux/smoke.sh

# 查看状态和日志
docker compose --env-file infra/linux/.env -f infra/linux/docker-compose.yml ps
docker compose --env-file infra/linux/.env -f infra/linux/docker-compose.yml logs -f api worker

# 停止，但保留 PostgreSQL/MinIO 数据卷
docker compose --env-file infra/linux/.env -f infra/linux/docker-compose.yml down

# 更新代码后重建
bash infra/linux/deploy.sh
```

不要随意执行 `down --volumes`；该参数会删除本机的数据库和照片数据。

## 5. 常见排查

- API 未启动：执行 `docker compose ... logs migrate api`，先看 Alembic 是否成功。
- 手机无法连接：检查 `.env` 中 `NIANNIAN_HOST`、Kali 防火墙和 Wi-Fi 的客户端隔离。
- 文字功能正常但照片上传失败：手机还必须能访问 `NIANNIAN_HOST:9000`。
- 换了 Kali IP：修改 `.env` 里的 `NIANNIAN_HOST`，再执行 `bash infra/linux/deploy.sh`。
