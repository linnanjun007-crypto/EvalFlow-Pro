# FastAPI 后端框架说明

> 适用于 `EvalFlow Pro` 的后端工程结构说明。  
> 目标：帮助你理解一个标准 FastAPI 后端一般长什么样，以及当前项目应该怎么组织。

---

## 1. 一个标准 FastAPI 后端通常包含什么

一个比较规范的 FastAPI 后端，一般会分成下面几层：

- `api`：对外暴露 HTTP 接口
- `schemas`：请求/响应数据结构定义
- `services`：业务逻辑
- `models`：数据库模型
- `db`：数据库连接、会话、迁移
- `core`：配置、安全、日志、异常等基础能力
- `integrations`：第三方系统接入
- `workers`：异步任务
- `utils`：通用工具函数
- `tests`：单元测试与集成测试

可以理解为：

```text
前端
  ↓
API 路由
  ↓
Service 业务层
  ↓
DB / Worker / Integration
  ↓
数据库 / 队列 / 外部服务
```

---

## 2. 标准项目目录长什么样

下面是一个常见的 FastAPI 项目目录模板：

```text
backend/
  app/
    main.py
    core/
      config.py
      security.py
      logging.py
      errors.py
    api/
      v1/
        router.py
        routes/
          health.py
          auth.py
          users.py
          projects.py
          files.py
          steps.py
          admin.py
    schemas/
      auth.py
      user.py
      project.py
      file.py
      step.py
      admin.py
    services/
      auth_service.py
      user_service.py
      project_service.py
      file_service.py
      step_service.py
      admin_service.py
      task_service.py
    models/
      user.py
      project.py
      file.py
      step_output.py
      step_history.py
      task_job.py
      llm_call.py
      prompt_version.py
      kb_version.py
      audit_log.py
      model_registry.py
    db/
      base.py
      session.py
      migrations/
    integrations/
      agent_runner.py
      storage/
      llm/
      ocr/
    workers/
      tasks.py
    utils/
      time.py
      text.py
      file.py
  tests/
  requirements.txt
```

---

## 3. 每一层分别做什么

### 3.1 `app/main.py`

这是整个服务的入口。

通常负责：
- 创建 `FastAPI()`
- 注册路由
- 注册中间件
- 注册生命周期事件
- 健康检查

示意：

```python
from fastapi import FastAPI

app = FastAPI()
```

---

### 3.2 `app/api`

这一层负责“对外提供接口”。

它的职责只有一个：
- 接收请求
- 调用 service
- 返回响应

它不应该写复杂业务逻辑。

#### 常见路由文件
- `health.py`
- `auth.py`
- `projects.py`
- `steps.py`
- `admin.py`

---

### 3.3 `app/schemas`

这一层放 Pydantic 模型。

用途：
- 定义请求体
- 定义响应体
- 校验输入数据

比如：
- `ProjectCreateRequest`
- `StepGenerateRequest`
- `StepGenerateResponse`

---

### 3.4 `app/services`

这一层是核心业务层。

用途：
- 处理项目创建逻辑
- 调用 agent
- 保存数据库
- 管理任务状态
- 组织导出流程

原则：
- route 不写业务，service 才写业务

---

### 3.5 `app/models`

这一层定义数据库表。

比如：
- `User`
- `Project`
- `File`
- `StepOutput`
- `TaskJob`
- `AuditLog`

它和数据库结构一一对应。

---

### 3.6 `app/db`

这一层负责数据库基础设施。

一般包括：
- 数据库连接
- Session 管理
- Base 类
- Alembic 迁移

---

### 3.7 `app/core`

这一层放系统级能力。

通常包括：
- 配置管理
- 安全认证
- 日志系统
- 全局异常处理
- 常量

---

### 3.8 `app/integrations`

这一层负责外部系统对接。

比如：
- LangGraph agent
- MinIO / OSS
- Redis
- OCR
- LLM API

---

### 3.9 `app/workers`

这一层负责异步任务。

适合放：
- 文件解析
- 文档导出
- 长文本生成
- 多模型并行任务
- OCR 任务

---

### 3.10 `app/utils`

