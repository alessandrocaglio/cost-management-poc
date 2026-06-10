#!/usr/bin/env python3
"""
Cost Management Redux Server Launcher

Starts the FastAPI backend server with optional token override for development/testing.

Usage:
    python run_server.py                           # Use OAuth2 from .env
    python run_server.py --token YOUR_TOKEN        # Override with bearer token
"""

import argparse
import os
import sys
import uvicorn
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Cost Management Redux Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Production mode with OAuth2 credentials from .env
  python run_server.py

  # Development mode with TMP_TOKEN from .env
  python run_server.py --token $(grep TMP_TOKEN .env | cut -d= -f2)

  # Development mode with explicit token
  python run_server.py --token "eyJhbGci..."

  # Custom host and port
  python run_server.py --host 127.0.0.1 --port 8080
        """
    )

    parser.add_argument(
        "--token",
        type=str,
        help="Override authentication with a bearer token (for development/testing)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Server bind address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes (development mode)"
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to .env file (default: .env)"
    )

    args = parser.parse_args()

    # Resolve paths
    project_root = Path(__file__).parent
    backend_dir = project_root / "backend"
    env_file = project_root / args.env_file

    if not backend_dir.exists():
        print(f"Error: Backend directory not found at {backend_dir}")
        sys.exit(1)

    # Set override token as environment variable if provided
    # This must be set BEFORE uvicorn.run to ensure it's inherited by subprocesses
    if args.token:
        print(f"🔑 Using override token: {args.token[:20]}...")
        os.environ['OVERRIDE_TOKEN'] = args.token

    print(f"🚀 Starting Cost Management Redux")
    print(f"   Host: {args.host}")
    print(f"   Port: {args.port}")
    print(f"   Auth: {'Override Token' if args.token else 'OAuth2 (from .env)'}")
    print(f"   Reload: {args.reload}")
    print(f"   Env file: {env_file}")
    print(f"\n   Dashboard: http://localhost:{args.port}")
    print(f"   API Docs: http://localhost:{args.port}/docs\n")

    # Start uvicorn from backend directory
    # We need to set the app path relative to backend dir
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(backend_dir)],
        env_file=str(env_file),
        log_level="info",
        app_dir=str(backend_dir)
    )


if __name__ == "__main__":
    main()
