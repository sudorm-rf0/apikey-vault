# apikey-vault 🔐

本地加密的 **API 密钥保险箱**，专为 AI Agent（Codex / Claude 等）设计。

把密钥明文写在 `.env` 或 shell profile 里很危险：可能被误提交进 Git、被 Agent 带进对话
上下文、散落各处难以轮换。`apikey-vault` 把所有密钥用 **AES-256-GCM** 加密后存在本地
SQLite 中，人类用 CLI 管理，Agent 用 CLI 或本地 HTTP API 按需获取。

## ✨ 特性

- **加密存储**：AES-256-GCM 认证加密 + scrypt 密钥派生；主密码永不落盘；磁盘上无明文。
- **人类 CLI**：`store` / `get` / `list` / `delete` / `rename` / `export-env` / `change-password`。
- **Agent HTTP API**：`apivault serve` 启动本地 REST 服务，Bearer Token 鉴权，默认只监听
  `127.0.0.1`。
- **安全细节**：每条密钥独立 nonce；会话 Token 内存中只存 SHA-256 摘要并带 TTL；
  `/v1/unlock` 失败限速；响应 `Cache-Control: no-store`；vault 文件权限 0600。
- **极简依赖**：仅依赖 `cryptography`，HTTP 服务用 Python 标准库。

## 📦 安装

```bash
pip install -e ".[dev]"     # 开发安装（含测试依赖）
# 或仅运行依赖
pip install -e .
```

需要 Python 3.10+。

## 🚀 快速开始（人类）

```bash
# 1. 初始化保险库（会要求设置主密码；之后每个命令都要用它解锁）
apivault init

# 2. 保存密钥（交互输入、--value、或 --stdin）
apivault store OPENAI_API_KEY
apivault store OPENAI_API_KEY --value sk-...
printf 'sk-...' | apivault store ANTHROPIC_API_KEY --stdin

# 3. 读取 / 列出 / 导出
apivault get OPENAI_API_KEY          # 仅 stdout 输出值，便于脚本/Agent 捕获
apivault list                        # 只显示元数据，绝不显示值
apivault export-env                  # 输出 export OPENAI_API_KEY='...' 行

# 4. 其他
apivault info OPENAI_API_KEY
apivault rename OPENAI_API_KEY OPENAI_KEY
apivault delete OPENAI_API_KEY --yes
apivault change-password             # 改主密码（自动重新加密所有密钥）
apivault status
```

### 密码从哪里来（按优先级）

1. `--password-file <file>`（推荐 Agent 长期使用：0600 权限文件）
2. `--password-stdin`
3. 环境变量 `APIVAULT_PASSWORD`
4. 交互式 `getpass` 输入

> 注：用环境变量最方便，但进程环境可能被同机进程读取；对高价值密钥建议用
> `--password-file`。

## 🤖 给 AI Agent 用（三种方式）

### 方式一：CLI 直接读（最简单）

```bash
KEY=$(apivault get OPENAI_API_KEY)   # Agent 在 shell 中捕获，密钥不进对话
export OPENAI_API_KEY="$KEY"
```

### 方式二：一次性加载全部密钥到环境

```bash
eval "$(apivault export-env)"
```

### 方式三：本地 HTTP API（推荐给长期运行的 Agent 服务）

```bash
# 终端 1：启动服务（自动解锁需提供密码；也可先锁定，稍后 /v1/unlock）
APIVAULT_PASSWORD='...' apivault serve --port 8417 --token my-static-agent-token

# 终端 2 / Agent：
curl -s http://127.0.0.1:8417/v1/health
curl -s -X PUT http://127.0.0.1:8417/v1/keys/OPENAI_API_KEY \
  -H "Authorization: Bearer my-static-agent-token" \
  -H "Content-Type: application/json" \
  -d '{"value":"sk-...","description":"OpenAI key"}'
curl -s http://127.0.0.1:8417/v1/keys/OPENAI_API_KEY \
  -H "Authorization: Bearer my-static-agent-token"
```

详细 API 见 [docs/API.md](docs/API.md)。

## 🗂️ 数据存放

默认目录 `~/.apikey-vault/vault.db`，可用环境变量 `APIVAULT_DIR` 覆盖，或给每个命令加
`--dir <dir>`。

- `keys` 表：`name, description, payload(BLOB), created_at, updated_at`
  - `payload = nonce(12B) || AES-256-GCM 密文 || tag(16B)`
- `meta` 表：scrypt 盐、验证 blob、KDF 参数、版本

## 🔒 安全模型

- **威胁**：vault 文件被复制、磁盘丢失 → 无主密码无法还原任何密钥。
- **假设**：运行时的本机可信；不防御键盘记录器 / 已解锁状态下的内存读取。
- **设计**：scrypt(N=2^17,r=8,p=1) 派生 32 字节密钥；AES-256-GCM 认证加密；密码本身
  永不存储，仅通过解密固定 magic 校验；内存中尽力清零敏感字节。
- 详细规划见 [PLAN.md](PLAN.md)。

## ✅ 测试

```bash
python -m pytest
```

覆盖密码学往返/篡改、存储 CRUD/改密、CLI 端到端、HTTP API 全链路（含限速与鉴权）。

## ⚠️ 注意事项

- 默认只监听 `127.0.0.1`；如需 `--host 0.0.0.0` 供局域网使用，请自行评估风险并确保
  Token 安全。
- 不要提交真实密钥；本仓库的测试只用假密钥。

## 📄 License

MIT
