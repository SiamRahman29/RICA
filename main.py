#!/usr/bin/env python3
"""
RICA - Rather Intelligent Conversational Assistant
Main entry point for the application.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path so we can import rica
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rica.cli import main


if __name__ == "__main__":
    """Main entry point for RICA."""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
