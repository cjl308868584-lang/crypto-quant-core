.PHONY: test validate

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

validate:
	PYTHONPATH=src python3 scripts/validate_release_config.py
