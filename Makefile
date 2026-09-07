PYTHONPATH_DEPS=PYTHONPATH=.deps
PYTHONPATH_APP=PYTHONPATH=.deps:.

NATIVE_CONFIG ?= native.env
PYTHON ?= python3

.PHONY: test test-cov test-ui test-all worker start stop status doctor

start stop status doctor worker:
	@$(PYTHONPATH_APP) $(PYTHON) scripts/native.py $@ --config "$(NATIVE_CONFIG)"

test:
	$(PYTHONPATH_DEPS) pytest tests -q --ignore=tests/test_ui_smoke.py

test-cov:
	$(PYTHONPATH_DEPS) pytest tests -q --ignore=tests/test_ui_smoke.py --cov=app --cov-report=term

test-ui:
	$(PYTHONPATH_DEPS) pytest tests/test_ui_smoke.py -q

test-all: test test-ui
