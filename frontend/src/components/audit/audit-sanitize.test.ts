import { describe, expect, it } from 'vitest'

import { isBindingHashKey, normalizeMetadataKey } from './audit-sanitize'

describe('normalizeMetadataKey', () => {
  it('maps binding_hash, bindingHash, and binding-hash to the same token', () => {
    expect(normalizeMetadataKey('binding_hash')).toBe('bindinghash')
    expect(normalizeMetadataKey('bindingHash')).toBe('bindinghash')
    expect(normalizeMetadataKey('binding-hash')).toBe('bindinghash')
  })

  it('is case-insensitive', () => {
    expect(normalizeMetadataKey('BINDING_HASH')).toBe('bindinghash')
    expect(normalizeMetadataKey('BindingHash')).toBe('bindinghash')
  })
})

describe('isBindingHashKey', () => {
  it('matches every spelling variant', () => {
    expect(isBindingHashKey('binding_hash')).toBe(true)
    expect(isBindingHashKey('bindingHash')).toBe(true)
    expect(isBindingHashKey('binding-hash')).toBe(true)
  })

  it('does not match unrelated or neighbouring keys', () => {
    expect(isBindingHashKey('action_type')).toBe(false)
    expect(isBindingHashKey('binding_version')).toBe(false)
    expect(isBindingHashKey('quantity')).toBe(false)
    expect(isBindingHashKey('approval_request_id')).toBe(false)
    expect(isBindingHashKey('component_code')).toBe(false)
  })
})
