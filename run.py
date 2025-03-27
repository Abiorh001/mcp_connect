#!/usr/bin/env python3
import asyncio

from src.mcpomni_connect.main import main
from src.mcpomni_connect.utils import logger

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Error in main: {e}")
