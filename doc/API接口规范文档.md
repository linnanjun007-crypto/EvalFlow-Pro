# EvalFlow Pro API 接口规范文档

> 本文档详细说明 FastAPI 后端所有接口的请求体、响应体、权限要求、错误码和使用示例。
>
> API 前缀：`/api/v1`
>
> 认证方式：Bearer Token（Header: `Authorization: Bearer user:<user_id>`）

---

## 目录

1. [认证接口（auth）](#认证接口)
2. [项目接口（projects）](#项目接口)
3. [文件接口（files）](#文件接口)
4. [步骤接口（steps）](#步骤接口)
5. [对话接口（chat）](#对话接口)
6. [管理接口（admin）](#管理接口)
7. [导出接口（exports）](#导出接口)
8. [其他接口](#其他接口)
9. [错误码速查表](#错误码速查表)

---

## 认证接口

**前缀**：`/api/v1/auth`

### 1. POST /register - 用户注册

**权限**：无需认证

**请求体**：
```json
{
  "username": "string (非空，长度 >= 1)",
  "password": "string (非空，长度 >= 1)"
}
```

**响应体** (200 OK)：
```json
{
  "id": "uuid",
  "username": "string",
  "role": "user",
  "status": "active"
}
```

**错误码**：
- `400 Bad Request`：用户名已存在或参数验证失败

**示例**：
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe", "password": "secure_pass123"}'
```

---

### 2. POST /login - 用户登录

**权限**：无需认证

**请求体**：
```json
{
  "username": "string",
  "password": "string"
}
```

**响应体** (200 OK)：
```json
{
  "access_token": "user:<user_id>",
  "token_type": "bearer"
}
```

**错误码**：
- `401 Unauthorized`：用户名或密码错误

**示例**：
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe", "password": "secure_pass123"}'
```

---

### 3. GET /me - 获取当前用户信息

**权限**：需要认证

**请求头**：
```
Authorization: Bearer user:<user_id>
```

**响应体** (200 OK)：
```json
{
  "id": "uuid",
  "username": "string",
  "role": "user|admin",
  "status": "active|disabled"
}
```

**错误码**：
- `401 Unauthorized`：Token 无效或过期

**示例**：
```bash
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer user:abc123def456"
```

---

### 4. GET /users - 列出所有用户（仅管理员）

**权限**：需要认证且为 admin 角色

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "username": "string",
      "role": "user|admin",
      "status": "active|disabled"
    }
  ]
}
```

---

### 5. PATCH /users/{user_id}/status - 更新用户状态（仅管理员）

**权限**：需要认证且为 admin 角色

**请求体**：
```json
{
  "status": "active|disabled"
}
```

**响应体** (200 OK)：
```json
{
  "id": "uuid",
  "username": "string",
  "role": "string",
  "status": "active|disabled"
}
```

---

## 项目接口

**前缀**：`/api/v1/projects`

### 1. GET / - 列出用户项目

**权限**：需要认证

**查询参数**：无

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "name": "string",
      "description": "string | null",
      "status": "active|archived|deleted",
      "created_at": "ISO8601 timestamp | null",
      "updated_at": "ISO8601 timestamp | null"
    }
  ]
}
```

**示例**：
```bash
curl -X GET http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer user:abc123def456"
```

---

### 2. POST / - 创建项目

**权限**：需要认证

**请求体**：
```json
{
  "name": "string (非空)",
  "description": "string | null (可选)"
}
```

**响应体** (200 OK)：
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "name": "string",
  "description": "string | null",
  "status": "active",
  "created_at": "ISO8601 timestamp | null",
  "updated_at": "ISO8601 timestamp | null"
}
```

**示例**：
```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer user:abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "2024年部门绩效评价",
    "description": "年度绩效评价报告"
  }'
```

---

### 3. GET /{project_id} - 获取项目详情

**权限**：需要认证且为项目所有者

**路径参数**：
- `project_id`：项目 UUID

**响应体** (200 OK)：
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "name": "string",
  "description": "string | null",
  "status": "active|archived|deleted",
  "created_at": "ISO8601 timestamp | null",
  "updated_at": "ISO8601 timestamp | null"
}
```

---

### 4. PATCH /{project_id} - 更新项目

**权限**：需要认证且为项目所有者

**请求体**：
```json
{
  "name": "string (可选)",
  "description": "string | null (可选)",
  "status": "active|archived (可选)"
}
```

**响应体** (200 OK)：返回更新后的项目对象

---

### 5. DELETE /{project_id} - 删除项目

**权限**：需要认证且为项目所有者

**响应体** (200 OK)：
```json
{
  "message": "deleted"
}
```

---

## 文件接口

**前缀**：`/api/v1/files`

### 1. POST /{project_id}/upload - 上传文件

**权限**：需要认证且为项目所有者

**请求类型**：multipart/form-data

**表单字段**：
- `upload`：File (必需，二进制文件)
- `user_id`：string (可选，默认 "demo-user-id")

**响应体** (200 OK)：
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "user_id": "uuid",
  "file_name": "string",
  "file_type": "string (后缀，如 pdf, docx)",
  "storage_key": "string (文件存储路径)",
  "parse_status": "pending|parsed|failed",
  "source_type": "local_upload|...",
  "file_size": "integer (字节)",
  "metadata_json": "string | null",
  "message": "uploaded",
  "stored_path": "string (完整存储路径)"
}
```

**示例**：
```bash
curl -X POST http://localhost:8000/api/v1/files/{project_id}/upload \
  -H "Authorization: Bearer user:abc123def456" \
  -F "upload=@/path/to/file.pdf" \
  -F "user_id=abc123def456"
```

---

### 2. GET /{project_id} - 列出项目文件

**权限**：需要认证且为项目所有者

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "project_id": "uuid",
      "user_id": "uuid",
      "file_name": "string",
      "file_type": "string",
      "storage_key": "string",
      "parse_status": "pending|parsed|failed",
      "source_type": "string | null",
      "file_size": "integer | null",
      "metadata_json": "string | null"
    }
  ]
}
```

---

### 3. GET /{project_id}/{file_id} - 获取文件详情

**权限**：需要认证且为项目所有者

**响应体** (200 OK)：返回单个文件对象

---

### 4. POST /{project_id} - 创建文件记录（不上传）

**权限**：需要认证且为项目所有者

**请求体**：
```json
{
  "user_id": "uuid",
  "file_name": "string",
  "file_type": "string",
  "storage_key": "string",
  "source_type": "string | null",
  "file_size": "integer | null",
  "metadata_json": "string | null",
  "project_name": "string | null",
  "draft_thread_id": "string | null",
  "draft_payload": "object | null"
}
```

---

### 5. DELETE /{project_id}/{file_id} - 删除文件

**权限**：需要认证且为项目所有者

**响应体** (200 OK)：
```json
{
  "message": "deleted"
}
```

---

## 步骤接口

**前缀**：`/api/v1/steps`

### 1. POST /{step_code}/generate - 执行步骤生成

**权限**：需要认证

**路径参数**：
- `step_code`：步骤编码，如 "step1", "step2" ... "step14"

**请求体**：
```json
{
  "project_id": "uuid (必需)",
  "workflow_role": "user|admin (默认 'user')",
  "review_mode": "string | null (可选：如 'auto-approval', 'manual')",
  "review_feedback": "string | null (可选：人工反馈)",
  "step_code": "string | null (可选，通常从路径获取)",
  "payload": {
    "任意字段": "值"
  }
}
```

**响应体** (200 OK)：
```json
{
  "task_id": "uuid | null",
  "step_code": "step1",
  "message": "step generated",
  "status": "queued|running|success|failed"
}
```

**错误码**：
- `400 Bad Request`：参数验证失败或业务规则冲突

**示例**：
```bash
curl -X POST http://localhost:8000/api/v1/steps/step1/generate \
  -H "Authorization: Bearer user:abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj-uuid",
    "workflow_role": "user",
    "payload": {
      "model_configs": [
        {
          "model_name": "gpt-4",
          "base_url": "https://api.openai.com/v1",
          "api_key": "sk-..."
        }
      ]
    }
  }'
```

---

### 2. GET /status - 查询工作流状态

**权限**：需要认证

**查询参数**：
- `project_id`：uuid (必需)

**响应体** (200 OK)：
```json
{
  "project_id": "uuid",
  "current_step": "step1|step2|...",
  "completed_steps": ["step1", ...],
  "in_progress_steps": ["step2", ...],
  "failed_steps": [],
  "overall_progress": "0-100 (百分比)",
  "last_update": "ISO8601 timestamp"
}
```

**示例**：
```bash
curl -X GET "http://localhost:8000/api/v1/steps/status?project_id=proj-uuid" \
  -H "Authorization: Bearer user:abc123def456"
```

---

### 3. GET /{step_code}/result - 获取步骤结果

**权限**：需要认证

**查询参数**：
- `project_id`：uuid (必需)

**路径参数**：
- `step_code`：步骤编码

**响应体** (200 OK)：
```json
{
  "project_id": "uuid",
  "step_code": "step1",
  "status": "draft|approved|final",
  "result": {
    "id": "uuid",
    "title": "string",
    "content_text": "string",
    "content_json": "JSON string",
    "version": "integer",
    "is_final": "boolean",
    "model_name": "string (生成模型)"
  }
}
```

---

### 4. POST /{step_code}/save - 保存步骤结果

**权限**：需要认证

**路径参数**：
- `step_code`：步骤编码

**请求体**：
```json
{
  "project_id": "uuid (必需)",
  "title": "string (可选，默认 '{step_code} 输出')",
  "content_text": "string",
  "content_json": "string (可选，JSON 字符串)",
  "model_name": "string (可选，默认 'manual-edit')"
}
```

**响应体** (200 OK)：返回保存的输出对象

---

### 5. GET /{step_code}/histories - 列出步骤历史

**权限**：需要认证

**查询参数**：
- `project_id`：uuid (必需)

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "step_output_id": "uuid",
      "model_name": "string",
      "prompt_version_id": "uuid | null",
      "content_json": "string",
      "content_text": "string",
      "created_at": "ISO8601 timestamp"
    }
  ]
}
```

---

### 6. DELETE /{step_code}/histories/{output_id} - 删除历史版本

**权限**：需要认证

**查询参数**：
- `project_id`：uuid (必需)

**响应体** (200 OK)：
```json
{
  "message": "deleted"
}
```

---

## 对话接口

**前缀**：`/api/v1/chat`

### 1. POST /send - 发送对话消息

**权限**：需要认证

**请求体**：
```json
{
  "project_id": "uuid",
  "step_code": "step1",
  "user_message": "string (用户输入)",
  "messages": [
    {
      "role": "user|assistant",
      "content": "string"
    }
  ],
  "workflow_role": "user|admin (默认 'user')",
  "workflow_state": "object (可选，工作流上下文)"
}
```

**响应体** (200 OK)：
```json
{
  "id": "uuid",
  "conversation_id": "uuid",
  "role": "assistant",
  "content": "string (AI 回复)",
  "model_name": "string",
  "created_at": "ISO8601 timestamp"
}
```

---

## 管理接口

**前缀**：`/api/v1/admin`

> **权限说明**：所有管理接口需要认证且用户角色为 `admin`。

### 步骤配置接口

#### 1. GET /steps - 列出管理步骤

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "code": "step1",
      "name": "资料清单生成",
      "description": "string",
      "is_active": "boolean",
      "prompts": [...],
      "kbs": [...]
    }
  ]
}
```

