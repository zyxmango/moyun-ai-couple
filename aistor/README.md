# 本地 AIStor

1. 在 MinIO 官方定价页申请 AIStor Free 许可证。
2. 下载许可证并保存为 `aistor/minio.license`。该文件已被 Git 忽略，禁止提交。
3. 如需修改默认本地凭据，在项目根目录 `.env` 中设置：

   ```env
   AISTOR_ROOT_USER=replace-me
   AISTOR_ROOT_PASSWORD=replace-with-a-long-random-password
   ```

4. 启动：

   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.aistor.yml up -d --build
   ```

AIStor API 默认使用 `http://localhost:9000`，管理控制台使用
`http://localhost:9001`。Bucket 保持私有，后端只返回短期签名 URL。
