# Dispatch And Wait Action

This action allows your workflow to dispatch another workflow, wait for it to complete, and fail if the other workflow fails.

It's designed to be a compact alternative to the [`return-dispatch`](https://github.com/Codex-/return-dispatch) and [`await-remote-run`](https://github.com/Codex-/await-remote-run) actions with very similar syntax.

## Usage

### Dispatching Workflow

```yaml
steps:

- name: Dispatch a workflow and wait for it to complete
  uses: Wurst-Imperium/dispatch-and-wait@v1
  id: dispatch_and_wait
  with:
    token: ${{ secrets.YOUR_CUSTOM_GITHUB_TOKEN }}  # Must have actions:write permission
    owner: your-username-or-org
    repo: your-repo-name
    ref: target_branch
    workflow: workflow-to-dispatch.yml
    workflow_inputs: |  # Optional
      {
        "some_input": "value"
      }
    run_timeout_seconds: 600 # Default: 300
    start_timeout_seconds: 120 # Default: 300
    poll_interval_ms: 3000 # Default: 5000
    do_summary: false # Default: true

- name: Use the output run ID and URL
  run: |
    echo ${{ steps.dispatch_and_wait.outputs.run_id }}
    echo ${{ steps.dispatch_and_wait.outputs.run_url }}
```

### Workflow Being Dispatched

As early as possible in the workflow, add the distinct ID to a **step name**. This is what allows the action to find the workflow run.

The `echo` command is only there because every step needs a `uses` or `run`.

```yaml
name: Workflow to Dispatch

on:
  workflow_dispatch:
    inputs:
      distinct_id:
        description: Automatically set by the dispatch-and-wait action (leave blank if running manually)
        required: false

jobs:
  some_job:
    runs-on: ubuntu-latest
    steps:
    - name: Echo distinct ID ${{ inputs.distinct_id }}
      run: echo ${{ inputs.distinct_id }}
```

## Token Permissions

To be able to dispatch a workflow, you need to use a token that has the `actions:write` permission for the target repository.

- If you are dispatching a workflow in the same repository, you can simply do:
  ```yaml
  permissions:
    actions: write

  jobs:
    example:
      runs-on: ubuntu-latest
      steps:
      - uses: Wurst-Imperium/dispatch-and-wait@v1
        with:
          token: ${{ github.token }}
          # ... other parameters ...
  ```
- If you are dispatching a workflow in a different repository, you will need to [create a personal access token](https://github.com/settings/personal-access-tokens) with the `actions:write` permission and appropriate repository access, [create a secret](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) holding the token, and use it like this:
  ```yaml
  # You don't need the permissions: block in this case

  jobs:
    example:
      runs-on: ubuntu-latest
      steps:
      - uses: Wurst-Imperium/dispatch-and-wait@v1
        with:
          token: ${{ secrets.YOUR_CUSTOM_GITHUB_TOKEN }}
          # ... other parameters ...
  ```

## When to use which action

`dispatch-and-wait` is optimized for the common case where you want to dispatch a workflow and wait for it to complete, but it's not a universal solution.

If you have custom logic between the dispatch and wait steps, or if you need to dispatch and get the run ID without waiting for the run to complete, then Codex-'s actions are still your best bet.

Here's a table to help you decide:

| Dispatch? | Wait? | Need run ID? | What to use |
|---|---|---|---|
| ✅ Yes | ✅ Yes | ✅ Yes | `dispatch-and-wait` |
| ✅ Yes | ✅ Yes | ❌ No | `dispatch-and-wait` |
| ✅ Yes | ❌ No | ✅ Yes | [`return-dispatch`](https://github.com/Codex-/return-dispatch) |
| ❌ No | ✅ Yes | n/a | [`await-remote-run`](https://github.com/Codex-/await-remote-run) |
| ✅ Yes | ❌ No | ❌ No | `gh workflow run` (see below) |

If you just want to dispatch a workflow without waiting, and you don't care about the run ID, then you don't need an action at all. Simply do this:

```yaml
- name: Dispatch a workflow without waiting
  run: |
    echo '${{ secrets.YOUR_CUSTOM_GITHUB_TOKEN }}' | gh auth login --with-token
    gh workflow run \
      --repo owner/repo \
      --ref target_branch \
      workflow-to-dispatch.yml \
      -f some_input=value
```

(If you're dispatching a workflow in the same repository, skip the `gh auth login` line.)

See [`gh workflow run` documentation](https://cli.github.com/manual/gh_workflow_run) for more information.
