# 生产上线检查清单

## 必须配置

- `APP_ENV=production`
- 使用至少 32 位随机 `SECRET_KEY`
- `ALLOW_LOCAL_VERIFICATION_CODE=false`
- 配置 `SMTP_EMAIL` 与 `SMTP_AUTH_CODE`
- `CORS_ORIGINS` 只填写正式前端域名
- PostgreSQL 使用独立强密码，不公开 5432 端口
- 图片使用私有 S3/AIStor Bucket 和短期签名 URL
- 前端与 API 统一通过 HTTPS 反向代理访问

生产配置不满足这些条件时，后端会拒绝启动。

## 数据保护

- 每天运行 `scripts/backup.ps1`，将结果复制到另一台机器或对象存储
- 每月在隔离环境恢复一次数据库和上传文件
- 为 S3/AIStor 开启版本控制或生命周期备份
- 上线前补充用户数据导出、注销与保留期限说明

## 监控

- 监控 `/health` 与 `/health/ready`
- 监控 memory-worker 容器健康状态
- 管理端关注消息积压、`dead_letter` 任务、模型失败率和 Token 成本
- 对 Qwen 欠费、限流和对象存储失败配置外部告警

## 当前扩容边界

WebSocket 在线连接仍保存在单个后端进程内。当前部署保持一个后端副本；需要多副本时，先接入 Redis Pub/Sub 或其他共享消息总线。

登录和验证码限流目前也保存在单个后端进程内。扩展为多个后端副本前，应将限流计数迁移到 Redis；反向代理需要正确传递并校验真实客户端地址。
