#!/usr/bin/env node

/**
 * GitHub Integration Testing Tool - TypeScript Edition
 * Checks if the GitHub App is installed on a specific repository
 */

import { Octokit } from '@octokit/rest';
import { readFileSync } from 'fs';
import { createAppAuth } from '@octokit/auth-app';

interface CliOptions {
  repo: string;
  key: string;
  client: string;
}

function parseCliArgs(): CliOptions {
  const args = process.argv.slice(2);

  if (args.length < 6 || !args.includes('--key') || !args.includes('--client')) {
    console.log(`
Usage: tsx src/tools/github-check.ts <repo> --key <private-key-path> --client <client-id>

Arguments:
  repo                   GitHub repository in the format 'owner/repo'
  --key <path>          Path to the private key file
  --client <client-id>  GitHub App client ID

Example:
  tsx src/tools/github-check.ts qubzes/hng12-devbotops --key ./private-key.pem --client 123456
    `);
    process.exit(1);
  }

  const repo = args[0];
  const keyIndex = args.indexOf('--key');
  const clientIndex = args.indexOf('--client');

  if (keyIndex === -1 || clientIndex === -1 || !args[keyIndex + 1] || !args[clientIndex + 1]) {
    console.error('Error: Missing required arguments');
    process.exit(1);
  }

  return {
    repo: repo!,
    key: args[keyIndex + 1]!,
    client: args[clientIndex + 1]!,
  };
}

async function checkBotInstallation(options: CliOptions): Promise<void> {
  try {
    // Load private key
    const privateKey = readFileSync(options.key, 'utf8');

    // Parse repository
    const [owner, repo] = options.repo.split('/');
    if (!owner || !repo) {
      throw new Error('Repository must be in format "owner/repo"');
    }

    // Create GitHub App authentication
    const octokit = new Octokit({
      authStrategy: createAppAuth,
      auth: {
        appId: options.client,
        privateKey,
      },
    });

    // Check if the app is installed on the repository
    try {
      const installation = await octokit.rest.apps.getRepoInstallation({
        owner,
        repo,
      });

      console.log(
        `✅ Bot is installed on ${options.repo} (Installation ID: ${installation.data.id})`
      );
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'status' in error && error.status === 404) {
        console.log(`❌ Bot is NOT installed on ${options.repo}`);
      } else {
        throw error;
      }
    }
  } catch (error) {
    console.error(`Error: ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  }
}

// Main execution
if (import.meta.url === `file://${process.argv[1]}`) {
  const options = parseCliArgs();
  checkBotInstallation(options).catch(error => {
    console.error('Unhandled error:', error);
    process.exit(1);
  });
}
