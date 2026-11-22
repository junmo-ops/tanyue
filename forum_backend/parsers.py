from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlparse

from forum_backend.config import extract_query_value

@dataclass(frozen=True)
class Topic:
    """列表页中的单个帖子摘要。"""

    title: str
    url: str
    author: str
    posted_at: str
    replies: int
    views: int = 0
    heatlevel: int = 0
    author_id: str = ""
    preview_url: str = ""

class _TopicParser(HTMLParser):
    """解析 Discuz 列表页中的帖子行。"""

    def __init__(self, base_url: str):
        """初始化列表页解析状态。"""
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.topics: list[Topic] = []
        self._in_thread = False
        self._thread_depth = 0
        self._current = {
            "title": "",
            "url": "",
            "author": "",
            "author_id": "",
            "posted_at": "",
            "replies": "",
            "views": "",
            "heatlevel": "",
            "preview_url": "",
        }
        self._capture: str | None = None
        self._capture_parts: list[str] = []
        self._in_num_td = False
        self._num_depth = 0
        self._num_anchor_seen = False
        self._num_anchor_depth = 0
        self._num_anchor_parts: list[str] = []
        self._num_em_depth = 0
        self._num_em_parts: list[str] = []
        self._by_cell_count = 0
        self._in_first_by_cell = False
        self._by_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """处理开始标签，并根据 Discuz DOM 结构收集帖子字段。"""
        attr = {name: value or "" for name, value in attrs}
        element_id = attr.get("id", "")

        if tag == "tbody" and element_id.startswith("normalthread_"):
            # 一个 normalthread tbody 对应一条普通帖子，进入帖子级状态机。
            self._in_thread = True
            self._thread_depth = 1
            self._current = {
                "title": "",
                "url": "",
                "author": "",
                "author_id": "",
                "posted_at": "",
                "replies": "",
                "views": "",
                "heatlevel": "",
                "preview_url": "",
            }
            self._capture = None
            self._capture_parts = []
            self._in_num_td = False
            self._num_anchor_seen = False
            self._num_em_depth = 0
            self._num_em_parts = []
            self._by_cell_count = 0
            self._in_first_by_cell = False
            self._by_depth = 0
            return

        if not self._in_thread:
            return

        is_void = tag in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
        if not is_void:
            self._thread_depth += 1

        if tag == "img":
            title = attr.get("title", "").strip()
            img_identity = " ".join(
                [attr.get("src", ""), attr.get("file", ""), attr.get("class", ""), title]
            ).lower()
            if "heatlevel" in img_identity or "hot_" in img_identity or "热度" in title:
                self._current["heatlevel"] = attr.get("title", "").strip()
                return
        if tag == "img" and not self._current["preview_url"]:
            preview_src = attr.get("file") or attr.get("src") or attr.get("zoomfile")
            if preview_src and not _is_forum_icon(preview_src):
                self._current["preview_url"] = urljoin(self.base_url, preview_src)
            return

        if tag == "a" and "xst" in attr.get("class", "").split():
            self._current["url"] = urljoin(self.base_url, attr.get("href", ""))
            self._start_capture("title")
            return

        if tag == "td" and "by" in attr.get("class", "").split():
            self._by_cell_count += 1
            if self._by_cell_count == 1:
                # 列表页通常有两个 by 单元格，只有第一个是发帖作者和发帖时间。
                self._in_first_by_cell = True
                self._by_depth = 1
            return

        if self._in_first_by_cell and not is_void:
            self._by_depth += 1

        if tag == "cite" and self._in_first_by_cell:
            self._start_capture("author")
            return

        if tag == "a" and self._capture == "author" and not self._current["author_id"]:
            self._current["author_id"] = extract_query_value(attr.get("href", ""), "uid")

        if tag == "span" and self._in_first_by_cell and not self._current["posted_at"]:
            title = attr.get("title", "").strip()
            if title:
                self._current["posted_at"] = title
                if self._capture == "posted_at":
                    self._capture = None
                    self._capture_parts = []
                return
            if self._capture != "posted_at":
                self._start_capture("posted_at")
                return

        if tag == "td" and "num" in attr.get("class", "").split():
            # num 单元格里 a 是回复数、em 是浏览数。
            self._in_num_td = True
            self._num_depth = 1
            self._num_anchor_seen = False
            return

        if self._in_num_td:
            if not is_void:
                self._num_depth += 1
            if tag == "a" and not self._num_anchor_seen:
                self._num_anchor_seen = True
                self._num_anchor_depth = 1
                self._num_anchor_parts = []
            elif self._num_anchor_seen and self._num_anchor_depth > 0 and not is_void:
                self._num_anchor_depth += 1
            if tag == "em" and self._num_em_depth == 0:
                self._num_em_depth = 1
                self._num_em_parts = []
            elif self._num_em_depth > 0 and not is_void:
                self._num_em_depth += 1

    def handle_data(self, data: str) -> None:
        """把当前捕获字段、回复数和浏览数的文本片段收集起来。"""
        if self._capture:
            self._capture_parts.append(data)

        if self._in_num_td and self._num_anchor_seen and self._num_anchor_depth > 0:
            self._num_anchor_parts.append(data)
        if self._in_num_td and self._num_em_depth > 0:
            self._num_em_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """把自闭合标签按开始标签处理，兼容 img 等元素。"""
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        """处理结束标签，并在帖子结束时产出 Topic。"""
        if not self._in_thread:
            return

        if self._capture and (
            (self._capture == "title" and tag == "a")
            or (self._capture == "author" and tag == "cite")
            or (self._capture == "posted_at" and tag == "span")
        ):
            self._finish_capture()

        if self._in_num_td and self._num_anchor_seen and self._num_anchor_depth > 0:
            self._num_anchor_depth -= 1
            if self._num_anchor_depth == 0:
                self._current["replies"] = "".join(self._num_anchor_parts).strip()

        if self._in_num_td and self._num_em_depth > 0:
            self._num_em_depth -= 1
            if self._num_em_depth == 0:
                self._current["views"] = "".join(self._num_em_parts).strip()

        if self._in_num_td:
            self._num_depth -= 1
            if self._num_depth <= 0 and tag == "td":
                self._in_num_td = False

        if self._in_first_by_cell:
            self._by_depth -= 1
            if self._by_depth <= 0 and tag == "td":
                self._in_first_by_cell = False

        self._thread_depth -= 1
        if self._thread_depth <= 0 and tag == "tbody":
            self._finish_thread()

    def _start_capture(self, field: str) -> None:
        """开始捕获某个文本字段。"""
        self._capture = field
        self._capture_parts = []

    def _finish_capture(self) -> None:
        """结束当前文本字段捕获，并做空白归一化。"""
        if self._capture:
            self._current[self._capture] = " ".join(
                "".join(self._capture_parts).split()
            )
        self._capture = None
        self._capture_parts = []

    def _finish_thread(self) -> None:
        """结束一条帖子解析，并把有效结果加入 topics。"""
        title = self._current["title"].strip()
        url = self._current["url"].strip()
        if title and url:
            self.topics.append(
                Topic(
                    title=title,
                    url=url,
                    author=self._current["author"].strip(),
                    author_id=self._current["author_id"].strip(),
                    posted_at=self._current["posted_at"].strip(),
                    replies=_parse_int(self._current["replies"]),
                    views=_parse_int(self._current["views"]),
                    heatlevel=_parse_int(self._current["heatlevel"]),
                    preview_url=self._current["preview_url"].strip(),
                )
            )
        self._in_thread = False
        self._thread_depth = 0


