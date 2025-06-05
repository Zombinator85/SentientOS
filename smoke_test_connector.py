from subprocess import call, check_call
import sys

print("Running connector smoke tests...")
check_call([sys.executable, "privilege_lint.py"])
call([sys.executable, "-m", "pytest", "-q", "tests/test_openai_connector.py"])
print("done")
