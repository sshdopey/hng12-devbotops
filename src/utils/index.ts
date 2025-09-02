import { URL } from 'node:url';
import { logger } from '@/config';
import type {
  SubmissionData,
  StageConfig,
  SlackSubmissionBody,
  ValidationError,
} from '@/types';

/**
 * Get the stage instance for a given channel
 */
export function getStage(stages: Record<number, new () => StageConfig>, channel: string): StageConfig | null {
  for (const StageClass of Object.values(stages)) {
    const stageInstance = new StageClass();
    if (stageInstance.channels.includes(channel)) {
      return stageInstance;
    }
  }
  return null;
}

/**
 * Clean and validate URL
 */
export function cleanUrl(url: string): string {
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    return '';
  }

  try {
    const parsed = new URL(url);
    if (!parsed.hostname) {
      return '';
    }
    return `${parsed.protocol}//${parsed.hostname}${parsed.pathname.replace(/\/$/, '')}`;
  } catch {
    return '';
  }
}

/**
 * Handle user promotion to next stage
 */
export async function handlePromotion(
  client: {
    conversations: {
      kick: (params: { channel: string; user: string; token?: string }) => Promise<void>;
      invite: (params: { channel: string; users: string }) => Promise<void>;
    };
    users: {
      profile: {
        set: (params: { user: string; profile: { status_emoji: string }; token?: string }) => Promise<void>;
      };
    };
  },
  userId: string,
  currentChannels: readonly string[],
  nextChannels: readonly string[],
  statusEmoji: string,
  token: string
): Promise<void> {
  // Remove user from current channels
  await Promise.allSettled(
    currentChannels.map(async channel => {
      try {
        await client.conversations.kick({
          channel,
          user: userId,
          token,
        });
      } catch (error) {
        logger.error(`Error removing user from channel ${channel}:`, error);
      }
    })
  );

  // Add user to next channels
  await Promise.allSettled(
    nextChannels.map(async channel => {
      try {
        await client.conversations.invite({
          channel,
          users: userId,
        });
      } catch (error) {
        logger.error(`Error adding user to channel ${channel}:`, error);
      }
    })
  );

  // Update user profile
  try {
    await client.users.profile.set({
      user: userId,
      profile: { status_emoji: statusEmoji },
      token,
    });
  } catch (error) {
    logger.error('Error setting user profile:', error);
  }
}

/**
 * Check if URL has been used by another user
 */
export async function checkUrlUniqueness(
  sheet: {
    getRow: (column: string, value: string) => Promise<{ rowNumber: number; data: Record<string, string> } | null>;
  },
  url: string,
  userId: string,
  field: string = 'deployed_url'
): Promise<{ isUnique: boolean; errorMessage: string }> {
  try {
    const submission = await sheet.getRow(field, url);
    
    if (submission && submission.data.user_id !== userId) {
      const fieldName = field === 'deployed_url' ? 'API endpoint' : 'GitHub repository';
      return {
        isUnique: false,
        errorMessage: `This ${fieldName} has already been submitted by another intern.`,
      };
    }
    
    return { isUnique: true, errorMessage: '' };
  } catch (error) {
    logger.error(`Error checking URL uniqueness for field ${field}:`, error);
    return {
      isUnique: false,
      errorMessage: 'Unable to verify URL uniqueness. Please try again.',
    };
  }
}

/**
 * Extract submission data from Slack body
 */
export function extractSubmissionData(body: SlackSubmissionBody): SubmissionData {
  return {
    userId: body.user.id,
    username: body.user.name,
    channelId: body.channel_id,
    timestamp: new Date().toISOString(),
    values: body.view.state.values,
  };
}

/**
 * Validate required fields in submission
 */
export function validateSubmission(
  values: Record<string, Record<string, { readonly value: string }>>,
  requiredFields: readonly string[]
): { isValid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  for (const field of requiredFields) {
    const fieldValue = values[field]?.[field]?.value;
    if (!fieldValue?.trim()) {
      errors.push(`${field.replace('_', ' ')} is required`);
    }
  }
  
  return {
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Format timestamp for sheets
 */
export function formatTimestamp(date: Date = new Date()): string {
  return date.toLocaleString('en-US', {
    timeZone: 'Africa/Lagos',
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/**
 * Sleep for specified milliseconds
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry function with exponential backoff
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  baseDelayMs: number = 1000
): Promise<T> {
  let lastError: Error;
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      
      if (attempt === maxRetries) {
        break;
      }
      
      const delay = baseDelayMs * Math.pow(2, attempt - 1);
      logger.warn(`Attempt ${attempt} failed, retrying in ${delay}ms:`, lastError.message);
      await sleep(delay);
    }
  }
  
  throw lastError!;
}