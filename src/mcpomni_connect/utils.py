import logging
import platform
import sys
from pathlib import Path
import os
import colorlog 

# configuration setting for logging
LOGLEVEL = os.environ.get('LOGLEVEL', 'info').upper()
logger = logging.getLogger("MCPOmni Connect CLI")
logger.setLevel(LOGLEVEL)

# Create a color handler
handler = colorlog.StreamHandler()
formatter = colorlog.ColoredFormatter(
    '%(log_color)s%(levelname)s:   %(asctime)s - %(name)s -  %(message)s',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    }
)
handler.setFormatter(formatter)
logger.addHandler(handler)