.PHONY: all venv run test test-only perf clean

all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python paradroid.py

test: venv
	.venv/bin/python -m tests.qa

test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

perf: venv
	.venv/bin/python -m tests.perf

clean:
	rm -rf __pycache__ */__pycache__ tests/out/*.svg
