import type {
  StageConfig,
  StageResult,
  SlackModalView,
  SlackSubmissionBody,
  SubmissionData,
} from '@/types';
import { GoogleSheetService } from '@/services/google-sheets';

export abstract class BaseStage implements StageConfig {
  abstract readonly emoji: string;
  abstract readonly channels: readonly string[];
  abstract readonly nextChannels: readonly string[];
  abstract readonly requiredScore: number;

  protected abstract readonly sheet: GoogleSheetService;

  /**
   * Generate the Slack modal view for submission
   */
  abstract submissionView(channelId: string): SlackModalView;

  /**
   * Process a submission and return the result
   */
  abstract processSubmission(data: SubmissionData): Promise<StageResult>;

  /**
   * Handle the complete submission flow including grading and promotion
   */
  abstract submit(channelId: string, body: SlackSubmissionBody, client: unknown): Promise<void>;

  /**
   * Grade a submission and return score with details
   */
  protected abstract gradeSubmission(data: SubmissionData): Promise<StageResult>;

  /**
   * Format the result message for display
   */
  protected abstract formatResultMessage(
    result: StageResult,
    userId: string,
    trials: number
  ): string;

  /**
   * Check if user has already been promoted
   */
  protected async checkIfAlreadyPromoted(userId: string): Promise<boolean> {
    try {
      const submission = await this.sheet.getRow('user_id', userId);
      return submission?.data.promoted === '1';
    } catch {
      return false;
    }
  }

  /**
   * Get or increment user trial count
   */
  protected async getTrialCount(userId: string): Promise<number> {
    try {
      const submission = await this.sheet.getRow('user_id', userId);
      if (submission) {
        const currentTrials = parseInt(submission.data.trials ?? '0', 10);
        return isNaN(currentTrials) ? 1 : currentTrials + 1;
      }
      return 1;
    } catch {
      return 1;
    }
  }

  /**
   * Update or create submission record
   */
  protected async updateSubmissionRecord(
    userId: string,
    username: string,
    data: Record<string, string>,
    promoted: boolean,
    trials: number
  ): Promise<void> {
    const submissionData = {
      timestamp: new Date().toLocaleString('en-US', {
        timeZone: 'Africa/Lagos',
        month: '2-digit',
        day: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }),
      username,
      user_id: userId,
      promoted: promoted ? '1' : '0',
      trials: trials.toString(),
      ...data,
    };

    const existingSubmission = await this.sheet.getRow('user_id', userId);

    if (existingSubmission) {
      await this.sheet.updateRow(existingSubmission.rowNumber, submissionData);
    } else {
      await this.sheet.appendRow(submissionData);
    }
  }
}