---

#### 2. GET /steps/{step_code} - 获取步骤配置

**响应体** (200 OK)：
```json
{
  "code": "step1",
  "name": "string",
  "prompts": [
    {
      "id": "uuid",
      "step_code": "step1",
      "version": "integer",
      "title": "string",
      "content": "string (Prompt 正文)",
      "is_active": "boolean"
    }
  ],
  "kbs": [
    {
      "id": "uuid",
      "step_code": "step1",
      "version": "integer",
      "name": "string",
      "storage_ref": "string",
      "is_active": "boolean"
    }
  ]
}
```

---

#### 3. GET /steps/{step_code}/active-config - 获取启用配置

**响应体** (200 OK)：
```json
{
  "prompt_text": "string",
  "prompt_title": "string",
  "knowledge_text": "string",
  "kb_name": "string"
}
```

---

#### 4. GET /steps/{step_code}/runtime-config - 获取客户端运行时配置

**说明**：客户端调用，仅返回配置是否存在，不返回正文

**响应体** (200 OK)：
```json
{
  "step_code": "step1",
  "has_config": "boolean",
  "config_version": "integer"
}
```

---

#### 5. POST /steps/{step_code}/config - 保存步骤配置

**请求体**：
```json
{
  "prompt_title": "string",
  "prompt_content": "string",
  "kb_name": "string",
  "kb_content": "string",
  "action": "save|preview"
}
```

