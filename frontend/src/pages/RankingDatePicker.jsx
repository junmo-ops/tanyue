import MobileSheet from '../MobileSheet.jsx'
import MobileCalendar from 'antd-mobile/es/components/calendar'
import { useState } from 'react'
import { Calendar, Popover } from 'antd'
import { useControls } from '../useControls.js'
import { CalendarOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

const dateFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
})
function dateKey(timestamp) {
  const parts = Object.fromEntries(dateFormat.formatToParts(new Date(timestamp)).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

export default function RankingDatePicker({ snapshots, snapshot, isMobile, onChange }) {
  const { Button } = useControls()
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState(() => dayjs().locale('zh-cn'))
  const dates = new Map()
  snapshots.forEach(item => {
    const key = dateKey(item.captured_at)
    if (!dates.has(key)) dates.set(key, String(item.id))
  })
  const selected = snapshots.find(item => String(item.id) === snapshot) || (!snapshot ? snapshots[0] : null)
  const selectedDay = selected ? dateKey(selected.captured_at) : null
  const choose = value => { setOpen(false); onChange(value) }
  const changeOpen = next => {
    if (next) setMonth((selectedDay ? dayjs(selectedDay) : dayjs()).locale('zh-cn'))
    setOpen(next)
  }
  const content = <div className="rankings-calendar">
    <Button type="text" onClick={() => choose('')}>最新榜单</Button>
    <Calendar fullscreen={false} value={month}
      fullCellRender={date => <span className={`rankings-calendar-day${date.format('YYYY-MM-DD') === selectedDay ? ' is-selected' : ''}`}>{date.date()}</span>}
      disabledDate={date => !dates.has(date.format('YYYY-MM-DD'))}
      headerRender={() => <div className="rankings-calendar-header">
        <Button type="text" aria-label="上个月" icon={<LeftOutlined />} onClick={() => setMonth(month.subtract(1, 'month'))} />
        <strong aria-live="polite">{month.format('YYYY年M月')}</strong>
        <Button type="text" aria-label="下个月" icon={<RightOutlined />} onClick={() => setMonth(month.add(1, 'month'))} />
      </div>}
      onSelect={(date, info) => {
        const id = dates.get(date.format('YYYY-MM-DD'))
        if (info.source === 'date' && id) choose(id)
      }}
    />
    <p>仅可选择有榜单的日期 · 北京时间</p>
  </div>
  const trigger = <Button className="rankings-history" icon={<CalendarOutlined />} disabled={!snapshots.length}
    aria-haspopup="dialog" aria-expanded={open} onClick={isMobile ? () => changeOpen(true) : undefined}>
    {snapshot && selectedDay ? dayjs(selectedDay).format('YYYY年M月D日') : '最新榜单'}
  </Button>
  return isMobile ? <>
    {trigger}
    <MobileSheet title="选择榜单日期" open={open} onClose={() => changeOpen(false)}>
      <button type="button" className="reader-sheet-link" onClick={() => choose('')}>最新榜单</button>
      <MobileCalendar selectionMode="single" weekStartsOn="Monday" allowClear={false}
        value={selectedDay ? dayjs(selectedDay).toDate() : null}
        shouldDisableDate={day => !dates.has(dayjs(day).format('YYYY-MM-DD'))}
        onChange={day => {
          const id = dates.get(dayjs(day).format('YYYY-MM-DD'))
          if (id) choose(id)
        }} />
      <p>仅可选择有榜单的日期 · 北京时间</p>
    </MobileSheet>
  </> : <Popover trigger="click" open={open} onOpenChange={changeOpen} content={content} placement="bottomRight">{trigger}</Popover>
}
