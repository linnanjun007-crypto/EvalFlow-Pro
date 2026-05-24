-- 个人知识库 RAG 模块 - 混合检索升级（向量 + BM25 + RRF + Rerank）
-- 在 Navicat / psql 中手动执行
--
-- 包含：
-- 1) kb_chunks 增加 content_tsv 列与 GIN 索引（用于 BM25 / tsvector 召回）
-- 2) kb_chunks 增加 kb_id 单列索引（融合查询时按 kb_id IN 过滤）
-- 3) user_knowledge_bases 增加开关字段：enable_bm25 / enable_rerank / rrf_k

-- 1) tsvector 列与 GIN 索引（BM25 召回）
ALTER TABLE kb_chunks
  ADD COLUMN IF NOT EXISTS content_tsv tsvector;

CREATE INDEX IF NOT EXISTS idx_kb_chunks_tsv
  ON kb_chunks USING GIN (content_tsv);

-- 2) kb_id 单列索引（融合候选过滤用）
CREATE INDEX IF NOT EXISTS idx_kb_chunks_kb_id
  ON kb_chunks (kb_id);

-- 3) KB 级开关
ALTER TABLE user_knowledge_bases
  ADD COLUMN IF NOT EXISTS enable_bm25 BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS enable_rerank BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS rrf_k INTEGER NOT NULL DEFAULT 60;

-- 验证：
--   \d kb_chunks               看到 content_tsv 列与 idx_kb_chunks_tsv 索引
--   \d user_knowledge_bases    看到 enable_bm25/enable_rerank/rrf_k 三列
--   SELECT count(*) FROM kb_chunks WHERE content_tsv IS NULL;  存量数据待回填
