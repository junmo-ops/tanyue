import { useContext } from 'react'
import { Button } from 'antd'
import { MoonOutlined, SunOutlined } from '@ant-design/icons'
import { ThemeContext } from './appearance.js'

export default function ThemeToggle() {
  const { dark, toggle } = useContext(ThemeContext)
  return <Button
    className="theme-toggle"
    type="text"
    icon={dark ? <SunOutlined /> : <MoonOutlined />}
    aria-label="深色模式"
    aria-pressed={dark}
    title={dark ? '切换到浅色模式' : '切换到深色模式'}
    onClick={toggle}
  />
}
