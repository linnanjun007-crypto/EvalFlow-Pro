-- EvalFlow Pro PostgreSQL schema with comments and foreign keys
-- Database: agent_king
-- User: postgres
-- Password: 123456
-- Execute in Navicat or any PostgreSQL client.

-- =====================================================
-- Table: users
-- 用户表，用于保存系统登录账号、角色和状态
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(128) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'user',
    status VARCHAR(32) NOT NULL DEFAULT 'active'
);

COMMENT ON TABLE users IS '用户表，用于保存系统登录账号、角色和状态';
COMMENT ON COLUMN users.id IS '用户主键ID';
COMMENT ON COLUMN users.username IS '用户名，唯一';
COMMENT ON COLUMN users.password_hash IS '密码哈希值';
COMMENT ON COLUMN users.role IS '用户角色，如 user、admin';
COMMENT ON COLUMN users.status IS '用户状态，如 active、disabled';

-- =====================================================
-- Table: projects
-- 项目表，一个用户可拥有多个项目
-- =====================================================
CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    CONSTRAINT fk_projects_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);

COMMENT ON TABLE projects IS '项目表，一个用户可拥有多个项目';
COMMENT ON COLUMN projects.id IS '项目主键ID';
COMMENT ON COLUMN projects.user_id IS '所属用户ID';
COMMENT ON COLUMN projects.name IS '项目名称';
COMMENT ON COLUMN projects.description IS '项目描述';
COMMENT ON COLUMN projects.status IS '项目状态，如 active、archived';

-- =====================================================
-- Table: files
-- 文件表，保存项目上传资料的元信息
-- =====================================================
CREATE TABLE IF NOT EXISTS files (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(64) NOT NULL,
    storage_key VARCHAR(512) NOT NULL,
    parse_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    source_type VARCHAR(32),
    file_size INTEGER,
    metadata_json TEXT,
    CONSTRAINT fk_files_project_id FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_files_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_files_project_id ON files(project_id);
CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);

COMMENT ON TABLE files IS '文件表，保存项目上传资料的元信息';
COMMENT ON COLUMN files.id IS '文件主键ID';
COMMENT ON COLUMN files.project_id IS '所属项目ID';
COMMENT ON COLUMN files.user_id IS '所属用户ID';
COMMENT ON COLUMN files.file_name IS '文件名称';
COMMENT ON COLUMN files.file_type IS '文件类型或后缀';
COMMENT ON COLUMN files.storage_key IS '文件在对象存储中的路径或Key';
COMMENT ON COLUMN files.parse_status IS '文件解析状态，如 pending、parsed、failed';
COMMENT ON COLUMN files.source_type IS '资料来源类型，如 media、documents';
COMMENT ON COLUMN files.file_size IS '文件大小，单位字节';
COMMENT ON COLUMN files.metadata_json IS '文件元数据JSON字符串';

