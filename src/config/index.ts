import { config } from 'dotenv';
import { createLogger, format, transports } from 'winston';
import { EnvSchema, type EnvConfig } from '@/types';

// Load environment variables
config();

// Validate environment configuration
const envResult = EnvSchema.safeParse(process.env);

if (!envResult.success) {
  const errors = envResult.error.errors.map(err => `${err.path.join('.')}: ${err.message}`);
  throw new Error(`Environment validation failed:\n${errors.join('\n')}`);
}

export const env: EnvConfig = envResult.data;

// Logger configuration
export const logger = createLogger({
  level: env.NODE_ENV === 'production' ? 'info' : 'debug',
  format: format.combine(
    format.timestamp(),
    format.errors({ stack: true }),
    format.json(),
    ...(env.NODE_ENV !== 'production'
      ? [format.colorize(), format.simple()]
      : [])
  ),
  transports: [
    new transports.Console(),
    new transports.File({ 
      filename: 'logs/error.log', 
      level: 'error',
      handleExceptions: true,
      handleRejections: true,
    }),
    new transports.File({ 
      filename: 'logs/combined.log',
      handleExceptions: true,
      handleRejections: true,
    }),
  ],
});

// Application configuration
export const Config = {
  slack: {
    botToken: env.SLACK_BOT_TOKEN,
    userToken: env.SLACK_USER_TOKEN,
    appToken: env.SLACK_APP_TOKEN,
    signingSecret: env.SLACK_SIGNING_SECRET,
  },
  github: {
    token: env.GITHUB_TOKEN,
  },
  app: {
    maintenanceMode: env.MAINTENANCE_MODE === '1',
    port: parseInt(env.PORT, 10),
    nodeEnv: env.NODE_ENV,
  },
  aws: {
    region: 'us-east-2',
    defaultInstanceType: 't3.micro',
    s3Bucket: 'hng12-devbotops',
  },
  timezone: 'Africa/Lagos',
} as const;

export type AppConfig = typeof Config;