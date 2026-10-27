#!/usr/bin/env python3
import uvicorn
from db import init_db

if __name__ == "__main__":
    print("=" * 60)
    print("Initializing Database & Starting AICTE APAAR Server...")
    print("Portal URL: http://127.0.0.1:8000")
    print("=" * 60)
    init_db()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
