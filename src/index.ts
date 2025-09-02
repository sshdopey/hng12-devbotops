import { App } from '@slack/bolt';
import { logger, Config } from '@/config';
import { getStage } from '@/utils';
import { AwsService } from '@/services/aws';
import { GoogleSheetService } from '@/services/google-sheets';
import { StageZero } from '@/stages/stage-zero';
import type { SlackSubmissionBody } from '@/types';

// Stage registry
const stages = {
  0: StageZero,
  // Additional stages will be added here
};

// Initialize Slack app
const app = new App({
  token: Config.slack.botToken,
  signingSecret: Config.slack.signingSecret,
  appToken: Config.slack.appToken,
  socketMode: true,
});

/**
 * Handle message events
 */
app.event('message', async ({ event, client }) => {
  try {
    // Check if bot is mentioned
    const authTest = await client.auth.test();
    const botUserId = authTest.user_id;

    if (botUserId && 'text' in event && event.text?.includes(botUserId)) {
      await client.chat.postMessage({
        channel: event.channel,
        thread_ts: event.ts,
        text: 'Please use */submit* to submit your task.',
      });
    }
  } catch (error) {
    logger.error('Error handling message event:', error);
  }
});

/**
 * Handle /submit command
 */
app.command('/submit', async ({ ack, body, client }) => {
  try {
    await ack();

    // Check maintenance mode
    if (Config.app.maintenanceMode) {
      await client.views.open({
        trigger_id: body.trigger_id,
        view: {
          type: 'modal',
          title: { type: 'plain_text', text: 'Under Maintenance' },
          blocks: [
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: '🛠 The bot is currently under maintenance. Please wait, we\'ll notify you when submissions resume. The bot needs some rest! 😴',
              },
            },
          ],
          close: { type: 'plain_text', text: 'Close' },
        },
      });
      return;
    }

    const channelId = body.channel_id;
    const triggerId = body.trigger_id;
    
    // Find appropriate stage for channel
    const stage = getStage(stages, channelId);
    
    if (!stage) {
      await client.views.open({
        trigger_id: triggerId,
        view: {
          type: 'modal',
          title: { type: 'plain_text', text: 'Channel Error' },
          blocks: [
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `The */submit* command cannot be used in <#${channelId}> 🙈.\nPlease head to the right devops stage channel to submit!`,
              },
            },
          ],
          close: { type: 'plain_text', text: 'Close' },
        },
      });
      return;
    }

    // Open submission modal
    await client.views.open({
      trigger_id: triggerId,
      view: stage.submissionView(channelId) as any,
    });
  } catch (error) {
    logger.error('Error handling submit command:', error);
    
    try {
      await client.chat.postEphemeral({
        channel: body.channel_id,
        user: body.user_id,
        text: '🔧 Oops! Something went wrong. Please try again.',
      });
    } catch (responseError) {
      logger.error('Error sending error response:', responseError);
    }
  }
});

/**
 * Handle /request-server command
 */
