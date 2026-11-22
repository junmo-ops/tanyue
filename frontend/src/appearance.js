import { createContext } from 'react'

export const ThemeContext = createContext(null)
export const themeStorageKey = 'forum-color-theme'

export function prefersDark() {
  try {
    return localStorage.getItem(themeStorageKey) === 'dark'
  } catch {
    return false
  }
}
