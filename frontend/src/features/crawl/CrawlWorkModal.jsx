import MobileSheet from '../../MobileSheet.jsx'
import { useControls } from '../../useControls.js'

export default function CrawlWorkModal({ isMobile, width = 520, className = '', ...props }) {
  const { Button, Modal } = useControls()
  if (isMobile) {
    const { open, onCancel, title, children, onOk, confirmLoading, cancelText, okText } = props
    return <MobileSheet open={open} onClose={onCancel} title={title} forceRender={props.forceRender}
      className={`crawl-work-modal ${className}`} footer={<>
        <Button type="text" onClick={onCancel}>{cancelText || '取消'}</Button>
        <Button type="primary" loading={confirmLoading} {...props.okButtonProps} onClick={onOk}>{okText || '确定'}</Button>
      </>}>{children}</MobileSheet>
  }
  return <Modal
    {...props}
    className={`crawl-admin-modal crawl-work-modal ${className}`.trim()}
    wrapClassName="crawl-work-modal-wrap"
    width={width}
    cancelButtonProps={{ type: 'text' }}
  />
}
