"""Feature schema constants shared by training and serving pipelines."""

REPO_FEATURE_ORDER = (
  "ansible/ansible",
  "hashicorp/terraform",
  "prometheus/prometheus",
)

TOP_50_LABELS = (
  "bug",
  "module",
  "support:core",
  "support:community",
  "feature",
  "enhancement",
  "provider/aws",
  "cloud",
  "has_pr",
  "new",
  "python3",
  "needs_info",
  "affects_2.9",
  "affects_2.4",
  "affects_2.3",
  "collection",
  "affects_2.8",
  "traceback",
  "networking",
  "bot_closed",
  "affects_2.5",
  "needs_collection_redirect",
  "core",
  "affects_2.7",
  "docs",
  "affects_2.2",
  "question",
  "affects_2.10",
  "windows",
  "affects_2.6",
  "aws",
  "cisco",
  "needs_template",
  "config",
  "P3",
  "P2",
  "cli",
  "affects_2.1",
  "waiting-response",
  "support:network",
  "crash",
  "collection:community.general",
  "provider/azurerm",
  "vmware",
  "system",
  "kind/bug",
  "affects_2.11",
  "documentation",
  "priority/P3",
  "packaging",
)

EMBEDDING_FEATURE_DIM = 384
NUMERIC_ENGINEERED_FEATURE_DIM = 6
ENGINEERED_FEATURE_DIM = (
  len(REPO_FEATURE_ORDER) + len(TOP_50_LABELS) + NUMERIC_ENGINEERED_FEATURE_DIM
)
TOTAL_FEATURE_DIM = EMBEDDING_FEATURE_DIM + ENGINEERED_FEATURE_DIM
