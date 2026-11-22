import { Modal } from 'antd'

export default function CrawlWorkModal({ isMobile, width = 520, className = '', ...props }) {
  return <Modal
    {...props}
    className={`crawl-admin-modal crawl-work-modal ${className}`.trim()}
    wrapClassName="crawl-work-modal-wrap"
    transitionName={isMobile ? 'crawl-work-sheet' : undefined}
    width={isMobile ? '100%' : width}
    cancelButtonProps={{ type: 'text' }}
  />
}
