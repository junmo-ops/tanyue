import { useId } from 'react'
import Popup from 'antd-mobile/es/components/popup'
import { CloseOutlined } from '@ant-design/icons'
import './MobileSheet.css'

export default function MobileSheet({ open, onClose, title, children, footer, className = '', forceRender }) {
  const titleId = useId()
  return <Popup position="bottom" visible={open} onClose={onClose} closeOnMaskClick
    forceRender={forceRender} destroyOnClose={!forceRender} bodyClassName={`reader-sheet ${className}`}>
    <section role="dialog" aria-modal="true" aria-labelledby={titleId}
      onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) onClose() }}>
      <header><h2 id={titleId}>{title}</h2><button type="button" aria-label="关闭" onClick={onClose}><CloseOutlined /></button></header>
      <div className="reader-sheet-content">{children}</div>
      {footer && <footer>{footer}</footer>}
    </section>
  </Popup>
}
