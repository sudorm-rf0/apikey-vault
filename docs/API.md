# apikey-vault HTTP API 文档

本地 REST 服务，供 AI Agent 程序化调用。启动方式：

```bash
apivault serve [--host 127.0.0.1] [--port 8417] [--token TOKEN ...] [--ttl 43200]
```

- 默认只监听 `127.0.0.1`。
- 所有响应均为 JSON，且带 `Cache-Control: no-store`。
- 除 `/v1/health`、`/v1/unlock`、`/v1/lock` 外，所有端点都需要请求头
  `Authorization: Bearer <token>`。
- Token 来源：启动时 `--token` 指定的静态 Token（不过期），或 `POST /v1/unlock`
  返回的动态 Token（默认 12 小时，`--ttl` 可调）。

## 端点一览

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/v1/health` | 否 | 健康检查 |
| POST | `/v1/unlock` | 否 | 用主密码换取 Token |
| POST | `/v1/lock` | 否 | 立即使所有 Token 失效并锁定保险库 |
| GET | `/v1/keys` | 是 | 列出密钥元数据 |
| PUT | `/v1/keys/{name}` | 是 | 保存/更新密钥 |
| GET | `/v1/keys/{name}` | 是 | 获取密钥值 |
| DELETE | `/v1/keys/{name}` | 是 | 删除密钥 |

## 详细说明

### GET /v1/health

```json
{"status": "ok", "initialized": true, "unlocked": false, "api": "v1"}
```

`unlocked: false` 表示保险库仍锁定，写/读密钥会返回 `423`。

### POST /v1/unlock

请求体：`{"password": "<master-password>"}`

成功（200）：

```json
{"token": "…", "ttl_seconds": 43200, "expires_at": "2026-08-22T04:00:00Z"}
```

失败（401）：`{"error": "invalid password"}`

限速：同一来源 IP 连续失败 5 次后，冷却 60 秒，期间返回 `429` 与 `Retry-After` 头。

### POST /v1/lock

不需要鉴权（锁定是安全正向操作）。使全部 Token 失效并清空内存中的解密密钥。

```json
{"status": "locked"}
```

### GET /v1/keys

```json
{"keys": [
  {"name": "OPENAI_API_KEY", "description": "OpenAI key",
   "created_at": "…", "updated_at": "…"}
]}
```

### PUT /v1/keys/{name}

请求体：`{"value": "<secret>", "description": "<可选>"}`

- 新建返回 `201 {"status": "created", "name": "…"}`
- 覆盖返回 `200 {"status": "updated", "name": "…"}`
- 缺 `value` 返回 `400`；名称含 `/`、`\` 或 NUL 返回 `400`。

### GET /v1/keys/{name}

```json
{"name": "OPENAI_API_KEY", "value": "sk-…"}
```

不存在返回 `404`。

### DELETE /v1/keys/{name}

```json
{"status": "deleted", "name": "…"}
```

不存在返回 `404`。

## 错误码

| 状态码 | 含义 |
| --- | --- |
| 400 | 请求体非法 |
| 401 | Token 缺失/无效，或主密码错误 |
| 404 | 路径或密钥不存在 |
| 423 | 保险库已锁定，先 `POST /v1/unlock` |
| 429 | unlock 限速中 |
| 500 | 保险库未初始化 |
