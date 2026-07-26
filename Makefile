.PHONY: test validate

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

validate:
	PYTHONPATH=src python3 scripts/validate_release_config.py
	PYTHONPATH=src python3 scripts/validate_governance_templates.py
	PYTHONPATH=src python3 scripts/validate_evaluator_build.py
	PYTHONPATH=src python3 scripts/validate_release_artifact_schemas.py
