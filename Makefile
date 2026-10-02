PYTHON ?= python3

.PHONY: setup ingest test report

setup:
	$(PYTHON) -m pip install -r requirements.txt

ingest:
	$(PYTHON) -m src.repository_availability --validate-only

test:
	$(PYTHON) -m unittest discover -s tests -v

report:
	$(PYTHON) -m src.repository_availability
	$(PYTHON) -m src.plot_repository_availability