**响应体** (200 OK)：
```json
{
  "step": {...},
  "graph_result": {...},
  "change_entries": [...]
}
```

---

### Prompt 管理接口

#### 1. GET /prompts - 列出 Prompt

**查询参数**：
- `step_code`：string (可选)

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "step_code": "step1",
      "version": "integer",
      "title": "string",
      "content": "string",
      "is_active": "boolean",
      "created_at": "ISO8601 timestamp"
    }
  ]
}
```

---

#### 2. POST /prompts - 创建 Prompt

**请求体**：
```json
{
  "step_code": "step1",
  "title": "string",
  "content": "string"
}
```

**响应体** (200 OK)：返回创建的 Prompt 对象

---

#### 3. PATCH /prompts/{prompt_id} - 更新 Prompt

**请求体**：
```json
{
  "title": "string (可选)",
  "content": "string (可选)"
}
```

---

#### 4. PATCH /prompts/{prompt_id}/activate - 激活 Prompt

**说明**：设置该版本为启用版本

**响应体** (200 OK)：返回激活后的 Prompt 对象

---

#### 5. DELETE /prompts/{prompt_id} - 删除 Prompt

**响应体** (200 OK)：
```json
{
  "message": "deleted"
}
```

---

### 知识库管理接口

#### 1. GET /kbs - 列出知识库

**查询参数**：
- `step_code`：string (可选)

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "step_code": "step1",
      "version": "integer",
      "name": "string",
      "storage_ref": "string",
      "is_active": "boolean",
      "created_at": "ISO8601 timestamp"
    }
  ]
}
```

