import { useEffect, useId, useRef, useState } from 'react'
import Popup from 'antd-mobile/es/components/popup'
import Button from 'antd-mobile/es/components/button'
import { LeftOutline } from 'antd-mobile-icons'

export function Bar({ title, right, back }) {
  return <header className="ty-bar">{back && <button type="button" className="ty-back" onClick={back} aria-label="返回"><LeftOutline /></button>}<h1>{title}</h1>{right}</header>
}
export function Body({ children, className = '', ...props }) {
  return <div {...props} className={'ty-body ' + className}>{children}</div>
}
export function Tabs({ items, value, onChange }) {
  return <nav className="ty-tabs" aria-label="切换视图">{items.map(([id, label]) =>
    <button type="button" key={id} aria-pressed={id === value} onClick={() => onChange(id)}>{label}</button>)}</nav>
}
export function Tools({ children }) { return <div className="ty-tools">{children}</div> }
export function Chip({ children, active, className = '', ...props }) {
  return <button type="button" className={'ty-chip '+className} aria-pressed={active} {...props}><span>{children}</span></button>
}
export function Primary({ children, className = '', ...props }) {
  return <Button color="primary" type="button" {...props} className={'ty-primary '+className}>{children}</Button>
}
export function Section({ title, action }) { return <div className="ty-section"><h2>{title}</h2>{action}</div> }
export function Field({ label, children }) { return <label className="ty-field"><span>{label}</span>{children}</label> }
export function KV({ label, children }) { return <div className="ty-kv"><span>{label}</span><div>{children}</div></div> }
export function Row({ title, meta, end, onClick, className = '' }) {
  const content=<><strong>{title}</strong>{(meta || end) && <span className="ty-meta"><span>{meta}</span><em>{end}</em></span>}</>
  return onClick ? <button type="button" className={'ty-row '+className} onClick={onClick}>{content}</button> : <div className={'ty-row '+className}>{content}</div>
}
export function Notice({ children }) { return <p role="status" className="ty-notice">{children}</p> }
export function Sheet({ title, onClose, footer, children }) {
  const titleId = useId()
  const closeRef = useRef(onClose)
  const dialog = useRef(null)
  const [visible,setVisible] = useState(false)
  useEffect(()=>{closeRef.current=onClose},[onClose])
  useEffect(()=>{
    const trigger=document.activeElement
    const frame=requestAnimationFrame(()=>setVisible(true))
    const onKey=e=>{
      if(e.defaultPrevented || document.querySelector('.ty-picker .adm-picker')) return
      const sheets=document.querySelectorAll('.ty-dialog')
      if (sheets[sheets.length-1] !== dialog.current) return
      if(e.key==='Escape'){e.preventDefault();closeRef.current?.()}
      if(e.key==='Tab'){
        const targets=[...dialog.current.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]')].filter(el=>el.offsetWidth)
        if(!targets.length){e.preventDefault();return}
        if(e.shiftKey && (document.activeElement===targets[0] || document.activeElement===dialog.current)){e.preventDefault();targets.at(-1).focus()}
        else if(!e.shiftKey && document.activeElement===targets.at(-1)){e.preventDefault();targets[0].focus()}
      }
    }
    document.addEventListener('keydown',onKey)
    return ()=>{cancelAnimationFrame(frame);document.removeEventListener('keydown',onKey);if(trigger?.isConnected)trigger.focus?.({preventScroll:true})}
  },[])
  return <Popup position="bottom" visible={visible} closeOnMaskClick onClose={onClose} bodyClassName="ty-sheet" maskStyle={{background:"#10253065"}}
    afterShow={()=>dialog.current?.focus({preventScroll:true})}>
    <section ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} className="ty-dialog">
      <div className="ty-handle" aria-hidden="true" /><header><h2 id={titleId}>{title}</h2><button type="button" aria-label="关闭" onClick={onClose}>×</button></header>
      <div className="ty-sheet-body">{children}</div>{footer && <footer>{footer}</footer>}
    </section>
  </Popup>
}
