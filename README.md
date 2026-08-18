<p align="center">
  <img src="docs/assets/banner.svg" width="100%" alt="foundry-studio banner" />
</p>

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?style=flat-square&logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)
![i18n](https://img.shields.io/badge/i18n-中_EN_日_RU-important?style=flat-square)
![GPU](https://img.shields.io/badge/GPU-NVIDIA_Ready-green?style=flat-square)
![MCP](https://img.shields.io/badge/MCP-Server_Ready-purple?style=flat-square)
![SSE](https://img.shields.io/badge/SSE-Streaming-gold?style=flat-square)
![LLM](https://img.shields.io/badge/LLM-Tool_Agent-orange?style=flat-square)

**蛋白质设计领域的专业级可视化平台 — 从自然语言到蛋白质结构，一步到位**

[English](README.md) · [中文](README.zh-CN.md)

</div>

---

## 🔬 项目概述

**foundry-studio** 是 [RosettaCommons Foundry](https://github.com/RosettaCommons/foundry)（华盛顿大学蛋白质设计研究所）官方工具箱的**企业级可视化平台**。

> 传统方式：编写冗长的命令行、记忆大量参数、手动管理输入输出文件。
>
> foundry-studio：将这一切转化为直观的 Web 界面——**自然语言描述你的设计目标，AI 帮你规划并执行完整的蛋白质设计流程**。

---

## ✨ 核心能力

### 🤖 AI 驱动的工作流

| 能力 | 说明 |
|------|------|
| 🗣️ **自然语言交互** | 用日常语言描述蛋白质设计需求，LLM Agent 自动拆解并调用正确工具链 |
| 🔧 **智能工具编排** | 支持 tool calling 循环（最多 5 步），工具注册表内置蛋白质设计专用工具（结构验证、序列校验、物性估算、任务管理等） |
| 🔄 **流式 SSE 响应** | token 级联输出 + tool-call 事件实时推送，无需等待完整响应 |
| 📋 **结构化规划** | LLM 生成完整 Agent Plan，前端以可视化卡片方式呈现，审批后执行 |
| 💬 **多轮对话记忆** | SQLite-backed Session Store，支持多轮对话上下文，复杂设计任务可分步确认 |

### 🧬 科学计算引擎

| 能力 | 说明 |
|------|------|
| ⚡ **异步任务队列** | 提交即返回，后台 worker 常驻执行，不阻塞界面，任务状态实时推送 |
| 🖥️ **4 大模型全覆盖** | RFD3（全新蛋白设计）、RFD3NA（核酸复合物设计）、RF3（结构预测）、ProteinMPNN（序列逆折叠） |
| 🏗️ **真实 + 模拟双模式** | 有 GPU + 权重 → 真实科学计算；无权重 → 格式合法的模拟数据，完整流程可演示 |
| 🔄 **崩溃自愈** | Worker 崩溃自动重启，遗留任务自动归队，确保长任务可靠执行 |

### 🌐 现代化前端体验

| 能力 | 说明 |
|------|------|
| 🌍 **四语界面** | 中文 / English / 日本語 / Русский，实时切换，localStorage 记忆偏好 |
| 📦 **权重一键管理** | 模型权重在线安装 / 清理，无需手动下载配置 |
| 📝 **动态参数表单** | 每个模型的参数自动生成带说明的表单，高级用户可直接编辑 JSON |
| 📜 **实时日志流** | SSE 推送运行日志，输出即时可见，错误定位一目了然 |
| 🖼️ **3D 结构查看** | NGL Viewer：卡通 / 球棍 / 表面 / 空间填充 / 丝带 5 种表示，4 种配色方案 |
| 📦 **结果一键下载** | 完整输出 ZIP 包，浏览器直接下载，无需翻找文件系统 |

### 🔌 MCP 生态集成

> MCP（Model Context Protocol）让 foundry-studio 可作为**蛋白质设计能力的 MCP Server**被其他 AI 工具调用。

| MCP 工具 | 功能 |
|----------|------|
| `list_models` | 列举可用模型 |
| `list_jobs` | 查看最近任务列表 |
| `get_job_status` | 查询任务状态 |
| `get_job_logs` | 获取实时日志 |
| `submit_design` | 提交设计任务 |
| `download_results` | 获取结果下载链接 |
| `cancel_job` | 取消任务 |

```bash
# 一键启动 MCP Server
foundry-mcp

# 或通过 MCP Inspector 测试
npx @modelcontextprotocol/inspector python -m foundry_studio.mcp.server
```

---

## 🧩 支持的模型

| 模型 | 任务类型 | 输入 | 输出 |
|------|----------|------|------|
| **RFD3** · RFdiffusion3 | 从零设计全新蛋白骨架（扩散模型） | 设计规格（contigs/hotspots/symmetry） | 设计好的蛋白结构 CIF |
| **RFD3NA** · RFdiffusion3-NA | 设计蛋白-核酸（DNA/RNA）复合物 | 含核酸链的设计规格 | 复合物结构 CIF |
| **RF3** · RosettaFold3 | 从序列预测蛋白三维结构（对标 AF-3 开源替代） | 序列 FASTA / 模板 CIF | 预测结构 CIF + pLDDT 评分 |
| **ProteinMPNN** | 逆折叠：给定骨架设计对应序列 | 骨架 CIF/PDB | 设计序列 FASTA + 结构 |

---

## 🚀 快速开始

```bash
# 克隆项目
git clone https://github.com/syxscott/foundry-studio.git
cd foundry-studio

# 安装（推荐虚拟环境）
python -m venv .venv
.venv\Scripts\pip install -e .     # Windows
# .venv/bin/pip install -e .       # macOS / Linux

# 启动服务
.venv\Scripts\foundry-studio serve  # Windows
# .venv/bin/foundry-studio serve    # macOS / Linux
```

打开浏览器访问 **[http://127.0.0.1:8765](http://127.0.0.1:8765)** 🎉

> API 文档（Swagger）：http://127.0.0.1:8765/docs

**安装模型权重**（需要真实计算时）：

```bash
.venv\Scripts\foundry-studio install-checkpoints rfd3 rf3 proteinmpnn
# 或在网页「环境管理」页面点击安装
```

**开发者模式**（前后端分离）：

```bash
cd frontend && npm install && npm run dev
# 访问 http://localhost:5173
```

---

## 🎭 运行模式说明

| 模式 | 触发条件 | 适用场景 |
|------|----------|----------|
| `auto`（默认） | 真实引擎可用则用，否则自动降级 | 日常使用 |
| `real` | 强制真实引擎，不可用则任务失败 | 生产计算 |
| `simulation` | 强制模拟模式 | 开发 / 演示 / 教学 |

> ⚠️ 模拟模式结果**不是真实预测**，界面会显示琥珀色警告横幅，仅用于流程验证。

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────── 浏览器 ────────────────────────────────────────────┐
│  React SPA（Vite + TypeScript + Tailwind + NGL 3D Viewer + i18next 四语）                      │
│  AgentPanel（流式对话 + tool-call 可视化） · 任务管理 · 3D 查看 · 权重管理                        │
└───────────────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                  │ HTTP/JSON + SSE 流式事件
┌───────────────────────────────────────────────▼─────────────────────────────────────────────────┐
│  FastAPI 后端（Python 3.12+）                                                                       │
│  · REST API：任务 / 模型 / 权重 / 文件 / i18n / Agent / MCP                                     │
│  · SQLite（WAL）：任务队列 + Worker 心跳（零外部依赖）                                             │
│  · ProviderTransport ABC：OpenAI / Anthropic 多 provider 统一抽象                                 │
│  · ToolRegistry：内置蛋白质设计工具 + 用户扩展                                                     │
│  · ToolAgent：LLM 驱动的工具调用循环（max 5 步）                                                  │
│  · SessionStore：多轮对话上下文持久化                                                              │
└────────────────┬───────────────────────────────────┬──────────────────────────────────────────┘
                 │ Subprocess                         │ Heartbeat / Status
    ┌────────────▼────────────┐          ┌───────────▼────────────────┐
    │  Worker 进程（每模型一个） │          │  数据目录                       │
    │  模型权重常驻内存复用     │          │  jobs/<id>/ 输入 + 输出        │
    │  崩溃自动重启             │          │  logs/<id>.log               │
    │  任务自动恢复             │          │  sessions.db                 │
    └─────────────────────────┘          └──────────────────────────────┘
```

**关键技术选型：**

- **ProviderTransport ABC**：provider 解耦，OpenAI / Anthropic 格式统一转换，新增 provider 仅需实现一个 Transport 类
- **ToolRegistry + TTL 缓存**：工具注册与可用性检测分离，30s 缓存避免频繁 IO
- **SSE 流式事件**：`token | tool-call | tool-result | plan | error | done` 六类事件，前端精准渲染
- **SQLite WAL 模式**：并发读写安全，无需独立数据库服务，本机零依赖

---

## 🧪 测试

```bash
.venv\bin\pip install -e ".[dev]"
.venv\bin\pytest backend/tests -q
```

覆盖：任务状态机、API 全流程、错误本地化、模拟引擎产物、权重注册表——全部离线可跑。

---

## 📂 项目结构

```
foundry-studio/
├── backend/foundry_studio/
│   ├── agent/             # ToolAgent（LLM 工具调用循环）
│   ├── api/               # REST 路由 / 错误处理 / 依赖注入
│   ├── engines/           # 模型注册表 + 真实/模拟引擎
│   ├── llm/               # LLM 核心（types / transports / providers）
│   │   └── transports/    # ProviderTransport ABC 实现
│   ├── mcp/               # MCP stdio Server（tools / handlers / transport）
│   ├── session/           # SessionStore（SQLite 多轮对话）
│   ├── tools/             # ToolRegistry + 内置工具
│   ├── workers/           # Worker 进程 + 监督管理器
│   └── i18n.py           # 后端四语消息
├── frontend/src/
│   ├── api/              # 类型化 API 客户端
│   ├── components/        # NGL 查看器 / AgentPanel / 状态徽章
│   ├── i18n/             # 中 / 英 / 日 / 俄 翻译
│   ├── pages/            # 首页 / 任务列表 / 详情 / 环境
│   └── types/            # TypeScript 类型（ChatMessagePart 等）
├── docs/                 # 文档 + 架构图
├── Dockerfile / docker-compose.yml
└── pyproject.toml
```

---

## ❓ 常见问题

**Q：我没有 GPU，能用吗？**
A：能。会自动进入模拟模式，完整流程（界面、队列、3D 查看、下载）都能体验。真实计算需要 NVIDIA GPU + CUDA。

**Q：装了 rc-foundry 但还是模拟模式？**
A：大概率是**权重未下载**。去「环境管理」页面查看各模型权重状态，点击「安装」即可。

**Q：任务一直排队不动？**
A：检查「环境」页面或 `GET /api/health` 的 worker 状态。worker 异常退出后会自动重启，也可设置 `FOUNDRY_WORKER_AUTOSTART=true`（默认开启）。

**Q：能在局域网给其他人用吗？**
A：可以。设置 `FOUNDRY_STUDIO_HOST=0.0.0.0` 和 `FOUNDRY_ALLOW_REMOTE_ACCESS=true`。对外暴露请务必配置反代 + TLS + 鉴权。

**Q：结果文件在哪里？**
A：默认在 `~/.foundry-studio/jobs/<任务id>/`，网页上可直接下载 ZIP。

---

## 🤝 致谢与许可

- 本工具基于 **RosettaCommons Foundry**（[BSD-3-Clause](https://github.com/RosettaCommons/foundry)），模型权重版权归原作者
- foundry-studio 本身采用 **MIT License**

---

<div align="center">

**Made with 🧬 for the protein design community**

<a href="https://github.com/syxscott/foundry-studio">github.com/syxscott/foundry-studio</a>

</div>
