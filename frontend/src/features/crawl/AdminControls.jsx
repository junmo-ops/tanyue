import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Dropdown, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Tabs, Tag, Typography, message } from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import ResponsiveRecords from './ResponsiveRecords.jsx'
import CrawlWorkModal from './CrawlWorkModal.jsx'
import { postJson, requestJson } from '../../api/client.js'

const labels = { sync: '同步列表', details: '补全详情', comments: '抓取评论', rankings: '采集排行榜' }
const taskTypes = Object.entries(labels).map(([value, label]) => ({ value, label }))
const maxPlanSteps = 10
const fields = [
  ['list_sync', 'workers', '列表并发', 1, 8], ['list_sync', 'refresh_pages', '最近刷新页数', 1, 100],
  ['list_sync', 'known_page_streak', '连续已知页停止阈值', 1, 20], ['list_sync', 'max_pages_per_fid', '单板块页数上限', 1, 2000],
  ['details', 'workers', '帖子并发', 1, 8], ['details', 'limit', '默认处理帖子上限', 1, 100000],
  ['comments', 'page_workers', '单帖评论页并发', 1, 8],
  ['network', 'delay_seconds', '请求间隔（秒）', 0, 60, 1], ['network', 'jitter_seconds', '随机间隔（秒）', 0, 60, 1],
  ['network', 'retries', '失败重试次数', 0, 5], ['network', 'retry_backoff_seconds', '重试退避（秒）', 0, 120, 1],
]
const date = (value) => value ? new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'

