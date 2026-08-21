# AGENTS.md — 给 AI Agent（Codex / Claude）的使用说明

本仓库提供 `apikey-vault`：一个本地加密的 API 密钥保险箱，让你（Agent）在需要密钥时
**按需、安全**地获取，而不用接触明文存储文件，也不会把密钥带进对话。

## 什么时候用它

- 任务需要某个 API 密钥（OpenAI / Anthropic / GitHub Token / 第三方服务密钥等）；
- 你被告知密钥保存在 `apikey-vault` 中；
- 你需要临时存储一个密钥供后续步骤使用。

## 怎么用（三条路径，任选）

### 1. 命令行直接读（最常用）

```bash
KEY=$(apivault get OPENAI_API_KEY)
export OPENAI_API_KEY="$KEY"
```

- `get` 只把值打印到 stdout，其余提示都在 stderr，命令替换是安全的。
- 需要主密码：设置 `APIVAULT_PASSWORD` 环境变量，或 `apivault get NAME --password-file ~/.apikey-vault-password`。

### 2. 本地 HTTP 服务（适合长驻 Agent / 多次调用）

1. 人类先启动：`apivault serve --port 8417 --token <token>`（或先锁定，之后 `POST /v1/unlock`）。
2. 你（Agent）通过 curl 使用：

```bash
BASE=http://127.0.0.1:8417
AUTH="Authorization: Bearer <token>"

curl -s $BASE/v1/health
curl -s -H "$AUTH" $BASE/v1/keys                          # 列出元数据
curl -s -H "$AUTH" $BASE/v1/keys/OPENAI_API_KEY            # 取密钥值
curl -s -X PUT -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"value":"sk-...","description":"OpenAI"}' $BASE/v1/keys/OPENAI_API_KEY
curl -s -X DELETE -H "$AUTH" $BASE/v1/keys/OPENAI_API_KEY
```

3. 若服务以锁定状态启动，先用主密码换取短期 Token：

```bash
curl -s -X POST $BASE/v1/unlock -H "Content-Type: application/json" \
     -d '{"password":"<master-password>"}'
# → {"token":"...", "ttl_seconds":43200, ...}
```

### 3. 一次性导出到环境

```bash
eval "$(apivault export-env)"
```

## 关键规则

- **不要把密钥写进对话/日志/补丁**：用 `$(apivault get NAME)` 在 shell 内捕获并注入环境，
  绝不在回复中回显密钥值。
- **如果用户贴给你的是占位符（`{{NAME}}` / `{{REDACTED}}` / `{{vault:NAME}}`），
  不要要求用户粘贴明文**：直接让用户运行 `apivault get <name>` 把值注入环境，
  或使用本地 API（`apivault serve`）取用。这是产品防泄露设计的一部分。
- **不要直接读 `vault.db`**：它是密文，读了也没用；请走 CLI 或 API。
- `list` / `info` 只含元数据（名称、描述、时间），可以安全展示。
- 找不到密钥时先 `apivault list` 看准确名称。
