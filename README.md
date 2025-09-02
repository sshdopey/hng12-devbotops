# HNG12 DevOps Stage Management Bot - TypeScript Edition

A modern TypeScript Slack bot for managing DevOps stage submissions and server provisioning in the HNG12 program.

## Features

- 🤖 **Slack Integration**: Handle submissions via `/submit` command
- 🏗️ **Stage Management**: Automated grading and promotion system
- ☁️ **AWS Integration**: Automatic EC2 instance provisioning
- 📊 **Google Sheets**: Data persistence and tracking
- 🔒 **Type Safety**: Full TypeScript implementation with strict typing
- 🧪 **Testing**: Comprehensive test suite with Vitest
- 📝 **Code Quality**: ESLint + Prettier for consistent code style

## Architecture

### Core Components

- **Stage System**: Modular stage implementations with base class
- **Services**: AWS, Google Sheets integration services
- **Utils**: Type-safe utility functions
- **Config**: Environment-based configuration with validation

### Technology Stack

- **Runtime**: Node.js 18+
- **Language**: TypeScript 5.5+
- **Framework**: Slack Bolt SDK
- **Cloud**: AWS SDK v2
- **Database**: Google Sheets API
- **Testing**: Vitest + coverage
- **Linting**: ESLint + TypeScript ESLint
- **Formatting**: Prettier

## Project Structure

```
src/
├── config/          # Configuration and environment setup
├── services/        # External service integrations
│   ├── aws.ts      # AWS EC2/S3 operations
│   └── google-sheets.ts # Google Sheets integration
├── stages/          # Stage implementations
│   ├── base-stage.ts    # Abstract base stage class
│   └── stage-zero.ts    # Stage 0 implementation
├── types/           # TypeScript type definitions
├── utils/           # Utility functions
└── index.ts         # Main application entry point
```

## Setup

### Prerequisites

- Node.js 18 or higher
- npm or yarn
- Slack workspace with bot permissions
- Google Cloud Service Account credentials
- AWS credentials with EC2/S3 permissions

### Installation

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Set up environment variables**:
   Create a `.env` file with the following variables:
   ```env
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_USER_TOKEN=xoxp-your-user-token
   SLACK_APP_TOKEN=xapp-your-app-token
   SLACK_SIGNING_SECRET=your-signing-secret
   GITHUB_TOKEN=your-github-token
   MAINTENANCE_MODE=0
   NODE_ENV=development
   PORT=3000
   ```

3. **Google Sheets Setup**:
   - Place your `token.json` service account file in the project root
   - Ensure the service account has access to your spreadsheets

4. **AWS Setup**:
   - Configure AWS credentials via AWS CLI or environment variables
   - Ensure permissions for EC2 and S3 operations

## Development

### Available Scripts

- `npm run dev` - Start development server with hot reload
- `npm run build` - Build for production
- `npm start` - Start production server
- `npm test` - Run tests
- `npm run test:coverage` - Run tests with coverage
- `npm run lint` - Check code style
- `npm run lint:fix` - Fix linting issues
- `npm run format` - Format code with Prettier
- `npm run typecheck` - Type checking without build
- `npm run clean` - Clean build artifacts

### Code Style

The project follows strict TypeScript and ESLint rules:

- **Strict typing**: No `any` types allowed (warnings only)
- **Error handling**: Proper error boundaries and typed errors
- **Async/await**: Consistent async patterns
- **Immutable data**: Readonly interfaces and const assertions
- **Path aliases**: Clean imports using `@/` prefix

### Testing

Tests are written using Vitest with full TypeScript support:

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run specific test file
npm test src/utils/index.test.ts
```

## Deployment

### Production Build

```bash
npm run build
npm start
```

### Environment Configuration

Ensure all environment variables are properly set in production:

- Slack tokens and secrets
- AWS credentials and region
- Google service account credentials
- Application configuration

## Stage System

### Adding New Stages

1. Create a new stage class extending `BaseStage`
2. Implement required methods:
   - `submissionView()` - Slack modal configuration
   - `processSubmission()` - Submission processing logic
   - `gradeSubmission()` - Scoring algorithm
   - `formatResultMessage()` - Result display formatting

3. Register the stage in the main application:
   ```typescript
   const stages = {
     0: StageZero,
     1: StageOne, // Add new stage here
   };
   ```

### Stage Configuration

Each stage defines:
- **Channels**: Slack channels where submissions are allowed
- **Next Channels**: Channels users get access to after passing
- **Required Score**: Minimum score needed to pass
- **Grading Logic**: How submissions are evaluated

## API Integration

### Google Sheets

The bot integrates with Google Sheets for data persistence:

- **Stage 0**: Submission tracking and grading results
- **Server Requests**: EC2 instance provisioning records

### AWS Services

- **EC2**: Automatic instance provisioning for backend stages
- **S3**: SSH key storage with presigned URLs
- **IAM**: Secure service access

### Slack API

- **Socket Mode**: Real-time event handling
- **Slash Commands**: `/submit` and `/request-server`
- **Modal Views**: Interactive submission forms
- **Messaging**: Results and notifications

## Security

- **Environment Variables**: Sensitive data in environment variables
- **Service Accounts**: Google Cloud service account authentication
- **AWS IAM**: Least privilege access for AWS operations
- **Input Validation**: Zod schema validation for all inputs
- **Error Handling**: Proper error boundaries without data leaks

## Monitoring

The application includes comprehensive logging:

- **Winston Logger**: Structured logging with different levels
- **Error Tracking**: Full stack traces for debugging
- **Request Logging**: API call monitoring
- **Performance Metrics**: Timing for critical operations

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes following the code style guidelines
4. Add tests for new functionality
5. Ensure all tests pass and code is properly typed
6. Submit a pull request

## License

MIT License - see LICENSE file for details.