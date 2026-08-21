# apikey-vault — 详细项目规划

> 面向 Codex / Claude 等 AI Agent 的本地加密 API 密钥管理器

## 1. 背景与目标

AI Agent（Codex、Claude CLI 等）在完成任务时经常需要 API 密钥（OpenAI、Anthropic、
GitHub Token、第三方服务密钥等）。常见的做法是把密钥明文写在 `.env` 或 shell profile 里，
风险很高：

- 明文密钥可能被意外提交进 Git 仓库；
- Agent 读取文件时可能把密钥内容带进对话上下文、日志或补丁；
- 密钥分散在多处，难以统一管理、轮换和回收。

本项目提供一个**本地、加密、可供 Agent 程序化调用**的密钥保险箱：

- **保存**：`apivault store <name> [--value <value>]`，交互式输入或从 stdin 读取；
- **加密**：所有密钥在磁盘上均为 AES-256-GCM 密文，主密码经 scrypt 派生密钥，密码本身
  永不落盘；
- **提供给 AI 使用**：Agent 既可以通过 CLI（`apivault get <name>`）读取，也可以通过
  本地 HTTP API（`apivault serve`）按需获取，无需接触明文存储文件。

## 2. 核心原则

| 原则 | 说明 |
| --- | --- |
| 安全第一 | 磁盘上无明文；不写日志；响应头禁用缓存；目录/文件权限收紧 |
| 极简依赖 | 仅依赖 `cryptography`（业界审计过的密码学库），HTTP 服务用 Python 标准库 |
| 人机双界面 | 人类用 CLI，Agent 用 CLI 或 HTTP API |
| 本地优先 | 默认只监听 127.0.0.1，密钥不出本机 |
| 可测试 | 密码学、存储、CLI、HTTP 全链路都有自动化测试 |

## 3. 威胁模型与安全设计

### 3.1 威胁模型

防御目标：即使 `vault.db` 文件被复制走、或笔记本丢失，攻击者也无法在不知道主密码的
情况下还原任何密钥。

- **假设**：运行本工具的主机本身可信（攻击者无法在工具运行时读取进程内存）。
- **不防御**：运行期间的主机 root 级内存读取、键盘记录器、已解锁状态下的恶意进程。

### 3.2 密码学设计

| 组件 | 选择 | 理由 |
| --- | --- | --- |
| 密钥派生 | scrypt（N=2^17, r=8, p=1） | OWASP 推荐的内存硬 KDF，抗 GPU 暴力破解 |
| 对称加密 | AES-256-GCM（`cryptography` 库） | 认证加密：同时保证机密性与完整性，防篡改 |
| 盐 | 16 字节 CSPRNG，每库随机，存于 vault 元数据 | 防彩虹表 |
| nonce | 12 字节 CSPRNG，**每条密钥独立** | 保证相同明文产生不同密文 |
| 主密码验证 | 加密一段固定 magic（`apikey-vault-verify-v1`） | 用解密是否成功来验证密码，密码本身不落盘 |
| 会话令牌 | 32 字节 `secrets.token_urlsafe`，内存中只存 SHA-256 摘要，带 TTL | Agent 不需要每次输入主密码 |

### 3.3 存储与权限

```
~/.apikey-vault/
├── vault.db          # SQLite，0600
└── (目录权限 0700)
```

可用 `APIVAULT_DIR` 环境变量覆盖存储位置。SQLite 表结构：

- `keys(name PK, description, payload BLOB, created_at, updated_at)`
  - `payload = nonce(12B) || AES-GCM-ciphertext || tag(16B)`
- `meta(key PK, value)` — 存 salt、verify blob、版本、KDF 参数

### 3.4 密码输入方式（按安全性排序）

1. `--password-file <路径>`：从 0600 权限文件读取（推荐给 Agent 的长期方案）；
2. `APIVAULT_PASSWORD` 环境变量：方便，但有进程环境泄漏面，文档中注明；
3. 交互式 `getpass` 输入：适合人类手动使用，不回显。

## 4. 功能清单

### 4.1 CLI（人类 + Agent 通用）

