export const kinds={sync:'同步帖子列表',details:'补全帖子详情',comments:'抓取已开启的评论',rankings:'采集排行榜'}
let serial=0
export const nextKey=()=>++serial
export const settingsFields=[
 ['list_sync','workers','列表并发',1,8],['list_sync','refresh_pages','最近刷新页数',1,100],['list_sync','known_page_streak','连续已知页停止阈值',1,20],['list_sync','max_pages_per_fid','单板块页数上限',1,2000],['details','workers','帖子并发',1,8],['details','limit','默认处理帖子上限',1,100000],['comments','page_workers','单帖评论页并发',1,8],['network','delay_seconds','请求间隔（秒）',0,60,.1],['network','jitter_seconds','随机间隔（秒）',0,60,.1],['network','retries','失败重试次数',0,5],['network','retry_backoff_seconds','重试退避（秒）',0,120,.1]]