class _DetailParser(HTMLParser):
    """解析帖子详情页中的正文、指标和评论。"""

    def __init__(self, base_url: str, tid: str, comment_page: int, fetched_at: str):
        """初始化详情页解析状态。"""
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.tid = tid
        self.comment_page = comment_page
        self.fetched_at = fetched_at
        self.content_text = ""
        self.image_urls: list[str] = []
        self.participant_count = 0
        self.money = 0
        self.rating = ""
        self.purchase_count = 0
        self.comments: list[dict] = []
        self._message_order = 0
        self._current_post_id = ""
        self._current_author = ""
        self._current_author_id = ""
        self._current_posted_at = ""
        self._capture: str | None = None
        self._capture_parts: list[str] = []
        self._in_message = False
        self._message_depth = 0
        self._message_parts: list[str] = []
        self._all_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """处理详情页开始标签，识别作者、时间、正文和图片。"""
        attr = {name: value or "" for name, value in attrs}
        element_id = attr.get("id", "")
        classes = attr.get("class", "").split()

        if element_id.startswith("post_"):
            self._current_post_id = element_id.replace("post_", "", 1)
            self._current_author = ""
            self._current_author_id = ""
            self._current_posted_at = ""

        if tag == "a" and "xw1" in classes:
            self._current_author_id = extract_query_value(attr.get("href", ""), "uid")
            self._start_capture("author")
            return

        if tag == "em" and element_id.startswith("authorposton"):
            self._start_capture("posted_at")
            return

        if element_id.startswith("postmessage_"):
            # 第一个 postmessage 是主楼正文，后续 postmessage 视为评论。
            self._message_order += 1
            self._in_message = True
            self._message_depth = 1
            self._message_parts = []
            self._current_post_id = element_id.replace("postmessage_", "", 1)
            return

        if self._in_message:
            if tag == "br":
                self._message_parts.append("\n")
            elif tag == "img" and self._message_order <= 1:
                src = attr.get("file") or attr.get("src") or attr.get("zoomfile")
                if src:
                    self.image_urls.append(urljoin(self.base_url, src))
            elif tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
                self._message_depth += 1

    def handle_data(self, data: str) -> None:
        """收集页面全文和当前正文块的文本。"""
        self._all_text_parts.append(data)
        if self._capture:
            self._capture_parts.append(data)
        if self._in_message:
            self._message_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """把详情页自闭合标签按开始标签处理。"""
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        """处理详情页结束标签，并在正文块结束时落成正文或评论。"""
        if self._capture == "author" and tag == "a":
            self._current_author = self._finish_capture_value()
        elif self._capture == "posted_at" and tag == "em":
            self._current_posted_at = _clean_posted_at(self._finish_capture_value())

        if self._in_message:
            self._message_depth -= 1
            if self._message_depth <= 0:
                message = _normalize_text("".join(self._message_parts))
                if self._message_order <= 1:
                    self.content_text = message
                elif message:
                    self.comments.append(
                        {
                            "tid": self.tid,
                            "comment_id": self._current_post_id,
                            "author": self._current_author,
                            "author_id": self._current_author_id,
                            "posted_at": self._current_posted_at,
                            "content_text": message,
                            "source_page": self.comment_page,
                            "fetched_at": self.fetched_at,
                        }
                    )
                self._in_message = False
                self._message_parts = []

    def close(self) -> None:
        """结束解析并从全文中补提详情指标。"""
        super().close()
        self._parse_metrics(_normalize_text(" ".join(self._all_text_parts)))

    def _parse_metrics(self, text: str, raw_html: str = "") -> None:
        """从页面文本中提取参与人数、金钱和评分。"""
        purchase_count = _parse_purchase_count(raw_html or text)
        if purchase_count:
            self.purchase_count = purchase_count
        metric_values = _parse_rating_summary_metrics(raw_html)
        if metric_values:
            self.participant_count = metric_values["participant_count"]
            self.money = metric_values["money"]
            self.rating = metric_values["rating"]
            return
        participant = re.search(r"参与人数\s*([+-]?\d+)", text)
        money = re.search(r"金钱\s*([+-]?\d+)", text)
        rating = re.search(r"评分\s*([+-]?\d+)", text)
        if participant:
            self.participant_count = _parse_int(participant.group(1))
        if money:
            self.money = _parse_int(money.group(1))
        if rating:
            self.rating = _clean_rating(rating.group(1))

    def _start_capture(self, field: str) -> None:
        """开始捕获详情页中的作者或发帖时间字段。"""
        self._capture = field
        self._capture_parts = []

    def _finish_capture_value(self) -> str:
        """结束当前字段捕获并返回归一化文本。"""
        value = _normalize_text("".join(self._capture_parts))
        self._capture = None
        self._capture_parts = []
        return value


