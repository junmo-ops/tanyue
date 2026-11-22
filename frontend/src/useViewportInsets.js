import { useEffect } from 'react'

// Keep sheet controls above the software keyboard without disabling pinch zoom.
export default function useViewportInsets() {
  useEffect(() => {
    const viewport = window.visualViewport
    if (!viewport) return
    const root = document.documentElement.style
    const update = () => {
      if (Math.abs(viewport.scale - 1) > 0.01) return
      root.setProperty('--ui-visible-height', `${viewport.height}px`)
      root.setProperty('--ui-visible-top', `${viewport.offsetTop}px`)
      root.setProperty('--ui-keyboard-inset', `${Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)}px`)
    }
    update()
    viewport.addEventListener('resize', update)
    viewport.addEventListener('scroll', update)
    return () => {
      viewport.removeEventListener('resize', update)
      viewport.removeEventListener('scroll', update)
      for (const key of ['--ui-visible-height', '--ui-visible-top', '--ui-keyboard-inset']) root.removeProperty(key)
    }
  }, [])
}
