import AWS from 'aws-sdk';
import { logger, Config } from '@/config';
import { ExternalServiceError, type AwsInstanceResult } from '@/types';

interface AwsInstanceConfig {
  readonly instanceType?: string;
  readonly securityGroupId?: string;
  readonly region?: string;
}

export class AwsService {
  private readonly ec2: AWS.EC2;
  private readonly s3: AWS.S3;

  constructor(private readonly config: AwsInstanceConfig = {}) {
    const region = config.region ?? Config.aws.region;

    AWS.config.update({ region });

    this.ec2 = new AWS.EC2({ region });
    this.s3 = new AWS.S3({ region });
  }

  /**
   * Upload SSH key to S3 and return presigned URL
   */
  private async uploadKeyToS3(keyMaterial: string, keyName: string): Promise<string> {
    try {
      const keyPath = `keys/${keyName}.pem`;

      await this.s3
        .putObject({
          Bucket: Config.aws.s3Bucket,
          Key: keyPath,
          Body: keyMaterial,
          ContentType: 'text/plain',
        })
        .promise();

      const url = this.s3.getSignedUrl('getObject', {
        Bucket: Config.aws.s3Bucket,
        Key: keyPath,
        Expires: 3600, // 1 hour
      });

      return url;
    } catch (error) {
      throw new ExternalServiceError(
        `Failed to upload key to S3: ${error instanceof Error ? error.message : String(error)}`,
        'AWS-S3'
      );
    }
  }

  /**
   * Get the latest Ubuntu 22.04 AMI ID
   */
  private async getUbuntuAmi(): Promise<string> {
    try {
      const result = await this.ec2
        .describeImages({
          Filters: [
            {
              Name: 'name',
              Values: ['ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*'],
            },
            { Name: 'state', Values: ['available'] },
            { Name: 'architecture', Values: ['x86_64'] },
          ],
          Owners: ['099720109477'], // Canonical
        })
        .promise();

      const images = result.Images ?? [];
      if (images.length === 0) {
        throw new Error('No Ubuntu AMIs found');
      }

      const latestImage = images.sort(
        (a, b) => new Date(b.CreationDate ?? 0).getTime() - new Date(a.CreationDate ?? 0).getTime()
      )[0];

      if (!latestImage?.ImageId) {
        throw new Error('No valid Ubuntu AMI found');
      }

      return latestImage.ImageId;
    } catch (error) {
      throw new ExternalServiceError(
        `Failed to get Ubuntu AMI: ${error instanceof Error ? error.message : String(error)}`,
        'AWS-EC2'
      );
    }
  }

  /**
   * Ensure security group exists or create it
   */
  private async ensureSecurityGroup(groupName: string = 'default-sg'): Promise<string> {
    try {
      // Get default VPC
      const vpcResult = await this.ec2
        .describeVpcs({
          Filters: [{ Name: 'isDefault', Values: ['true'] }],
        })
        .promise();

      const defaultVpc = vpcResult.Vpcs?.[0];
      if (!defaultVpc?.VpcId) {
        throw new Error('No default VPC found');
      }

      // Check if security group exists
      try {
        const sgResult = await this.ec2
          .describeSecurityGroups({
            Filters: [{ Name: 'group-name', Values: [groupName] }],
          })
          .promise();

        const existingSg = sgResult.SecurityGroups?.[0];
        if (existingSg?.GroupId) {
          return existingSg.GroupId;
        }
      } catch {
        // Security group doesn't exist, will create it
      }

      // Create security group
      const createResult = await this.ec2
        .createSecurityGroup({
          GroupName: groupName,
          Description: 'Security group for EC2 instances',
          VpcId: defaultVpc.VpcId,
        })
        .promise();

      const securityGroupId = createResult.GroupId;
      if (!securityGroupId) {
        throw new Error('Failed to create security group');
      }

      // Add SSH access rule
      await this.ec2
        .authorizeSecurityGroupIngress({
          GroupId: securityGroupId,
          IpPermissions: [
            {
              IpProtocol: 'tcp',
              FromPort: 22,
              ToPort: 22,
              IpRanges: [{ CidrIp: '0.0.0.0/0' }],
            },
          ],
        })
        .promise();

      return securityGroupId;
    } catch (error) {
      throw new ExternalServiceError(
        `Failed to ensure security group: ${error instanceof Error ? error.message : String(error)}`,
        'AWS-EC2'
      );
    }
  }