app.command('/request-server', async ({ ack, body, client }) => {
  try {
    await ack();

    // Server provisioning sheet
    const serverSheet = new GoogleSheetService({
      spreadsheetId: '1b9zb83mMZXoJn3B191oQru3_ZHq2COxqmbYtbH0xhuo',
      columns: {
        A: 'timestamp',
        B: 'display_name',
        C: 'user_id',
        D: 'instance_id',
        E: 'key_id',
        F: 'ip_address',
        G: 'status',
      },
    });

    // Check maintenance mode
    const maintenanceMode = true; // Set this as config or remove for production
    if (maintenanceMode) {
      await client.views.open({
        trigger_id: body.trigger_id,
        view: {
          type: 'modal',
          title: { type: 'plain_text', text: 'Backend Stage 2' },
          blocks: [
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: '🛠 The bot is currently under maintenance. Please try again later 😠.',
              },
            },
          ],
          close: { type: 'plain_text', text: 'Close' },
        },
      });
      return;
    }

    // Check for existing request
    const existingRequest = await serverSheet.getRow('user_id', body.user_id);
    
    if (existingRequest) {
      const status = existingRequest.data.status;
      
      if (status === 'provisioning') {
        await client.chat.postEphemeral({
          channel: body.channel_id,
          user: body.user_id,
          text: '⚠️ You already have a server being provisioned. Please wait for it to complete.',
        });
        return;
      }
      
      await client.chat.postEphemeral({
        channel: body.channel_id,
        user: body.user_id,
        text: '⚠️ You have already been provided a server. Multiple server requests are not allowed.',
      });
      return;
    }

    // Create provisioning record
    await serverSheet.appendRow({
      timestamp: new Date().toLocaleString('en-US', {
        timeZone: Config.timezone,
        month: '2-digit',
        day: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }),
      display_name: body.user_name,
      user_id: body.user_id,
      status: 'provisioning',
    });

    await client.chat.postEphemeral({
      channel: body.channel_id,
      user: body.user_id,
      text: '🔄 Your server is being provisioned. This may take a few minutes...',
    });

    // Provision server asynchronously
    setImmediate(async () => {
      try {
        logger.info('Starting server provisioning process...');
        
        const awsService = new AwsService();
        const instanceData = await awsService.setupInstance();
        
        logger.info(`AWS instance created successfully: ${instanceData.instanceId}`);

        // Update sheet with instance data
        const userRecord = await serverSheet.getRow('user_id', body.user_id);
        if (userRecord) {
          await serverSheet.updateRow(userRecord.rowNumber, {
            instance_id: instanceData.instanceId,
            key_id: instanceData.keyId,
            ip_address: instanceData.ipAddress,
            status: 'ready',
          });
        }

        await client.chat.postMessage({
          channel: body.user_id,
          text: [
            '✅ Server has been provisioned successfully!',
            `IP Address: ${instanceData.ipAddress}`,
            `Username: ${instanceData.username}`,
            `Your SSH private key can be downloaded from: ${instanceData.keyUrl}`,
          ].join('\n'),
        });

        logger.info('Server provisioning completed successfully');
      } catch (error) {
        logger.error('Error in server provisioning:', error);
        
        try {
          await client.chat.postMessage({
            channel: body.user_id,
            text: '❌ Server provisioning failed. Please try again.',
          });
        } catch (messageError) {
          logger.error('Error sending failure message:', messageError);
        }
      }
    });
  } catch (error) {
    logger.error('Error handling server request:', error);
    
    try {
      await client.chat.postEphemeral({
        channel: body.channel_id,
        user: body.user_id,
        text: '🔧 Oops! Something went wrong setting up the server. Please try again.',
      });
    } catch (responseError) {
      logger.error('Error sending error response:', responseError);
    }
  }
});

/**
 * Handle submission modal
 */
app.view('submission', async ({ ack, body, client }) => {
  try {
    await ack();
    
    const channelId = body.view.private_metadata;
    if (!channelId) {
      logger.error('No channel ID in private metadata');
      return;
    }
    
    const stage = getStage(stages, channelId);
    if (!stage) {
      logger.error(`No stage found for channel: ${channelId}`);
      return;
    }

    await stage.submit(channelId, body as unknown as SlackSubmissionBody, client);
  } catch (error) {
    logger.error('Error handling submission:', error);
    
    try {
      const channelId = body.view.private_metadata ?? 'unknown';
      await client.chat.postEphemeral({
        channel: channelId,
        user: body.user.id,
        text: '🔧 Oops! Something went wrong. Please try again.',
      });
    } catch (responseError) {
      logger.error('Error sending error response:', responseError);
    }
  }
});

/**
 * Global error handler
 */
app.error(async (error) => {
  logger.error('Global Slack app error:', error);
});

/**
 * Start the application
 */
async function startApp(): Promise<void> {
  try {
    await app.start();
    logger.info(`🚀 HNG12 DevOps Bot is running on port ${Config.app.port}`);
  } catch (error) {
    logger.error('Failed to start application:', error);
    process.exit(1);
  }
}

/**
 * Graceful shutdown
 */
process.on('SIGINT', async () => {
  logger.info('Received SIGINT, shutting down gracefully...');
  try {
    await app.stop();
    logger.info('Application stopped successfully');
    process.exit(0);
  } catch (error) {
    logger.error('Error during shutdown:', error);
    process.exit(1);
  }
});

process.on('SIGTERM', async () => {
  logger.info('Received SIGTERM, shutting down gracefully...');
  try {
    await app.stop();
    logger.info('Application stopped successfully');
    process.exit(0);
  } catch (error) {
    logger.error('Error during shutdown:', error);
    process.exit(1);
  }
});

// Start the application
if (import.meta.url === `file://${process.argv[1]}`) {
  startApp().catch(error => {
    logger.error('Unhandled error during startup:', error);
    process.exit(1);
  });
}

export { app, startApp };