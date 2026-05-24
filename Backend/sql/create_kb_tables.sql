-- 个人知识库 RAG 模块 - 数据库迁移
-- 前置：PostgreSQL 需安装 pgvector 扩展

CREATE EXTENSION IF NOT EXISTS vector;

-- 1) 扩展 model_registry 支持 embedding 类型
ALTER TABLE model_registry
  ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'chat',
  ADD COLUMN IF NOT EXISTS dimensions INTEGER NULL,
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_model_registry_default_per_kind
  ON model_registry(kind) WHERE is_default = TRUE;

-- 2) 用户知识库
CREATE TABLE IF NOT EXISTS user_knowledge_bases (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  embedding_model_id VARCHAR(36) NOT NULL,
  embedding_dim INTEGER NOT NULL DEFAULT 1536,
  chunk_size INTEGER NOT NULL DEFAULT 500,
  chunk_overlap INTEGER NOT NULL DEFAULT 80,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_kbs_user ON user_knowledge_bases(user_id);

-- 3) KB 文档
CREATE TABLE IF NOT EXISTS kb_documents (
  id VARCHAR(36) PRIMARY KEY,
  kb_id VARCHAR(36) NOT NULL REFERENCES user_knowledge_bases(id) ON DELETE CASCADE,
  source_file_id VARCHAR(36) NULL,
  source_type VARCHAR(32) NOT NULL DEFAULT 'upload',
  file_name VARCHAR(512) NOT NULL,
  file_type VARCHAR(32) NOT NULL,
  storage_key VARCHAR(1024) NOT NULL,
  file_size BIGINT,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  indexed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_kb_docs_kb ON kb_documents(kb_id);
CREATE INDEX IF NOT EXISTS ix_kb_docs_status ON kb_documents(status);

-- 4) Chunks + 向量
CREATE TABLE IF NOT EXISTS kb_chunks (
  id BIGSERIAL PRIMARY KEY,
  kb_id VARCHAR(36) NOT NULL REFERENCES user_knowledge_bases(id) ON DELETE CASCADE,
  document_id VARCHAR(36) NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1536) NOT NULL,
  embedding_model_id VARCHAR(36) NOT NULL,
  metadata_json JSONB
);
CREATE INDEX IF NOT EXISTS ix_kb_chunks_doc ON kb_chunks(document_id);
CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding_hnsw
  ON kb_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 5) 项目 ↔ KB 绑定
CREATE TABLE IF NOT EXISTS project_knowledge_bases (
  project_id VARCHAR(36) NOT NULL,
  kb_id VARCHAR(36) NOT NULL REFERENCES user_knowledge_bases(id) ON DELETE CASCADE,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (project_id, kb_id)
);
CREATE INDEX IF NOT EXISTS ix_project_kbs_kb ON project_knowledge_bases(kb_id);
