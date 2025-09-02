import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cleanUrl, formatTimestamp } from '../utils';

// Mock the config module to avoid environment validation during tests
vi.mock('../config', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
  Config: {
    timezone: 'Africa/Lagos',
  },
}));

describe('Utils', () => {
  describe('cleanUrl', () => {
    it('should clean and validate HTTP URLs', () => {
      expect(cleanUrl('http://example.com')).toBe('http://example.com');
      expect(cleanUrl('https://example.com/path/')).toBe('https://example.com/path');
      expect(cleanUrl('https://example.com/path?query=1')).toBe('https://example.com/path');
    });

    it('should return empty string for invalid URLs', () => {
      expect(cleanUrl('not-a-url')).toBe('');
      expect(cleanUrl('ftp://example.com')).toBe('');
      expect(cleanUrl('')).toBe('');
    });
  });

  describe('formatTimestamp', () => {
    it('should format timestamp correctly', () => {
      const date = new Date('2024-01-01T12:00:00Z');
      const formatted = formatTimestamp(date);
      expect(formatted).toMatch(/\d{2}\/\d{2}\/\d{4},? \d{2}:\d{2}:\d{2}/);
    });
  });
});