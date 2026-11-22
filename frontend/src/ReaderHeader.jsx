import { useControls } from './useControls.js'
import { ArrowLeftOutlined } from '@ant-design/icons'
import ThemeToggle from './ThemeToggle.jsx'

export default function ReaderHeader({ title, icon, onBack, backLabel = '返回帖子', actions, headingRef }) {
  const { Button } = useControls()
  return <header className="thread-hero reader-masthead">
    <div className="thread-hero-copy">
      <div className="thread-hero-title">
        {icon}
        <h1 className="ant-typography" tabIndex={-1} ref={headingRef}>{title}</h1>
        <ThemeToggle />
      </div>
    </div>
    <div className="thread-hero-actions">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>{backLabel}</Button>
      {actions}
    </div>
  </header>
}
