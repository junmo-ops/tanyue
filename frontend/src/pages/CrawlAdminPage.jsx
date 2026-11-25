import { useEffect, useState } from 'react'
import { Grid } from 'antd'
import { useControls } from '../useControls.js'
import { postJson, requestJson } from '../api/client.js'
import AdminControls from '../features/crawl/AdminControls.jsx'
import CrawlWorkModal from '../features/crawl/CrawlWorkModal.jsx'
import { ArrowLeftOutlined, PlusOutlined, RightOutlined } from '@ant-design/icons'
import JobDetail from '../features/crawl/JobDetail.jsx'
import ThemeToggle from '../ThemeToggle.jsx'
import { CrawlCurrentTask, CrawlRecords } from '../features/crawl/CrawlDashboard.jsx'
import './CrawlDashboard.css'

const kinds = { sync: '同步帖子列表', details: '补全帖子详情', comments: '抓取已开启的评论', rankings: '采集排行榜' }
const states = {
  queued: '排队中',
  stopping: '正在停止', cancelled: '已停止',
  running: '运行中', succeeded: '已完成',
  partial: '部分失败', failed: '失败', interrupted: '服务中断',
}
const viewOptions = [
  { value: 'overview', label: '概览', title: '' },
  { value: 'records', label: '任务记录', title: '' },
  { value: 'plans', label: '方案与定时', title: '' },
  { value: 'settings', label: '设置', title: '' },
]
const recordFilters = [
  { value: 'all', label: '全部', title: '' },
  { value: 'active', label: '进行中', title: '' },
  { value: 'attention', label: '异常', title: '' },
  { value: 'history', label: '历史', title: '' },
]

export default function CrawlAdminPage({ onBack }) {
  const { Alert, Button, Collapse, Descriptions, Drawer, Empty, Form, Input, InputNumber, Segmented, Select, Spin, Typography, message } = useControls()
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
  const groups = { all: data.items, active, attention: needsAttention, history }
  const filtered = groups[filter]
  const currentTask = running ?? active[0]
  const queuedCount = active.filter(job => job.status === 'queued').length
  const consoleView = view === 'overview' || view === 'records'
  const environment = loaded ? (data.environment === 'production' ? '生产环境' : '测试环境') : ''
  const siteContext = [data.site_name, view !== 'overview' && environment, view !== 'overview' && data.database].filter(Boolean).join(' · ')
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
  const stopButton = (job, quiet = false) => ['queued', 'running', 'stopping'].includes(job?.status) && (
    <Button danger={!quiet} size="small" disabled={!!error} loading={stopping === job.id || job.status === 'stopping'} onClick={() => stopJob(job.id)}>
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
  function showRecords(nextFilter) {
    setFilter(nextFilter)
    setPage(1)
    setView('records')
  }

  const navigation = <nav className="thread-query-panel crawl-navigation crawl-console-wrap" aria-label="采集管理导航">
    <div className="browse-mode-row">
      <div className="browse-mode-control">
        <Segmented value={view} onChange={setView} aria-label="采集管理分区" options={viewOptions} />
      </div>
    </div>
  </nav>
  const headerActions = <div className="thread-hero-actions">
    <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>返回帖子</Button>
    {(!isMobile || consoleView) && <Button type="primary" icon={<PlusOutlined />} disabled={!loaded || !!error}
      onClick={() => setCreating(true)}>新建采集</Button>}
  </div>
  const overviewTask = view === 'overview' && currentTask ? <CrawlCurrentTask job={currentTask}
    title={kinds[currentTask.kind] ?? currentTask.kind} labels={states}
    onQueue={() => showRecords('active')} onDetails={() => setSelected(currentTask.id)}
    action={stopButton(currentTask, true)} /> : null

  return (
    <main className={`app-shell thread-list-shell crawl-admin crawl-console${consoleView ? ' crawl-console-workspace' : ''}`}>
      <header className="crawl-console-header">
        <div className="crawl-console-wrap crawl-console-masthead">
          <div className="crawl-console-brand">
            <span className="crawl-console-mark" aria-hidden="true">坛</span>
            <div><h1>采集管理</h1>{siteContext && <p>{siteContext}</p>}</div>
            <ThemeToggle />
          </div>
          {headerActions}
        </div>
      </header>
      <div className="crawl-console-nav">{navigation}</div>
      <div className="crawl-admin-content crawl-console-wrap crawl-console-content">
        {error && <Alert type="error" showIcon title="暂时无法获取最新状态，正在自动重连" description={error} />}
        {!loaded && !error && <Spin tip="正在加载采集状态"><div style={{ height: 120 }} /></Spin>}
        {view === 'overview' && loaded && <div className="crawl-console-status" aria-label="采集状态">
          <span className="crawl-console-health">
            <span className={`crawl-console-signal${error ? ' is-offline' : ''}`} aria-hidden="true" />
            {error ? '连接异常' : '服务已连接'}
            <small>{environment}</small>
          </span>
          <span>运行中 <strong>{active.length - queuedCount}</strong></span>
          <span>等待 <strong>{queuedCount}</strong></span>
          {needsAttention.length > 0 && <Button className="crawl-console-attention" type="text"
            onClick={() => showRecords('attention')}>异常 {needsAttention.length} 条 <RightOutlined /></Button>}
        </div>}
        <AdminControls view={view} isMobile={isMobile} onQueued={queued} onNavigate={setView}
          forums={data.forums} overviewTask={overviewTask} showOverview={loaded} />
        {consoleView && loaded && <CrawlRecords
          overview={view === 'overview'} records={records}
          filterOptions={recordFilters.map(option => ({ ...option, label: `${option.label} ${groups[option.value].length}` }))}
          filter={filter} onFilter={showRecords} count={filtered.length} page={visiblePage} onPage={setPage}
          onAll={() => showRecords('all')} onDetails={setSelected} onStop={stopJob} onResume={resume}
          busy={submitting} stopping={stopping} offline={!!error} kinds={kinds} labels={states} />}
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
