import { describe, it, expect } from 'vitest';
import { EnvSchema } from '../types';

describe('Configuration', () => {
  describe('EnvSchema', () => {
    it('should validate required environment variables', () => {
      const validEnv = {
        SLACK_BOT_TOKEN: 'xoxb-test',
        SLACK_USER_TOKEN: 'xoxp-test',
        SLACK_APP_TOKEN: 'xapp-test',
        SLACK_SIGNING_SECRET: 'test-secret',
        GITHUB_TOKEN: 'gh-test',
      };

      const result = EnvSchema.safeParse(validEnv);
      expect(result.success).toBe(true);
    });

    it('should fail with missing required variables', () => {
      const invalidEnv = {
        SLACK_BOT_TOKEN: 'xoxb-test',
        // Missing other required fields
      };

      const result = EnvSchema.safeParse(invalidEnv);
      expect(result.success).toBe(false);
    });

    it('should provide default values for optional fields', () => {
      const envWithDefaults = {
        SLACK_BOT_TOKEN: 'xoxb-test',
        SLACK_USER_TOKEN: 'xoxp-test',
        SLACK_APP_TOKEN: 'xapp-test',
        SLACK_SIGNING_SECRET: 'test-secret',
        GITHUB_TOKEN: 'gh-test',
      };

      const result = EnvSchema.safeParse(envWithDefaults);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.MAINTENANCE_MODE).toBe('0');
        expect(result.data.NODE_ENV).toBe('development');
        expect(result.data.PORT).toBe('3000');
      }
    });
  });
});
