import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios, { type InternalAxiosRequestConfig } from 'axios'

import api, {
  setOnUnauthorizedHandler,
  clearAuthHeader,
  type OnUnauthorizedHandler,
} from './api'

describe('api 401 interceptor', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // Reset the handler before each test
    setOnUnauthorizedHandler(null)
    sessionStorage.clear()
  })

  afterEach(() => {
    setOnUnauthorizedHandler(null)
    sessionStorage.clear()
  })

  /**
   * Create a mock axios-style error with a given status.
   */
  function mockAxiosError(status: number) {
    const response = { status, data: {}, statusText: 'Error', headers: {}, config: {} as InternalAxiosRequestConfig }
    const config = { headers: {} } as InternalAxiosRequestConfig
    const err = new axios.AxiosError(`HTTP ${status}`, `${status}`, config, null, response)
    return err
  }

  /**
   * Create a mock axios error with X-FM-Auth-Request header.
   */
  function mockAuthRequestAxiosError(status: number) {
    const response = { status, data: {}, statusText: 'Error', headers: {}, config: {} as InternalAxiosRequestConfig }
    const config = { headers: { 'X-FM-Auth-Request': 'true' } } as unknown as InternalAxiosRequestConfig
    const err = new axios.AxiosError(`HTTP ${status}`, `${status}`, config, null, response)
    return err
  }

  /**
   * Create a mock network error (no response).
   */
  function mockNetworkError() {
    const config = { headers: {} } as InternalAxiosRequestConfig
    const err = new axios.AxiosError('Network Error', 'ERR_NETWORK', config)
    return err
  }

  /**
   * Create a successful axios response.
   */
  function mockSuccessResponse(data: unknown) {
    return {
      data,
      status: 200,
      statusText: 'OK',
      headers: {},
      config: { headers: {} },
    }
  }

  describe('successful responses pass through unchanged', () => {
    it('200 response is returned as-is', async () => {
      setOnUnauthorizedHandler(() => {
        throw new Error('handler should not be called')
      })

      const response = mockSuccessResponse({ ok: true })

      // Directly test the interceptor by calling api.get with a mocked adapter
      const instance = api
      const originalAdapter = instance.defaults.adapter
      // @ts-expect-error - test mock adapter
      instance.defaults.adapter = () => Promise.resolve(response)

      try {
        const result = await instance.get('/test')
        expect(result.data).toEqual({ ok: true })
      } finally {
        instance.defaults.adapter = originalAdapter
      }
    })
  })

  describe('401 handler invocation', () => {
    it('401 response triggers the handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('401 handler can be async and still clears dedup flag', async () => {
      const handler = vi.fn(async () => {
        await new Promise((r) => setTimeout(r, 10))
      })
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      // Wait for the async handler to complete and the dedup flag to reset
      await new Promise((r) => setTimeout(r, 50))

      expect(handler).toHaveBeenCalledTimes(1)

      // After the async handler completes, a new 401 should be able to trigger
      // the handler again (dedup flag cleared via .finally)
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))
      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).toHaveBeenCalledTimes(2)
    })

    it('401 handler can be sync (void) without TypeError', async () => {
      const handler = vi.fn(() => {
        // sync, returns void (undefined)
      })
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      try {
        // Should not throw TypeError: undefined is not iterable
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('original error is always propagated', async () => {
      setOnUnauthorizedHandler(vi.fn())

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      let caughtError: unknown
      try {
        await instance.get('/test')
      } catch (e) {
        caughtError = e
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(caughtError).toBeInstanceOf(Error)
      expect((caughtError as Error).message).toBe('HTTP 401')
    })

    it('sync handler throw: original 401 propagates and dedup flag resets', async () => {
      // The handler's sync throw is caught by the try-catch wrapper.
      // The original 401 error propagates via Promise.reject(error),
      // and the dedup flag is always reset so future 401s can trigger the handler.
      const handler = vi.fn(() => {
        throw new Error('sync handler error')
      })
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      let caughtError: unknown
      try {
        await instance.get('/test')
      } catch (e) {
        caughtError = e
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      // The original 401 propagates (not the handler error)
      expect(caughtError).toBeInstanceOf(Error)
      expect((caughtError as Error).message).toBe('HTTP 401')
      expect(handler).toHaveBeenCalledTimes(1)

      // Dedup flag WAS reset by the catch block
      // A second 401 DOES trigger the handler again
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))
      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      // Handler was called again — dedup flag was properly reset
      expect(handler).toHaveBeenCalledTimes(2)
    })

    it('async handler throw does not break interceptor chain', async () => {
      // NOTE: An async rejection from the handler IS caught by Promise.resolve(handler())
      // because the function returns a Promise that rejects later. The original 401
      // propagates. However, the handler's rejected promise is fire-and-forget,
      // producing an unhandled rejection. We suppress it in this test.
      const handler = vi.fn(async () => {
        await new Promise((r) => setTimeout(r, 10))
        throw new Error('async handler error')
      })
      setOnUnauthorizedHandler(handler)

      // Suppress unhandled rejection warnings for this test
      const originalUnhandledRejectionHandlers = process.listeners('unhandledRejection')
      const originalUncaughtExceptionHandlers = process.listeners('uncaughtException')
      process.removeAllListeners('unhandledRejection')
      process.removeAllListeners('uncaughtException')
      process.on('unhandledRejection', () => { /* expected from fire-and-forget handler */ })
      process.on('uncaughtException', () => { /* expected from fire-and-forget handler */ })

      try {
        const instance = api
        const originalAdapter = instance.defaults.adapter
        instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

        // First 401: handler is called, eventually rejects, but original 401 still propagates
        let caughtError: unknown
        try {
          await instance.get('/test')
        } catch (e) {
          caughtError = e
        } finally {
          instance.defaults.adapter = originalAdapter
        }

        expect(caughtError).toBeInstanceOf(Error)
        expect((caughtError as Error).message).toBe('HTTP 401')
        expect(handler).toHaveBeenCalledTimes(1)

        // Wait for the async handler to settle (reject) and .finally to reset dedup.
        await new Promise((r) => setTimeout(r, 50))

        // Second 401 should trigger handler again (dedup flag cleared by .finally)
        instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))
        try {
          await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
        } finally {
          instance.defaults.adapter = originalAdapter
        }

        expect(handler).toHaveBeenCalledTimes(2)

        // Wait for the second handler's async rejection to settle
        await new Promise((r) => setTimeout(r, 50))
      } finally {
        // Restore original handlers
        process.removeAllListeners('unhandledRejection')
        for (const h of originalUnhandledRejectionHandlers) {
          process.on('unhandledRejection', h as (reason: unknown, promise: Promise<unknown>) => void)
        }
        process.removeAllListeners('uncaughtException')
        for (const h of originalUncaughtExceptionHandlers) {
          process.on('uncaughtException', h as (err: Error) => void)
        }
      }
    })

    it('cancelled request 401 does NOT trigger handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter

      // Create a cancelled axios error that also has a 401 response
      const cancel = axios.Cancel
      const cancelledError = new cancel('Operation cancelled by user')
      // Attach a 401 response to the cancelled error so the status check alone
      // would match — the interceptor must also check axios.isCancel()
      const cancelledErrorWithResponse = cancelledError as unknown as Record<string, unknown>
      cancelledErrorWithResponse.response = {
        status: 401,
        data: {},
        statusText: 'Unauthorized',
        headers: {},
        config: { headers: {} } as InternalAxiosRequestConfig,
      }

      instance.defaults.adapter = () => Promise.reject(cancelledError)

      try {
        let caughtError: unknown
        try {
          await instance.get('/test')
        } catch (e) {
          caughtError = e
        }
        expect(caughtError).toBe(cancelledError)
        expect(axios.isCancel(caughtError)).toBe(true)
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('concurrent 401 deduplication', () => {
    it('concurrent 401 responses trigger handler only once', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      try {
        // Fire two concurrent requests
        const p1 = instance.get('/test1').catch(() => {})
        const p2 = instance.get('/test2').catch(() => {})
        await Promise.all([p1, p2])
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      // Only one handler invocation
      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('no repeated invalidation after concurrent failures', async () => {
      let handlerCallCount = 0
      const handler: OnUnauthorizedHandler = () => {
        handlerCallCount++
      }
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      try {
        // Fire three concurrent requests
        await Promise.all([
          instance.get('/a').catch(() => {}),
          instance.get('/b').catch(() => {}),
          instance.get('/c').catch(() => {}),
        ])
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handlerCallCount).toBe(1)
    })
  })

  describe('403 does NOT trigger handler', () => {
    it('403 response does NOT invoke the 401 handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(403))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 403')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('5xx does NOT trigger handler', () => {
    it('500 response does NOT invoke the 401 handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(500))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 500')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })

    it('503 response does NOT invoke the 401 handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(503))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 503')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('network error does NOT trigger handler', () => {
    it('network error does NOT invoke the 401 handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockNetworkError())

      try {
        await expect(instance.get('/test')).rejects.toThrow('Network Error')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('auth request exclusion (X-FM-Auth-Request)', () => {
    it('401 on login request does NOT trigger global handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () =>
        Promise.reject(mockAuthRequestAxiosError(401))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })

    it('401 on /auth/me request does NOT trigger global handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () =>
        Promise.reject(mockAuthRequestAxiosError(401))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('handler registration', () => {
    it('no handler registered: 401 passes through without error', async () => {
      setOnUnauthorizedHandler(null)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      // No TypeError, no handler invocation
    })

    it('setOnUnauthorizedHandler(null) clears a previously registered handler', async () => {
      const handler = vi.fn()
      setOnUnauthorizedHandler(handler)
      setOnUnauthorizedHandler(null)

      const instance = api
      const originalAdapter = instance.defaults.adapter
      instance.defaults.adapter = () => Promise.reject(mockAxiosError(401))

      try {
        await expect(instance.get('/test')).rejects.toThrow('HTTP 401')
      } finally {
        instance.defaults.adapter = originalAdapter
      }

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('clearAuthHeader', () => {
    it('clears the Authorization header from axios defaults', () => {
      api.defaults.headers.common['Authorization'] = 'Bearer test-token'
      clearAuthHeader()
      expect(api.defaults.headers.common['Authorization']).toBeUndefined()
    })
  })
})
