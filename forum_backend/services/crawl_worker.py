"""Run the existing crawler in an isolated process; stdout is the job log."""
import json
import sys
import os
import threading
from forum_backend.config import resolve_database_path
from forum_backend.services.managed_crawler import ManagedCrawler
from forum_backend.crawler import crawl_list_to_db, crawl_details_to_db, crawl_comments_to_db


def watch_manager(parent_pid):
    while True:
        threading.Event().wait(0.5)
        if os.getppid() != parent_pid:
            os._exit(3)  # Avoid orphan crawls after the API service crashes.


def main():
    actions = {'sync': crawl_list_to_db, 'details': crawl_details_to_db, 'comments': crawl_comments_to_db}
    try:
        config = json.load(sys.stdin)
        if config.get('_manager_pid'):
            threading.Thread(target=watch_manager, args=(config['_manager_pid'],), daemon=True).start()
        job_id = config.get('_crawl_job_id')
        result = ManagedCrawler(config, job_id, resolve_database_path(config)).run(sys.argv[1]) if job_id else actions[sys.argv[1]](config)
        unit = {'sync': '页', 'rankings': '份榜单'}.get(sys.argv[1], '个帖子') if job_id else '个帖子'
        print(f"采集结束：完成 {result['success_count']} {unit}，失败 {result['failure_count']} 项")
        if result['failure_count']:
            return 1 if sys.argv[1] == 'rankings' and not result['success_count'] else 2
        return 0
    except Exception as exc:
        print(f'采集失败：{exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
