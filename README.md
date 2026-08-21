# apikey-vault 🔐

本地加密的 **API 密钥保险箱**，带图形界面，专为 AI Agent（Codex / Claude 等）与多设备使用设计。

把密钥明文写在 `.env` 或 shell profile 里很危险：可能被误提交进 Git、被 Agent 带进对话
上下文、散落各处难以轮换。`apikey-vault` 把所有密钥用 **AES-256-GCM** 加密后存在本地
SQLite 中：人类用**图形界面或 CLI** 管理，Agent 用 CLI 或本地 HTTP API 按需获取。

## ✨ 特性

- **图形界面（GUI）**：浏览器单页应用，锁定/解锁门禁、密钥库列表、密钥输入/编辑、一键复制、
  显示/隐藏、重命名、删除、改密、导出/导入、首启初始化。
- **加密存储**：AES-256-GCM 认证加密 + scrypt 密钥派生；主密码永不落盘；磁盘上无明文。
- **人类 CLI**：`store` / `get` / `list` / `delete` / `rename` / `export-env` / `change-password` / `export` / `import`。
- **Agent HTTP API**：`apivault serve` 启动本地 REST 服务，Bearer Token 鉴权，默认只监听 `127.0.0.1`。
- **多端可用**：`--host 0.0.0.0` 后同一局域网内手机/电脑浏览器直接访问 GUI；加密 vault 文件可
  导出/导入到任意设备（密文传输，安全）。
- **独立端**：`apivault serve --open` 一键打开 GUI；`scripts/build_app.sh` 可打包为 macOS
  独立 `.app`（内嵌 Python 环境，无需预装依赖）。
- **安全细节**：每条密钥独立 nonce；会话 Token 内存中只存 SHA-256 摘要并带 TTL；
  `/v1/unlock` 失败限速；响应 `Cache-Control: no-store` + CSP；vault 文件权限 0600。
- **极简依赖**：运行时仅依赖 `cryptography`，HTTP 服务与 GUI 用 Python 标准库 + 原生 JS。

## 📸 界面预览

![锁定界面](docs/screenshot-locked.png)
![密钥库](docs/screenshot-unlocked.png)
![密钥详情](docs/screenshot-detail.png)

## 📦 安装

```bash
pip install -e ".[dev]"     # 开发安装（含测试依赖）
```

需要 Python 3.10+。

## 🖥️ 图形界面（推荐）

```bash
apivault serve --open        # 启动并自动打开浏览器 http://127.0.0.1:8417
```

- **首次使用**：界面会引导你创建保险库（设置主密码）。
- 之后每次打开：输入主密码解锁 → 增删改查密钥库。
- 底部栏可**锁定 / 改密 / 导出加密 vault / 导入加密 vault**。

### 多端访问（局域网）

```bash
apivault serve --host 0.0.0.0 --port 8417 --token <你的agent令牌>
```

手机或其它电脑用浏览器访问 `http://<本机IP>:8417`，在「Use a bearer token instead」
输入令牌即可连接（保险库解锁后可用）。注意：`--host 0.0.0.0` 会把服务暴露到局域网，
务必使用强令牌，且仅限可信网络。

### 独立 App（macOS）

```bash
./scripts/build_app.sh        # 生成 dist/apikey-vault.app（内嵌 Python，无需预装依赖）
open dist/apikey-vault.app    # 双击即启动，自动打开浏览器
```

日志在 `~/.apikey-vault/app.log`。

## 🚀 快速开始（CLI）

```bash
# 1. 初始化保险库
apivault init

# 2. 保存密钥（交互输入、--value、或 --stdin）
apivault store OPENAI_API_KEY
apivault store OPENAI_API_KEY --value sk-...

# 3. 读取 / 列出 / 导出
apivault get OPENAI_API_KEY          # 仅 stdout 输出值，便于脚本/Agent 捕获
apivault list                        # 只显示元数据，绝不显示值
apivault export-env                  # 输出 export OPENAI_API_KEY='...' 行

# 4. 跨设备迁移（加密文件，安全）
apivault export ~/vault-backup.db    # 导出
apivault import ~/vault-backup.db    # 在另一台设备导入（需 --yes 确认）

# 5. 其他
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

覆盖密码学往返/篡改、存储 CRUD/改密/导出导入、CLI 端到端、HTTP API 全链路
（含鉴权、限速、静态 GUI、首启初始化）。

## ⚠️ 注意事项

- 默认只监听 `127.0.0.1`；如需 `--host 0.0.0.0` 供局域网使用，请自行评估风险并确保
  Token 安全。
- 不要提交真实密钥；本仓库的测试只用假密钥。
- 跨设备迁移用 `export`/`import` 时，请确保目标设备上没有更新的本地改动（导出/导入是
  整体替换，不做合并）。

## 📄 License

MIT
