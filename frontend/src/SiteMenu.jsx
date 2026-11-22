import { useEffect, useState } from 'react'
import { useControls } from './useControls.js'
import { DownOutlined } from '@ant-design/icons'
import { postJson, requestJson } from './api/client.js'
import { siteId, siteUrl } from './api/site.js'

export default function SiteMenu({ first = false }) {
  const { Alert, Button, Checkbox, Dropdown, Form, Input, Modal, Select, Space } = useControls()
  const [sites, setSites] = useState([])
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [cookie, setCookie] = useState('')
  const [name, setName] = useState('')
  const [forums, setForums] = useState({})
  const [selected, setSelected] = useState([])
  const [sample, setSample] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [listError, setListError] = useState('')
  useEffect(() => {
    requestJson('/api/sites').then(data => setSites(data.items)).catch(e => setListError(e.message))
  }, [])
  function resetBoards() {
    setForums({})
    setSelected([])
    setPreview(null)
    setError('')
  }
  async function submit(action) {
    setBusy(action)
    setError('')
    try {
      if (action === 'discover') {
        const data = await postJson('/api/sites/discover', { url, cookie })
        const ids = Object.keys(data.forums)
        setForums(data.forums)
        setSelected([ids[0]])
        setSample(ids[0])
        if (!name.trim()) setName(new URL(url).hostname)
      } else if (action === 'probe') {
        setPreview(await postJson('/api/sites/probe', { url, cookie, fid: sample }))
      } else {
        const data = await postJson('/api/sites', { url, cookie, name, forums: Object.fromEntries(selected.map(fid => [fid, forums[fid]])) })
        window.location.assign(siteUrl(first ? '/admin' : '/', data.id))
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }
  function dismiss() {
    if (busy) return
    setOpen(false)
    setCookie('')
    resetBoards()
  }
  const options = Object.entries(forums).map(([value, label]) => ({ value, label }))
  return <>
    {first ? <Button type="primary" onClick={() => setOpen(true)}>接入第一个论坛</Button> : <Dropdown trigger={['click']} menu={{
      selectedKeys: [siteId],
      items: [...sites.map(site => ({ key: site.id, label: site.name })), { type: 'divider' }, { key: 'add', label: '接入论坛' }],
      onClick: ({ key }) => key === 'add' ? setOpen(true) : window.location.assign(siteUrl('/', key)),
    }}>
      <Button className="site-switch" type="text" size="small" aria-label="选择论坛">
        <span style={{maxWidth:'10em', overflow:'hidden', textOverflow:'ellipsis'}}>{sites.find(site => site.id === siteId)?.name || '选择论坛'}</span>
        <DownOutlined />
      </Button>
    </Dropdown>}
    {listError && <Alert type="error" title={listError} />}
    <Modal open={open} title="接入 Discuz! 论坛" onCancel={dismiss} footer={null}>
      <Form layout="vertical" disabled={Boolean(busy)}>
        <Form.Item label="论坛安装地址"><Input placeholder="https://example.com/bbs/" value={url} onChange={e => { setUrl(e.target.value); resetBoards() }} /></Form.Item>
        <Form.Item label="登录 Cookie（选填）"><Input.Password autoComplete="off" value={cookie} onChange={e => { setCookie(e.target.value); resetBoards() }} /></Form.Item>
        {options.length === 0 ? <Button type="primary" disabled={!url.trim()} loading={busy === 'discover'} onClick={() => submit('discover')}>识别板块</Button> : <>
          <Form.Item label="站点名称"><Input maxLength={80} value={name} onChange={e => setName(e.target.value)} /></Form.Item>
          <Form.Item label="采集板块"><Checkbox.Group options={options} value={selected} onChange={setSelected} /></Form.Item>
          <Form.Item label="取样检查"><Space.Compact style={{width:'100%'}}><Select style={{flex:1}} value={sample} options={options} onChange={id => {setSample(id); setPreview(null)}} /><Button loading={busy === 'probe'} onClick={() => submit('probe')}>预览</Button></Space.Compact></Form.Item>
          {preview && <Form.Item><Alert type="info" title={preview.title} description={`列表识别 ${preview.count} 条 · ${preview.detail ? '可读详情' : '未识别正文'} · 样本首页解析到 ${preview.comments} 条回复 · 今日回复榜${preview.rankings ? '可读' : '未识别'}`} /></Form.Item>}
          <Button type="primary" disabled={!selected.length || !name.trim()} loading={busy === 'save'} onClick={() => submit('save')}>接入并切换</Button>
        </>}
        {error && <Alert style={{marginTop:12}} type="error" title={error} />}
      </Form>
    </Modal>
  </>
}
