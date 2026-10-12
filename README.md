# 诊小通 Agent —— 互联网医院智能服务平台（后端）

> 依据《诊小通 Agent 需求说明书 v2.1.0》与「网页展示」原型实现的后端服务。
> 前端工作台已分离到独立仓库：**`D:\pythonAI\Med_Link_Web`**。

围绕 **分诊、问诊、用药、报告、记录、挂号** 六类高频医疗服务流程构建完整业务闭环，
采用 **FastAPI + 多 Agent 协作 + RAG 知识库 + 联网增强 + 安全合规 + MySQL** 的后端架构。

| 模块 | 位置 | 技术栈 | 默认地址 |
| --- | --- | --- | --- |
| 后端服务 | 本仓库 | Python 3.11 / FastAPI / LangGraph / MySQL 8 | http://127.0.0.1:8012 |
| 前端工作台 | `D:\pythonAI\Med_Link_Web\med_web` | Vue 2.7 / Element UI / axios / Vue CLI 5 | http://127.0.0.1:5178 |

---

## 一、快速开始

```bash
# 0. 前置：MySQL 8 已启动，且 .env 中的账号可登录
#    （建库、建表、写入科室/排班/默认账号都由服务启动时自动完成）

# 1. 安装依赖（推荐 Python 3.11）
pip install -r requirements.txt

# 2. 启动后端（默认 0.0.0.0:8012）
python main.py

# 3. 打开接口文档
#    Swagger UI : http://127.0.0.1:8012/docs
#    OpenAPI    : http://127.0.0.1:8012/openapi.json

# 4. 健康检查（验收项 AC-1，无需登录）
curl http://127.0.0.1:8012/api/health
# → {"status":"ok","database":{"backend":"mysql","database":"med_link_agent",...}}

# 5. 登录拿令牌
curl -X POST http://127.0.0.1:8012/api/user/login \
     -H "Content-Type: application/json" \
     -d '{"account":"admin","password":"123456"}'
# → {"user_id":"2","account":"admin","token":"...","expires_in_hours":72}

# 6. 启动前端工作台（另一个仓库）
cd D:\pythonAI\Med_Link_Web\med_web
npm install && npm run serve
# → http://127.0.0.1:5178   （验收项 AC-2）
```

前端使用说明详见 `D:\pythonAI\Med_Link_Web\med_web\README.md`。

### 验收自测

```bash
python tests/test_acceptance.py
```

覆盖需求 7.2 节 AC-1 ~ AC-10 及登录鉴权、数据落库、报告上传，共 **118 项** 断言，全部通过。
脚本运行结束会自动清理测试账号（`--no-cleanup` 可跳过）。

---

## 二、架构总览

```
                        ┌──────────────── HTTP / JSON ────────────────┐
   Vue 工作台  ───────►  │  FastAPI (routers/api/*)                    │
   (Med_Link_Web)       │      ↓   Bearer 令牌鉴权 (utils/security)    │
                        │  Service 层 (service/*)                     │
                        │      ↓                                      │
                        │  ┌── 多 Agent 编排 (agent/graph.py) ──┐      │
                        │  │ Router → Context → RAG ∥ Research │      │
                        │  │        → Reasoning → Formatter(条件)      │
                        │  │        → Safety                    │      │
                        │  └────────────────┬──────────────────┘      │
                        │      ↓            ↓             ↓          │
                        │  DAO 层       RAG 知识库     大模型/联网     │
                        └───────┬────────────┬─────────────┬─────────┘
                                ↓            ↓             ↓
                             MySQL 8      Markdown     OpenAI 兼容
                          med_link_agent  knowledge_base   / Ollama
```

### 目录结构

