# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

**回答问题一定要用中文回答。** All responses to the user must be in Chinese (Simplified). This applies to explanations, summaries, status updates, and any other user-facing text. Code, identifiers, and file content follow the conventions of the surrounding code.

## Project Overview

**EvalFlow Pro** (云海睿评) is a web system for generating AI-assisted performance evaluation reports. The core workflow is: user login → create project → upload materials → execute step-by-step workflows → generate content → support multi-model comparison, human review, version history, and export to Word/PDF. An admin console allows managing prompts, knowledge bases, and model configurations.

## Technology Stack

- **Frontend**: Vue 3 + TypeScript + Vite + Element Plus + Tailwind CSS
- **Backend**: FastAPI + LangGraph (agentic workflows) + PostgreSQL + Redis
- **Storage**: File uploads handled via FastAPI multipart, outputs stored in `data/uploads` and `data/outputs`
- **LangGraph**: Separate project structure in `Backend/agent/` with `user_graphs` and `admin_graphs` submodules

## Project Structure

```
/f/AgentSystem/
├── frontend/                    # Vue 3 application
│   ├── src/
│   │   ├── pages/              # Page components (routed views)
│   │   ├── components/         # Reusable Vue components
│   │   ├── layouts/            # Layout templates (AppLayout.vue)
│   │   ├── router/             # Vue Router configuration
│   │   ├── stores/             # Pinia state management
│   │   ├── services/           # API client code (axios-based)
│   │   ├── styles/             # Tailwind + CSS
│   │   └── assets/             # Images, fonts, etc.
│   └── package.json            # Frontend dependencies (Vue 3.5, Element Plus, Pinia)
├── Backend/
│   ├── app/                    # FastAPI application
│   │   ├── api/v1/
│   │   │   ├── routes/         # Route handlers (auth, chat, projects, files, steps, etc.)
│   │   │   └── router.py       # API router configuration
│   │   ├── core/
│   │   │   ├── config.py       # Settings (DB URL, Redis, paths, API prefix)
│   │   │   ├── errors.py       # Custom exceptions
│   │   │   └── deps.py         # Dependency injection
│   │   ├── services/           # Business logic layer
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── db/                 # Database setup
│   │   ├── integrations/       # LangGraph and external system integrations
│   │   ├── utils/              # Utility functions
│   │   ├── workers/            # Background tasks
│   │   └── main.py             # FastAPI app instance
│   ├── agent/                  # LangGraph project (separate Git-like structure)
│   │   ├── src/agent/
│   │   │   ├── graph.py        # Entry router (routes to user_graphs or admin_graphs)
│   │   │   ├── user_graphs/    # User workflow steps (step1, step2, etc.)
│   │   │   └── admin_graphs/   # Admin configuration workflows
│   │   ├── pyproject.toml
│   │   ├── Makefile
│   │   └── langgraph.json      # LangGraph server config
│   ├── requirements.txt        # Backend dependencies (FastAPI, SQLAlchemy, LangGraph, httpx, etc.)
│   ├── database_schema.sql     # PostgreSQL schema (import in Navicat or psql)
│   ├── init_db.py              # Database initialization script
│   └── README.md               # Backend-specific instructions
└── doc/                        # Documentation (in Chinese)
    ├── 后端开发方案.md          # Backend architecture and design
    ├── 数据库表结构说明.md      # Database schema documentation
    ├── LangGraph搭建参考文档.md # LangGraph setup reference
    └── [other docs]
```

## Architecture Layers

1. **Vue 3 Frontend**: Handles UI rendering, user input, and calls FastAPI via axios
2. **FastAPI API Layer**: HTTP request/response, authentication, validation, CORS enabled for ports 5173 and 5174
3. **Service Layer**: Orchestrates LangGraph execution, persists results, manages business rules
4. **LangGraph Agent Layer**: Executes multi-step workflows, handles file parsing, model comparison, review/approval flows
5. **Data Layer**: PostgreSQL (primary), Redis (caching/tasks), file storage (`data/uploads`, `data/outputs`)

## API Structure

The FastAPI v1 API is routed from `/api/v1` and includes these main modules (see `Backend/app/api/v1/router.py`):
- `auth`: User authentication
- `projects`: Project management
- `files`: File upload/management
- `steps`: Workflow step execution
- `chat`: Chat/conversation with LLM
- `conversations`: Conversation history
- `admin`: Admin panel endpoints
- `agent`: Direct agent workflow calls
- `history`, `downloads`, `exports`, `audit`, `usage`: Supporting features

## Common Development Commands

### Frontend
```bash
cd frontend

# Development server (runs on http://localhost:5173)
npm run dev

# Build for production
npm run build

# Preview production build locally
npm run preview
```

### Backend
```bash
cd Backend

# Install dependencies
pip install -r requirements.txt

# Initialize database (creates tables from database_schema.sql)
python init_db.py

# Run FastAPI development server (runs on http://localhost:8000)
uvicorn app.main:app --reload

# Test a single endpoint example:
curl -X GET http://localhost:8000/api/v1/health
```

### LangGraph Agent
```bash
cd Backend/agent

# Install dependencies
pip install -e ".[dev]"  # From pyproject.toml

# Run LangGraph studio for visualization/debugging
langgraph dev

# Run tests
make test

# Build/compile the agent
make build
```

## Database Setup

- **Connection**: `postgresql+psycopg://postgres:123456@localhost:5432/agent_king`
- **Host**: `localhost`
- **Port**: `5432`
- **Database**: `agent_king`
- **User**: `postgres`
- **Password**: `123456`

To initialize: `python Backend/init_db.py` or load `Backend/database_schema.sql` directly in PostgreSQL.

