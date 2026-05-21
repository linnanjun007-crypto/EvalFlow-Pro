-- Step memory and run history tables
-- PostgreSQL DDL with comments

CREATE TABLE IF NOT EXISTS project_memory_sessions (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36),
    step_code VARCHAR(32),
    memory_scope VARCHAR(32) NOT NULL DEFAULT 'short_term',
    summary TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE project_memory_sessions IS '项目记忆会话表，保存短期/长期记忆的会话上下文';
COMMENT ON COLUMN project_memory_sessions.id IS '会话主键';
COMMENT ON COLUMN project_memory_sessions.project_id IS '项目ID';
COMMENT ON COLUMN project_memory_sessions.user_id IS '用户ID';
COMMENT ON COLUMN project_memory_sessions.step_code IS '关联的步骤编码';
COMMENT ON COLUMN project_memory_sessions.memory_scope IS '记忆范围：short_term / long_term';
COMMENT ON COLUMN project_memory_sessions.summary IS '会话摘要，用于长期记忆检索';
COMMENT ON COLUMN project_memory_sessions.status IS '会话状态';
COMMENT ON COLUMN project_memory_sessions.created_at IS '创建时间';
COMMENT ON COLUMN project_memory_sessions.updated_at IS '更新时间';

CREATE INDEX IF NOT EXISTS ix_project_memory_sessions_project_id ON project_memory_sessions(project_id);
CREATE INDEX IF NOT EXISTS ix_project_memory_sessions_user_id ON project_memory_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_project_memory_sessions_step_code ON project_memory_sessions(step_code);

CREATE TABLE IF NOT EXISTS project_memory_entries (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES project_memory_sessions(id) ON DELETE CASCADE,
    project_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36),
    step_code VARCHAR(32) NOT NULL,
    memory_type VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT,
    embedding_model VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE project_memory_entries IS '项目记忆条目表，保存短期记忆与长期记忆片段';
COMMENT ON COLUMN project_memory_entries.id IS '条目主键';
COMMENT ON COLUMN project_memory_entries.session_id IS '所属会话ID';
COMMENT ON COLUMN project_memory_entries.project_id IS '项目ID';
COMMENT ON COLUMN project_memory_entries.user_id IS '用户ID';
COMMENT ON COLUMN project_memory_entries.step_code IS '步骤编码';
COMMENT ON COLUMN project_memory_entries.memory_type IS '记忆类型，如 short_term / long_term / summary';
COMMENT ON COLUMN project_memory_entries.content IS '记忆内容';
COMMENT ON COLUMN project_memory_entries.metadata_json IS '附加元数据JSON';
COMMENT ON COLUMN project_memory_entries.embedding_model IS '用于向量化的模型名（当前可为空）';
COMMENT ON COLUMN project_memory_entries.created_at IS '创建时间';

CREATE INDEX IF NOT EXISTS ix_project_memory_entries_project_id ON project_memory_entries(project_id);
CREATE INDEX IF NOT EXISTS ix_project_memory_entries_user_id ON project_memory_entries(user_id);
CREATE INDEX IF NOT EXISTS ix_project_memory_entries_step_code ON project_memory_entries(step_code);
CREATE INDEX IF NOT EXISTS ix_project_memory_entries_session_id ON project_memory_entries(session_id);
CREATE INDEX IF NOT EXISTS ix_project_memory_entries_project_step_type ON project_memory_entries(project_id, step_code, memory_type);

CREATE TABLE IF NOT EXISTS project_step_runs (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36),
    step_code VARCHAR(32) NOT NULL,
    workflow_role VARCHAR(32) NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'success',
    error_message TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE project_step_runs IS '项目步骤执行记录表，保存每次 step 调用与结果';
COMMENT ON COLUMN project_step_runs.id IS '执行记录主键';
COMMENT ON COLUMN project_step_runs.project_id IS '项目ID';
COMMENT ON COLUMN project_step_runs.user_id IS '用户ID';
COMMENT ON COLUMN project_step_runs.step_code IS '步骤编码';
COMMENT ON COLUMN project_step_runs.workflow_role IS '工作流角色';
COMMENT ON COLUMN project_step_runs.input_json IS '输入JSON';
COMMENT ON COLUMN project_step_runs.output_json IS '输出JSON';
COMMENT ON COLUMN project_step_runs.status IS '执行状态';
COMMENT ON COLUMN project_step_runs.error_message IS '错误信息';
COMMENT ON COLUMN project_step_runs.duration_ms IS '执行耗时毫秒';
COMMENT ON COLUMN project_step_runs.created_at IS '创建时间';

CREATE INDEX IF NOT EXISTS ix_project_step_runs_project_id ON project_step_runs(project_id);
CREATE INDEX IF NOT EXISTS ix_project_step_runs_user_id ON project_step_runs(user_id);
CREATE INDEX IF NOT EXISTS ix_project_step_runs_step_code ON project_step_runs(step_code);
CREATE INDEX IF NOT EXISTS ix_project_step_runs_workflow_role ON project_step_runs(workflow_role);