| 目录 | 说明 |
| --- | --- |
| `main.py` | FastAPI 应用入口，注册路由、CORS、全局异常、启动自检 |
| `config/` | 全局配置（`.env` 驱动，含全部默认值） |
| `routers/api/` | 接口层（8 个路由模块） |
| `service/` | 业务服务层（鉴权、对话、报告、记录、预约、设置） |
| `agent/` | 多 Agent 编排（图、节点、提示词、规则引擎、大模型客户端、联网检索） |
| `rag/` | 知识库检索（轻量倒排+余弦 / 可选 Chroma 向量库） |
| `dao/` | 数据访问层（9 个 DAO，字段严格对齐现有 MySQL 表） |
| `schema/dto/` | 请求/响应数据结构（Pydantic） |
| `utils/` | 数据库封装、表结构声明、枚举映射、鉴权、合规、文本工具 |
| `data/knowledge_base/` | 本地 Markdown 知识库（10 篇） |
| `tests/` | 验收自测脚本（118 项断言）+ 测试数据清理脚本 |
| `docs/sql/` | `schema.sql`（建表）与 `seed.sql`（科室/排班/默认账号） |

---

## 三、数据库（MySQL）

### 3.1 连接配置

数据库配置全部来自 `.env`（**只使用 MySQL，不再支持 SQLite**）：

```ini
DB_BACKEND=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=med_link_agent
```

> **重要变更**：早期版本提供 `DB_BACKEND=auto`「MySQL 连不上就静默降级 SQLite」。
> 该行为会让系统在 MySQL 不可用时把数据写进本地文件、表面上一切正常，
> 实际数据库里一条记录都没有。现已彻底移除：连不上 MySQL 会在启动时直接报错退出。

### 3.2 表结构（与现有库完全一致）

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `user` | 用户账号 | `id` / `account` / `password`(MD5) / `create_time` |
| `user_tokens` | 登录令牌（本项目新增） | `token` / `user_id` / `expire_time` |
| `departments` | 科室字典（16 个） | `department_code` / `department_name` / `sort_order` / `is_active` |
| `doctor_schedules` | 医生排班号源（32 条） | `department_code` / `doctor` / `doctor_title` / `total_slots` / `booked_slots` |
| `sessions` | 会话 | `id`(char36) / `user_id` / `title` / `create_time` / `update_time` |
| `messages` | 会话消息 | `session_id` / `role` / `content` / `metadata`(JSON) |
| `encounters` | 问诊记录 | `user_id` / `scene` / `chief_complaint` / `risk_level` / `department` / `metadata`(JSON) |
| `health_profiles` | 健康档案 | `id`(char36) / `user_id`(int) / `age` / `gender` / JSON 病史 |
| `appointments` | 预约 | `user_id` / `department` / `doctor` / `visit_date` / `period` / `time_slot` / `status` |
| `reports` / `report_items` | 报告与指标明细 | `report_type` / `abnormal_flag` / `reference_range` 等 |
| `report_files` | 报告附件（上传功能新增） | `report_id` / `file_name` / `file_path` / `file_size` / `parse_note` |

字段命名遵循现有库的 **`create_time` / `update_time`** 约定（不是 `created_at`）。

首次启动会自动建库建表并写入种子数据；也可手工导入：

```bash
mysql -uroot -proot < docs/sql/schema.sql
mysql -uroot -proot med_link_agent < docs/sql/seed.sql
```

### 3.3 枚举值约定

数据库注释对枚举的写法是「英文枚举；中文」，本项目统一 **入库存英文枚举**，
**出库在 Service 层转回中文**，前端拿到的仍是「中风险」这类可直接展示的值。

| 字段 | 入库值 | 出库展示 |
| --- | --- | --- |
| `encounters.risk_level` | `low` / `medium` / `high` | 低风险 / 中风险 / 高风险 |
| `appointments.period` | `morning` / `afternoon` | 上午 / 下午 |
| `appointments.status` | `booked` / `cancelled` | 已预约 / 已取消 |
| `reports.report_type` | `laboratory` / `examination` | 检验 / 检查 |
| `report_items.abnormal_flag` | `normal` / `high` / `low` / `abnormal` | 正常 / 偏高 / 偏低 / 异常 |
| `health_profiles.gender` | `male` / `female` / `other` | 男 / 女 / 其他 |

