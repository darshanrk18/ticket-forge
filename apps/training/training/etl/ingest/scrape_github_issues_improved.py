"""GraphQL scraper for all issue types from all repos."""

import asyncio

import httpx
from pydantic import BaseModel, Field
from shared.configuration import getenv
from tqdm import tqdm


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


REPOS = [
  ("hashicorp", "terraform"),
  ("ansible", "ansible"),
  ("prometheus", "prometheus"),
]

GRAPHQL_URL = "https://api.github.com/graphql"


def _headers() -> dict[str, str]:
  """Build GitHub GraphQL auth headers from env."""
  token = getenv("GITHUB_TOKEN")

  return {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
  }


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


async def scrape_repo_state(  # noqa: PLR0915
  client: httpx.AsyncClient,
  owner: str,
  name: str,
  state: str,
  limit: int | None = None,
) -> list[GitHubIssue]:
  """Scrape issues of a specific state from one repo."""
  repo_full = f"{owner}/{name}"
  issues_list: list[GitHubIssue] = []
  cursor: str | None = None
  page = 1

  pbar = tqdm(unit="issue", desc=f"{repo_full} ({state.lower()})", leave=False)

  retry = 0

  while True:
    if limit and len(issues_list) >= limit:
      break

    response = await client.post(
      GRAPHQL_URL,
      json=build_query(owner, name, state, cursor),
    )

    if response.status_code != 200:
      retry += 1
      assert retry <= 5, "failed to scrape from repo after 5 attempts!"
      if response.status_code == 403:
        pbar.write("Rate limited. Waiting 60s...")
        await asyncio.sleep(60)
      else:
        pbar.write(f"GraphQL error {response.status_code}")
        await asyncio.sleep(2**retry)

      continue

    payload = response.json()
    if "errors" in payload:
      pbar.write(f"GraphQL errors: {payload['errors']}")
      break
    retry = 0

    issues_data = payload["data"]["repository"]["issues"]
    nodes = issues_data["nodes"]
    page_info = issues_data["pageInfo"]

    for item in nodes:
      if limit and len(issues_list) >= limit:
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

      issues_list.append(
        GitHubIssue(
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
      )
      pbar.update(1)

    pbar.set_postfix({"page": page, "total": len(issues_list)})

    if not page_info["hasNextPage"]:
      break

    cursor = page_info["endCursor"]
    page += 1
    await asyncio.sleep(0.3)

  pbar.close()
  return issues_list


async def scrape_all_issues(limit_per_state: int | None = None) -> list[dict]:
  """Scrape all configured repos and return issue records in-memory."""
  all_issues: list[GitHubIssue] = []

  async with httpx.AsyncClient(headers=_headers(), timeout=60.0) as client:
    for owner, name in REPOS:
      repo_full = f"{owner}/{name}"
      print(f"Processing {repo_full}...")

      closed = await scrape_repo_state(client, owner, name, "CLOSED", limit_per_state)
      open_all = await scrape_repo_state(client, owner, name, "OPEN", limit_per_state)
      all_issues.extend(closed)
      all_issues.extend(open_all)

      print(f"Total from {repo_full}: {len(closed) + len(open_all)}")

  total = len(all_issues)
  closed_count = sum(1 for i in all_issues if i.issue_type == "closed")
  assigned_count = sum(1 for i in all_issues if i.issue_type == "open_assigned")
  backlog_count = sum(1 for i in all_issues if i.issue_type == "open_unassigned")

  print(f"Total issues: {total}")
  print(f"Closed: {closed_count}")
  print(f"Open+Assigned: {assigned_count}")
  print(f"Open+Unassigned: {backlog_count}")

  return [issue.model_dump() for issue in all_issues]


async def main() -> None:
  """Standalone runner for scrape-only testing."""
  records = await scrape_all_issues()
  print(f"Scraped {len(records)} issue records.")


if __name__ == "__main__":
  asyncio.run(main())