| 命令 | 说明 |
| --- | --- |
| `apivault init` | 初始化新保险库（设置主密码） |
| `apivault status` | 查看保险库路径、是否已初始化、是否已解锁 |
| `apivault store <name>` | 保存/更新密钥（`--value` / `--stdin` / 交互输入） |
| `apivault get <name>` | 输出密钥值（仅 stdout 输出值本身，方便 Agent 捕获） |
| `apivault list` | 列出密钥名与元数据（绝不输出值） |
| `apivault info <name>` | 查看单条元数据（创建/更新时间、描述） |
| `apivault delete <name>` | 删除密钥（需 `--yes` 确认） |
| `apivault rename <old> <new>` | 重命名 |
| `apivault export-env` | 输出 `export NAME='...'` 行，供 shell 一次性加载 |
| `apivault change-password` | 修改主密码（重新加密所有密钥） |
| `apivault serve` | 启动本地 HTTP API（供 Agent 调用） |

### 4.2 HTTP API（Agent 专用）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/v1/health` | 健康检查，返回是否已初始化/已解锁 |
| `POST` | `/v1/unlock` | 用主密码换取短期 Bearer Token |
| `POST` | `/v1/lock` | 立即使当前 Token 失效 |
| `GET` | `/v1/keys` | 列出密钥元数据 |
| `PUT` | `/v1/keys/{name}` | 保存/更新密钥 |
| `GET` | `/v1/keys/{name}` | 获取密钥值 |
| `DELETE` | `/v1/keys/{name}` | 删除密钥 |

- 默认监听 `127.0.0.1`，可用 `--host`/`--port` 覆盖（文档中警示风险）；
- Token 默认 TTL 12 小时，`--ttl` 可调；
- `/v1/unlock` 有简单的失败限速（5 次失败 → 429 冷却 60 秒）；
- 所有响应 `Cache-Control: no-store`，防止密钥被浏览器/代理缓存。

## 5. 目录结构

```
apikey-vault/
├── PLAN.md                 # 本文档
├── README.md               # 总览 + 快速开始
├── AGENTS.md               # 给 AI Agent 的使用说明（会被 Codex/Claude 自动读取）
├── LICENSE                 # MIT
├── pyproject.toml          # 打包与依赖声明
├── apivault/
│   ├── __init__.py         # 版本号
│   ├── __main__.py         # python -m apivault
│   ├── crypto.py           # scrypt KDF + AES-256-GCM 加解密
│   ├── store.py            # SQLite 存储层（含解锁/锁定/改密）
│   ├── passwords.py        # 密码读取辅助（env/file/getpass）
│   ├── cli.py              # argparse CLI
│   └── server.py           # ThreadingHTTPServer REST API
├── docs/
│   └── API.md              # HTTP API 详细文档
└── tests/
    ├── test_crypto.py
    ├── test_store.py
    ├── test_cli.py
    └── test_server.py
```

## 6. 实现要点

- `store.py` 持有解锁后的 32 字节密钥于内存，`lock()` 时用 `ctypes` 尽力清零；
- `get` 输出值到 stdout，所有提示/日志走 stderr，保证 Agent 捕获纯值；
- 服务器 Token 内存中仅存 SHA-256 摘要，服务器不落盘任何 Token；
- 每个 HTTP 请求在独立线程处理，SQLite 连接按线程管理（`check_same_thread=False` + 锁）。

## 7. 测试策略

- 密码学：加解密往返、错误密钥/篡改密文必须失败；
- 存储：初始化、错误密码、CRUD、改密后旧密码失效；
- CLI：子进程端到端（init → store → get → list → delete → export-env）；
- HTTP：真实启动服务，覆盖认证、CRUD、限速、404/401 等路径。

## 8. 交付与发布

- 本地 `git init`，提交全部源码与文档（**不含任何真实密钥/测试假密钥的明文**）；
- 用 `gh repo create` 在 sudorm-rf0 账号下创建仓库并推送（默认 **private**，可随时改 public）；
- 提供 README 快速开始 + AGENTS.md 让 Agent 开箱即用。

---

## 9. v0.2 更新：图形界面 + 多端 + 独立端

在 v0.1（CLI + HTTP API）基础上新增：

### 9.1 图形界面（GUI）

- 服务端新增静态资源目录 `apivault/web/`（`index.html` / `style.css` / `app.js`），
  同源提供，无构建步骤、无 CORS。
