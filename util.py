import os


def gh_output(key: str, value: str) -> None:
	if "GITHUB_OUTPUT" in os.environ:
		with open(os.environ["GITHUB_OUTPUT"], "a") as f:
			f.write(f"{key}={value}\n")
	else:
		print(f"{key}={value}", flush=True)


def gh_error(message: str) -> None:
	print(f"::error::{message}", flush=True)


def gh_notice(message: str) -> None:
	print(f"::notice::{message}", flush=True)


def log(message: str) -> None:
	print(message, flush=True)
