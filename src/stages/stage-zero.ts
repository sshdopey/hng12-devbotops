import fetch from 'node-fetch';
import { BaseStage } from './base-stage';
import { GoogleSheetService } from '@/services/google-sheets';
import { logger, Config } from '@/config';
import { handlePromotion, checkUrlUniqueness, extractSubmissionData } from '@/utils';
import type { StageResult, SlackModalView, SlackSubmissionBody, SubmissionData } from '@/types';

interface StageZeroResult {
  readonly deployedValid: boolean;
  readonly messagePresent: boolean;
  readonly nginxPresent: boolean;
  readonly blogValid: boolean;
  readonly backlinkPresent: boolean;
  readonly server: string;
  readonly errors: readonly string[];
}

export class StageZero extends BaseStage {
  readonly emoji = ':zero:';
  readonly channels = ['C089GSHEMFT'] as const;
  readonly nextChannels = ['C089GSHEMFT', 'C08AHHWBTK8', 'C08B3UKM0QN'] as const;
  readonly requiredScore = 5;
  readonly expectedText = 'Welcome to DevOps Stage 0';

  readonly backlinks = [
    'https://hng.tech/hire/devops-engineers',
    'https://hng.tech/hire/cloud-engineers',
    'https://hng.tech/hire/site-reliability-engineers',
    'https://hng.tech/hire/platform-engineers',
    'https://hng.tech/hire/infrastructure-engineers',
    'https://hng.tech/hire/kubernetes-specialists',
    'https://hng.tech/hire/aws-solutions-architects',
    'https://hng.tech/hire/azure-devops-engineers',
    'https://hng.tech/hire/google-cloud-engineers',
    'https://hng.tech/hire/ci-cd-pipeline-engineers',
    'https://hng.tech/hire/monitoring-observability-engineers',
    'https://hng.tech/hire/automation-engineers',
    'https://hng.tech/hire/docker-specialists',
    'https://hng.tech/hire/linux-developers',
    'https://hng.tech/hire/postgresql-developers',
  ] as const;

  protected readonly sheet = new GoogleSheetService({
    spreadsheetId: '1t-JU71GkCOlYf7nAWdJWxoJpzNcDiKlqfB4aZDmDiAg',
    columns: {
      A: 'timestamp',
      B: 'username',
      C: 'user_id',
      D: 'trials',
      E: 'deployed_url',
      F: 'blog_url',
      G: 'promoted',
    },
  });

  submissionView(channelId: string): SlackModalView {
    return {
      type: 'modal',
      title: { type: 'plain_text', text: 'DevOps Stage 0' },
      blocks: [
        {
          type: 'input',
          block_id: 'deployed_url',
          label: { type: 'plain_text', text: 'Deployed URL' },
          element: {
            type: 'plain_text_input',
            action_id: 'deployed_url',
            placeholder: {
              type: 'plain_text',
              text: 'Enter the full URL (including http:// or https://)',
            },
          },
        },
        {
          type: 'input',
          block_id: 'blog_url',
          label: { type: 'plain_text', text: 'Blog Post URL' },
          element: {
            type: 'plain_text_input',
            action_id: 'blog_url',
            placeholder: {
              type: 'plain_text',
              text: 'Enter your blog post URL',
            },
          },
        },
      ],
      close: { type: 'plain_text', text: 'Cancel' },
      submit: { type: 'plain_text', text: 'Submit' },
      callback_id: 'submission',
      private_metadata: channelId,
    };
  }

  async submit(
    channelId: string,
    body: SlackSubmissionBody,
    client: unknown // Using unknown for now due to complex Slack client typing
  ): Promise<void> {
    try {
      const submissionData = extractSubmissionData(body);
      const { userId, username } = submissionData;

      // Check if already promoted
      if (await this.checkIfAlreadyPromoted(userId)) {
        await (client as any).chat.postEphemeral({
          channel: channelId,
          user: userId,
          text: '🎉 You have already passed Stage 0! No need to submit again.',
        });
        return;
      }

      // Extract URLs from submission
      const values = body.view.state.values;
      const deployedUrl = values.deployed_url?.deployed_url?.value;
      const blogUrl = values.blog_url?.blog_url?.value;

      if (!deployedUrl || !blogUrl) {
        await (client as any).chat.postEphemeral({
          channel: channelId,
          user: userId,
          text: '❌ Both deployed URL and blog URL are required.',
        });
        return;
      }

      // Validate URL uniqueness
      for (const [url, urlType] of [
        [deployedUrl, 'deployed_url'],
        [blogUrl, 'blog_url'],
      ] as const) {
        const { isUnique, errorMessage } = await checkUrlUniqueness(
          this.sheet,
          url,
          userId,
          urlType
        );

        if (!isUnique) {
          await (client as any).chat.postEphemeral({
            channel: channelId,
            user: userId,
            text: `❌ ${errorMessage}`,
          });
          return;
        }
      }

      // Grade submission
      const result = await this.processSubmission({
        ...submissionData,
        values: { deployedUrl, blogUrl },
      });

      const trials = await this.getTrialCount(userId);
      const promoted = result.passed;

      // Update submission record
      await this.updateSubmissionRecord(
        userId,
        username,
        {
          deployed_url: deployedUrl,
          blog_url: blogUrl,
        },
        promoted,
        trials
      );

      // Generate result message
      const message = this.formatResultMessage(result, userId, trials);

      if (promoted) {
        // Handle promotion
        await handlePromotion(
          client as any,
          userId,
          this.channels,
          this.nextChannels,
          this.emoji,
          Config.slack.userToken
        );

        const newChannels = this.nextChannels
          .filter(ch => !(this.channels as readonly string[]).includes(ch))
          .map(ch => `<#${ch}>`)
          .join(', ');

        await (client as any).chat.postMessage({
          channel: userId,
          text: `${message}\n\n🚀 Access granted to: ${newChannels}`,
        });
      } else {
        await (client as any).chat.postEphemeral({
          channel: channelId,
          user: userId,
          text: message,
        });
      }
    } catch (error) {
      logger.error('Stage 0 submission error:', error);
      await (client as any).chat.postEphemeral({
        channel: channelId,
        user: body.user.id,
        text: '🚨 An error occurred while processing your submission. Please try again or contact support.',
      });
    }
  }