- 设计锚点：**Industrial**（暖黑底、等宽字体、1px 边框、语义信号色绿/红/琥珀），
  契合“安全仪器”的定位；全部图标为内联 SVG（非 Unicode 字符）。
- 界面流程：
  - 首启 `Initialize vault` 界面（POST `/v1/init` 创建保险库并自动解锁）；
  - 锁定门禁 `Vault locked`（主密码 / Bearer Token 两种解锁方式）；
  - 解锁后：左侧密钥库（过滤、计数）+ 右侧详情（显示/隐藏、复制、重命名、删除）；
  - 底部状态栏：锁定、改密、导出加密 vault、导入加密 vault。
- 安全：CSP `default-src 'self'`、`Cache-Control: no-store`、`X-Frame-Options: DENY`、
  路径穿越防护；密钥值仅在“显示/复制”时按需拉取，不在内存中长期保留。

### 9.2 多端可用

- `--host 0.0.0.0`：局域网内任意设备浏览器访问 GUI（需 Bearer Token）。
- `export` / `import`（CLI 与 API）：加密 vault 文件整体迁移；因为全是密文，
  跨设备/跨网络传输安全；目标设备用原主密码解锁。
- 静态 Token（`--token`）在锁定后保留：`Lock` 只吊销动态会话 Token，静态 Agent
  Token 在重新解锁后继续可用（锁定期间返回 423）。

### 9.3 独立端

- `apivault serve --open`：启动服务并自动打开默认浏览器。
- `scripts/build_app.sh`：构建 `dist/apikey-vault.app`（macOS），内嵌 Python
  virtualenv + 项目安装包，无需全局依赖；双击启动、日志写 `~/.apikey-vault/app.log`。

### 9.4 新增 API

| 端点 | 说明 |
| --- | --- |
| POST `/v1/init` | 首启创建保险库（未初始化时） |
| POST `/v1/password` | 修改主密码（需旧密码） |
| GET `/v1/export` | 下载加密 vault 文件 |
| POST `/v1/import` | 上传并整体替换 vault（吊销 Token、重新锁定） |

### 9.5 测试

38 个测试全部通过，覆盖：/v1/init、改密 API、导出/导入（含非法文件拒绝）、
静态 GUI 服务与路径穿越、静态 Token 跨 Lock 存活、CLI export/import 端到端。
GUI 通过真实 Chrome（playwright-core）做了端到端验证：首启初始化 → 解锁 →
增删改查 → 显示/复制 → 改密 → 导出 → 锁定，控制台零报错。


---

## 10. v0.3 更新：原生 macOS App（Apple 设计）

用 `build-macos-apps` 技能包（swiftui-patterns / liquid-glass / build-run-debug）
构建原生 SwiftUI 独立端：

- **工程**：`macos/Package.swift`，三个 target：
  - `APIVaultCore`：Swift 服务层（`APIClient` actor、`BackendManager` 进程托管）；
  - `APIVaultApp`：SwiftUI 界面（App/Views/Support 按职责拆分）；
  - `SelfTest`：无 UI 端到端自检（真实拉起 Python 后端，跑完整 API 往返）。
- **设计**（遵循 liquid-glass）：`NavigationSplitView` 分栏 + 系统材质、工具栏原生按钮
  与 Menu 分组、`searchable` 挂载在分栏层、解锁/初始化用系统材质卡片（macOS 26 自动获得
  Liquid Glass 系统外观）、自适应深/浅色，未手搓任何系统组件。
- **后端**：App 启动时自动拉起内嵌 Python venv 的 `apivault serve`（健康检查通过后连接；
  已运行则直接复用），退出时终止子进程；日志写 `~/.apikey-vault/app.log`。
- **功能**：首启初始化、主密码/Bearer Token 解锁、密钥库（搜索/过滤）、单条表单或
  多行 `NAME=value` 粘贴输入、显示/隐藏（60s 自动隐藏）、一键复制、重命名、删除、
  改密、加密导出/导入。
- **验证**：`apikey-vault-selftest` 全链路 SELFTEST OK（init→CRUD→改密→锁定→旧密码
  拒绝→删除→导出/导入往返）；`script/build_and_run.sh --verify` 确认 .app 启动并
  自动拉起后端（健康检查 OK）。
