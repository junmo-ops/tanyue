from forum_backend.config import *  # noqa: F401,F403
from forum_backend.crawler import *  # noqa: F401,F403
from forum_backend.db import *  # noqa: F401,F403
from forum_backend.parsers import *  # noqa: F401,F403
from forum_backend.crawler import main


if __name__ == "__main__":
    raise SystemExit(main())
