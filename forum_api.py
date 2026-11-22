from forum_backend.api.services import *  # noqa: F401,F403
from forum_backend.api.server import *  # noqa: F401,F403
from forum_backend.api.server import run_server


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Discuz Reader")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        run_server(args.config, args.host, args.port)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