def _normalize_text(value: str) -> str:
    """把 HTML 文本中的连续空白压缩成单个空格。"""
    return " ".join(value.replace("\xa0", " ").split())


def _clean_posted_at(value: str) -> str:
    """去掉 Discuz 发帖时间前缀。"""
    return value.replace("发表于", "", 1).strip()


def _parse_rating_summary_metrics(raw_html: str) -> dict[str, int | str] | None:
    """Parse Discuz rating summary values from the structured rating table."""
    if not raw_html:
        return None
    participant_label = "\u53c2\u4e0e\u4eba\u6570"
    money_label = "\u91d1\u94b1"
    rating_label = "\u8bc4\u5206"
    start = raw_html.find(participant_label)
    if start < 0:
        return None
    snippet = raw_html[start : start + 1200]

    participant = re.search(
        re.escape(participant_label) + r"(?:\s*<[^>]*>)*\s*([+-]?\d[\d,]*)",
        snippet,
        flags=re.S,
    )
    money = re.search(
        re.escape(money_label) + r"(?:\s*<[^>]*>)*\s*([+-]?\d[\d,]*)",
        snippet,
        flags=re.S,
    )
    rating = re.search(
        re.escape(rating_label) + r"(?:\s*<[^>]*>)*\s*([+-]?\d[\d,]*)",
        snippet,
        flags=re.S,
    )
    if not (participant and money and rating):
        return None
    return {
        "participant_count": _parse_int(participant.group(1)),
        "money": _parse_int(money.group(1)),
        "rating": _clean_rating(rating.group(1)),
    }


