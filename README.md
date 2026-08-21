# apikey-vault 🔐

本地加密的 **API 密钥保险箱**，带图形界面，专为 AI Agent（Codex / Claude 等）与多设备使用设计。

把密钥明文写在 `.env` 或 shell profile 里很危险：可能被误提交进 Git、被 Agent 带进对话
上下文、散落各处难以轮换。`apikey-vault` 把所有密钥用 **AES-256-GCM** 加密后存在本地
SQLite 中：人类用**图形界面或 CLI** 管理，Agent 用 CLI 或本地 HTTP API 按需获取。

## ✨ 特性

- **图形界面（GUI）**：浏览器单页应用，锁定/解锁门禁、密钥库列表、**密钥粘贴输入框**
  （支持多行 `NAME=value`、`export` 前缀、带引号值、裸值+名称）、密钥输入/编辑、一键复制、
  显示/隐藏、重命名、删除、改密、导出/导入、首启初始化。
- **加密存储**：AES-256-GCM 认证加密 + scrypt 密钥派生；主密码永不落盘；磁盘上无明文。
- **人类 CLI**：`store` / `get` / `list` / `delete` / `rename` / `export-env` / `change-password` / `export` / `import`。
- **Agent HTTP API**：`apivault serve` 启动本地 REST 服务，Bearer Token 鉴权，默认只监听 `127.0.0.1`。
- **多端可用**：`--host 0.0.0.0` 后同一局域网内手机/电脑浏览器直接访问 GUI；加密 vault 文件可
  导出/导入到任意设备（密文传输，安全）。
- **原生 macOS 独立端（Apple 设计）**：SwiftUI 应用，遵循苹果设计语言（系统材质、
  Liquid Glass、自适应深/浅色、原生分栏与工具栏）；内嵌 Python 加密后端，双击即用。
- **独立端（Web 版）**：`apivault serve --open` 一键打开浏览器 GUI；
  `scripts/build_app.sh` 可打包 `apikey-vault-web.app`（内嵌 Python 环境）。
- **安全细节**：每条密钥独立 nonce；会话 Token 内存中只存 SHA-256 摘要并带 TTL；
  `/v1/unlock` 失败限速；响应 `Cache-Control: no-store` + CSP；vault 文件权限 0600；
  **无操作 15 分钟自动锁定**（Web GUI 与原生 App）；**导入前自动备份旧 vault**
  （保留最近 5 份 `vault.db.backup-*`）。
- **极简依赖**：运行时仅依赖 `cryptography`，HTTP 服务与 GUI 用 Python 标准库 + 原生 JS。

## 📸 界面预览

![锁定界面](docs/screenshot-locked.png)
![密钥库（含粘贴输入框）](docs/screenshot-unlocked.png)
![密钥详情](docs/screenshot-detail.png)
![粘贴密钥](docs/screenshot-paste.png)

> 原生 macOS App 使用相同的加密后端与界面流程（SwiftUI 实现，遵循 Apple HIG / Liquid Glass）。

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
- 之后每次打开：输入主密码解锁 → 在顶部 **Paste a key** 框直接粘贴密钥
  （`OPENAI_API_KEY=sk-...`，可一次粘贴多行；`Cmd/Ctrl+Enter` 快速保存），
  或点左侧 **Add key** 逐个填写。
- 底部栏可**锁定 / 改密 / 导出加密 vault / 导入加密 vault**。

### 多端访问（局域网）

```bash
apivault serve --host 0.0.0.0 --port 8417 --token <你的agent令牌>
```

手机或其它电脑用浏览器访问 `http://<本机IP>:8417`，在「Use a bearer token instead」
输入令牌即可连接（保险库解锁后可用）。注意：`--host 0.0.0.0` 会把服务暴露到局域网，
务必使用强令牌，且仅限可信网络。

### 原生 macOS App（Apple 设计）

用 SwiftUI + 苹果设计语言构建的原生应用：系统材质与 Liquid Glass、自适应深/浅色、
原生分栏密钥库与工具栏；内嵌 Python 加密后端，双击即用，无需预装任何依赖。

```bash
./script/build_and_run.sh          # 编译并启动 dist/apikey-vault.app
./script/build_and_run.sh --verify # 启动并确认进程存活
open dist/apikey-vault.app         # 之后直接双击启动
```

- 首启显示「Initialize vault」创建保险库，之后每次输入主密码解锁。
- 支持粘贴多行 `NAME=value` 密钥、显示/复制、改密、加密导出/导入。
- 数据与 CLI 共用 `~/.apikey-vault`；后端日志在 `~/.apikey-vault/app.log`。

> 需要 Xcode 工具链（`xcode-select --install`）。Web 版打包请用
> `./scripts/build_app.sh`（生成 `dist/apikey-vault-web.app`）。

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