  async processSubmission(data: SubmissionData): Promise<StageResult> {
    return this.gradeSubmission(data);
  }

  protected async gradeSubmission(data: SubmissionData): Promise<StageResult> {
    const { deployedUrl, blogUrl } = data.values as { deployedUrl: string; blogUrl: string };

    let score = 0;
    let details: StageZeroResult = {
      deployedValid: false,
      messagePresent: false,
      nginxPresent: false,
      blogValid: false,
      backlinkPresent: false,
      server: 'Unknown',
      errors: [],
    };

    const errors: string[] = [];

    // Check deployed URL
    const deployedResult = await this.fetchUrlContent(deployedUrl);
    if (deployedResult.success) {
      details = { ...details, deployedValid: true };
      score += 1;

      if (deployedResult.content.includes(this.expectedText)) {
        details = { ...details, messagePresent: true };
        score += 1;
      }

      const server = deployedResult.response?.headers?.get('server') ?? 'Unknown';
      details = { ...details, server };

      if (server.toLowerCase().includes('nginx')) {
        details = { ...details, nginxPresent: true };
        score += 1;
      }
    } else {
      errors.push(`Deployed URL: ${deployedResult.error}`);
    }

    // Check blog URL
    const blogResult = await this.fetchUrlContent(blogUrl);
    if (blogResult.success) {
      details = { ...details, blogValid: true };
      score += 1;

      if (this.checkBacklinks(blogResult.content)) {
        details = { ...details, backlinkPresent: true };
        score += 1;
      }
    } else {
      errors.push(`Blog URL: ${blogResult.error}`);
    }

    return {
      score,
      passed: score >= this.requiredScore,
      details: { ...details, errors },
      errors,
    };
  }

  private async fetchUrlContent(
    url: string,
    timeout: number = 15000
  ): Promise<{
    success: boolean;
    content: string;
    error?: string;
    response?: import('node-fetch').Response;
  }> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeout);

      const response = await fetch(url, {
        signal: controller.signal,
        redirect: 'follow',
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        return {
          success: false,
          content: '',
          error: `HTTP ${response.status}: ${response.statusText}`,
        };
      }

      const content = await response.text();
      return {
        success: true,
        content,
        response,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        content: '',
        error: `Error accessing URL: ${errorMessage}`,
      };
    }
  }

  private checkBacklinks(content: string): boolean {
    return this.backlinks.some(backlink => content.includes(backlink));
  }

  protected formatResultMessage(result: StageResult, userId: string, trials: number): string {
    const details = result.details as unknown as StageZeroResult;
    const lines = [
      `<@${userId}> Stage 0 Results (Attempt #${trials}):\n`,
      '📋 Requirements Check:',
      `${details.deployedValid ? '✅' : '❌'} Deployed URL is accessible`,
      `${details.messagePresent ? '✅' : '❌'} Welcome message present`,
      `${details.nginxPresent ? '✅' : '❌'} NGINX server detected`,
      `${details.blogValid ? '✅' : '❌'} Blog post is accessible`,
      `${details.backlinkPresent ? '✅' : '❌'} Backlinks present`,
      `Server: ${details.server}`,
      `Score: ${result.score}/${this.requiredScore}\n`,
    ];

    if (details.errors.length > 0) {
      lines.push('⚠️ Errors encountered:');
      lines.push(...details.errors.map(error => `• ${error}`));
      lines.push('');
    }

    if (!result.passed) {
      lines.push('📝 Required improvements:');
      if (!details.deployedValid) {
        lines.push('• Ensure your deployed URL is accessible');
      }
      if (!details.messagePresent) {
        lines.push(`• Add '${this.expectedText}' to your page`);
      }
      if (!details.nginxPresent) {
        lines.push('• Configure NGINX as your web server');
      }
      if (!details.blogValid) {
        lines.push('• Ensure your blog post URL is accessible');
      }
      if (!details.backlinkPresent) {
        lines.push('• Include at least one of the provided backlinks in your blog post');
      }
      lines.push("\n💡 Resubmit when you've made these improvements!");
    } else {
      lines.push(
        `🎉 Congratulations! You've completed Stage 0 in ${trials} ${
          trials === 1 ? 'attempt' : 'attempts'
        }!`
      );
    }

    return lines.join('\n');
  }
}
