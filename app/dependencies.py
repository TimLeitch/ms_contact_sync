from typing import Optional
import os
import logging
import logging.config
from fastapi import Request
from fastapi.templating import Jinja2Templates

# Configure logging
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
        },
    },
    'loggers': {
        '': {  # Root logger
            'handlers': ['console'],
            'level': 'INFO',
        },
        'httpcore': {
            'level': 'WARNING',
        },
        'httpx': {
            'level': 'WARNING',
        },
    },
})

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")
