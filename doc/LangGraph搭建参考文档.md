# EvalFlow Pro LangGraph 搭建参考文档

> 目标：给后端智能体开发时直接参考的实现文档。
> 
> 结论先说：**这些能力不是不能用 LangChain 实现，而是 LangGraph 更适合做“状态机 + 多步骤工作流 + 分支回退 + 持久化恢复”**。LangChain 更适合做“单次模型调用、Prompt 管理、工具封装、链式处理”。

---

## 1. 先回答你的问题：这些能不能只用 LangChain？

### 简短结论
**可以做一部分，但不推荐只用 LangChain 做全部。**

### 为什么
LangChain 擅长：
- 调模型
- 管 Prompt
- 调工具
- 做简单 Chain
- 做 RAG
- 做输出解析

LangGraph 擅长：
- 多节点工作流编排
- 状态流转
- 分支条件路由
- 回退和恢复
- 循环
- 并行节点
- 任务图可视化
- 支持“步骤型业务流程”

### 对你的项目来说
EvalFlow Pro 的后端不是“问一句答一句”的聊天机器人，而是：
- 项目创建后有固定流程
- 14 步工作流
- 每一步要保存版本
- 每一步可恢复、可重试、可对比
- 管理端还要配置 Prompt / 知识库 / 模型

所以更合理的架构是：
- **LangGraph：负责流程图**
- **LangChain：负责节点内部的模型能力**

---

## 2. 你这个项目里，LangGraph 最适合承接什么

### 2.1 适合用 LangGraph 的部分
1. **14 步工作流编排**
   - Step1 到 Step14 的流转
   - 支持跳步、重试、回退

2. **步骤状态保存与恢复**
   - 当前项目做到第几步
   - 每一步的最终版本是什么
   - 哪一步失败了

3. **多模型对比流程**
   - 同一输入并行调用多个模型
   - 汇总输出
   - 选择最佳版本

4. **长任务处理**
   - queued / running / succeeded / failed / canceled
   - 失败时继续从上次状态恢复

5. **一致性检查**
   - 比如 Step7、Step9、Step10、Step11 之间要相互校验

6. **导出前拼装**
   - Step1~Step13 产物拼成 Step14 报告

---

## 3. LangChain 适合承接什么

### 3.1 适合用 LangChain 的部分
1. **LLM 调用封装**
   - OpenAI、Anthropic、Qwen 等模型统一接口

2. **Prompt 模板**
   - Step1~Step14 的提示词模板
   - 管理端配置的 Prompt

3. **工具调用**
   - 文件解析
   - 文本切分
   - 指标树构建
   - 导出

4. **输出解析**
   - JSON 结构化输出
   - 表格输出
   - 树结构输出

5. **RAG / 检索增强**
   - 知识库检索
   - 政策条文引用

6. **简单链式处理**
   - 输入 → Prompt → 模型 → 解析 → 返回

---

## 4. 推荐的整体分层

建议你按下面方式做：

```text
API 层（FastAPI）
  ↓
应用服务层（项目、版本、历史、导出）
  ↓
LangGraph 工作流层（步骤编排）
  ↓
LangChain 执行层（模型、Prompt、工具、解析）
  ↓
数据层（PostgreSQL / Redis / 文件存储）
```

---

## 5. EvalFlow Pro 推荐的 LangGraph 主图结构

### 5.1 主图逻辑

```text
start
  ↓
load_project_context
  ↓
detect_step
  ↓
step_x_node
  ↓
validate_output
  ↓
save_version
  ↓
update_history
  ↓
maybe_export
  ↓
end
```

### 5.2 说明
- `load_project_context`
  - 读取项目、历史、当前步骤配置
- `detect_step`
  - 根据 `step_id` 路由到对应步骤
- `step_x_node`
  - 执行实际生成逻辑
- `validate_output`
  - 校验结构与业务规则
- `save_version`
  - 保存步骤版本
- `update_history`
  - 写历史与审计
- `maybe_export`
  - 如果是 Step14 或用户触发导出，则进入导出子图

---

## 6. 每一步应该怎么接 LangChain

### Step1 资料清单
- LangChain 负责：
  - 提示词生成资料摘要
  - 文本分类
- LangGraph 负责：
  - 步骤流转
  - 状态保存

### Step2 有效项目资料
- LangChain 负责：
  - 文本抽取后的归类
  - 引用片段整理
- LangGraph 负责：
  - 读取文件、状态更新、输出版本保存

### Step3 指标体系
- LangChain 负责：
  - 生成指标树 JSON
  - 做层级命名优化
- LangGraph 负责：
  - 控制是否回退到上一步重生成

### Step4 分值
- LangChain 负责：
  - 依据规则生成分值建议
- LangGraph 负责：
  - 校验是否等于 100
  - 不通过则路由到修复节点

### Step5 评分标准
- LangChain 负责：
  - 生成评分标准文本
- LangGraph 负责：
  - 多模型并行、版本选择

### Step6 完整指标体系
- LangChain 负责：
  - 组合表格内容