## 🔒 Key Guard：防止密钥以明文进入 AI 对话框

这个产品存在的意义：**密钥永远不应该以明文出现在 AI 对话框里**。三层防护：

### 1. 界面层（Web GUI 与原生 App）

- **复制默认给安全占位符**：点 Copy 复制的是 `{{OPENAI_API_KEY}}` 而不是真实值——
  即使误粘贴进 AI 对话框，泄露的也只是占位符。
- **明文复制需显式确认**：点 Plaintext… 会弹出警告，确认后才会复制真实密钥，
  并提示「切勿粘贴进 AI 对话框」。
- **原生 App 额外自动清空**：明文复制后 30 秒自动清空剪贴板。
- **屏幕明文警示**：Reveal 显示真实值时，界面显示橙色警告条。
- **无操作自动锁定**：解锁后 15 分钟无操作，Web GUI 与原生 App 都会自动锁定。

### 2. 浏览器扩展（Chrome / Edge，MV3）

`extension/` 目录是一个即装即用的浏览器扩展，会在**所有网页的输入框**（包括
ChatGPT、Claude 等 AI 对话输入框）拦截常见 API 密钥格式：

- 支持：`sk-`（OpenAI）、`sk-ant-`（Anthropic）、`ghp_`/`github_pat_`（GitHub）、
  `AIza`（Google）、`xoxb-`（Slack）、`AKIA`（AWS）、`sk_live_`/`sk_test_`（Stripe）、
  JWT 形态 Token 等。
- **粘贴即拦截**：检测到密钥的粘贴会被阻止并替换为 `{{REDACTED}}`，同时弹出警告；
- **输入即脱敏**：手动输入密钥也会被实时脱敏；
- **可选 vault 集成**：在扩展设置里启用「Resolve keys against the local vault」、
  填入 vault 服务地址（默认 `http://127.0.0.1:8417`，可改端口）与
  `apivault serve --token` 的令牌后，匹配本地 vault 的密钥会被替换为
  `{{vault:KEY_NAME}}`，AI 可用 `apivault get KEY_NAME` 安全取用。

安装（Chrome/Edge 开发者模式 → 加载已解压的扩展程序 → 选择 `extension/` 目录）。

![Key Guard 拦截示例](docs/screenshot-guard.png)

### 3. Agent 协作规范

见 [AGENTS.md](AGENTS.md)：Agent 通过 `apivault get <name>` / `{{vault:NAME}}`
占位符获取密钥，绝不要求用户在对话框粘贴明文。

## 🔒 安全模型

- **威胁**：vault 文件被复制、磁盘丢失 → 无主密码无法还原任何密钥。
- **假设**：运行时的本机可信；不防御键盘记录器 / 已解锁状态下的内存读取。
- **设计**：scrypt(N=2^17,r=8,p=1) 派生 32 字节密钥；AES-256-GCM 认证加密；密码本身
  永不存储，仅通过解密固定 magic 校验；内存中尽力清零敏感字节。
- 详细规划见 [PLAN.md](PLAN.md)。

## ✅ 测试

```bash
./script/test.sh        # Python 测试 + Key Guard 模式测试 + Swift 自检
# 或单独运行：
python -m pytest
node tests/test_patterns.js
```

覆盖密码学往返/篡改、存储 CRUD/改密/导出导入（含导入自动备份）、CLI 端到端、
HTTP API 全链路（含鉴权、限速、静态 GUI、首启初始化）、Key Guard 密钥模式、
Swift 客户端↔真实后端往返。

## 🛠️ 故障排查

- **端口被占用**：原生 App 或 `apivault serve` 默认用 `8417`。如果 8417 已被其它
  进程占用，原生 App 会连接已有服务（若其 vault 路径不同请注意）；CLI 用
  `--port` 指定其它端口，扩展在设置里改「Vault server URL」。
- **扩展在开发者模式加载后不生效**：新版 Chrome/Edge 会默认禁用命令行加载的扩展；
  正式使用请通过 扩展管理 → 开发者模式 → 加载已解压的扩展程序 安装，并确认开关已开启。
- **剪贴板/粘贴被系统拦截**：macOS 首次使用剪贴板或输入监控会请求权限，请在
  系统设置 → 隐私与安全性 中允许。
- **误导入后想恢复**：每次导入前会自动备份，恢复 `~/.apikey-vault/vault.db.backup-*`
  中的文件即可（先停止服务再替换）。

## ⚠️ 注意事项

- 默认只监听 `127.0.0.1`；如需 `--host 0.0.0.0` 供局域网使用，请自行评估风险并确保
  Token 安全。
- 不要提交真实密钥；本仓库的测试只用假密钥。
- 跨设备迁移用 `export`/`import` 时，请确保目标设备上没有更新的本地改动（导出/导入是
  整体替换，不做合并）。

## 📄 License

MIT
