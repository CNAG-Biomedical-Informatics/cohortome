PYTHONPATH_DEPS=PYTHONPATH=.deps

.PHONY: test test-cov test-ui test-all

test:
	$(PYTHONPATH_DEPS) pytest tests/test_bff.py -q

test-cov:
	$(PYTHONPATH_DEPS) pytest tests/test_bff.py --cov=app --cov-report=term -q

test-ui:
	$(PYTHONPATH_DEPS) pytest tests/test_ui_smoke.py -q

test-all: test test-ui
