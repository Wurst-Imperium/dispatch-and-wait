import json
import os
import requests
import traceback
from pydantic import BaseModel
from typing import Literal

CheckStatus = Literal[
	"completed",
	"expected",
	"failure",
	"in_progress",
	"pending",
	"queued",
	"requested",
	"startup_failure",
	"waiting",
]


CheckConclusion = Literal[
	"action_required",
	"cancelled",
	"failure",
	"neutral",
	"skipped",
	"stale",
	"success",
	"timed_out",
]


class WorkflowRunStep(BaseModel):
	name: str
	status: CheckStatus
	conclusion: CheckConclusion | None = None

	def is_failed(self) -> bool:
		return self.conclusion and self.conclusion not in ["success", "neutral", "skipped"]


class WorkflowRunJob(BaseModel):
	name: str
	status: CheckStatus
	conclusion: CheckConclusion | None = None
	steps: list[WorkflowRunStep]

	def is_failed(self) -> bool:
		return self.conclusion and self.conclusion not in ["success", "neutral", "skipped"]


class WorkflowRun(BaseModel):
	id: int
	status: CheckStatus
	conclusion: CheckConclusion | None = None
	html_url: str

	def is_finished(self) -> bool:
		return self.conclusion is not None

	def is_successful(self) -> bool:
		return self.conclusion in ["success", "neutral", "skipped"]


headers = {
	"Authorization": f"Bearer {os.getenv("GITHUB_TOKEN")}",
	"X-GitHub-Api-Version": "2022-11-28",
}


def dispatch_workflow(owner: str, repo: str, workflow: str, ref: str, inputs: dict) -> bool:
	try:
		url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
		payload = {"ref": ref, "inputs": inputs}
		response = requests.post(url, headers=headers, json=payload, timeout=30)
		response.raise_for_status()
		print(
			f"::notice::Successfully dispatched workflow:\n"
			f"  Ref: {owner}/{repo}@{ref}\n"
			f"  File: {workflow}\n"
			f"  Inputs: {json.dumps(inputs)}\n"
			f"  Status: {response.status_code}\n"
			f"  Response: {response.text}"
		)
		return True
	except Exception as e:
		traceback.print_exc()
		print(
			f"::error::Failed to dispatch workflow:\n"
			f"  Ref: {owner}/{repo}@{ref}\n"
			f"  File: {workflow}\n"
			f"  Inputs: {json.dumps(inputs)}\n"
			f"  Status: {_get_status_code(e)}\n"
			f"  Response: {_get_response_text(e)}"
		)
		return False


def list_workflow_runs(
	owner: str, repo: str, workflow: str, start_time_iso: str
) -> list[WorkflowRun]:
	try:
		url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/runs"
		params = {
			"event": "workflow_dispatch",
			"created": f">={start_time_iso}",
		}
		response = requests.get(url, headers=headers, params=params, timeout=30)
		response.raise_for_status()
		return [WorkflowRun.model_validate(run) for run in response.json().get("workflow_runs", [])]
	except Exception as e:
		traceback.print_exc()
		print(
			f"::error::Failed to list workflow runs:\n"
			f"  Repo: {owner}/{repo}\n"
			f"  Workflow: {workflow}\n"
			f"  Start Time: {start_time_iso}\n"
			f"  Status: {_get_status_code(e)}\n"
			f"  Response: {_get_response_text(e)}"
		)
		return []


def get_workflow_run(owner: str, repo: str, run_id: int) -> WorkflowRun | None:
	try:
		url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
		response = requests.get(url, headers=headers, timeout=30)
		response.raise_for_status()
		return WorkflowRun.model_validate(response.json())
	except Exception as e:
		traceback.print_exc()
		print(
			f"::error::Failed to get workflow run:\n"
			f"  Repo: {owner}/{repo}\n"
			f"  Run ID: {run_id}\n"
			f"  Status: {_get_status_code(e)}\n"
			f"  Response: {_get_response_text(e)}"
		)
		return None


def list_workflow_run_jobs(owner: str, repo: str, run_id: int) -> list[WorkflowRunJob]:
	try:
		url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
		response = requests.get(url, headers=headers, timeout=30)
		response.raise_for_status()
		return [WorkflowRunJob.model_validate(job) for job in response.json().get("jobs", [])]
	except Exception as e:
		traceback.print_exc()
		print(
			f"::error::Failed to list workflow run jobs:\n"
			f"  Repo: {owner}/{repo}\n"
			f"  Run ID: {run_id}\n"
			f"  Status: {_get_status_code(e)}\n"
			f"  Response: {_get_response_text(e)}"
		)
		return []


def _get_status_code(e: Exception) -> str:
	try:
		return e.response.status_code
	except Exception:
		return "Unknown"


def _get_response_text(e: Exception) -> str:
	try:
		return e.response.text
	except Exception:
		return "Unknown"
