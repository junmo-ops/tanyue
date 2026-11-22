import { lazy, Suspense, useSyncExternalStore } from 'react'

const MobileApp = lazy(() => import('./mobile/App.jsx'))
const DesktopApp = lazy(() => import('./StartPage.jsx'))
const narrow = window.matchMedia('(max-width: 767px)')

function subscribe(listener) {
  narrow.addEventListener('change', listener)
  return () => narrow.removeEventListener('change', listener)
}

export default function DeviceApp() {
  const mobile = useSyncExternalStore(subscribe, () => narrow.matches)
  return <Suspense fallback={<p role="status">正在加载…</p>}>
    {mobile ? <MobileApp /> : <DesktopApp />}
  </Suspense>
}
