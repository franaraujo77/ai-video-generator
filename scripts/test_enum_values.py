#!/usr/bin/env python3
"""Test script to check TaskStatus enum values."""

import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import TaskStatus

print("TaskStatus enum values:\n")
for status in TaskStatus:
    print(f"  {status.name:<30} = {status.value!r}")

print(f"\nTesting specific values:")
print(f"  TaskStatus.GENERATING_COMPOSITES.name  = {TaskStatus.GENERATING_COMPOSITES.name!r}")
print(f"  TaskStatus.GENERATING_COMPOSITES.value = {TaskStatus.GENERATING_COMPOSITES.value!r}")
print(f"  str(TaskStatus.GENERATING_COMPOSITES)  = {str(TaskStatus.GENERATING_COMPOSITES)!r}")
