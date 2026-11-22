import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import StartPage from './StartPage.jsx'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

dayjs.locale('zh-cn')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <StartPage />
  </StrictMode>,
)
