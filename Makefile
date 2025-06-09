lint      : ; pre-commit run --all-files

test      : ; pytest -q

strict-ci : ; SENTIENTOS_LINT_STRICT=1 python privilege_lint.py --no-emoji && \
              SENTIENTOS_LINT_STRICT=1 python verify_audits.py logs/ --no-emoji

coverage  : ; pytest -q --cov=sentientos --cov-report=term --cov-report=xml
