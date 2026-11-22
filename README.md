# Discuz Reader

自托管的 Discuz! X3.5 采集与阅读工具。你可以在电脑上定时同步多个论坛，在手机上继续找未读热帖、查看评论或回看某一天的排行榜。每个论坛独立保存帖子、登录状态、阅读记录和定时任务。

![使用模拟数据的帖子列表](docs/reader-demo.png)

## 第一次使用

1. 解压发行包 `discuz-reader-0.1.0.zip`，进入其中的 `discuz-reader` 目录。安装 Python 3.13 后运行 `python3 forum_api.py`。Windows 可使用 `py -3.13 forum_api.py`。
2. 打开 [本地阅读器](http://127.0.0.1:8000/)，点击「接入第一个论坛」。输入论坛安装目录，如 `https://forum.example.org/bbs/`。公共板块可以匿名读取；需要登录时使用该论坛属于自己的 Cookie。
3. 点击「识别板块」，勾选一个板块，用「预览」检查样本帖。接入后在「采集管理 → 新建采集」选择同步列表、指定板块和 **1 页**。任务完成后返回帖子列表，切换到「全部帖子」查看。
4. 在「方案与定时」为当前站点建立定时任务。调度器随服务运行，电脑需保持唤醒。

## 手机访问

本机默认监听 `127.0.0.1:8000`。通过 Tailscale 访问时，先让电脑和手机加入同一个私有网络，在电脑终端设置环境变量 `FORUM_PASSWORD`，然后绑定电脑的 Tailscale 地址。例如在 zsh 中运行：

```sh
read -rs 'FORUM_PASSWORD?管理密码：'
export FORUM_PASSWORD
python3 forum_api.py --host "$(tailscale ip -4)"
```

在手机上打开 `http://电脑的Tailscale地址:8000/`，用户名为 `admin`，密码为刚才输入的值。局域网访问可将 `--host` 指向电脑的局域网 IPv4 地址。浏览器使用 HTTP Basic 认证，请在加密隧道或 HTTPS 连接中传输凭据。该服务面向单人使用，具有登录凭据的设备可以读写所有站点。

## 兼容范围

| 功能 | 如何确认 |
| --- | --- |
| 板块和列表 | 支持标准 Discuz 桌面模板的动态链接及常见伪静态链接。先用一个板块同步一页。 |
| 详情与评论 | 用「预览」读取样本帖。登录权限、模板及评论分页会影响可读范围。 |
| 排行榜 | 站点需开放对应排行。预览检查今日回复榜；完整采集按排行和周期记录结果。历史榜单来自本机采集的每日快照。 |

采集目标应是你有权读取的公共网络论坛。采集器限制并发、支持请求间隔，拒绝内网目的地址和跨源重定向。请遵守站点规则，合理设置抓取频率。

## 备份与开发

服务停止后备份整个 `data/` 目录，以及自行创建的 `config.json`。各站点的 `cookie.txt` 属于登录凭据，备份应按敏感数据保管。首次安装自动使用 `config.example.json`；需要自定义数据库路径时可复制为 `config.json`。

源码开发使用 Python 3.13 和 Node.js 24，在仓库根目录运行：

```sh
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
python3 -m unittest discover -s tests
python3 forum_api.py
```

运行 `python3 scripts/package_release.py` 生成包含网页和后端的 ZIP。代码采用 MIT 许可证，前端依赖的许可信息随构建产物保存在 `web/THIRD-PARTY.md`。问题反馈请附版本、失败步骤与脱敏错误信息，移除 Cookie、真实帖子、私有域名和数据库。
