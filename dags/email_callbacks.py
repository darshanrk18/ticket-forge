"""Email callbacks for Airflow DAG success/failure notifications."""
# noqa

from __future__ import annotations

import logging
import os
from typing import Any

from airflow.utils.email import send_email

logger = logging.getLogger(__name__)


def _build_email_body(
  context: dict[str, Any],
  is_success: bool,
  failed_tasks: list[str] | None = None,
  successful_tasks: list[str] | None = None,
  additional_text: str | None = None,
) -> str:
  """Build email body with task status and optional additional details.

  Args:
      context: Airflow context
      is_success: Whether the DAG succeeded
      failed_tasks: List of failed task IDs
      successful_tasks: List of successful task IDs
      additional_text: Optional extra section appended to email

  Returns:
      Formatted email body string
  """
  dag_id = context.get("dag_run").dag_id
  task_id = context.get("task_instance").task_id
  execution_date = context.get("execution_date")
  status = "SUCCESS" if is_success else "FAILURE"

  body_lines = [
    f"DAG: {dag_id}",
    f"Task: {task_id}",
    f"Status: {status}",
    f"Execution Date: {execution_date}",
    "",
  ]

  # Add task summary
  if successful_tasks:
    body_lines.extend(
      [
        f"Successful Tasks ({len(successful_tasks)}):",
        *[f"  ✓ {task}" for task in successful_tasks],
        "",
      ]
    )

  if failed_tasks:
    body_lines.extend(
      [
        f"Failed Tasks ({len(failed_tasks)}):",
        *[f"  ✗ {task}" for task in failed_tasks],
        "",
      ]
    )

  # Add optional appendix section
  if additional_text:
    body_lines.extend(
      [
        "ADDITIONAL DETAILS:",
        "",
        additional_text.strip(),
        "",
      ]
    )

  # Add exception info for failures
  if not is_success:
    exception = context.get("exception")
    if exception:
      body_lines.extend(
        [
          "Error:",
          str(exception),
          "",
        ]
      )

  return "\n".join(body_lines)


def send_dag_status_email(additional_text: str | None = None, **context: Any) -> None:
  """Send email based on DAG run status with optional extra details.

  Args:
      additional_text: Optional extra section appended to email
      **context: Airflow context
  """
  logger.info("DAG status email task triggered")

  email = os.environ.get("GMAIL_APP_USERNAME")
  logger.info(f"Email address from env: {email}")

  if not email:
    logger.warning("No GMAIL_APP_USERNAME found in environment, skipping email")
    return

  # Check if any upstream tasks failed
  task_instance = context["task_instance"]
  dag_run = context["dag_run"]

  # Get all task instances for this dag run
  failed_tasks = []
  successful_tasks = []

  for ti in dag_run.get_task_instances():
    if ti.task_id == task_instance.task_id:
      # Skip self
      continue
    if ti.state == "failed":
      failed_tasks.append(ti.task_id)
    elif ti.state == "success":
      successful_tasks.append(ti.task_id)

  is_success = len(failed_tasks) == 0
  dag_id = dag_run.dag_id

  if is_success:
    subject = f"[Airflow] DAG Success: {dag_id}"
  else:
    subject = f"[Airflow] DAG Failure: {dag_id}"

  body = _build_email_body(
    context,
    is_success=is_success,
    failed_tasks=failed_tasks,
    successful_tasks=successful_tasks,
    additional_text=additional_text,
  )

  logger.info(
    f"Attempting to send {'success' if is_success else 'failure'} email to {email} for DAG {dag_id}"
  )

  try:
    send_email(to=[email], subject=subject, html_content=f"<pre>{body}</pre>")
    logger.info("Email sent successfully")
  except Exception as e:
    logger.error(f"Failed to send email: {e}", exc_info=True)
    # Don't fail the task if email fails
    pass
