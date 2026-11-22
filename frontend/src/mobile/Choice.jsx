import { useEffect, useRef, useState } from 'react'
import Picker from 'antd-mobile/es/components/picker'
import { DownOutline } from 'antd-mobile-icons'
import { KV } from './ui.jsx'

export default function Choice({ label, value, options, onChange, inline = false, compact = false }) {
  const [visible, setVisible] = useState(false)
  const trigger = useRef(null)
  const column = options.map(([value, label]) => ({ value: String(value), label }))
  const selected = column.find(item => item.value === String(value ?? ''))

  useEffect(() => {
    if (!visible) return
    const button = trigger.current
    function handleKeyboard(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        setVisible(false)
      }
      if (event.key !== 'Tab') return
      const picker = document.querySelector('.ty-picker .adm-picker')
      const targets = [...(picker?.querySelectorAll('[tabindex="0"], button:not(:disabled)') ?? [])]
        .filter(element => element.getClientRects().length)
      const edge = event.shiftKey ? targets.at(-1) : targets[0]
      const otherEdge = event.shiftKey ? targets[0] : targets.at(-1)
      if (edge && (event.target === otherEdge || !picker.contains(event.target))) {
        event.preventDefault()
        edge.focus()
      }
    }
    document.addEventListener('keydown', handleKeyboard, true)
    return () => {
      document.removeEventListener('keydown', handleKeyboard, true)
      if (button?.isConnected) button.focus({ preventScroll: true })
    }
  }, [visible])

  function focusPicker() {
    const picker = document.querySelector('.ty-picker .adm-picker')
    if (!picker) return
    picker.setAttribute('role', 'dialog')
    picker.setAttribute('aria-modal', 'true')
    picker.setAttribute('aria-label', label)
    const actions = [...picker.querySelectorAll('[role="button"]')]
    for (const action of actions) {
      action.tabIndex = 0
      action.onkeydown = event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          action.click()
        }
      }
    }
    actions[0]?.focus({ preventScroll: true })
  }

  const control = <button ref={trigger} type="button"
    className={'ty-choice-trigger' + (inline || compact ? ' ty-choice-inline' : '')}
    aria-label={label + (selected ? '，' + selected.label : '')}
    aria-haspopup="dialog" aria-expanded={visible}
    disabled={!column.length} onClick={() => {
      if (document.activeElement instanceof HTMLInputElement) document.activeElement.blur()
      setVisible(true)
    }}>
    <span>{selected?.label ?? '请选择'}</span><DownOutline aria-hidden="true" />
  </button>

  return <>
    {compact ? control : inline ? <KV label={label}>{control}</KV> : <div className="ty-field"><span>{label}</span>{control}</div>}
    {visible && <Picker visible columns={[column]} value={[selected?.value ?? column[0]?.value]}
      title={label} cancelText="取消" confirmText="确定" popupClassName="ty-picker"
      popupStyle={{ '--z-index': '1100' }} mouseWheel
      onConfirm={([next]) => { if (next !== undefined && next !== selected?.value) onChange(next) }}
      afterShow={focusPicker} onClose={() => setVisible(false)}
    />}
  </>
}
