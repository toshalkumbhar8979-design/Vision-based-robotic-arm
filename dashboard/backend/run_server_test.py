#!/usr/bin/env python3
"""Test runner: starts the dashboard backend without reload for endpoint smoke tests."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8060, reload=False, log_level="warning")
