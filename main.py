import github
import json
import os
import sys
import time
import util
import uuid
from argparse import ArgumentParser
from datetime import datetime, timezone
from pydantic import BaseModel


class DispatchContext(BaseModel):
	owner: str
	repo: str
	ref: str
	workflow: str
	workflow_inputs: dict
	run_timeout_seconds: int
	start_timeout_seconds: int
	poll_interval: float
	do_summary: bool

	def dispatch(self, distinct_id: str) -> bool:
		adjusted_inputs = {"distinct_id": distinct_id, **self.workflow_inputs}
		return github.dispatch_workflow(
			self.owner, self.repo, self.workflow, self.ref, adjusted_inputs
		)

	def find_run(self, start_time: float, distinct_id: str) -> github.WorkflowRun:
		util.log(f"Searching for workflow run with distinct ID {distinct_id}...")
		start_time_iso = datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat()
		deadline = start_time + self.start_timeout_seconds
		already_checked_runs = set()
		while time.time() < deadline:
			util.log(f"Listing workflow runs after {start_time_iso}...")
			runs = github.list_workflow_runs(self.owner, self.repo, self.workflow, start_time_iso)
			runs = [run for run in runs if run.id not in already_checked_runs]
			for run in runs:
				util.log(f"Checking run {run.id}...")
				jobs = github.list_workflow_run_jobs(self.owner, self.repo, run.id)
				for job in jobs:
					for step in job.steps:
						if distinct_id in step.name:
							util.log(
								f"Successfully identified the workflow run:\n"
								f"  ID: {run.id}\n"
								f"  URL: {run.html_url}"
							)
							return run
				if jobs and run.is_finished():
					already_checked_runs.add(run.id)
			time.sleep(max(0.001, min(self.poll_interval, deadline - time.time())))
		raise Exception(
			"Timed out trying to find the workflow run\n"
			"Make sure the workflow sets distinct_id as a step name, e.g.:\n"
			r"    - name: Echo distinct ID ${{ inputs.distinct_id }}\n"
			r"      run: echo ${{ inputs.distinct_id }}\n"
			"Place this step as early in the workflow as possible."
		)

	def wait_for_run(self, run_id: int) -> github.WorkflowRun:
		deadline = time.time() + self.run_timeout_seconds
		while time.time() < deadline:
			time.sleep(max(0.001, min(self.poll_interval, deadline - time.time())))
			run = github.get_workflow_run(self.owner, self.repo, run_id)
			if run is not None and run.is_finished():
				return run
		if self.do_summary:
			util.gh_summary("❌ Run timed out")
		raise Exception("Timed out waiting for workflow run")

	def on_run_finished(self, run: github.WorkflowRun) -> None:
		if run.is_successful():
			if self.do_summary:
				util.gh_summary("✅ Run finished successfully")
			util.log(
				"Workflow run finished successfully:\n"
				f"  ID: {run.id}\n"
				f"  URL: {run.html_url}\n"
				f"  Status: {run.status}\n"
				f"  Conclusion: {run.conclusion}"
			)
		else:
			failed_steps = self._get_failed_steps(run.id)
			if self.do_summary:
				util.gh_summary(f"❌ Run failed\nFailed steps:{failed_steps}")
			raise Exception(
				"Workflow run failed:\n"
				f"  ID: {run.id}\n"
				f"  URL: {run.html_url}\n"
				f"  Status: {run.status}\n"
				f"  Conclusion: {run.conclusion}\n"
				f"  Failed steps:{failed_steps}"
			)

	def _get_failed_steps(self, run_id: int) -> str:
		jobs = github.list_workflow_run_jobs(self.owner, self.repo, run_id)
		if not jobs:
			return " Unknown"
		result = ""
		for job in jobs:
			if not job.is_failed():
				continue
			for step in job.steps:
				if not step.is_failed():
					continue
				result += f"\n- {step.name} (status: {step.status}, conclusion: {step.conclusion})"
		return result


def main(context: DispatchContext) -> None:
	start_time = time.time()
	distinct_id = str(uuid.uuid4())
	if not context.dispatch(distinct_id):
		raise Exception(
			"Failed to dispatch workflow\n"
			f"Make sure your token has actions:write permission for {context.owner}/{context.repo}"
		)
	run = context.find_run(start_time, distinct_id)
	util.gh_output("run_id", run.id)
	util.gh_output("run_url", run.html_url)
	if context.do_summary:
		util.gh_summary(
			f"Dispatched run: [{run.id}]({run.html_url})\n"
			f"Repository: {context.owner}/{context.repo}@{context.ref}\n"
			f"Workflow: [{context.workflow}](https://github.com/{context.owner}/{context.repo}/blob/{context.ref}/.github/workflows/{context.workflow})\n"
			f"Inputs:\n```\n{json.dumps(context.workflow_inputs, indent=2)}\n```"
		)
	if not run.is_finished():
		run = context.wait_for_run(run.id)
	context.on_run_finished(run)


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
		parser.add_argument("do_summary", type=bool, default=True)
		args = parser.parse_args()
		if os.getenv("GITHUB_TOKEN") is None:
			parser.error("token is missing")

		main(
			DispatchContext(
				owner=args.owner,
				repo=args.repo,
				ref=args.ref,
				workflow=args.workflow,
				workflow_inputs=args.workflow_inputs,
				run_timeout_seconds=args.run_timeout_seconds,
				start_timeout_seconds=args.start_timeout_seconds,
				poll_interval=args.poll_interval_ms / 1000.0,
				do_summary=args.do_summary,
			)
		)
	except Exception as e:
		util.gh_error(f"{e}")
		util.gh_traceback()
		sys.exit(1)