-- =====================================================
-- Table: step_outputs
-- 步骤最终输出表，保存每一步的最终成品
-- =====================================================
CREATE TABLE IF NOT EXISTS step_outputs (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    step_code VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content_json TEXT,
    content_text TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_step_outputs_project_id FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_outputs_project_id ON step_outputs(project_id);
CREATE INDEX IF NOT EXISTS idx_step_outputs_step_code ON step_outputs(step_code);

COMMENT ON TABLE step_outputs IS '步骤最终输出表，保存每一步的最终成品';
COMMENT ON COLUMN step_outputs.id IS '步骤输出主键ID';
COMMENT ON COLUMN step_outputs.project_id IS '所属项目ID';
COMMENT ON COLUMN step_outputs.step_code IS '步骤编码，如 step1、step2';
COMMENT ON COLUMN step_outputs.title IS '输出标题';
COMMENT ON COLUMN step_outputs.content_json IS '结构化输出JSON字符串';
COMMENT ON COLUMN step_outputs.content_text IS '纯文本输出内容';
COMMENT ON COLUMN step_outputs.version IS '版本号';
COMMENT ON COLUMN step_outputs.is_final IS '是否为最终版本';

-- =====================================================
-- Table: step_histories
-- 步骤历史表，保存多轮修改和多模型对比结果
-- =====================================================
CREATE TABLE IF NOT EXISTS step_histories (
    id VARCHAR(36) PRIMARY KEY,
    step_output_id VARCHAR(36) NOT NULL,
    model_name VARCHAR(128),
    prompt_version_id VARCHAR(36),
    content_json TEXT,
    content_text TEXT,
    CONSTRAINT fk_step_histories_step_output_id FOREIGN KEY (step_output_id) REFERENCES step_outputs(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_step_histories_prompt_version_id FOREIGN KEY (prompt_version_id) REFERENCES prompt_versions(id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_histories_step_output_id ON step_histories(step_output_id);

COMMENT ON TABLE step_histories IS '步骤历史表，保存多轮修改和多模型对比结果';
COMMENT ON COLUMN step_histories.id IS '历史记录主键ID';
COMMENT ON COLUMN step_histories.step_output_id IS '关联的步骤输出ID';
COMMENT ON COLUMN step_histories.model_name IS '生成该版本的模型名称';
COMMENT ON COLUMN step_histories.prompt_version_id IS '关联的Prompt版本ID';
COMMENT ON COLUMN step_histories.content_json IS '历史结构化内容JSON';
COMMENT ON COLUMN step_histories.content_text IS '历史文本内容';

-- =====================================================
-- Table: task_jobs
-- 异步任务表，保存步骤执行任务状态
-- =====================================================
CREATE TABLE IF NOT EXISTS task_jobs (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    step_code VARCHAR(32) NOT NULL,
    task_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    CONSTRAINT fk_task_jobs_project_id FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_jobs_project_id ON task_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_task_jobs_step_code ON task_jobs(step_code);

COMMENT ON TABLE task_jobs IS '异步任务表，保存步骤执行任务状态';
COMMENT ON COLUMN task_jobs.id IS '任务主键ID';
COMMENT ON COLUMN task_jobs.project_id IS '所属项目ID';
COMMENT ON COLUMN task_jobs.step_code IS '任务对应步骤编码';
COMMENT ON COLUMN task_jobs.task_type IS '任务类型，如 generate、export、parse';
COMMENT ON COLUMN task_jobs.status IS '任务状态，如 pending、running、succeeded、failed、canceled';
COMMENT ON COLUMN task_jobs.progress IS '任务进度，百分比';
COMMENT ON COLUMN task_jobs.error_message IS '任务失败时的错误信息';

-- =====================================================
-- Table: prompt_versions
-- Prompt版本表，用于管理端维护提示词版本
-- =====================================================
CREATE TABLE IF NOT EXISTS prompt_versions (
    id VARCHAR(36) PRIMARY KEY,
    step_code VARCHAR(32) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_step_code ON prompt_versions(step_code);

COMMENT ON TABLE prompt_versions IS 'Prompt版本表，用于管理端维护提示词版本';
COMMENT ON COLUMN prompt_versions.id IS 'Prompt版本主键ID';
COMMENT ON COLUMN prompt_versions.step_code IS '适用步骤编码';
COMMENT ON COLUMN prompt_versions.version IS 'Prompt版本号';
COMMENT ON COLUMN prompt_versions.title IS 'Prompt标题';
COMMENT ON COLUMN prompt_versions.content IS 'Prompt内容';
COMMENT ON COLUMN prompt_versions.is_active IS '是否当前启用';

-- =====================================================
-- Table: kb_versions
-- 知识库版本表，用于管理端维护知识库文件版本
-- =====================================================
CREATE TABLE IF NOT EXISTS kb_versions (
    id VARCHAR(36) PRIMARY KEY,
    step_code VARCHAR(32) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    name VARCHAR(255) NOT NULL,
    storage_ref TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_kb_versions_step_code ON kb_versions(step_code);

COMMENT ON TABLE kb_versions IS '知识库版本表，用于管理端维护知识库文件版本';
COMMENT ON COLUMN kb_versions.id IS '知识库版本主键ID';
COMMENT ON COLUMN kb_versions.step_code IS '适用步骤编码';
COMMENT ON COLUMN kb_versions.version IS '知识库版本号';
COMMENT ON COLUMN kb_versions.name IS '知识库名称';
COMMENT ON COLUMN kb_versions.storage_ref IS '知识库存储引用或路径';
COMMENT ON COLUMN kb_versions.is_active IS '是否当前启用';

-- =====================================================
-- Table: llm_calls
-- 大模型调用记录表，用于统计tokens和耗时
-- =====================================================
CREATE TABLE IF NOT EXISTS llm_calls (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    step_code VARCHAR(32) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    request_payload TEXT,
    response_payload TEXT,
    CONSTRAINT fk_llm_calls_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_llm_calls_project_id FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_user_id ON llm_calls(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_project_id ON llm_calls(project_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_step_code ON llm_calls(step_code);

COMMENT ON TABLE llm_calls IS '大模型调用记录表，用于统计tokens和耗时';
COMMENT ON COLUMN llm_calls.id IS '调用记录主键ID';
COMMENT ON COLUMN llm_calls.user_id IS '调用用户ID';
COMMENT ON COLUMN llm_calls.project_id IS '所属项目ID';
COMMENT ON COLUMN llm_calls.step_code IS '调用步骤编码';
COMMENT ON COLUMN llm_calls.model_name IS '使用的模型名称';
COMMENT ON COLUMN llm_calls.prompt_tokens IS 'Prompt tokens数量';
COMMENT ON COLUMN llm_calls.completion_tokens IS 'Completion tokens数量';
COMMENT ON COLUMN llm_calls.total_tokens IS '总tokens数量';
COMMENT ON COLUMN llm_calls.latency_ms IS '调用耗时，毫秒';
COMMENT ON COLUMN llm_calls.request_payload IS '请求内容JSON字符串';
COMMENT ON COLUMN llm_calls.response_payload IS '响应内容JSON字符串';

-- =====================================================
-- Table: audit_logs
-- 审计日志表，记录关键操作变更
-- =====================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    actor_user_id VARCHAR(36) NOT NULL,
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    target_id VARCHAR(36) NOT NULL,
    before_data TEXT,
    after_data TEXT,
    created_at TIMESTAMPTZ,
    CONSTRAINT fk_audit_logs_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_target_id ON audit_logs(target_id);

COMMENT ON TABLE audit_logs IS '审计日志表，记录关键操作变更';
COMMENT ON COLUMN audit_logs.id IS '审计日志主键ID';
COMMENT ON COLUMN audit_logs.actor_user_id IS '执行操作的用户ID';
COMMENT ON COLUMN audit_logs.action IS '操作动作，如 create、update、delete、publish';
COMMENT ON COLUMN audit_logs.target_type IS '操作对象类型，如 project、prompt、kb';
COMMENT ON COLUMN audit_logs.target_id IS '操作对象ID';
COMMENT ON COLUMN audit_logs.before_data IS '变更前数据JSON字符串';
COMMENT ON COLUMN audit_logs.after_data IS '变更后数据JSON字符串';
COMMENT ON COLUMN audit_logs.created_at IS '操作时间';

-- 已有库升级（若缺少 created_at 列可手动执行）
-- ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;

-- =====================================================
-- Table: model_registry
-- 模型配置表，保存管理端配置的大模型接入信息
-- =====================================================
CREATE TABLE IF NOT EXISTS model_registry (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    api_key TEXT,
    base_url TEXT,
    model_id VARCHAR(128) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    supports_vision BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE model_registry IS '模型配置表，保存管理端配置的大模型接入信息';
COMMENT ON COLUMN model_registry.id IS '模型配置主键ID';
COMMENT ON COLUMN model_registry.name IS '模型名称';
COMMENT ON COLUMN model_registry.api_key IS '模型API Key';
COMMENT ON COLUMN model_registry.base_url IS '模型API基础地址';
COMMENT ON COLUMN model_registry.model_id IS '模型ID';
COMMENT ON COLUMN model_registry.enabled IS '是否启用';
COMMENT ON COLUMN model_registry.supports_vision IS '是否支持图片/PDF等多模态能力';