## Key Configuration Files

- `Backend/app/core/config.py`: Project settings (database URL, API prefix `/api/v1`, file upload directories)
- `frontend/package.json`: Frontend scripts and dependencies
- `Backend/requirements.txt`: Backend Python dependencies
- `Backend/agent/langgraph.json`: LangGraph server configuration

## Important Architectural Notes

1. **Frontend-Backend Communication**: Vue frontend calls FastAPI endpoints via axios. CORS is configured for localhost ports 5173 and 5174.

2. **LangGraph Integration**: The `Backend/agent/` directory is a separate LangGraph project. It defines workflow graphs that the FastAPI service layer invokes. The workflow state flows through `user_graphs` (for end-user workflows like report generation) and `admin_graphs` (for admin configuration).

3. **Workflow Pattern**: Step-based report generation uses a multi-turn approval pattern—LangGraph nodes generate drafts, users review, and upon approval, results are persisted to PostgreSQL and optionally exported.

4. **File Handling**: Files uploaded via the frontend are stored in `Backend/data/uploads/`. Processed outputs go to `Backend/data/outputs/`. These paths are configurable in `config.py`.

5. **Redis**: Used for caching and task queuing (workers may process async operations).

## Step 存储规则（所有 step 必须遵守）

客户端（`workflow_role = client/user`）所有 `step1` – `step14` 的草稿、生成内容、模型对比结果在用户**未确认提交**前，统一只放在短期记忆里，**不写 PostgreSQL 业务表（`step_output` / `step_history`）**。

### 双层短期记忆

1. **后端 LangGraph MemorySaver（主短期记忆）**
   - 每个 step graph 都用 `graph.compile(checkpointer=MemorySaver(), ...)` 编译
   - thread 命名约定：`<step_code>:<project_id>`（如 `step3:abc123`）
   - 每次 `runAgent` / `updateThreadState` 都把生成结果、用户编辑写到对应 thread state
   - 同时在 `project_memory_session` / `project_memory_entry` 表里记录 `memory_scope='short_term'` 的会话痕迹

2. **前端 `localStorage`（保险副本）**
   - key 命名约定：`ef_<step_code>_draft:<project_id>:<thread_id>`，历史版本副 key 用 `ef_<step_code>_draft_history:...`
   - 保存所有用户可编辑字段（`editor` 文本、`currentResult`、step 特有的结构化字段如 `step3SkeletonTasks`、`step4FlatL2Tasks`、`step9StyleMode`、`step14ExportCustomTitle` 等）
   - 进入 step 页面优先 `loadStepDraftState`，命中后不去重新拉数据库结果
   - 用 debounce/`watch` 在编辑器变化时自动写入，作为 MemorySaver 的浏览器侧保险

### 确认提交动作

只有用户点击"确认提交 / 保存最终版本"按钮时才走持久化路径：

1. 调 `POST /api/v1/steps/{step_code}/save`（`step_service.save_step_result`），写入 `step_output` + `step_history`，递增 `version`，`is_final=True`
2. 提交成功后，**两层短期缓存必须同时清除**：
   - 前端：`localStorage.removeItem(step{N}DraftKey.value)` + 历史副本 key + 重置内存中的 `step{N}DraftDirty / step{N}DraftHistory` ref
   - 后端：调 `POST /api/v1/agent/state/clear`（`agent_runner.clear_thread`）丢弃该 `step_code:project_id` thread 的 MemorySaver 检查点；并将 `project_memory_session.status` 置为 `archived`

### 禁止的反例

- ❌ 不要让 `runAgent` / `generateStep` 直接产出 `step_output`/`step_history` 记录（生成只能落短期记忆）
- ❌ 不要在 `saveStepResult` 之外的路径（自动保存、心跳、切换 step）写 `step_output`
- ❌ 不要在 `saveStepResult` 成功后跳过任一层短期缓存的清理 —— 残留会导致用户下次进入 step 看到旧草稿覆盖最终版本
- ❌ 不要为新 step 跳过 `localStorage` 双保险层；浏览器刷新或后端重启 MemorySaver 丢失时，没有它就没有兜底

新增/重构 step 时务必同时实现 `saveStep{N}DraftState` / `loadStep{N}DraftState` / `clearStep{N}DraftState` 三件套，并在确认提交回调里同时调用 `clearStep{N}DraftState()` 与 `clearAgentThreadState('step{N}', threadId)`。

## Running the Full Stack Locally

1. Start PostgreSQL and ensure `agent_king` database exists
2. Run `python Backend/init_db.py` to initialize schema
3. Start Redis (if using async workers)
4. In one terminal: `cd Backend && uvicorn app.main:app --reload` (FastAPI on port 8000)
5. In another terminal: `cd frontend && npm run dev` (Vue on port 5173)
6. Open http://localhost:5173 in your browser

For LangGraph debugging during development:
- `cd Backend/agent && langgraph dev` (LangGraph Studio on http://localhost:2024)

## Notes for Future Development

- **API Routing**: New endpoints should follow the pattern in `Backend/app/api/v1/routes/` and be registered in `Backend/app/api/v1/router.py`.
- **Schemas**: Request/response validation uses Pydantic schemas in `Backend/app/schemas/`.
- **Database Models**: ORM models are in `Backend/app/models/` and use SQLAlchemy.
- **Services**: Business logic that coordinates workflows should be in `Backend/app/services/`.
- **Frontend Components**: Prefer reusable components in `src/components/`, use Pinia stores for state, and route new pages through Vue Router.
- **LangGraph Workflows**: Modifications to step logic go in `Backend/agent/src/agent/user_graphs/` or admin workflows. Use LangGraph Studio for visualization.
