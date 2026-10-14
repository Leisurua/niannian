# ADR-006 对象存储

- Status: Accepted
- Date: 2026-09-22

## Context

家庭照片和可能的短期音频是二进制文件，不能塞进 PostgreSQL；撤回授权、删除和访问审计必须可追踪。

## Options

1. PostgreSQL bytea。
2. MinIO/S3 Compatible 对象存储。
3. 直接依赖某一家云厂商 SDK。

## Decision

采用 S3 Compatible 接口，开发环境使用 MinIO。PostgreSQL 保存 object key、元数据、授权和生命周期；读取使用服务端授权后的 Signed URL。删除包括业务删除、embedding/cache 失效、对象删除或生命周期清理和 AuditLog。

## Consequences

文件容量和数据库事务解耦，未来可替换云存储。需要在 Compose 初始化 bucket、配置生命周期，并测试 Signed URL 过期和撤回后的不可访问性。


## 2026-10-10 已批准澄清

按 [W3-04](../plan/week3-contract-review.md)，下载 Signed URL 指向鉴权后端代理，必须同时有有效登录，并在每次读取时重查授权和资源状态；不返回可绕过撤权的对象存储直签下载链接。上传仍使用短期私有 S3 签名。解码重编码的图片写入独立只读对象键，客户端上传签名不能覆盖下载副本。