---

#### 2. POST /kbs - 创建知识库

**请求体**：
```json
{
  "step_code": "step1",
  "name": "string",
  "storage_ref": "string (存储位置引用)"
}
```

---

#### 3. PATCH /kbs/{kb_id} - 更新知识库

**请求体**：
```json
{
  "name": "string (可选)",
  "storage_ref": "string (可选)"
}
```

---

#### 4. PATCH /kbs/{kb_id}/activate - 激活知识库

**响应体** (200 OK)：返回激活后的知识库对象

---

#### 5. DELETE /kbs/{kb_id} - 删除知识库

**响应体** (200 OK)：
```json
{
  "message": "deleted"
}
```

---

### 模型配置接口

#### 1. GET /models - 列出模型

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string (显示名)",
      "model_id": "string (调用时使用的ID)",
      "api_key": "string (脱敏显示，如 'sk-***')",
      "base_url": "string",
      "enabled": "boolean",
      "supports_vision": "boolean",
      "created_at": "ISO8601 timestamp"
    }
  ]
}
```

---

#### 2. POST /models - 创建模型配置

**请求体**：
```json
{
  "name": "string",
  "model_id": "string",
  "api_key": "string (可选)",
  "base_url": "string (可选)",
  "supports_vision": "boolean (默认 false)"
}
```

**响应体** (200 OK)：返回创建的模型对象

---

#### 3. PATCH /models/{model_id} - 切换模型启用状态

**请求体**：
```json
{
  "enabled": "boolean"
}
```

**响应体** (200 OK)：返回更新后的模型对象

---

#### 4. DELETE /models/{model_id} - 删除模型配置

**响应体** (200 OK)：
```json
{
  "message": "deleted"
}
```

---

### 审计和变更日志

#### 1. GET /change-logs - 列出变更日志

**查询参数**：
- `step_code`：string (可选)
- `target_type`：string (可选：prompt, kb, model)
- `limit`：integer (默认 100)

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "actor_user_id": "uuid",
      "action": "create|update|delete|publish",
      "target_type": "prompt|kb|model",
      "target_id": "uuid",
      "before_data": "JSON string (变更前)",
      "after_data": "JSON string (变更后)",
      "created_at": "ISO8601 timestamp"
    }
  ]
}
```

---

## 导出接口

**前缀**：`/api/v1/exports`

### 1. POST /step1/word - 导出 Step 1 为 Word

**权限**：需要认证

**请求体**：
```json
{
  "project_name": "string",
  "content_text": "string",
  "content_json": "string (可选)",
  "export_style": "classic|custom (默认 'classic')",
  "custom_title": "string (可选)",
  "save_to_database": "boolean (默认 true)",
  "draft_payload": "object (可选)"
}
```

**响应体**：文件下载 (200 OK，Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document)

**文件头**：
```
Content-Disposition: attachment; filename="xxx.docx"
```

---

### 2. POST /step2/word - 导出 Step 2 为 Word

