-- model-launch-lag v1 schema. SQLite (stdlib `sqlite3`, no dependency).
-- Raw API responses live gzipped under raw/<source>/<snapshot_date>/ so the whole
-- database can be rebuilt, and issues reclassified, without re-fetching.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS frameworks (
  id            TEXT PRIMARY KEY,         -- 'vllm','sglang','ollama','llamacpp','trtllm','transformers'
  repo          TEXT NOT NULL,            -- 'vllm-project/vllm'
  support_via   TEXT NOT NULL,            -- 'code' | 'library' | 'both'  (see docs/evidence-rules.md)
  notes         TEXT
);

CREATE TABLE IF NOT EXISTS models (
  hf_id                  TEXT PRIMARY KEY,   -- 'Qwen/Qwen3-8B'
  family                 TEXT NOT NULL,      -- 'qwen3'  (rollup key)
  variant                TEXT,               -- 'base'|'instruct'|'coder'|'vision'|'reasoning'
  architecture           TEXT,               -- config.json architectures[0], e.g. 'Qwen3ForCausalLM'
  params_b               REAL,
  release_date           TEXT,               -- resolved per docs/metrics.md §0
  release_date_method    TEXT NOT NULL,      -- 'first_commit'|'created_at'|'hand_resolved'
  release_date_uncertain INTEGER DEFAULT 0,  -- candidates disagree > 2 days
  created_at_api         TEXT,               -- raw Hub createdAt, kept for audit
  first_commit_at        TEXT,
  license                TEXT,
  support_kind           TEXT,               -- 'new_arch' | 'variant'   (docs/metrics.md §1)
  in_cohort              INTEGER DEFAULT 1,
  -- Hardware floor: ARITHMETIC ESTIMATES, never measurements (docs/metrics.md §6).
  vram_floor_fp16_gb     REAL,
  vram_floor_int4_gb     REAL,
  min_gpu_class_fp16     TEXT                -- smallest common card clearing the fp16 floor
);

-- The name-matching problem: 'Qwen3', 'qwen-3', 'Qwen/Qwen3-8B', 'qwen3:8b' (Ollama tag).
CREATE TABLE IF NOT EXISTS aliases (
  alias       TEXT NOT NULL,                 -- stored lowercase
  hf_id       TEXT REFERENCES models(hf_id),
  family      TEXT,                          -- set instead of hf_id for family-level aliases
  kind        TEXT NOT NULL,                 -- 'exact_id'|'slug'|'ollama_tag'|'arch_class'|'loose'
  PRIMARY KEY (alias, kind)
);
-- 'loose' aliases ('qwen3') match a family but not a checkpoint, so an issue matched
-- only by a loose alias cannot be attributed to a variant. Store match_kind on issues.

CREATE TABLE IF NOT EXISTS download_snapshots (
  hf_id        TEXT REFERENCES models(hf_id),
  fetched_at   TEXT NOT NULL,
  downloads_30d INTEGER,
  likes        INTEGER,
  PRIMARY KEY (hf_id, fetched_at)
);

CREATE TABLE IF NOT EXISTS support_events (
  framework_id  TEXT REFERENCES frameworks(id),
  hf_id         TEXT REFERENCES models(hf_id),
  state         TEXT NOT NULL,            -- supported|partial|remote_code|unsupported|not_applicable
  event_date    TEXT,                     -- NULL when unsupported (censored at snapshot_date)
  days_to_support INTEGER,                -- SIGNED; negative = pre-release / early access
  evidence_rule TEXT NOT NULL,            -- clause id from docs/evidence-rules.md
  fidelity      TEXT NOT NULL,            -- 'exact'|'good'|'coarse'
  evidence_urls TEXT,                     -- JSON array; multi-part support stores all parts
  verified_by   TEXT,                     -- hand-verification is mandatory (100% of rows)
  verified_at   TEXT,
  snapshot_date TEXT NOT NULL,
  PRIMARY KEY (framework_id, hf_id)
);

CREATE TABLE IF NOT EXISTS issues (
  id             INTEGER PRIMARY KEY,      -- GitHub issue node numeric id
  framework_id   TEXT REFERENCES frameworks(id),
  number         INTEGER NOT NULL,
  url            TEXT NOT NULL,            -- link, never redistribute body text
  title          TEXT,
  body_excerpt   TEXT,                     -- first traceback + 2000 chars; what the classifier sees
  is_pr          INTEGER DEFAULT 0,
  author_login   TEXT,
  author_is_bot  INTEGER DEFAULT 0,
  labels         TEXT,                     -- JSON array of maintainer labels
  created_at     TEXT NOT NULL,
  closed_at      TEXT,
  state_reason   TEXT,                     -- completed|not_planned|duplicate|reopened
  closed_by_fix  INTEGER,                  -- linked commit/PR closed it
  has_traceback  INTEGER,
  comment_count  INTEGER,
  reactions      INTEGER,
  hf_id          TEXT REFERENCES models(hf_id),   -- NULL if unmatched
  family         TEXT,
  match_kind     TEXT,                     -- which alias kind matched (confidence proxy)
  excluded       INTEGER DEFAULT 0,
  exclude_reason TEXT,                     -- codebook exclusion code
  snapshot_date  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_issues_fw_created ON issues(framework_id, created_at);
CREATE INDEX IF NOT EXISTS ix_issues_model ON issues(hf_id);

-- Hand labels and machine labels share one table, separated by `source`, so the eval
-- is a join rather than a bespoke script.
CREATE TABLE IF NOT EXISTS labels (
  issue_id          INTEGER REFERENCES issues(id),
  source            TEXT NOT NULL,        -- 'hand'|'hand_pass2'|'llm'|'regex_baseline'|'gh_labels'
  codebook_version  TEXT NOT NULL,        -- 'v1'
  category_primary  TEXT,
  category_secondary TEXT,                -- JSON array
  severity          TEXT,
  reason            TEXT,                 -- one line
  split             TEXT,                 -- 'dev'|'test' (assigned at sample time, immutable)
  labeled_at        TEXT NOT NULL,
  run_id            TEXT REFERENCES runs(run_id),
  PRIMARY KEY (issue_id, source, codebook_version)
);

-- Reproducibility contract, docs/metrics.md. A run that can't fill these isn't publishable.
CREATE TABLE IF NOT EXISTS runs (
  run_id           TEXT PRIMARY KEY,
  started_at       TEXT NOT NULL,
  snapshot_date    TEXT NOT NULL,
  codebook_version TEXT NOT NULL,
  classifier_model TEXT,                  -- exact tag or digest, e.g. 'qwen3:8b-q4_K_M'
  prompt_version   TEXT,
  repo_commit      TEXT,
  raw_dir          TEXT,
  notes            TEXT
);

-- Hardware mentioned in issue reports. Mined by regex from body_excerpt, so it is a
-- lower bound on what people ran: absence of a GPU name is not absence of a GPU.
CREATE TABLE IF NOT EXISTS issue_hardware (
  issue_id        INTEGER REFERENCES issues(id),
  gpu_names       TEXT,        -- JSON array of normalized names: 'RTX 4090','A100-80GB','T4'
  gpu_class       TEXT,        -- 'consumer' | 'workstation' | 'datacenter' | 'apple_silicon' | 'cpu_only'
  vram_reported_gb REAL,       -- parsed from CUDA OOM text ("total capacity of 23.64 GiB")
  quant_mentioned TEXT,        -- 'gguf_q4_k_m','awq','fp8',... normalized, else NULL
  extract_method  TEXT NOT NULL, -- 'regex_traceback'|'regex_body'|'hand'
  PRIMARY KEY (issue_id)
);
