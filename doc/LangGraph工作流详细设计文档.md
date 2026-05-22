# EvalFlow Pro LangGraph 工作流详细文档

> 本文档详细说明 LangGraph 智能体的工作流设计、状态管理、节点定义和扩展方法。
>
> 框架：LangGraph + LangChain  
> 语言：Python 3.10+

---

## 目录

1. [架构概览](#架构概览)
2. [核心概念](#核心概念)
3. [状态定义](#状态定义)
4. [路由层设计](#路由层设计)
5. [用户工作流（User Graphs）](#用户工作流)
6. [管理工作流（Admin Graphs）](#管理工作流)
7. [Step 通用模式](#step-通用模式)
8. [扩展指南](#扩展指南)
9. [本地调试](#本地调试)

---

## 架构概览

### 目录结构

```
Backend/agent/
├── src/agent/
│   ├── graph.py                    # 统一路由入口
│   ├── user_graphs/
│   │   ├── __init__.py
│   │   ├── step1.py               # Step 1: 资料清单生成
│   │   ├── step2.py               # Step 2: 核心内容生成
│   │   ├── step3.py - step14.py   # Step 3-14
│   │   └── chat.py                # 多轮对话
│   └── admin_graphs/
│       ├── __init__.py
│       ├── step1.py - step14.py   # 管理端各步骤配置工作流
│       └── __init__.py
├── langgraph.json                  # LangGraph Server 配置
├── Makefile
├── pyproject.toml
└── README.md
```

### 执行流程

```
前端请求
   │
   ▼
FastAPI Service Layer
   │
   ├─ 解析 workflow_role (user or admin)
   ├─ 组织 state 对象
   └─ 调用 AgentRunner.run()
       │
       ▼
   Backend/app/integrations/agent_runner.py
       │
       ├─ 导入 Backend/agent/src/agent/graph.py
       ├─ 调用 graph.invoke(state) 或 graph.stream(state)
       └─ 返回结果给前端
           │
           ▼
       用户端或管理端工作流
           │
           ├─ 路由到对应的 step graph
           ├─ 执行节点链
           ├─ 与 LLM 交互
           └─ 返回结果
```

---

## 核心概念

### 1. StateGraph

LangGraph 的状态机，定义了工作流的节点和边。

**基本结构**：

```python
from langgraph.graph import StateGraph, START, END

class MyState(TypedDict):
    messages: list
    user_input: str
    output: str

def node1(state: MyState) -> MyState:
    # 处理输入
    return {"output": "result"}

def node2(state: MyState) -> MyState:
    # 继续处理
    return {"output": state["output"] + " more"}

# 构建图
graph = StateGraph(MyState)
graph.add_node("node1", node1)
graph.add_node("node2", node2)
graph.add_edge(START, "node1")
graph.add_edge("node1", "node2")
graph.add_edge("node2", END)

# 编译
compiled = graph.compile()

# 执行
result = compiled.invoke({"messages": [], "user_input": "hello"})
```

---

### 2. 节点 (Nodes)

节点是工作流中执行实际业务逻辑的单位。每个节点是一个函数，接收当前状态，返回状态更新。

**节点函数签名**：

```python
def my_node(state: StateType) -> StateType | dict:
    """
    处理状态，返回更新。
    
    Args:
        state: 当前工作流状态
    
    Returns:
        dict: 要合并到状态的字段（不需要返回全部状态）
    """
    # 读取状态
    messages = state.get("messages", [])
    
    # 执行逻辑
    result = process(messages)
    
    # 返回更新
    return {"messages": messages + [result]}
```

---

### 3. 边 (Edges)

边连接节点，定义执行流程。

**固定边**：
```python
graph.add_edge("node1", "node2")  # node1 → node2
```

**条件边** (Conditional Edges)：
```python
def route_next(state: StateType) -> str:
    if state["temperature"] > 0.7:
        return "high_temp_branch"
    else:
        return "low_temp_branch"

graph.add_conditional_edges(
    "current_node",
    route_next,
    {
        "high_temp_branch": "node_a",
        "low_temp_branch": "node_b",
    }
)
```

---

### 4. 检查点 (Checkpoints)

保存工作流执行的中间状态，支持恢复和重试。

```python
from langgraph.checkpoint.memory import MemorySaver

graph = graph.compile(checkpointer=MemorySaver())
```

---

## 状态定义

### RouterState（路由层状态）

**文件**：`Backend/agent/src/agent/graph.py`

```python
class RouterState(TypedDict, total=False):
    workflow_role: WorkflowRole          # "user", "client", "admin" 等
    workflow_name: str                  # 工作流名称 (set by router)
    status: str                         # 当前状态: "routed", "processing"
    error: str                          # 错误信息
    selected_graph: str                 # 路由选中的图名 (set by router)
    messages: list[Any]                 # 消息历史
```

### RouterContext（上下文）

```python
class RouterContext(TypedDict, total=False):
    project_id: str                     # 项目 ID
    user_id: str                        # 用户 ID
    model_name: str                     # 当前使用的模型
    compare_models: list[str]           # 对比的模型列表
    enable_multi_model: bool            # 是否启用多模型对比
    system_prompt_stub: str             # 系统 Prompt
    knowledge_stub: str                 # 知识库内容
    output_dir: str                     # 输出目录
```

### Step 工作流状态（示例：Step 1）

```python
class Step1State(TypedDict, total=False):
    # 输入
    project_name: str
    source_files: list[DocumentItem]    # 上传的文件
    user_input: str                     # 用户输入或反馈
    review_mode: str                    # "auto-approval", "manual"
    
    # 处理过程
    extracted_metadata: list[dict]      # 提取的文件元数据
    model_drafts: list[ModelComparison] # 各模型的草稿输出
    
    # 输出
    final_manifest: str                 # 最终清单
    review_status: str                  # "draft", "approved", "final"
    error: str                          # 错误信息
    
    # 元数据
    timestamp: str
    messages: list[BaseMessage]         # LangChain 消息历史
```

---

## 路由层设计

### 统一入口 (graph.py)

```python
from langgraph.graph import StateGraph, START, END

def route_workflow(state: RouterState) -> RouterState:
    """根据 workflow_role 选择目标工作流"""
    role = state.get("workflow_role", "user").lower()
    
    graph_info = {
        "user": ("user", user_step1.graph),
        "admin": ("admin", admin_step1.graph),
        # ... 其他角色
    }
    
    workflow_name, selected_graph = graph_info.get(role, graph_info["user"])
    
    return {
        "workflow_name": workflow_name,
        "selected_graph": selected_graph,
        "status": "routed"
    }

def build_graph():
    graph = StateGraph(RouterState, context_schema=RouterContext)
    graph.add_node("route_workflow", route_workflow)
    graph.add_edge(START, "route_workflow")
    graph.add_edge("route_workflow", END)
    return graph.compile(name="evalflow-pro-router")

graph = build_graph()
```

### 使用路由

```python
# 在 FastAPI 服务中
from app.integrations.agent_runner import AgentRunner

runner = AgentRunner()
result = runner.run(
    role="user",                # 或 "admin"
    step_code="step1",
    payload={...},              # 业务数据
    context={"user_id": "...", "project_id": "..."}
)
```

---

## 用户工作流

### Step 1：资料清单生成

**文件**：`Backend/agent/src/agent/user_graphs/step1.py`

**功能**：
1. 解析上传的文件（PDF、DOCX、XLSX）
2. 提取文件元数据和内容摘要
3. 多模型对比生成清单
4. 支持人工审核和迭代修改
5. 输出最终清单

**节点流程**：

```
┌────────────────────┐
│  START             │
└─────────┬──────────┘
          │
          ▼
┌────────────────────────┐
│ parse_source_files     │  提取文件元数据
└─────────┬──────────────┘
          │
          ▼
┌────────────────────────┐
│ generate_drafts        │  多模型生成草稿
└─────────┬──────────────┘
          │
          ▼
        ┌─────────────┐
        │ review_mode │
        └──┬────────┬─┘
           │        │
    ┌──────┘        └──────┐
    │                      │
    ▼                      ▼
auto_approve          manual_review
    │                      │
    │              ┌───────┴───────┐
    │              │               │
    │              ▼               ▼
    │         approved         rejected
    │              │               │
    │              │         ┌─────┘
    │              │         │ feedback
    │              │         │
    └──────┬───────┘         │
           │                 │
           ▼                 ▼
    ┌─────────────┐    refine_drafts
    │ finalize    │         │
    └──────┬──────┘         │
           │         ┌───────┘
           │         │
           └────┬────┘
                │
                ▼
           ┌─────────┐
           │   END   │
           └─────────┘
```

**State 定义**：

```python
class Step1State(TypedDict, total=False):
    project_name: str                              # 项目名称
    source_files: list[DocumentItem]               # 输入文件
    user_feedback: str                             # 用户反馈
    review_mode: Literal["auto-approval", "manual"] # 审核模式
    
    # 处理过程
    extracted_docs: list[dict]                     # 提取的文档
    model_configs: list[ModelConfig]               # 模型配置
    compare_models: list[str]                      # 对比模型列表
    model_drafts: dict[str, str]                   # 模型输出
    
    # 输出
    final_manifest: str                            # 最终清单
    review_status: str                             # draft|approved|final
    messages: list[BaseMessage]                    # 消息历史
    error: str                                     # 错误
```

**节点实现**（简化示例）：

```python
async def parse_source_files(state: Step1State) -> dict:
    """提取文件元数据"""
    files = state["source_files"]
    extracted = []
    
    for file in files:
        # 根据文件类型解析
        if file["type"] == "pdf":
            content = extract_pdf(file["source_path"])
        elif file["type"] == "docx":
            content = extract_docx(file["source_path"])
        else:
            content = read_text(file["source_path"])
        
        extracted.append({
            "name": file["name"],
            "type": file["type"],
            "content": content,
            "summary": summarize(content)
        })
    
    return {"extracted_docs": extracted}


async def generate_drafts(state: Step1State) -> dict:
    """多模型生成草稿"""
    models = state["model_configs"]
    docs = state["extracted_docs"]
    drafts = {}
    
    for model in models:
        try:
            # 调用 LLM API
            client = create_llm_client(model["api_key"], model["base_url"])
            prompt = build_prompt(docs)
            
            response = await client.generate(
                prompt=prompt,
                model=model["model_name"],
                temperature=model["temperature"]
            )
            drafts[model["model_name"]] = response
        except Exception as e:
            drafts[model["model_name"]] = f"Error: {str(e)}"
    
    return {"model_drafts": drafts}


def review_mode_router(state: Step1State) -> str:
    """根据审核模式路由"""
    mode = state.get("review_mode", "manual")
    return "auto_approve" if mode == "auto-approval" else "manual_review"


async def auto_approve(state: Step1State) -> dict:
    """自动审批"""
    # 选择最佳模型输出
    best_draft = select_best_draft(state["model_drafts"])
    return {
        "final_manifest": best_draft,
        "review_status": "approved"
    }


async def manual_review(state: Step1State) -> dict:
    """等待人工审核"""
    # 标记为待审核状态，前端展示并收集反馈
    return {"review_status": "pending_review"}


async def refine_drafts(state: Step1State) -> dict:
    """根据反馈重新生成"""
    feedback = state["user_feedback"]
    # 使用反馈重新调用模型
    refined = refine_with_feedback(
        state["model_drafts"],
        feedback,
        state["model_configs"]
    )
    return {"model_drafts": refined}
```

**图构建**：

```python
def build_step1_graph():
    graph = StateGraph(Step1State)
    
    # 添加节点
    graph.add_node("parse_files", parse_source_files)
    graph.add_node("generate", generate_drafts)
    graph.add_node("auto_approve", auto_approve)
    graph.add_node("manual_review", manual_review)
    graph.add_node("refine", refine_drafts)
    graph.add_node("finalize", finalize)
    
    # 添加边
    graph.add_edge(START, "parse_files")
    graph.add_edge("parse_files", "generate")
    
    # 条件边：根据审核模式路由
    graph.add_conditional_edges(
        "generate",
        review_mode_router,
        {
            "auto_approve": "auto_approve",
            "manual_review": "manual_review"
        }
    )
    
    graph.add_edge("auto_approve", "finalize")
    graph.add_edge("manual_review", END)  # 等待前端反馈
    graph.add_edge("refine", "finalize")
    graph.add_edge("finalize", END)
    
    return graph.compile(name="step1")

graph = build_step1_graph()
```

---

### Step 2-14：通用模式

其他 Step 遵循类似的模式：

```
输入数据 → 数据准备 → 多模型生成 → 审核 → 最终输出
```

---

## 管理工作流

### 特点

- 用于管理端配置 Prompt、知识库、模型
- 支持配置预览和发布
- 记录所有变更到审计日志

### Admin Step 工作流（示例）

```python
class AdminStepState(TypedDict, total=False):
    step_code: str                      # 步骤编码 (step1-step14)
    action: Literal["save", "preview"]  # 保存或预览
    
    # 输入数据
    prompt_title: str                   # Prompt 标题
    prompt_content: str                 # Prompt 内容
    kb_name: str                        # 知识库名称
    kb_content: str                     # 知识库内容
    
    # 前一版本（用于变更追踪）
    previous_prompt_content: str
    previous_kb_content: str
    
    # 处理结果
    validation_result: dict             # 验证结果
    change_entries: list[dict]          # 变更记录
    status: str                         # success|validation_failed
    error: str
```

**流程**：

```
validate_inputs
    ↓
[action: save or preview]
    ├─ save → apply_changes → audit_log → finalize
    └─ preview → generate_preview → return
```

---

## Step 通用模式

### 输入/输出约定

每个 Step 接收的 payload 格式：

```python
{
    "project_id": str,           # 项目 ID
    "step_code": str,            # 步骤代码
    "payload": dict,             # Step 特定数据
    "model_configs": list,       # 可用模型列表
    "review_mode": str,          # "auto-approval" or "manual"
    "review_feedback": str,      # 用户反馈（用于修改）
    "actor_user_id": str         # 当前用户 ID（admin 步骤）
}
```

输出格式：

```python
{
    "status": "success|failed|validation_failed",
    "step_code": str,
    "result": {                  # Step 特定输出
        "title": str,
        "content": str,
        "model_name": str,
        # ... 其他
    },
    "error": str | None,         # 错误信息
    "change_entries": list       # 审计信息
}
```

---

## 扩展指南

### 创建新 Step 的步骤

#### 1. 定义 Step 状态

创建 `Backend/agent/src/agent/user_graphs/stepN.py`：

```python
from typing import TypedDict, Literal, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END

class StepNState(TypedDict, total=False):
    # 输入
    project_name: str
    input_data: dict
    
    # 处理
    intermediate_result: str
    
    # 输出
    final_output: str
    review_status: Literal["draft", "approved", "final"]
    error: str
```

#### 2. 实现节点

```python
async def prepare_data(state: StepNState) -> dict:
    """准备输入数据"""
    input_data = state["input_data"]
    prepared = process_input(input_data)
    return {"intermediate_result": prepared}


async def generate_output(state: StepNState) -> dict:
    """使用模型生成输出"""
    prompt = build_prompt(state["intermediate_result"])
    output = await call_llm(prompt)
    return {"final_output": output, "review_status": "draft"}


async def finalize(state: StepNState) -> dict:
    """最终化"""
    return {"review_status": "final"}
```

#### 3. 构建图

```python
def build_stepN_graph():
    graph = StateGraph(StepNState)
    
    graph.add_node("prepare", prepare_data)
    graph.add_node("generate", generate_output)
    graph.add_node("finalize", finalize)
    
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "generate")
    graph.add_edge("generate", "finalize")
    graph.add_edge("finalize", END)
    
    return graph.compile(name="stepN", checkpointer=MemorySaver())

graph = build_stepN_graph()
```

#### 4. 集成到路由

编辑 `Backend/agent/src/agent/graph.py`：

```python
from .user_graphs import stepN

_GRAPHS = {
    # ...existing...
    "user": _GraphRef("user", stepN.graph),  # 或其他步骤
}
```

#### 5. 更新 FastAPI 路由

在 `Backend/app/api/v1/routes/steps.py` 中已有通用处理，无需额外修改。

---

## 本地调试

### 1. 启动 LangGraph Studio

```bash
cd Backend/agent
langgraph dev
```

访问 http://localhost:2024，可视化和调试工作流。

### 2. 直接调用图

```python
from Backend.agent.src.agent.user_graphs import step1

state = {
    "project_name": "test",
    "source_files": [...],
    "model_configs": [...],
    "review_mode": "auto-approval"
}

# 同步执行
result = step1.graph.invoke(state)

# 流式输出（用于长时间操作）
for chunk in step1.graph.stream(state):
    print(chunk)
```

### 3. 测试状态转移

```python
# 使用检查点恢复
from langgraph.checkpoint.memory import MemorySaver

graph = step1.graph  # 需要编译时包含 checkpointer

# 执行到某个节点后暂停
config = {"configurable": {"thread_id": "test-1"}}
state = graph.invoke(state, config=config)

# 修改状态并继续
new_state = {**state, "user_feedback": "please refine"}
result = graph.invoke(new_state, config=config)
```

### 4. 调试提示

**打印状态**：
```python
def debug_node(state: StepState) -> dict:
    print(f"State: {json.dumps(state, indent=2)}")
    return {}

# 添加到图中
graph.add_node("_debug", debug_node)
graph.add_edge("some_node", "_debug")
```

**捕获异常**：
```python
async def safe_generate(state: StepState) -> dict:
    try:
        result = await generate_output(state)
        return result
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
```

**性能分析**：
```python
import time

async def timed_node(state: StepState) -> dict:
    start = time.time()
    result = await do_work(state)
    elapsed = time.time() - start
    print(f"Node took {elapsed:.2f}s")
    return result
```

---

## 常见问题

### Q: 如何跨步骤共享状态？

A: 使用上下文 (context_schema) 或外部存储（Redis）。

```python
# 方案 1：上下文
class MyContext(TypedDict):
    shared_data: dict

graph = StateGraph(MyState, context_schema=MyContext)

# 在节点中访问
def my_node(state: MyState, context: MyContext) -> dict:
    data = context["shared_data"]
    return {...}
```

### Q: 如何实现超时控制？

A: 使用 `asyncio.wait_for()`

```python
import asyncio

async def generate_with_timeout(state, timeout_seconds=30):
    try:
        result = await asyncio.wait_for(
            call_llm(...),
            timeout=timeout_seconds
        )
        return result
    except asyncio.TimeoutError:
        return {"error": "Generation timeout"}
```

### Q: 如何处理模型调用错误？

A: 使用 try-except 和重试逻辑

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2))
async def call_llm_with_retry(prompt, model, **kwargs):
    return await llm_client.generate(prompt, model=model, **kwargs)
```

---

## 性能优化建议

1. **并行执行**：使用多个模型对比时，并发调用而不是顺序调用

```python
import asyncio

async def generate_drafts(state: Step1State) -> dict:
    tasks = [
        call_llm(prompt, model)
        for model in state["model_configs"]
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {"model_drafts": results}
```

2. **缓存频繁操作**：Prompt、知识库等可缓存

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def load_prompt_template(step_code: str) -> str:
    return fetch_from_db(step_code)
```

3. **流式输出**：对于长文本生成，使用 `graph.stream()` 而不是 `invoke()`

---

**文档版本**：v1.0  
**最后更新**：2026-05-22
