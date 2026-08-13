PYTHONPATH_DEPS=PYTHONPATH=.deps
PYTHONPATH_APP=PYTHONPATH=.deps:.

.PHONY: test test-cov test-ui test-all worker

worker:
	@set -e; \
	cohortome_perl_root="$${PERL_LOCAL_LIB_ROOT:-$$HOME/perl5}"; \
	if [ -d "$$cohortome_perl_root/lib/perl5" ]; then \
		export PERL5LIB="$$cohortome_perl_root/lib/perl5$${PERL5LIB:+:$$PERL5LIB}"; \
		export PATH="$$cohortome_perl_root/bin:$$PATH"; \
	fi; \
	$(PYTHONPATH_APP) python3 -c 'from dotenv import load_dotenv; load_dotenv("docker/.env"); from rq.cli import main; main()' worker analysis --url redis://127.0.0.1:6379/0

test:
	$(PYTHONPATH_DEPS) pytest tests/test_bff.py -q

test-cov:
	$(PYTHONPATH_DEPS) pytest tests/test_bff.py --cov=app --cov-report=term -q

test-ui:
	$(PYTHONPATH_DEPS) pytest tests/test_ui_smoke.py -q

test-all: test test-ui