- LangGraph 负责：
  - 合并 Step3 + Step5 的结果

### Step7 分析 + 得分表
- LangChain 负责：
  - 生成分析描述
- LangGraph 负责：
  - 汇总多段输出，计算得分表

### Step8 经验做法
- LangChain 负责：
  - 提炼经验做法
- LangGraph 负责：
  - 保存版本与历史

### Step9 问题与原因
- LangChain 负责：
  - 问题提炼
  - 原因分析
- LangGraph 负责：
  - 从扣分项路由到对应问题生成节点

### Step10 建议
- LangChain 负责：
  - 建议生成
- LangGraph 负责：
  - 与问题一一对应校验

### Step11 综合评价
- LangChain 负责：
  - 总结性结论生成
- LangGraph 负责：
  - 从前序所有步骤汇总上下文

### Step12 基本情况
- LangChain 负责：
  - 基本情况段落生成
- LangGraph 负责：
  - 从项目元数据填充上下文

### Step13 工作开展情况
- LangChain 负责：
  - 过程描述生成
- LangGraph 负责：
  - 调整生成顺序、持久化

### Step14 评价报告
- LangChain 负责：
  - 报告正文补写
- LangGraph 负责：
  - 汇总 Step1~13
  - 拼装全文
  - 触发导出流程

---

## 7. 什么时候可以只用 LangChain，不用 LangGraph

下面这些场景可以只用 LangChain：
- 一个简单的问答助手
- 单轮或多轮聊天
- 单个 Prompt + 单次生成
- 简单 RAG
- 简单工具调用
- 没有复杂步骤控制的内容生成

但你的项目不属于这个范围，因为你是：
- 多步骤业务流程
- 每步都要保存
- 每步可恢复
- 每步可对比
- 每步可导出

所以只用 LangChain 会很难维护。

---

## 8. 推荐的工作流拆分方式

### 8.1 第一层：项目主流程图
用于控制：
- 当前步骤
- 跳步
- 恢复
- 导出

### 8.2 第二层：步骤子图
用于每一步的具体逻辑，比如：
- Step2 文档解析子图
- Step3 指标树生成子图
- Step4 分值校验子图
- Step5 多模型对比子图
- Step14 报告导出子图

### 8.3 第三层：工具函数
用于：
- 文件处理
- 文本拆分
- 模型调用
- 版本存储
- 导出文件生成

---

## 9. 推荐的数据流设计

### 9.1 输入数据
- 用户上传文件
- 项目基础信息
- 当前步骤配置
- Prompt 版本
- 模型配置
- 知识库检索结果

### 9.2 中间数据
- 文本抽取结果
- 结构化 JSON
- 表格结构
- 版本记录
- 错误信息

### 9.3 输出数据
- 当前步骤成品
- 历史版本
- 审计记录
- 导出任务
- 最终报告

---

## 10. 你搭建 LangGraph 时最需要先做的几件事

### 第一步：定义状态结构
建议先定义一个统一的 `State`，比如包含：
- `project_id`
- `step_id`
- `user_id`
- `input_files`
- `context`
- `step_output`
- `final_output`
- `version_id`
- `status`
- `error`

### 第二步：定义主图路由
先把 Step1~Step14 的路由跑通，不要一开始就追求复杂生成。

### 第三步：先实现 3 个重点步骤
建议先做：
- Step2（资料抽取）
- Step3（指标体系）
- Step14（报告拼装）

这三个最能代表系统价值。

### 第四步：把 LangChain 接进节点
每个节点内部用 LangChain 调模型，不要把模型调用写死在图逻辑里。

### 第五步：加版本与恢复
这是你这个产品真正的关键。

---

## 11. 推荐目录结构

```text
backend/
  app/
    api/
    core/
    db/
    models/
    schemas/
    services/
    graphs/
      main_graph.py
      step2_graph.py
      step3_graph.py
      step14_graph.py
    tools/
    prompts/
    utils/
```

---

## 12. 推荐实现顺序

### MVP 顺序
1. 登录 / 项目 / 权限
2. LangGraph 主图
3. Step2 / Step3 / Step14
4. 历史版本
5. 导出
6. 管理端配置
7. Step4 / Step5 / Step7 / Step9 / Step10 / Step11
8. 统计与审计

---

## 13. 结论

### 你的问题答案
**不是“这些无法用 LangChain 实现”，而是“这些如果只用 LangChain 做，会变得难维护、难恢复、难扩展”。**

### 最佳实践
- **LangGraph 负责流程编排与状态管理**
- **LangChain 负责每个节点内部的模型调用、Prompt 和工具**

### 对 EvalFlow Pro 的建议
如果你要做的是“工作流型智能体系统”，就应该优先用 **LangGraph + LangChain 组合方案**。

---

## 14. 下一步建议

如果你愿意，我下一步可以继续给你生成一份：

1. **LangGraph 主图 Mermaid 图**
2. **Step2 / Step3 / Step14 的子图设计图**
3. **LangGraph + LangChain 的 Python 代码骨架**

你只要回复一句：
**“继续出代码骨架”**
我就直接接着写。
