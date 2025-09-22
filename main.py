import github
import json
import os
import time
import traceback
import util
import uuid
from argparse import ArgumentParser
from datetime import datetime, timezone


def find_workflow_run(
	owner: str,
	repo: str,
	workflow: str,
	start_time: float,
	distinct_id: str,
	poll_interval: float,
	start_timeout_seconds: int,
) -> github.WorkflowRun:
	util.log(f"Searching for workflow run with distinct ID {distinct_id}...")
	start_time_iso = datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat()
	deadline = start_time + start_timeout_seconds
	already_checked_runs = set()
	while time.time() < deadline:
		util.log(f"Listing workflow runs after {start_time_iso}...")
		runs = github.list_workflow_runs(owner, repo, workflow, start_time_iso)
		runs = [run for run in runs if run.id not in already_checked_runs]
		for run in runs:
			util.log(f"Checking run {run.id}...")
			jobs = github.list_workflow_run_jobs(owner, repo, run.id)
			for job in jobs:
				for step in job.steps:
					if distinct_id in step.name:
						util.gh_notice(
							f"Successfully identified the workflow run:\n"
							f"  ID: {run.id}\n"
							f"  URL: {run.html_url}"
						)
						return run
			if jobs and run.is_finished():
				already_checked_runs.add(run.id)
		time.sleep(max(0.001, min(poll_interval, deadline - time.time())))
	util.gh_error(
		"Timed out trying to find the workflow run\n"
		"Make sure the workflow sets distinct_id as a step name, e.g.:\n"
		r"    - name: Echo distinct ID ${{ inputs.distinct_id }}\n"
		r"      run: echo ${{ inputs.distinct_id }}\n"
		"Place this step as early in the workflow as possible."
	)
	raise Exception("Timed out trying to find the workflow run")


def wait_for_workflow_run(
	owner: str, repo: str, run_id: int, poll_interval: float, run_timeout_seconds: int
) -> None:
	deadline = time.time() + run_timeout_seconds
	while time.time() < deadline:
		time.sleep(max(0.001, min(poll_interval, deadline - time.time())))
		run = github.get_workflow_run(owner, repo, run_id)
		if run is not None and run.is_finished():
			on_run_finished(owner, repo, run)
			return
	util.gh_error("Timed out waiting for workflow run")
	raise Exception("Timed out waiting for workflow run")


def on_run_finished(owner: str, repo: str, run: github.WorkflowRun) -> None:
	if run.is_successful():
		util.gh_notice(
			"Workflow run finished successfully:\n"
			f"  ID: {run.id}\n"
			f"  URL: {run.html_url}\n"
			f"  Status: {run.status}\n"
			f"  Conclusion: {run.conclusion}"
		)
	else:
		failed_steps = _get_failed_steps(owner, repo, run.id)
		util.gh_error(
			"Workflow run failed:\n"
			f"  ID: {run.id}\n"
			f"  URL: {run.html_url}\n"
			f"  Status: {run.status}\n"
			f"  Conclusion: {run.conclusion}\n"
			f"  Failed steps:{failed_steps}"
		)
		raise Exception("Workflow run failed")


def _get_failed_steps(owner: str, repo: str, run_id: int) -> str:
	jobs = github.list_workflow_run_jobs(owner, repo, run_id)
	if not jobs:
		return " Unknown"
	result = ""
	for job in jobs:
		if not job.is_failed():
			continue
		for step in job.steps:
			if not step.is_failed():
				continue
			result += f"\n    {step.name}"
			result += f"\n      Status: {step.status}"
			result += f"\n      Conclusion: {step.conclusion}"
	return result


def main(
	owner: str,
	repo: str,
	ref: str,
	workflow: str,
	workflow_inputs: dict,
	run_timeout_seconds: int,
	start_timeout_seconds: int,
	poll_interval: float,
) -> None:
	start_time = time.time()
	distinct_id = str(uuid.uuid4())
	adjusted_inputs = {"distinct_id": distinct_id, **workflow_inputs}
	if not github.dispatch_workflow(owner, repo, workflow, ref, adjusted_inputs):
		raise Exception(
			"Failed to dispatch workflow\n"
			f"Make sure your token has actions:write permission for {owner}/{repo}"
		)
	run = find_workflow_run(
		owner, repo, workflow, start_time, distinct_id, poll_interval, start_timeout_seconds
	)
	util.gh_output("run_id", run.id)
	util.gh_output("run_url", run.html_url)
	if run.is_finished():
		on_run_finished(owner, repo, run)
		return
	wait_for_workflow_run(owner, repo, run.id, poll_interval, run_timeout_seconds)


if __name__ == "__main__":
	try:
		parser = ArgumentParser()
		parser.add_argument("owner")
		parser.add_argument("repo")
		parser.add_argument(
			"ref",
			type=lambda x: x.removeprefix("refs/heads/").removeprefix("refs/tags/"),
		)
		parser.add_argument("workflow")
		parser.add_argument("workflow_inputs", type=json.loads)
		parser.add_argument(
			"run_timeout_seconds",
			type=lambda x: int(x)
			if int(x) > 0
			else parser.error("run_timeout_seconds must be positive"),
		)
		parser.add_argument(
			"start_timeout_seconds",
			type=lambda x: int(x)
			if int(x) > 0
			else parser.error("start_timeout_seconds must be positive"),
		)
		parser.add_argument(
			"poll_interval_ms",
			type=lambda x: int(x)
			if int(x) > 0
			else parser.error("poll_interval_ms must be positive"),
		)
		args = parser.parse_args()
		if os.getenv("GITHUB_TOKEN") is None:
			parser.error("token is missing")

		main(
			args.owner,
			args.repo,
			args.ref,
			args.workflow,
			args.workflow_inputs,
			args.run_timeout_seconds,
			args.start_timeout_seconds,
			args.poll_interval_ms / 1000.0,
		)
	except Exception as e:
		util.gh_error(f"{e}")
		traceback.print_exc()
		raise e
