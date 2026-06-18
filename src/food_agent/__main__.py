"""food_agent.__main__: 让 `python -m food_agent` 工作."""
import sys

from food_agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
