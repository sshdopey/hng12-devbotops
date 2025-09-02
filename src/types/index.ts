import { z } from 'zod';

// Environment configuration schema
export const EnvSchema = z.object({
  SLACK_BOT_TOKEN: z.string().min(1, 'SLACK_BOT_TOKEN is required'),
  SLACK_USER_TOKEN: z.string().min(1, 'SLACK_USER_TOKEN is required'),
  SLACK_APP_TOKEN: z.string().min(1, 'SLACK_APP_TOKEN is required'),
  SLACK_SIGNING_SECRET: z.string().min(1, 'SLACK_SIGNING_SECRET is required'),
  GITHUB_TOKEN: z.string().min(1, 'GITHUB_TOKEN is required'),
  MAINTENANCE_MODE: z.string().optional().default('0'),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  PORT: z.string().optional().default('3000'),
});

export type EnvConfig = z.infer<typeof EnvSchema>;

// Stage interfaces
export interface StageConfig {
  readonly emoji: string;
  readonly channels: readonly string[];
  readonly nextChannels: readonly string[];
  readonly requiredScore: number;
  submissionView(channelId: string): SlackModalView;
  submit(channelId: string, body: SlackSubmissionBody, client: unknown): Promise<void>;
}

export interface StageResult {
  readonly score: number;
  readonly passed: boolean;
  readonly details: Record<string, unknown>;
  readonly errors: readonly string[];
}

export interface SubmissionData {
  readonly userId: string;
  readonly username: string;
  readonly channelId: string | undefined;
  readonly timestamp: string;
  readonly values: Record<string, unknown>;
}

// Google Sheets interfaces
export interface SheetColumn {
  readonly letter: string;
  readonly name: string;
}

export interface SheetRow {
  readonly rowNumber: number;
  readonly data: Record<string, string>;
}

export interface SheetConfig {
  readonly spreadsheetId: string;
  readonly columns: Record<string, string>;
}

// AWS interfaces
export interface AwsInstanceConfig {
  readonly instanceType: string;
  readonly securityGroupId: string;
  readonly region: string;
}

export interface AwsInstanceResult {
  readonly instanceId: string;
  readonly keyId: string;
  readonly username: string;
  readonly ipAddress: string;
  readonly keyUrl: string;
}

// Slack interfaces
export interface SlackModalView {
  readonly type: 'modal';
  readonly title: { readonly type: 'plain_text'; readonly text: string };
  readonly blocks: unknown[];
  readonly close: { readonly type: 'plain_text'; readonly text: string };
  readonly submit?: { readonly type: 'plain_text'; readonly text: string };
  readonly callback_id?: string;
  readonly private_metadata?: string;
}

export interface SlackSubmissionBody {
  readonly user: {
    readonly id: string;
    readonly name: string;
  };
  readonly view: {
    readonly state: {
      readonly values: Record<string, Record<string, { readonly value: string }>>;
    };
    readonly private_metadata?: string;
  };
  readonly channel_id?: string;
  readonly user_id: string;
  readonly user_name?: string;
  readonly trigger_id?: string;
}

// Error types
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly statusCode: number = 500
  ) {
    super(message);
    this.name = 'AppError';
  }
}

export class ValidationError extends AppError {
  constructor(message: string) {
    super(message, 'VALIDATION_ERROR', 400);
    this.name = 'ValidationError';
  }
}

export class ExternalServiceError extends AppError {
  constructor(message: string, service: string) {
    super(message, `${service.toUpperCase()}_ERROR`, 502);
    this.name = 'ExternalServiceError';
  }
}
