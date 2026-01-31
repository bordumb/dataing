#!/bin/bash
# Health check script for Temporal worker
# Verifies the worker can connect to Temporal server

python -c "
import asyncio
from temporalio.client import Client
async def check():
    await Client.connect('temporal:7233')
asyncio.run(check())
" 2>/dev/null && exit 0 || exit 1
