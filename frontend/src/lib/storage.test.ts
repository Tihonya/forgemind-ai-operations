import { describe, it, expect, beforeEach } from 'vitest'
import {
  getAccessToken,
  setAccessToken,
  removeAccessToken,
  ACCESS_TOKEN_STORAGE_KEY,
} from './storage'

describe('storage', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('storing token writes to sessionStorage only, never localStorage', () => {
    setAccessToken('test-token')

    expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe('test-token')
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
    expect(localStorage.length).toBe(0)
  })

  it('reading token returns null when none stored', () => {
    expect(getAccessToken()).toBeNull()
  })

  it('reading token returns stored value', () => {
    sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'my-token')
    expect(getAccessToken()).toBe('my-token')
  })

  it('removing token clears it from sessionStorage', () => {
    setAccessToken('test-token')
    expect(getAccessToken()).toBe('test-token')

    removeAccessToken()
    expect(getAccessToken()).toBeNull()
    expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
  })

  it('never stores password', () => {
    // No password-related keys should ever exist in storage
    setAccessToken('token-value')

    const allKeys = Object.keys(sessionStorage)
    const passwordKeys = allKeys.filter((k) =>
      k.toLowerCase().includes('password')
    )
    expect(passwordKeys).toHaveLength(0)

    // Password should never be in sessionStorage under any key
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i)
      if (!key) continue
      const value = sessionStorage.getItem(key)
      expect(value?.toLowerCase()).not.toContain('secret-password')
      expect(value?.toLowerCase()).not.toContain('user-pwd')
    }
  })

  it('localStorage remains completely unused', () => {
    setAccessToken('token')
    removeAccessToken()

    expect(localStorage.length).toBe(0)
  })

  it('storage key is a single named constant', () => {
    expect(ACCESS_TOKEN_STORAGE_KEY).toBe('forgemind_access_token')
    expect(typeof ACCESS_TOKEN_STORAGE_KEY).toBe('string')
  })
})