export default function AdminControls({ view, isMobile, onQueued, onNavigate, onCreate, forums }) {
  const [data, setData] = useState({ presets: [], schedules: [] })
  const [settingsForm] = Form.useForm()
  const [planForm] = Form.useForm()
  const [scheduleForm] = Form.useForm()
  const [editingPlan, setEditingPlan] = useState(null)
  const [editingSchedule, setEditingSchedule] = useState(null)
  const [deletingRecord, setDeletingRecord] = useState(null)
  const scheduleMode = Form.useWatch('mode', scheduleForm)
  const [controlTab, setControlTab] = useState('plans')
  const [runPreview, setRunPreview] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [login, setLogin] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let timer
    let initialized = false
    async function load() {
      try {
        const result = await requestJson('/api/crawl-admin', { signal: controller.signal })
        if (controller.signal.aborted) return
        setData(result); setError('')
        if (!initialized) { settingsForm.setFieldsValue(result.settings); initialized = true }
      } catch (err) { if (!controller.signal.aborted) setError(err.message) }
      if (!controller.signal.aborted) timer = setTimeout(load, 5000)
    }
    load()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [settingsForm])
  async function act(key, path, body, done) {
    setBusy(key)
    try {
      const result = await postJson(`/api/crawl-admin/${path}`, body)
      await done?.(result)
      try { setData(await requestJson('/api/crawl-admin')) }
      catch { message.warning('操作已完成，页面状态暂未刷新，请勿重复提交') }
      if (path !== 'check-login') message.success(path === 'presets/run' ? `已加入 ${result.ids?.length || 1} 个采集任务，将按顺序执行` : '操作已保存')
    } catch (err) { message.error(err.message) }
    finally { setBusy('') }
  }
  function editPlan(plan = null) {
    const next = plan || { name: '', steps: [{ kind: 'sync' }] }
    planForm.resetFields(); planForm.setFieldsValue(next); setEditingPlan(next)
  }
  function editSchedule(schedule = null) {
    const next = schedule ? { ...schedule, enabled: !!schedule.enabled } : { name: '', mode: 'interval', every_minutes: 60, daily_time: '09:00', busy_policy: 'skip', enabled: false }
    scheduleForm.resetFields(); scheduleForm.setFieldsValue(next); setEditingSchedule(next)
  }
  async function previewPlan(plan) {
    setBusy(plan.id)
    try {
      const previews = await Promise.all(plan.steps.map(step => postJson('/api/crawl-jobs/preview', step)))
      setRunPreview({ plan, previews })
    } catch (err) { message.error(err.message) }
    finally { setBusy('') }
  }
  function deleteAction(row, kind, mobile) {
    const title = kind === 'presets' ? '删除这个方案？' : '删除这个定时计划？'
    if (!mobile) return <Popconfirm title={title} onConfirm={() => act(row.id, `${kind}/delete`, { id: row.id })}>
      <Button danger>删除</Button>
    </Popconfirm>
    return <Dropdown
      trigger={['click']}
      placement="bottomRight"
      classNames={{ root: 'crawl-record-menu' }}
      menu={{
        items: [{ key: 'delete', label: '删除', danger: true }],
        onClick: () => setDeletingRecord({ id: row.id, name: row.name, kind, title }),
      }}
    >
      <Button type="text" icon={<MoreOutlined />} disabled={!!busy} aria-label={`${row.name}的更多操作`} aria-haspopup="menu" />
    </Dropdown>
  }
  function planActions(row, mobile = false) {
    return <>
      <Button loading={busy === row.id} disabled={!!busy} onClick={() => previewPlan(row)}>预览并运行</Button>
      <Button className="mobile-quiet-action" onClick={() => editPlan(row)}>编辑</Button>
      {deleteAction(row, 'presets', mobile)}
    </>
  }
  function scheduleActions(row, mobile = false) {
    return <>
      <Button disabled={!!busy} onClick={() => act(row.id, 'schedules', { ...row, enabled: !row.enabled })}>{row.enabled ? '停用' : '启用'}</Button>
      <Button className="mobile-quiet-action" onClick={() => editSchedule(row)}>编辑</Button>
      {deleteAction(row, 'schedules', mobile)}
    </>
  }
  return <>
    {error && <Alert type="error" title={error} />}
    {view === 'overview' && (!isMobile || data.presets.length > 0) && <Card title="快捷采集" extra={<Button type="link" onClick={() => onNavigate('plans')}>管理方案</Button>}>
      <div className="crawl-quick-plans">{data.presets.map(plan => <div className="crawl-quick-plan" key={plan.id}>
        <Typography.Text strong>{plan.name}</Typography.Text><Typography.Text type="secondary">{plan.steps.map(step => labels[step.kind]).join(' → ')}</Typography.Text>
        <Button loading={busy === plan.id} disabled={!!busy} onClick={() => previewPlan(plan)}>预览并运行</Button>
      </div>)}{!isMobile && <div className="crawl-quick-plan"><Typography.Text strong>自定义采集</Typography.Text><Typography.Text type="secondary">选择板块、任务类型或指定范围</Typography.Text><Button onClick={onCreate}>新建采集</Button></div>}</div>
    </Card>}
    <Card hidden={!['plans', 'settings'].includes(view)}><Tabs activeKey={view === 'settings' ? 'settings' : controlTab} onChange={setControlTab} items={[
      { key: 'plans', label: '常用方案', children: <>
        <div className="crawl-section-tools"><Button icon={isMobile ? <PlusOutlined /> : undefined} onClick={() => editPlan()}>新建采集方案</Button><Typography.Text type="secondary">每个方案按步骤顺序排队，后续步骤在开始时读取最新待办数据。</Typography.Text></div>
        <ResponsiveRecords rowKey="id" dataSource={data.presets} pagination={false} scroll={{ x: 600 }} renderMobileActions={(row) => planActions(row, true)} columns={[
          { title: '名称', dataIndex: 'name' }, { title: '步骤', dataIndex: 'steps', render: (steps) => steps.map((step) => labels[step.kind]).join(' → ') },
          { key: 'actions', title: '操作', render: (_, row) => <Space wrap>{planActions(row)}</Space> },
        ]} />
      </> },
      { key: 'schedules', label: '定时计划', children: <>
        <Alert type="info" showIcon title="按北京时间执行，后端服务需保持运行。服务离线期间错过的计划，重启后最多补执行一次。" />
        <Button type={isMobile ? 'primary' : 'default'} style={{ margin: '16px 0' }} onClick={() => editSchedule()}>新建定时计划</Button>
        <ResponsiveRecords rowKey="id" dataSource={data.schedules} pagination={false} scroll={{ x: 900 }} renderMobileActions={(row) => scheduleActions(row, true)} columns={[
          { title: '计划', dataIndex: 'name' }, { title: '状态', render: (_, row) => <Tag className={row.enabled ? 'crawl-status-success' : undefined} color={row.enabled ? 'green' : 'default'}>{row.enabled ? '已启用' : '已停用'}</Tag> },
          { title: '时间', render: (_, row) => row.mode === 'daily' ? `每天 ${row.daily_time}` : `每 ${row.every_minutes} 分钟` },
          { title: '下次执行', render: (_, row) => row.enabled ? date(row.next_run) : '—' },
          { title: '最近触发', dataIndex: 'last_result', render: (value) => value || '尚未触发' },
          { key: 'actions', title: '操作', render: (_, row) => <Space wrap>{scheduleActions(row)}</Space> },
        ]} />
      </> },
      { key: 'settings', label: '采集配置与登录检查', children: <>
        <Typography.Paragraph type="secondary">配置仅影响之后提交的管理端任务；已排队任务及命令行配置不变。</Typography.Paragraph>
        <Space wrap style={{ marginBottom: 16 }}><Button loading={busy === 'login'} disabled={!!busy || !data.settings} onClick={() => act('login', 'check-login', {}, setLogin)}>检查 Cookie 与站点访问</Button><Typography.Text type="secondary">仅检查站点连接，不采集或显示 Cookie。</Typography.Text></Space>
        {login && <Alert style={{ marginBottom: 16 }} showIcon type={login.status === 'ok' ? 'success' : 'warning'} title={login.message} />}
        <Form name="admin_settings" form={settingsForm} layout="vertical" onValuesChange={() => setDirty(true)} onFinish={(values) => act('settings', 'settings', values, () => setDirty(false))}>
          <Collapse defaultActiveKey={['collection']} items={[{key: 'collection', label: '采集数量与并发', forceRender: true, children: <div className="crawl-settings-grid">{fields.filter(([section]) => section !== 'network').map(([section, key, label, min, max, precision = 0]) => <Form.Item key={`${section}.${key}`} name={[section, key]} label={label} rules={[{ required: true }]}><InputNumber min={min} max={max} precision={precision} style={{ width: '100%' }} /></Form.Item>)}
          <Form.Item name={['comments', 'pages']} label="每帖评论页数" rules={[{ required: true }]}><Select options={[{ value: 'all', label: '全部页面' }, ...[1, 3, 5, 10, 20, 50, 100].map((value) => ({ value, label: `最多 ${value} 页` }))]} /></Form.Item>
          <Form.Item name={['comments', 'refresh_existing']} label="重新抓取已完成评论" valuePropName="checked"><Switch /></Form.Item></div>}, {key: 'network', label: '网络与重试（高级）', forceRender: true, children: <div className="crawl-settings-grid">{fields.filter(([section]) => section === 'network').map(([section, key, label, min, max, precision = 0]) => <Form.Item key={key} name={[section, key]} label={label} rules={[{required:true}]}><InputNumber min={min} max={max} precision={precision} style={{width:'100%'}} /></Form.Item>)}</div>}]} />
          <div className="crawl-settings-save"><Typography.Text type="secondary">{dirty ? '有尚未保存的修改' : '配置已同步'}</Typography.Text><Button type="primary" htmlType="submit" loading={busy === 'settings'} disabled={!!busy || !data.settings}>保存采集配置</Button></div>
        </Form>
      </> },
    ].filter(item => view === 'settings' ? item.key === 'settings' : item.key !== 'settings')} /></Card>
    <CrawlWorkModal isMobile={isMobile} title="确认运行方案" open={!!runPreview} onCancel={() => setRunPreview(null)} confirmLoading={busy === 'run-plan'} okText="加入采集队列" onOk={() => act('run-plan', 'presets/run', { id: runPreview.plan.id }, async result => { setRunPreview(null); await onQueued(result) })}>
      {runPreview && <><Typography.Paragraph strong>{runPreview.plan.name} · {runPreview.plan.steps.length} 个步骤</Typography.Paragraph><ol className="crawl-plan-preview">{runPreview.previews.map((preview, index) => <li key={index}><strong>{labels[preview.kind]}</strong><p>{preview.kind === 'sync' ? `${preview.fids.map(fid => forums.find(f => f.value === fid)?.label || fid).join('、')} · ${preview.pages ? `${preview.pages} 页` : '自动增量同步'}` : `当前预计 ${preview.target_count} ${preview.kind === 'rankings' ? '份榜单' : '个帖子'}`}</p></li>)}</ol><Typography.Paragraph type="secondary">按步骤顺序执行，后续步骤开始时会重新确定待办范围。关闭页面后继续采集。</Typography.Paragraph>{runPreview.previews.some(preview => !preview.anonymous_allowed && !preview.cookie_available) && <Alert type="warning" showIcon title="Cookie 文件不可用，请先更新主机上的 Cookie。" />}</>}
    </CrawlWorkModal>
    <Modal centered className="crawl-admin-modal crawl-confirm-modal" title={deletingRecord?.title} open={!!deletingRecord} onCancel={() => setDeletingRecord(null)}
      onOk={() => act('delete-record', `${deletingRecord.kind}/delete`, { id: deletingRecord.id }, () => setDeletingRecord(null))}
      confirmLoading={busy === 'delete-record'} okText="删除" okButtonProps={{ danger: true }}
    >
      {deletingRecord?.name}
    </Modal>
    <CrawlWorkModal
      className="crawl-plan-editor"
      isMobile={isMobile}
      title={editingPlan?.id ? '编辑采集方案' : '新建采集方案'}
      open={!!editingPlan}
      onCancel={() => setEditingPlan(null)}
      onOk={() => planForm.submit()}
      confirmLoading={busy === 'plan'}
      okText="保存方案"
      width={640}
    >
      <Form name="admin_plan" form={planForm} layout="vertical" onFinish={(values) => act('plan', 'presets', { ...values, id: editingPlan?.id }, () => setEditingPlan(null))}>
        <Form.Item name="name" label="方案名称" rules={[{ required: true }]}>
          <Input maxLength={60} placeholder="例如：日常同步" />
        </Form.Item>
        <Form.List name="steps">{(steps, { add, remove, move }) => (
          <section className="crawl-plan-sequence" aria-labelledby="crawl-plan-steps-title">
            <div className="crawl-plan-sequence-header">
              <div><h3 id="crawl-plan-steps-title">采集步骤</h3><p>任务按下方顺序执行。</p></div>
              <span>{steps.length} / {maxPlanSteps} 步</span>
            </div>
            <ol className="crawl-plan-steps" role="list">
              {steps.map((step, index) => (
                <li className="crawl-plan-step" key={step.key}>
                  <span className="crawl-plan-step-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                  <div className="crawl-plan-step-fields">
                    <div className="crawl-plan-step-toolbar">
                      <Form.Item name={[step.name, 'kind']} label="任务类型">
                        <Select options={taskTypes} onChange={(kind) => planForm.setFieldValue(['steps', step.name], { kind })} />
                      </Form.Item>
                      {steps.length > 1 && <div className="crawl-plan-step-actions">
                        {index > 0 && <Button type="text" size="small" aria-label={`上移第 ${index + 1} 步`} onClick={() => move(step.name, step.name - 1)}>上移</Button>}
                        <Button type="text" size="small" aria-label={`移除第 ${index + 1} 步`} onClick={() => remove(step.name)}>移除</Button>
                      </div>}
                    </div>
                    <Form.Item noStyle shouldUpdate>{() => {
                      const kind = planForm.getFieldValue(['steps', step.name, 'kind'])
                      return kind === 'sync' ? <>
                        <Form.Item name={[step.name, 'fid']} label="板块">
                          <Select allowClear placeholder="全部已配置板块" options={forums} />
                        </Form.Item>
                        <div className="crawl-plan-page-range">
                          <Form.Item name={[step.name, 'pages']} label="抓取页数"><InputNumber min={1} max={2000} precision={0} inputMode="numeric" placeholder="自动增量" /></Form.Item>
                          <Form.Item name={[step.name, 'start_page']} label="起始页"><InputNumber min={1} max={100000} precision={0} inputMode="numeric" placeholder="默认 1" /></Form.Item>
                        </div>
                      </> : kind === 'rankings' ? null : <>
                        <Form.Item name={[step.name, 'limit']} label="处理上限"><InputNumber min={1} max={100000} precision={0} inputMode="numeric" placeholder="使用采集配置" /></Form.Item>
                        {kind === 'details' && <Form.Item name={[step.name, 'tids']} label="指定帖子 ID（可选）"><Input placeholder="英文逗号分隔" /></Form.Item>}
                      </>
                    }}</Form.Item>
                  </div>
                </li>
              ))}
            </ol>
            <Button className="crawl-plan-add" type="text" icon={<PlusOutlined />} disabled={steps.length >= maxPlanSteps} onClick={() => add({ kind: 'details' })}>添加步骤</Button>
          </section>
        )}</Form.List>
      </Form>
    </CrawlWorkModal>
    <CrawlWorkModal isMobile={isMobile} title={editingSchedule?.id ? '编辑定时计划' : '新建定时计划'} open={!!editingSchedule} onCancel={() => setEditingSchedule(null)} onOk={() => scheduleForm.submit()} confirmLoading={busy === 'schedule'} okText="保存计划">
      <Form className="crawl-work-form" name="admin_schedule" form={scheduleForm} layout="vertical" onFinish={(values) => act('schedule', 'schedules', { ...values, id: editingSchedule?.id }, () => setEditingSchedule(null))}>
        <Form.Item name="name" label="计划名称" rules={[{ required: true }]}><Input maxLength={60} /></Form.Item>
        <Form.Item name="preset_id" label="执行方案" rules={[{ required: true }]}><Select options={data.presets.map((p) => ({ label: p.name, value: p.id }))} /></Form.Item>
        <div className="crawl-work-field-pair">
          <Form.Item name="mode" label="周期"><Select options={[{ value: 'interval', label: '固定间隔' }, { value: 'daily', label: '每天固定时间' }]} /></Form.Item>
          {scheduleMode !== 'daily' ? (
            <Form.Item name="every_minutes" label="间隔（分钟）"><InputNumber min={5} max={43200} precision={0} inputMode="numeric" /></Form.Item>
          ) : (
            <Form.Item name="daily_time" label="时间（北京时间）" rules={[{ pattern: /^(?:[01]\d|2[0-3]):[0-5]\d$/, message: '例如 09:00' }]}><Input placeholder="09:00" /></Form.Item>
          )}
        </div>
        <Form.Item name="busy_policy" label="已有任务时"><Select options={[{ value: 'skip', label: '跳过本次' }, { value: 'queue', label: '加入队列' }]} /></Form.Item>
        <Form.Item className="crawl-work-switch" name="enabled" label="启用计划" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </CrawlWorkModal>
  </>
}
