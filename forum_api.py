from forum_backend.api.services import *  # noqa: F401,F403
from forum_backend.api.server import *  # noqa: F401,F403
from forum_backend.api.server import run_server


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Discuz Reader")
    parser.add_argument("--host", help="显式指定监听地址，关闭自动局域网发现")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        run_server(args.config, args.host or DEFAULT_HOST, args.port, auto_lan=args.host is None)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
