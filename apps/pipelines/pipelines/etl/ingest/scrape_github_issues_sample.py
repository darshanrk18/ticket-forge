"""GraphQL scraper for a sample of 200 issues per state from all repos."""

import asyncio
import os

import httpx
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from shared.configuration import Paths
from tqdm import tqdm

SAMPLE_SIZE = 200


class GitHubIssue(BaseModel):
  """Represents a GitHub issue."""

  id: str
  repo: str
  title: str
  body: str | None = ""
  labels: str
  assignee: str | None
  state: str
  issue_type: str
  created_at: str
  assigned_at: str | None = None
  closed_at: str | None = None
  comments_count: int = Field(alias="comments")
  url: str = Field(alias="html_url")

  class Config:
    """Pydantic configuration."""

    populate_by_name = True


load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
  msg = "GITHUB_TOKEN missing."
  raise RuntimeError(msg)

REPOS = [
  ("hashicorp", "terraform"),
  ("ansible", "ansible"),
  ("prometheus", "prometheus"),
]

HEADERS = {
  "Authorization": f"Bearer {GITHUB_TOKEN}",
  "Content-Type": "application/json",
}

GRAPHQL_URL = "https://api.github.com/graphql"


def build_query(owner: str, name: str, state: str, cursor: str | None = None) -> dict:
  """Build GraphQL query for issues."""
  after_clause = f', after: "{cursor}"' if cursor else ""

  query = f"""
    query {{
      repository(owner: "{owner}", name: "{name}") {{
        issues(
            first: 100,
            states: {state},
            orderBy: {{field: CREATED_AT, direction: DESC}}{after_clause}
        ) {{
          pageInfo {{
            hasNextPage
            endCursor
          }}
          nodes {{
            number
            title
            body
            state
            createdAt
            closedAt
            url
            comments {{
              totalCount
            }}
            labels(first: 10) {{
              nodes {{
                name
              }}
            }}
            assignees(first: 5) {{
              nodes {{
                login
              }}
            }}
            timelineItems(itemTypes: [ASSIGNED_EVENT], first: 1) {{
              nodes {{
                ... on AssignedEvent {{
                  createdAt
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """

  return {"query": query}


async def scrape_repo_state(
  client: httpx.AsyncClient,
  owner: str,
  name: str,
  state: str,
  limit: int = SAMPLE_SIZE,
) -> list[GitHubIssue]:
  """Scrape up to limit issues of a specific state from a repo."""
  repo_full = f"{owner}/{name}"
  issues_list: list[GitHubIssue] = []
  cursor: str | None = None
  page = 1

  desc = f"{repo_full} ({state.lower()})"
  pbar = tqdm(total=limit, unit="issue", desc=desc, leave=False)

  while True:
    if len(issues_list) >= limit:
      break

    query = build_query(owner, name, state, cursor)
    response = await client.post(GRAPHQL_URL, json=query)

    if response.status_code == 403:
      await asyncio.sleep(60)
      continue

    if response.status_code != 200:
      break

    data = response.json()

    if "errors" in data:
      break

    nodes = data["data"]["repository"]["issues"]["nodes"]
    page_info = data["data"]["repository"]["issues"]["pageInfo"]

    for item in nodes:
      if len(issues_list) >= limit:
        break

      assignees = item.get("assignees", {}).get("nodes", [])
      assignee = assignees[0]["login"] if assignees else None

      timeline_items = item.get("timelineItems", {}).get("nodes", [])
      assigned_at = timeline_items[0].get("createdAt") if timeline_items else None

      labels_nodes = item.get("labels", {}).get("nodes", [])
      labels_str = ",".join([label["name"] for label in labels_nodes])

      if state == "CLOSED":
        issue_type = "closed"
      elif assignee:
        issue_type = "open_assigned"
      else:
        issue_type = "open_unassigned"

      issue = GitHubIssue(
        id=f"{owner}_{name}-{item['number']}",
        repo=repo_full,
        title=item["title"],
        body=item.get("body"),
        labels=labels_str,
        assignee=assignee,
        state=item["state"].lower(),
        issue_type=issue_type,
        created_at=item["createdAt"],
        assigned_at=assigned_at,
        closed_at=item.get("closedAt"),
        comments=item["comments"]["totalCount"],
        html_url=item["url"],
      )

      issues_list.append(issue)
      pbar.update(1)

    pbar.set_postfix({"page": page, "total": len(issues_list)})

    if not page_info["hasNextPage"]:
      break

    cursor = page_info["endCursor"]
    page += 1
    await asyncio.sleep(0.3)

  pbar.close()
  return issues_list


async def main() -> None:
  """Scrape a sample of 200 issues per state from all repos and save to JSON."""
  all_issues: list[GitHubIssue] = []

  async with httpx.AsyncClient(headers=HEADERS, timeout=60.0) as client:
    for owner, name in REPOS:
      closed = await scrape_repo_state(client, owner, name, "CLOSED", SAMPLE_SIZE)
      open_issues = await scrape_repo_state(
        client, owner, name, "OPEN", SAMPLE_SIZE * 2
      )

      open_assigned = [i for i in open_issues if i.issue_type == "open_assigned"][
        :SAMPLE_SIZE
      ]
      open_unassigned = [i for i in open_issues if i.issue_type == "open_unassigned"][
        :SAMPLE_SIZE
      ]

      all_issues.extend(closed + open_assigned + open_unassigned)

  if not all_issues:
    return

  df = pd.DataFrame([issue.model_dump() for issue in all_issues])

  data_dir = Paths.data_root / "github_issues"
  data_dir.mkdir(parents=True, exist_ok=True)
  output = data_dir / "sample_tickets.json"
  df.to_json(output, orient="records", indent=2)

  print("Total:", len(df))
  print("  closed:         ", len(df[df["issue_type"] == "closed"]))
  print("  open_assigned:  ", len(df[df["issue_type"] == "open_assigned"]))
  print("  open_unassigned:", len(df[df["issue_type"] == "open_unassigned"]))
  print("Saved to:", output)


if __name__ == "__main__":
  asyncio.run(main())
