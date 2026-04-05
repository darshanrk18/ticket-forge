# csv_to_json.py

import gzip
import json
from datetime import datetime

import pandas as pd
from shared.configuration import Paths
from shared.logging import get_logger

logger = get_logger(__name__)

DATA_DIR = Paths.data_root / "github_issues"
DATA_DIR.mkdir(exist_ok=True, parents=True)

INPUT_CSV = DATA_DIR / "tickets_raw.csv"
OUTPUT_JSON = DATA_DIR / "tickets_final.json.gz"

logger.info("Loading CSV...")
df = pd.read_csv(INPUT_CSV)

json_output = {
  "board": {
    "source": "github_issues",
    "issue_state": "closed",
    "generated_at": datetime.utcnow().isoformat(),
    "total_tickets": len(df),
  },
  "tickets": df.to_dict(orient="records"),
}

logger.info("Writing compressed JSON...")
with gzip.open(OUTPUT_JSON, "wt", encoding="utf-8") as f:
  json.dump(json_output, f)

logger.info(f"Created {OUTPUT_JSON}")
