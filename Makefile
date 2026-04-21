PYTHON ?= python3
VENV_PY := venv/bin/python

.PHONY: test typecheck snapshot-update snapshot-check

test:
	@if [ -x "$(VENV_PY)" ]; then \
		"$(VENV_PY)" -m unittest discover -s tests -p 'test_*.py'; \
	else \
		"$(PYTHON)" -m unittest discover -s tests -p 'test_*.py'; \
	fi

typecheck:
	@if [ -x "$(VENV_PY)" ]; then \
		"$(VENV_PY)" -m mypy render_models.py email_rendering.py web_rendering.py generate_html.py; \
	else \
		"$(PYTHON)" -m mypy render_models.py email_rendering.py web_rendering.py generate_html.py; \
	fi

snapshot-update:
	@if [ -x "$(VENV_PY)" ]; then \
		"$(VENV_PY)" scripts/update_snapshots.py; \
	else \
		"$(PYTHON)" scripts/update_snapshots.py; \
	fi

snapshot-check:
	@$(MAKE) snapshot-update
	@git diff --quiet -- tests/snapshots || ( \
		echo "Snapshot files are out of date. Run 'make snapshot-update' and commit the changes."; \
		git diff -- tests/snapshots; \
		exit 1; \
	)