这一层放通用小工具。

比如：
- 字符串处理
- 文件名清理
- 时间格式化
- 内容截断
- 编号生成

---

## 4. FastAPI 后端的请求流程一般是怎样的

标准请求链路一般如下：

```text
前端发请求
  ↓
API 路由接收
  ↓
Pydantic 校验参数
  ↓
Service 执行业务
  ↓
调用 DB / Agent / Worker / 外部服务
  ↓
返回响应
```

举个例子：用户点击“生成 Step2 核心内容”。

流程可能是：

1. 前端请求 `POST /api/v1/steps/step2/generate`
2. `steps.py` 接到请求
3. `StepService` 读取项目资料
4. `AgentService` 调用 `user_graphs.step2`
5. 保存结果到 `step_outputs`
6. 返回 `task_id` 或结果给前端

---

## 5. 一般 FastAPI 项目为什么要分层

因为如果所有代码都写在路由里，很快会变成：

- 代码难维护
- 逻辑难测试
- 改一个步骤牵一大片
- 前后端联调容易混乱

分层后好处是：

- 职责清晰
- 代码更容易扩展
- 测试更方便
- 后期可以替换实现而不影响接口层

---

## 6. 结合你这个项目，应该怎么理解这些层

你这个项目不是纯 CRUD，它有明显的工作流特征：

- 上传文件
- 解析资料
- 生成 Step1 / Step2 / Step3 ...
- 人工修订
- 版本保存
- 导出
- 管理端配置 Prompt / 知识库 / 模型

所以更适合：

- `api` 负责前端入口
- `services` 负责调度流程
- `integrations` 负责调用 LangGraph
- `workers` 负责慢任务
- `models` 负责持久化

---

## 7. 当前项目里已经有的结构

你现在的 `Backend/app` 已经开始向标准 FastAPI 结构靠拢了，已经有这些东西：

- `main.py`：应用入口
- `api/v1/router.py`：接口聚合
- `api/v1/routes/`：具体路由
- `core/config.py`：配置
- `db/session.py`：数据库会话
- `models/`：模型
- `schemas/`：请求响应模型
- `services/`：业务层
- `integrations/`：外部接入

说明这个项目已经具备标准后端骨架，只差把业务填完整。

---

## 8. 推荐你这个项目下一步怎么扩展

建议优先补齐：

1. 用户登录鉴权
2. 项目 CRUD
3. 文件上传与存储
4. Step1 / Step2 生成接口
5. 任务状态表
6. 步骤历史版本表
7. 管理端 Prompt / 模型管理
8. 导出 Word / PDF

---

## 9. 你可以直接参考的设计原则

### 路由层
只做：
- 参数接收
- 调用 service
- 返回结果

### Service 层
只做：
- 业务决策
- 调用 agent / db / worker

### Model 层
只做：
- 数据表定义

### Schema 层
只做：
- 入参出参结构定义

### Worker 层
只做：
- 耗时任务执行

---

## 10. 一个标准 FastAPI 后端的最小闭环

最小可用版本通常至少包括：

- 健康检查
- 登录鉴权
- 一个业务实体 CRUD
- 一个异步任务
- 一个持久化表

而你的项目里，最小闭环建议是：

- 登录
- 创建项目
- 上传资料
- 生成 Step1
- 生成 Step2
- 保存历史版本
- 导出结果

---

## 11. 总结

一个标准 FastAPI 后端大体就是：

- `main.py` 负责启动
- `api` 负责接前端
- `schemas` 负责参数校验
- `services` 负责业务逻辑
- `models` 负责数据库结构
- `db` 负责数据库连接
- `core` 负责配置与基础能力
- `integrations` 负责接外部系统
- `workers` 负责异步任务
- `utils` 负责公共工具

对你这个项目来说，最重要的不是“有没有目录”，而是“每一层职责是否清楚”。

---

## 12. 这份文档的用途

这份文档可以作为你后续开发时的“项目结构说明书”。

后面你可以继续在这个基础上补：
- 接口设计文档
- 数据库设计文档
- agent 调用文档
- 前后端联调文档

