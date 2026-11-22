import { useEffect, useState } from 'react'
import { Grid } from 'antd'
import { useControls } from '../useControls.js'
import { postJson, requestJson } from '../api/client.js'
import AdminControls from '../features/crawl/AdminControls.jsx'
import CrawlWorkModal from '../features/crawl/CrawlWorkModal.jsx'
import { ArrowLeftOutlined, PlusOutlined, RightOutlined, SyncOutlined } from '@ant-design/icons'
import JobDetail, { JobResult } from '../features/crawl/JobDetail.jsx'
import ThemeToggle from '../ThemeToggle.jsx'

const kinds = { sync: '同步帖子列表', details: '补全帖子详情', comments: '抓取已开启的评论', rankings: '采集排行榜' }
const states = {
  queued: ['排队中', 'default'],
  stopping: ['正在停止', 'warning'], cancelled: ['已停止', 'default'],
  running: ['运行中', 'processing'], succeeded: ['已完成', 'success'],
  partial: ['部分失败', 'warning'], failed: ['失败', 'error'], interrupted: ['服务中断', 'warning'],
}
const time = (value) => value ? new Date(`${value.replace(' ', 'T')}Z`).toLocaleString('zh-CN', { hour12: false }) : '—'

export default function CrawlAdminPage({ onBack }) {
  const { Alert, Button, Card, Collapse, Descriptions, Drawer, Empty, Form, Input, InputNumber, Pagination, Segmented, Select, Space, Spin, Tag, Typography, message } = useControls()
  const [form] = Form.useForm()
  const screens = Grid.useBreakpoint()
  const isMobile = screens.md === false
  const [view, setView] = useState('overview')
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(1)
  const kind = Form.useWatch('kind', form) || 'sync'
  const [data, setData] = useState({ items: [], forums: [] })
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [stopping, setStopping] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [preview, setPreview] = useState(null)
  const [observedAt, setObservedAt] = useState(() => Date.now())
  useEffect(() => {
    let stopped = false
    let timer
    const controller = new AbortController()
    async function poll() {
      try {
        const payload = await requestJson('/api/crawl-jobs', { signal: controller.signal })
        if (!stopped) { setData(payload); setError(''); setLoaded(true); setObservedAt(Date.now()) }
      } catch (err) {
        if (!stopped) setError(err.message)
      } finally {
        if (!stopped) timer = setTimeout(poll, 2000)
      }
    }
    poll()
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [])
  const current = data.items.find((item) => item.id === selected)
  const active = data.items.filter((item) => ['running', 'stopping', 'queued'].includes(item.status))
  const running = active.find((item) => item.status !== 'queued')
  const needsAttention = data.items.filter((item) => ['failed', 'partial', 'interrupted'].includes(item.status))
  const history = data.items.filter((item) => !['running', 'stopping', 'queued'].includes(item.status))
  const filtered = filter === 'active' ? active : filter === 'attention' ? needsAttention : filter === 'history' ? history : data.items
  const visiblePage = Math.min(page, Math.max(1, Math.ceil(filtered.length / 8)))
  const records = view === 'overview' ? history.slice(0, 3) : filtered.slice((visiblePage - 1) * 8, visiblePage * 8)
  async function stopJob(id) {
    setStopping(id)
    try {
      await postJson('/api/crawl-jobs/stop', { id })
      setData(await requestJson('/api/crawl-jobs'))
      message.success('已发送停止请求，已入库的数据会保留')
    } catch (err) { message.error(err.message) }
    finally { setStopping('') }
  }
  const stopButton = (job) => ['queued', 'running', 'stopping'].includes(job?.status) && (
    <Button danger size="small" disabled={!!error} loading={stopping === job.id || job.status === 'stopping'} onClick={() => stopJob(job.id)}>
      {job.status === 'queued' ? '取消排队' : job.status === 'stopping' ? '正在停止' : '停止任务'}
    </Button>
  )
  function taskBody(values = form.getFieldsValue()) {
    const body = { kind: values.kind || 'sync' }
    const keys = body.kind === 'sync' ? ['fid', 'pages', 'start_page'] : body.kind === 'details' ? ['limit', 'tids'] : body.kind === 'comments' ? ['limit'] : []
    keys.forEach((key) => { if (values[key] != null && values[key] !== '') body[key] = values[key] })
    return body
  }
  async function showPreview(values) {
    setSubmitting(true)
    try {
      const body = taskBody(values)
      const result = await postJson('/api/crawl-jobs/preview', body)
      setPreview({ ...result, body })
      setCreating(false)
    } catch (err) { message.error(err.message) }
    finally { setSubmitting(false) }
  }
  async function queued(result) {
    setSelected(result.id)
    setCreating(false)
    try { setData(await requestJson('/api/crawl-jobs')) }
    catch { message.warning('任务已加入队列，状态暂未刷新，请勿重复提交') }
  }
  async function resume(id) {
    setSubmitting(true)
    try { await queued(await postJson('/api/crawl-jobs/resume', { id })); message.success('已安排续爬，成功部分会跳过') }
    catch (err) { message.error(err.message) }
    finally { setSubmitting(false) }
  }
  async function submit() {
    setSubmitting(true)
    try {
      await queued(await postJson('/api/crawl-jobs', preview.body))
      setPreview(null)
      message.success('采集任务已加入队列')
    } catch (err) { message.error(err.message) }
    finally { setSubmitting(false) }
  }
  function actions(job) {
    if (['failed', 'partial', 'cancelled', 'interrupted'].includes(job.status)) {
      return <Button loading={submitting} disabled={!!error} onClick={() => resume(job.id)}>继续未完成</Button>
    }
    return stopButton(job)
  }
  return (
    <main className="app-shell thread-list-shell crawl-admin">
      <header className="thread-hero">
        <div className="thread-hero-copy">
          <div className="thread-hero-title"><SyncOutlined className="header-icon" /><Typography.Title level={1}>采集管理</Typography.Title><ThemeToggle /></div>
          <div className="data-status-line crawl-connection"><span className={`environment-badge ${data.environment === 'test' ? 'is-test' : ''}`}>{loaded ? data.environment === 'production' ? '生产环境' : '测试环境' : '连接中'}</span><span>{data.site_name}</span><span>{data.database}</span><span>{error ? '连接异常 · 当前显示上次获取的数据' : loaded ? '服务已连接 · 自动更新' : '正在获取任务'}</span></div>
        </div>
        <div className="thread-hero-actions">
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>返回帖子</Button>
          {(!isMobile || view === 'overview' || view === 'records') && (
            <Button type="primary" icon={<PlusOutlined />} disabled={!loaded || !!error} onClick={() => setCreating(true)}>新建采集</Button>
          )}
        </div>
      </header>
      <div className="thread-reader-content crawl-admin-content">
        <nav className="thread-query-panel crawl-navigation" aria-label="采集管理导航">
          <div className="browse-mode-row">
            <div className="browse-mode-control">
              <Segmented value={view} onChange={setView} options={[{ value: 'overview', label: '概览' }, { value: 'records', label: '任务记录' }, { value: 'plans', label: '方案与定时' }, { value: 'settings', label: '设置' }]} />
            </div>
          </div>
        </nav>
        {error && <Alert type="error" showIcon title="暂时无法获取最新状态，正在自动重连" description={error} />}
        {!loaded && !error && <Spin tip="正在加载采集状态"><div style={{ height: 120 }} /></Spin>}
        {view === 'overview' && loaded && <>
          <div className="crawl-overview-metrics">
            <div><span>当前执行</span><strong>{running ? kinds[running.kind] : '暂无运行任务'}</strong></div>
            <div><span>等待执行</span><strong>{active.filter((j) => j.status === 'queued').length}<small> 个任务</small></strong></div>
            <button onClick={() => { setFilter('attention'); setPage(1); setView('records') }}><span>异常记录</span><strong>{needsAttention.length}<small> 条记录</small></strong></button>
          </div>
          {active.length > 0 && <Card title={running ? '正在采集' : '等待执行'} extra={<Button type="link" onClick={() => { setFilter('active'); setPage(1); setView('records') }}>查看队列 ({active.length})</Button>}>
            <div className="crawl-task-heading"><Typography.Text strong>{kinds[(running || active[0]).kind]}</Typography.Text><Tag color={states[(running || active[0]).status]?.[1]}>{states[(running || active[0]).status]?.[0]}</Tag></div>
            <JobResult job={running || active[0]} observedAt={observedAt} />
            <Space wrap className="crawl-job-actions"><Button type={isMobile ? 'text' : 'default'} onClick={() => setSelected((running || active[0]).id)}>查看详情</Button>{actions(running || active[0])}</Space>
          </Card>}
        </>}
        <AdminControls view={view} isMobile={isMobile} onQueued={queued} onNavigate={setView} onCreate={() => setCreating(true)} forums={data.forums} />
        {(view === 'overview' || view === 'records') && loaded && <Card title={view === 'overview' ? '最近采集结果' : '任务记录'} extra={view === 'overview' ? <Button type="link" onClick={() => { setFilter('all'); setView('records') }}>全部记录</Button> : <Typography.Text type="secondary">保留最近 30 次历史</Typography.Text>}>
          {view === 'records' && <div className="crawl-record-filters"><Segmented value={filter} onChange={(value) => { setFilter(value); setPage(1) }} options={[{value:'all',label:'全部'}, {value:'active',label:'进行中'}, {value:'attention',label:'异常'}, {value:'history',label:'历史'}]} /></div>}
          {!records.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={view === 'overview' ? '还没有采集结果，从常用方案开始吧' : '没有符合条件的任务'} /> : <div className="crawl-job-list">{records.map((job) => {
            const taskAction = actions(job)
            const details = <Button
              type={isMobile ? 'text' : 'default'}
              className="crawl-job-detail-link"
              icon={isMobile ? <RightOutlined /> : undefined}
              iconPlacement="end"
              onClick={() => setSelected(job.id)}
            >详情</Button>
            return <article className="crawl-job-row" key={job.id}>
              <div className="crawl-job-identity"><div className="crawl-task-heading"><Typography.Text strong>{kinds[job.kind]}</Typography.Text><Tag className={job.status === 'succeeded' ? 'crawl-status-success' : undefined} color={states[job.status]?.[1]}>{states[job.status]?.[0]}</Tag></div><Typography.Text type="secondary">{time(job.created_at)}</Typography.Text></div>
              {isMobile && details}
              <div className="crawl-job-result">{job.kind === 'rankings' ? `已保存 ${job.progress?.completed || 0} 份 · 失败 ${job.progress?.failed || 0} 份` : job.progress ? `新增 ${job.progress.new} · 更新 ${job.progress.updated} · 失败 ${job.progress.failed}` : '等待执行'}{job.kind === 'comments' && <span>保存评论 {job.progress?.saved_comments || 0}</span>}</div>
              {(!isMobile || taskAction) && <Space wrap className="crawl-job-actions">{!isMobile && details}{taskAction}</Space>}
            </article>
          })}</div>}
          {view === 'records' && filtered.length > 8 && <Pagination className="crawl-record-pagination" simple current={visiblePage} pageSize={8} total={filtered.length} onChange={setPage} showSizeChanger={false} />}
        </Card>}
      </div>
      <Drawer className="crawl-detail-drawer" title="任务详情" placement={isMobile ? 'bottom' : 'right'} height={isMobile ? '85dvh' : undefined} open={!!selected} onClose={() => setSelected('')} width={screens.md ? 620 : '100%'}>
        {current ? <JobDetail key={current.id} job={current} observedAt={observedAt} actions={actions(current)} onBack={onBack} /> : <Empty description="该记录已不在最近任务中" />}
      </Drawer>
      <CrawlWorkModal isMobile={isMobile} title="新建采集" open={creating} onCancel={() => setCreating(false)} confirmLoading={submitting} okText="预览采集范围"
        okButtonProps={{ htmlType: 'submit', form: 'crawl_task', disabled: !loaded || !!error }} forceRender>
          <Form className="crawl-work-form" id="crawl_task" name="crawl_task" form={form} layout="vertical" initialValues={{ kind: 'sync' }} onFinish={showPreview}>
            <Form.Item name="kind" label="采集类型"><Select options={Object.entries(kinds).map(([value, label]) => ({ value, label }))} /></Form.Item>
            {kind === 'sync' ? <>
              <Form.Item name="fid" label="板块"><Select allowClear placeholder="全部已配置板块" options={data.forums} /></Form.Item>
              <Collapse ghost items={[{ key: 'range', label: '指定页数与起始页（可选）', forceRender: true, children: <>
              <div className="crawl-work-field-pair">
                <Form.Item name="pages" label="抓取页数"><InputNumber min={1} max={2000} precision={0} inputMode="numeric" placeholder="自动增量" /></Form.Item>
                <Form.Item name="start_page" label="起始页"><InputNumber min={1} max={100000} precision={0} inputMode="numeric" placeholder="1" /></Form.Item>
              </div>
              <Typography.Text type="secondary">填写起始页时，也需要填写抓取页数。</Typography.Text>
              </> }]} />
              <Typography.Paragraph type="secondary">默认自动增量同步，达到已知页面阈值后停止。</Typography.Paragraph>
            </> : kind === 'rankings' ? <Typography.Paragraph type="secondary">采集论坛的 20 份榜单，按北京时间保留每份榜单当天最后一次成功的快照。</Typography.Paragraph> : <>
              <Form.Item name="limit" label="最多处理帖子数（留空使用配置）"><InputNumber min={1} max={100000} precision={0} style={{ width: '100%' }} /></Form.Item>
              {kind === 'details' && <Form.Item name="tids" label="指定帖子 ID（可选，优先于数量上限）"><Input placeholder="例如：3513476,3516439" maxLength={4000} /></Form.Item>}
              <Typography.Paragraph type="secondary">{kind === 'comments' ? '仅抓取已开启评论开关的帖子；是否刷新已有评论遵循当前配置。' : '默认处理待补全的帖子，也可指定已有帖子的 ID。'}</Typography.Paragraph>
            </>}
          </Form>
      </CrawlWorkModal>
      <CrawlWorkModal isMobile={isMobile} title="确认本次采集范围" open={!!preview} onCancel={() => { setPreview(null); setCreating(true) }} onOk={submit} confirmLoading={submitting} cancelText="返回修改" okText="加入采集队列">
        {preview && <>
          <Descriptions column={1} items={[
            { key: 'db', label: '数据环境', children: `${preview.environment} · ${preview.database}` },
            { key: 'kind', label: '任务类型', children: kinds[preview.kind] },
            { key: 'range', label: '预计范围', children: preview.kind === 'sync' ? `${preview.fids.map((fid) => data.forums.find((f) => f.value === fid)?.label || fid).join('、')} · ${preview.pages ? `${preview.pages} 页` : '自动增量，页数待定'}` : `${preview.target_count} ${preview.kind === 'rankings' ? '份榜单' : '个帖子'}` },
            { key: 'pending', label: '详情待办', children: `${preview.detail_pending} 个待抓取，${preview.detail_failed} 个失败` },
          ]} />
          <Typography.Paragraph type="secondary">{preview.note}</Typography.Paragraph>
          {!preview.anonymous_allowed && !preview.cookie_available && <Alert type="warning" showIcon title="未找到可用的 Cookie 文件；任务开始前需要更新 Cookie。" />}
        </>}
      </CrawlWorkModal>
    </main>
  )
}