def _parse_purchase_count(value: str) -> int:
    """Extract Discuz paid-thread purchase count."""
    if not value:
        return 0
    match = re.search(r"\u5df2\u6709\s*(\d[\d,]*)\s*\u4eba\u8d2d\u4e70", value)
    if not match:
        return 0
    return _parse_int(match.group(1))

def parse_detail_page(
    html_text: str,
    base_url: str,
    tid: str,
    comment_page: int,
    fetched_at: str,
) -> dict:
    """解析详情页 HTML，返回正文、图片、详情指标和评论。"""
    parser = _DetailParser(base_url, tid, comment_page, fetched_at)
    parser.feed(html_text)
    parser.close()
    parser._parse_metrics(_normalize_text(" ".join(parser._all_text_parts)), html_text)
    return {
        "content_text": parser.content_text,
        "image_urls": parser.image_urls,
        "participant_count": parser.participant_count,
        "money": parser.money,
        "rating": parser.rating,
        "purchase_count": parser.purchase_count,
        "comments": parser.comments,
    }


def detect_detail_comment_page_count(html_text: str, tid: str) -> int:
    """从详情页分页链接中识别该帖子的最大评论页码。"""
    pages = {1}
    for href in re.findall(r"""href=["']([^"']+)["']""", html_text, flags=re.IGNORECASE):
        parsed = urlparse(html.unescape(href))
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if query.get("tid") != str(tid):
            continue
        page = _parse_int(query.get("page", ""))
        if page > 0:
            pages.add(page)
    return max(pages)


def _parse_int(value: str | int) -> int:
    """从字符串中提取第一个整数，失败时返回 0。"""
    value = str(value)
    match = re.search(r"-?\d+", value.replace(",", ""))
    return int(match.group(0)) if match else 0


def _clean_rating(value: str | int | None) -> str:
    """把评分字段清洗成非负数字字符串。"""
    if value is None:
        return ""
    match = re.search(r"-?\d+", str(value).replace(",", ""))
    if not match:
        return ""
    return str(abs(int(match.group(0))))


def _is_forum_icon(src: str) -> bool:
    """判断图片链接是否属于论坛 UI 图标而非帖子预览图。"""
    lowered = src.lower()
    icon_markers = (
        "static/image/",
        "template/",
        "common/",
        "folder_",
        "pin_",
        "digest_",
        "hot_",
    )
    return any(marker in lowered for marker in icon_markers)


def parse_topics(html_text: str, base_url: str) -> list[Topic]:
    """解析列表页 HTML，返回帖子摘要列表。"""
    parser = _TopicParser(base_url)
    parser.feed(html_text)
    return parser.topics