**请求体**：
```json
{
  "project_name": "string",
  "content_text": "string",
  "content_json": "string (可选)",
  "export_style": "classic|custom (默认 'classic')",
  "custom_title": "string (可选)",
  "save_to_database": "boolean (默认 true)",
  "draft_payload": "object (可选)",
  "categories": ["分类1", "分类2"] (可选),
  "format_options": {
    "font_family": "宋体",
    "font_size_pt": 12,
    "heading_font_size_pt": 16,
    "line_spacing": 1.5,
    "paragraph_spacing_pt": 6,
    "first_line_indent_chars": 2
  } (可选)
}
```

---

## 其他接口

### 1. GET /health - 健康检查

**权限**：无需认证

**响应体** (200 OK)：
```json
{
  "status": "healthy"
}
```

---

### 2. GET /api/v1/audit - 审计日志

**权限**：需要认证（admin 可查看全部，user 仅查看自己的）

**查询参数**：
- `limit`：integer (默认 100)
- `offset`：integer (默认 0)

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "actor_user_id": "uuid",
      "action": "string",
      "target_type": "string",
      "target_id": "uuid",
      "before_data": "string (JSON)",
      "after_data": "string (JSON)",
      "created_at": "ISO8601 timestamp"
    }
  ]
}
```

---

### 3. GET /conversations - 对话列表

**权限**：需要认证

**查询参数**：
- `project_id`：uuid (可选)
- `step_code`：string (可选)

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "project_id": "uuid",
      "step_code": "step1",
      "user_id": "uuid",
      "title": "string",
      "status": "active|archived",
      "created_at": "ISO8601 timestamp",
      "updated_at": "ISO8601 timestamp"
    }
  ]
}
```

---

### 4. GET /conversations/{conversation_id}/messages - 获取对话消息

**权限**：需要认证且为对话所有者

**响应体** (200 OK)：
```json
{
  "items": [
    {
      "id": "uuid",
      "conversation_id": "uuid",
      "role": "user|assistant|system",
      "content": "string",
      "model_name": "string (可选)",
      "created_at": "ISO8601 timestamp"
    }
  ]
}
```

---

## 错误码速查表

| 状态码 | 错误类型 | 说明 | 常见原因 |
|--------|---------|------|---------|
| 400 | Bad Request | 请求参数验证失败 | 缺少必需字段、类型错误、长度限制 |
| 401 | Unauthorized | 认证失败或 Token 无效 | 未提供 Token、Token 过期、用户不存在 |
| 403 | Forbidden | 权限不足（无法操作他人资源或需要 admin 权限） | 尝试访问他人项目、非 admin 访问管理接口 |
| 404 | Not Found | 资源不存在 | 项目/文件/步骤/用户 UUID 不存在 |
| 409 | Conflict | 业务规则冲突 | 重复创建资源、状态不允许该操作 |
| 500 | Internal Server Error | 服务器内部错误 | LangGraph 执行失败、数据库错误、外部 API 超时 |
| 503 | Service Unavailable | 服务暂时不可用 | 数据库连接故障、Redis 不可用 |

---

## 通用响应模式

### 成功响应 (200, 201)

```json
{
  "data": {...} 或 {"items": [...]}
}
```

### 错误响应 (4xx, 5xx)

```json
{
  "detail": "error message"
}
```

---

## 认证示例

所有受保护的接口均在 Header 中使用 Bearer Token：

```bash
curl -X GET http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer user:<user_id>"
```

Token 格式：`user:<uuid>`（在登录时由后端返回）

---

## 跨域配置

前端运行在 http://localhost:5173 或 http://localhost:5174 时，FastAPI 已配置 CORS 允许访问。

如需修改 CORS 配置，编辑 `Backend/app/main.py`：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 文件上传最佳实践

1. **单文件上传**：使用 `POST /files/{project_id}/upload` 端点
2. **多文件上传**：循环调用单文件上传接口
3. **文件大小限制**：建议不超过 500MB（可在 `config.py` 中配置）
4. **文件格式支持**：PDF, DOCX, XLSX, TXT, 图片（JPG, PNG）

---

## 异步任务查询

步骤生成是异步操作，返回 `task_id`。可通过定时轮询 `GET /steps/status` 查询进度：

```bash
while true; do
  curl -X GET "http://localhost:8000/api/v1/steps/status?project_id=proj-uuid"
  sleep 2
done
```

---

**文档版本**：v1.0  
**最后更新**：2026-05-22
