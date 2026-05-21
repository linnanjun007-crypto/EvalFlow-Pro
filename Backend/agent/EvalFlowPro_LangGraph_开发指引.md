# EvalFlow Pro LangGraph 开发指引

> 适用目录：`Backend/agent`
>
> 目的：告诉你这个模板项目里每个关键文件是干什么的，以及后续应该在哪些文件里写代码实现 EvalFlow Pro 的智能体后端功能。

---

## 1. 这个目录的定位

`Backend/agent` 目前是一个 **LangGraph Python 模板工程**。

它的作用不是直接完成业务，而是提供：
- LangGraph 的可运行骨架
- 图编排入口
- 测试框架
- 环境变量示例
- 项目依赖与打包配置

后续你要做的，就是把 EvalFlow Pro 的业务流程、工具调用、Prompt、版本管理等内容逐步接到这个骨架里。

---

## 2. 最重要的文件：你主要在哪写代码

### 2.1 `src/agent/graph.py`

这是你**最先需要改**、也是最重要的文件。

#### 它负责什么
- 定义 LangGraph 的 `State`
- 定义上下文 `Context`
- 定义节点函数
- 定义图的边与路由规则
- 最后 `compile` 出可运行的 graph

#### 你后续会在这里写什么
- 项目上下文加载节点
- 步骤路由节点
- Step1~Step14 的主流程节点
- 校验节点
- 保存版本节点
- 历史写入节点
- 导出触发节点

#### 建议原则
- `graph.py` 只负责“流程和连接”
- 不要把所有业务逻辑都堆在这里
- 复杂逻辑要拆到 `tools/`、`services/`、`prompts/` 中

---

### 2.2 `src/agent/__init__.py`

#### 它负责什么
- Python 包入口
- 暴露模块对象

#### 一般用途
- 导出 graph
- 导出公共配置

#### 建议
- 不要放核心业务逻辑
- 保持简洁

---

### 2.3 `langgraph.json`

#### 它负责什么
这是 LangGraph CLI 的配置文件，用来告诉系统：
- 哪个 graph 是入口
- 运行时读取哪些路径
- 开发环境如何识别项目

#### 你后面可能会改
- graph 入口路径
- 多个 graph 的注册
- 环境变量配置

---

### 2.4 `pyproject.toml`

#### 它负责什么
- Python 依赖管理
- 项目构建配置
- 打包信息

#### 你后面会往里加什么
建议后续补充：
- `fastapi`
- `uvicorn`
- `sqlalchemy` / `sqlmodel`
- `psycopg`
- `redis`
- 文档解析库
- 图片 OCR 库
- 你后续接入的 LLM SDK

---

### 2.5 `.env.example`

#### 它负责什么
环境变量示例。

#### 后续会放什么
例如：
- `LANGSMITH_PROJECT`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

#### 建议
- 真实密钥放 `.env`
- `.env.example` 只保留字段名，不放真实值

---

## 3. 测试文件说明

### 3.1 `tests/integration_tests/test_graph.py`

#### 它负责什么
这是 graph 的集成测试文件。

#### 你后面会用它测试什么
- graph 能不能正常跑
- 输入一个项目状态后是否能返回结果
- 某个步骤节点的输出格式是否正确
- 状态流转是否符合预期

#### 建议
后续可以把它改成：
- Step2 是否产出结构化结果
- Step4 是否校验总分为 100
- Step14 是否能拼装报告

---

### 3.2 `tests/unit_tests/test_configuration.py`

#### 它负责什么
配置类与环境变量读取的单元测试。

#### 适合测试
- 配置是否能正常加载
- 环境变量是否缺失
- 默认值是否合理

---

### 3.3 `tests/conftest.py`

#### 它负责什么
pytest 公共测试配置。

#### 一般用途
- 测试夹具
- Mock 数据
- 公共初始化逻辑

---

## 4. 文档与说明文件

### 4.1 `README.md`

#### 它负责什么
项目说明、安装方式、启动方式、开发说明。

#### 后续建议
你应该把它改成 EvalFlow Pro 自己的项目说明，而不是模板说明。

建议内容包括：
- 项目简介
- 开发环境要求
- 启动命令
- 目录结构说明
- Graph 入口说明
- 调试方式

---

### 4.2 `Makefile`

#### 它负责什么
放常用命令，减少手敲复杂命令。

#### 典型命令
- 启动
- 测试
- 格式化
- lint
- 打包

---

### 4.3 `LICENSE`

#### 它负责什么
开源协议说明。

#### 一般不用改业务
除非你要替换授权方式。

---

## 5. GitHub 工作流文件

### 5.1 `.github/workflows/unit-tests.yml`
### 5.2 `.github/workflows/integration-tests.yml`

