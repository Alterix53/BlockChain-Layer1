import os
import sys

# Ensure Workspace and Workspace/tests are in sys.path
workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
tests_dir = os.path.dirname(__file__)

for p in (workspace_dir, tests_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