  /**
   * Setup AWS EC2 instance with SSH key
   */
  async setupInstance(): Promise<AwsInstanceResult> {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    const keyName = `key-${timestamp}`;

    try {
      logger.info('Creating key pair...');
      const keyPair = await this.ec2.createKeyPair({ KeyName: keyName }).promise();

      if (!keyPair.KeyMaterial) {
        throw new Error('No key material returned from AWS');
      }

      logger.info('Uploading key to S3...');
      const keyUrl = await this.uploadKeyToS3(keyPair.KeyMaterial, keyName);

      logger.info('Getting Ubuntu AMI...');
      const amiId = await this.getUbuntuAmi();

      logger.info('Ensuring security group...');
      const securityGroupId = this.config.securityGroupId ?? (await this.ensureSecurityGroup());

      logger.info('Launching EC2 instance...');
      const instanceResult = await this.ec2
        .runInstances({
          ImageId: amiId,
          InstanceType: this.config.instanceType ?? Config.aws.defaultInstanceType,
          SecurityGroupIds: [securityGroupId],
          KeyName: keyName,
          MinCount: 1,
          MaxCount: 1,
        })
        .promise();

      const instance = instanceResult.Instances?.[0];
      if (!instance?.InstanceId) {
        throw new Error('No instance returned from AWS');
      }

      logger.info(`Waiting for instance ${instance.InstanceId} to be running...`);
      await this.ec2
        .waitFor('instanceRunning', {
          InstanceIds: [instance.InstanceId],
        })
        .promise();

      logger.info('Getting instance public IP...');
      const describeResult = await this.ec2
        .describeInstances({
          InstanceIds: [instance.InstanceId],
        })
        .promise();

      const runningInstance = describeResult.Reservations?.[0]?.Instances?.[0];
      if (!runningInstance?.PublicIpAddress) {
        throw new Error('No public IP address found for instance');
      }

      const result: AwsInstanceResult = {
        instanceId: instance.InstanceId,
        keyId: keyName,
        username: 'ubuntu',
        ipAddress: runningInstance.PublicIpAddress,
        keyUrl,
      };

      logger.info('EC2 instance setup completed successfully:', result);
      return result;
    } catch (error) {
      // Cleanup on failure
      try {
        await this.ec2.deleteKeyPair({ KeyName: keyName }).promise();
        await this.s3
          .deleteObject({
            Bucket: Config.aws.s3Bucket,
            Key: `keys/${keyName}.pem`,
          })
          .promise();
      } catch (cleanupError) {
        logger.error('Error during cleanup:', cleanupError);
      }

      throw new ExternalServiceError(
        `Failed to setup AWS instance: ${error instanceof Error ? error.message : String(error)}`,
        'AWS-EC2'
      );
    }
  }

  /**
   * Destroy all instances and cleanup resources
   */
  async destroyAllInstances(regions: string[] = ['us-east-1', 'us-east-2']): Promise<void> {
    const cleanupPromises = regions.map(async region => {
      const ec2 = new AWS.EC2({ region });

      try {
        // Get all instances
        const instancesResult = await ec2.describeInstances().promise();
        const instanceIds: string[] = [];

        for (const reservation of instancesResult.Reservations ?? []) {
          for (const instance of reservation.Instances ?? []) {
            if (instance.State?.Name !== 'terminated' && instance.InstanceId) {
              instanceIds.push(instance.InstanceId);
            }
          }
        }

        // Terminate instances
        if (instanceIds.length > 0) {
          await ec2.terminateInstances({ InstanceIds: instanceIds }).promise();
          logger.info(`Terminated ${instanceIds.length} instances in ${region}`);
        }

        // Delete all key pairs
        const keysResult = await ec2.describeKeyPairs().promise();
        for (const key of keysResult.KeyPairs ?? []) {
          if (key.KeyName) {
            await ec2.deleteKeyPair({ KeyName: key.KeyName }).promise();
            logger.info(`Deleted key pair ${key.KeyName} in ${region}`);
          }
        }
      } catch (error) {
        logger.error(`Error cleaning up resources in ${region}:`, error);
      }
    });

    // Cleanup S3 keys
    try {
      const s3Objects = await this.s3
        .listObjectsV2({
          Bucket: Config.aws.s3Bucket,
          Prefix: 'keys/',
        })
        .promise();

      if (s3Objects.Contents) {
        const deleteObjects = s3Objects.Contents.filter(obj => obj.Key).map(obj => ({
          Key: obj.Key!,
        }));

        if (deleteObjects.length > 0) {
          await this.s3
            .deleteObjects({
              Bucket: Config.aws.s3Bucket,
              Delete: { Objects: deleteObjects },
            })
            .promise();
          logger.info('Cleaned up keys from S3');
        }
      }
    } catch (error) {
      logger.error('Error cleaning up S3 keys:', error);
    }

    await Promise.all(cleanupPromises);
  }
}