#### 它们负责什么
CI 自动化测试。

#### 后面可做什么
- push 后自动跑单测
- push 后自动跑集成测试
- 提前发现 graph 改动导致的问题

---

## 6. 你后面应该新增哪些目录

模板只给了最小结构，后面建议你自己加以下目录：

```text
Backend/agent/src/agent/
  api/
  core/
  graphs/
  models/
  prompts/
  services/
  tools/
  schemas/
  utils/
```

---

## 7. 每个目录应该写什么

### 7.1 `api/`

#### 写什么
- 对外 HTTP 接口
- 项目创建
- 步骤触发
- 历史查询
- 导出任务查询

#### 适合放
- FastAPI 路由
- 请求/响应处理

---

### 7.2 `core/`

#### 写什么
- 配置
- 常量
- 权限
- 基础上下文

#### 适合放
- 系统级配置
- 全局依赖

---

### 7.3 `graphs/`

#### 写什么
- 主图
- Step 子图
- 导出子图

#### 示例
- `main_graph.py`
- `step2_graph.py`
- `step3_graph.py`
- `step14_graph.py`
- `export_graph.py`

---

### 7.4 `models/`

#### 写什么
- 数据库模型
- 表结构定义

#### 建议包含
- `User`
- `Project`
- `StepOutput`
- `StepVersion`
- `ModelRegistry`
- `PromptTemplate`
- `AuditLog`
- `ExportJob`

---

### 7.5 `prompts/`

#### 写什么
- Step1~Step14 的提示词模板
- 通用系统提示词
- 校验提示词
- 对比提示词

#### 建议
Prompt 不要硬编码在 graph 中，后面统一放这里。

---

### 7.6 `services/`

#### 写什么
- 业务逻辑
- 项目服务
- 历史版本服务
- 导出服务
- 任务管理服务

#### 原则
业务规则尽量放这里，不要都写在节点里。

---

### 7.7 `tools/`

#### 写什么
- 文件解析工具
- 文本切分工具
- 指标树工具
- 分值校验工具
- 报告拼装工具
- 导出工具

#### 原则
LangChain/LangGraph 节点可以调用这些工具，但不要让工具反过来控制流程。

---

### 7.8 `schemas/`

#### 写什么
- Pydantic 请求/响应模型
- graph state 的结构
- API 输入输出模型

---

### 7.9 `utils/`

#### 写什么
- 通用小工具
- 时间处理
- 文本处理
- 编号处理
- 日志辅助函数

---

## 8. EvalFlow Pro 后端功能应该写在哪

下面是最直接的分工。

### 8.1 工作流主流程
写在：
- `src/agent/graph.py`
- 或后续拆分到 `graphs/main_graph.py`

### 8.2 每步业务逻辑
写在：
- `services/`
- `tools/`
- `prompts/`

### 8.3 数据持久化
写在：
- `models/`
- `services/`
- `db/`（你后续可新增）

### 8.4 接口
写在：
- `api/`

### 8.5 状态与 schema
写在：
- `schemas/`
- `core/`

---

## 9. 推荐的开发顺序

### 第一步
改 `src/agent/graph.py`，把模板变成你自己的主图骨架。

### 第二步
新增 `graphs/`、`services/`、`tools/`、`prompts/`。

### 第三步
先做最重要的三个步骤：
- Step2：有效项目资料
- Step3：指标体系
- Step14：评价报告

### 第四步
接数据库和历史版本。

### 第五步
再补齐管理端能力与导出能力。

---

## 10. 你现在最应该关注的文件

如果只记 3 个文件，记住这三个：

1. `src/agent/graph.py`
   - 写工作流主逻辑

2. `pyproject.toml`
   - 管依赖

3. `.env.example`
   - 管环境变量

---

## 11. 简单总结

`Backend/agent` 这个模板的核心意义是：

- 它先给你搭好 LangGraph 的“地基”
- 你要做的，是在这个地基上把 EvalFlow Pro 的步骤式智能体、Prompt、工具、数据持久化和 API 一层层补上去

如果你只想马上开工，优先从 `src/agent/graph.py` 开始。

---

## 12. 建议你下一步怎么做

我建议你下一步按下面顺序推进：

1. 定义 `State`
2. 定义 `Context`
3. 拆出 Step2 / Step3 / Step14 节点
4. 新建 `tools/` 和 `prompts/`
5. 接数据库和历史版本

---

## 13. 备注

如果你需要，我可以继续帮你生成一份：
- **目录结构图**
- **LangGraph 主图代码骨架**
- **Step2/Step3/Step14 的节点拆分清单**

这样你就可以直接开始写代码。