---

## 四、登录鉴权

账号体系完全基于数据库 `user` 表（密码 MD5 存储，与现有 `admin` 记录一致）。

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/user/register` | POST | 注册（账号 3~32 位，密码 ≥6 位），成功即返回令牌 |
| `/api/user/login` | POST | 校验密码 → 写入 `user_tokens` → 返回令牌（默认 72 小时） |
| `/api/user/logout` | POST | 删除令牌，**立即失效** |
| `/api/user/profile` | GET | 当前用户信息 + 会话/记录/预约统计 |
| `/api/user/password` | POST | 修改密码，并注销该用户全部令牌 |

**默认账号：`admin` / `123456`**

鉴权规则（可在 `.env` 用 `AUTH_REQUIRED` 关闭）：

- **公开**：`GET /api/health`、`POST /api/user/login`、`POST /api/user/register`
- **需要令牌**：其余全部接口，请求头 `Authorization: Bearer <token>`

> 业务接口**不再接受前端传入的 `user_id`**：用户身份一律由令牌解析，
> 会话、记录、报告、预约均按当前登录用户隔离，避免越权访问他人数据。

---

## 五、多 Agent 编排链路

一次请求的完整链路（需求 3.8）：

| # | Agent | 职责 | 并发 |
| --- | --- | --- | --- |
| 1 | **RouterAgent** | 场景路由（分诊 / 问诊 / 用药） | |
| 2 | **ContextAgent** | 患者上下文 + 历史对话 + 本地症状线索与风险评估 | |
| 3 | **RAGAgent** | 本地知识库召回（默认 6 条） | ∥ |
| 4 | **ResearchAgent** | 联网 DeepResearch（默认 3 条） | ∥ |
| 5 | **ReasoningAgent** | 大模型结构化医学推理 | |
| 6 | **FormatterAgent** | 输出非法 JSON 时结构化修复（条件触发） | |
| 7 | **SafetyAgent** | 合规检查 + 免责声明 | |

### 结构化输出降级顺序

```
JSON 解析 → 叙事解析 → JSON 修复 → 叙事重试 → 规则兜底
```

任何一步成功即停止；全部失败则使用本地规则引擎结果（`agent/rules.py`）。

---

## 六、关键设计要点

### 1. 科室与排班全部来自数据库

- 科室列表读 `departments` 表（**16 个，含急诊科**），不再硬编码；
- 医生花名册与总号源读 `doctor_schedules` 表（每科室 2 名医生）；
- 某天某时段的剩余号源 = `total_slots` − `appointments` 中该号源 `status='booked'` 的条数；
- 每次预约 / 取消后回写 `doctor_schedules.booked_slots`，保证计数器与明细一致；
- **高风险**分诊结果统一引导到「急诊科」。

### 2. 报告按需落库 + 报告上传

用户首次访问 `/api/reports` 时，把内置的 3 份模拟报告
（血常规 / 胸部 CT / 肝肾功能）写入 `reports` + `report_items`，之后全部读库。

**报告上传**（`POST /api/reports/upload`）支持把真实报告文件解析入库：

| 环节 | 说明 |
| --- | --- |
| 支持格式 | PDF、txt/csv/md、png/jpg/webp、docx、xlsx（可在 `.env` 用 `UPLOAD_ALLOWED_EXT` 调整） |
| 大小限制 | 默认 10 MB（`UPLOAD_MAX_MB`） |
| 文本抽取 | PDF 用 pdfminer.six（回退 pypdf）；文本按 UTF-8→GBK 解码；Word/Excel 依赖 python-docx / openpyxl |
| 指标识别 | 正则解析「名称 结果 单位 参考范围 异常标记」；解析不到时由**大模型兜底**抽取 |
| 自动推断 | 报告名称、类型（检验/检查）、开单科室、异常标记（与参考范围比较得出） |
| 附件留存 | 原始文件存 `data/uploads/<user_id>/`，元信息写入 `report_files` 表 |
| 后续操作 | 可在列表直接下载附件、删除报告（同时清理明细与磁盘文件） |

> 图片报告本环境未启用 OCR，仅保存附件并提示人工补录；PDF 与文本可全自动解析。
> `docs/samples/` 下提供了两份示例报告文件，可直接用于体验上传功能。

### 3. 无 API Key 可降级运行（验收 AC-10）

大模型客户端不可用时自动切换到 **本地规则引擎 + 知识库检索**，
仍能输出推荐科室、风险等级、依据、追问与健康建议；
知识库检索默认使用 `lightweight` 后端（关键词倒排 + TF-IDF 余弦相似度），完全离线可用。

### 4. 联网增强用国内可达的搜索引擎

`agent/research.py` 支持多引擎按优先级回退，由 `DEEP_SEARCH_ENGINES` 配置：

| 顺序 | 引擎 | 入口 | 说明 |
| --- | --- | --- | --- |
| 1 | `bing` | `cn.bing.com` | **默认**，境内可直连 |
| 2 | `duckduckgo` | `html.duckduckgo.com` | 备用；境内通常连接超时 |
| — | `bing_intl` | `www.bing.com` | 可选，境外环境适用 |

> **修复记录**：早期版本只用了 DuckDuckGo 两个入口，而 DuckDuckGo 在境内网络不可达
> （`ConnectTimeout`），导致「开启联网增强」后始终只能拿到降级提示
> 「联网检索当前不可用」。现已把 **Bing 中国** 设为默认引擎，
> 实测可正常返回中文医学资料（百度百科、默沙东诊疗手册、丁香医生等）。

所有引擎都失败时仍返回一条降级证据（内容会带上「已尝试：Bing 中国、DuckDuckGo」），
保证主链路不中断。当前联网状态可在「系统设置」页查看。

### 5. 医疗合规硬约束（验收 AC-9）

`utils/compliance.py` 的 `compliance_guard()` 对最终回答执行：

- 替换绝对化/诊断性表达（`确诊为` → `需要由医生评估是否为` 等 20+ 条规则）；
- 剔除具体处方剂量（正则识别 `每次X片`、`X mg/日` 等）；
- 保证免责声明存在：*以上内容仅用于健康科普和就医参考，不能替代医生诊断、处方或治疗。*

---

## 七、接口清单

Base URL：`http://127.0.0.1:8012`

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/health` | 公开 | 健康检查（含 MySQL 连接状态） |
| POST | `/api/user/register` | 公开 | 注册 |
| POST | `/api/user/login` | 公开 | 登录 |
| POST | `/api/user/logout` | 需登录 | 退出登录 |
| GET | `/api/user/profile` | 需登录 | 当前用户信息 |
| POST | `/api/user/password` | 需登录 | 修改密码 |
| POST | `/api/chat` | 需登录 | 通用问诊 |
| POST | `/api/triage` | 需登录 | 智能分诊 |
| POST | `/api/consultation` | 需登录 | 线上问诊 |
| POST | `/api/medication` | 需登录 | 用药咨询 |
| GET | `/api/sessions` | 需登录 | 我的会话列表 |
| GET | `/api/sessions/{id}/messages` | 需登录 | 会话消息（最多 100 条） |
| DELETE | `/api/sessions/{id}` | 需登录 | 删除指定会话 |
| DELETE | `/api/sessions` | 需登录 | 清空数据（普通用户清自己的，admin 清全库） |
| GET | `/api/records` | 需登录 | 我的问诊记录（`days`） |
| GET | `/api/records/{id}` | 需登录 | 问诊记录详情 |
| GET | `/api/reports` | 需登录 | 我的报告列表 |
| POST | `/api/reports/upload` | 需登录 | **上传报告文件并自动解析指标**（multipart） |
| GET | `/api/reports/{id}/interpret` | 需登录 | 报告 AI 解读 |
| GET | `/api/reports/{id}/file` | 需登录 | 下载报告原始附件 |
| DELETE | `/api/reports/{id}` | 需登录 | 删除报告（含指标明细与附件） |
| GET | `/api/departments` | 需登录 | 科室列表（16 个） |
| GET | `/api/departments/schedules` | 需登录 | 全部医生排班号源 |
| GET | `/api/appointments/schedule` | 需登录 | 科室排班（`department`、`days`） |
| POST | `/api/appointments` | 需登录 | 创建预约 |
| GET | `/api/appointments` | 需登录 | 我的预约 |
| DELETE | `/api/appointments/{id}` | 需登录 | 取消预约 |
| POST | `/api/appointments/intent` | 需登录 | 预约意图识别（扩展） |
| GET | `/api/metrics` | 需登录 | 平台指标（当前用户） |
| GET | `/api/settings` | 需登录 | 系统设置状态 |
| GET | `/api/agent/status` | 需登录 | Agent 运行态 |
| POST | `/api/knowledge/reload` | 需登录 | 重建知识库索引 |

---

## 八、配置说明

全部配置项见 `.env`，均有默认值。核心项：

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8012` | 服务端口 |
| `DB_BACKEND` | `mysql` | 仅支持 MySQL |
| `MYSQL_*` | 127.0.0.1:3306 / root / root / med_link_agent | MySQL 连接参数 |
| `AUTH_TOKEN_EXPIRE_HOURS` | `72` | 令牌有效期（小时） |
| `AUTH_REQUIRED` | `true` | 是否强制登录 |
| `ENABLE_LLM` | `true` | 是否启用大模型 |
| `LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI 兼容端点 |
| `LLM_MODEL` | `qwen2.5:7b` | 模型名称 |
| `RAG_BACKEND` | `lightweight` | `lightweight` / `chroma` |
| `RAG_CHAIN_TOP_K` | `6` | 分诊/问诊链路召回条数 |
| `DEEP_SEARCH_ENABLED` | `false` | 联网增强总开关（前端提交时可对单次请求勾选开启） |
| `DEEP_SEARCH_ENGINES` | `bing,duckduckgo` | 搜索引擎优先级；`bing` = `cn.bing.com`，境内可直连 |
| `HISTORY_MEMORY_LIMIT` | `12` | 推理使用的历史对话条数 |

> 接口**不返回 API Key 明文**，仅返回 `api_key_configured` 布尔值（需求 3.7）。

---

## 九、知识库

`data/knowledge_base/` 下 10 篇 Markdown：

发热与感染、高血压生活方式管理、糖尿病与血糖管理、胸痛呼吸困难急症提醒、
胃肠道症状处理、医疗合规与问诊边界、妇科月经异常与痛经就诊建议、
腰痛骨科与泌尿妇科鉴别、常见感冒药与止痛药用药安全、腹泻腹痛消化科就诊建议。

检索实现（`rag/lightweight.py`）：按 Markdown 标题切块 → 构建关键词倒排索引 →
TF-IDF 向量化 → 余弦相似度排序 → 返回 `Evidence(source, title, score, content)`。

---

## 十、文档与截图

- 后端设计说明书（Word）：`docs/诊小通Agent后端设计说明书.doc`
- 需求规格说明书（提取文本）：`docs/需求规格说明书-提取文本.txt`
- 数据库建表 / 种子数据：`docs/sql/schema.sql`、`docs/sql/seed.sql`
- **原型截图**（来自「网页展示.doc」）：`docs/ui/01~04-*.png`
- **实现效果截图**（真实运行截图，含登录页）：`docs/ui/frontend/01~10-*.png`
