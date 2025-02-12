from datetime import datetime

import boto3


def upload_to_s3(key_material, key_name):
    """Upload key to S3 and return the download URL"""
    s3 = boto3.client('s3')
    bucket_name = 'hng12-devbotops'
    key_path = f'keys/{key_name}.pem'
    
    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=key_path,
            Body=key_material,
            ContentType='text/plain'
        )
        
        # Generate presigned URL that expires in 1 hour
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': key_path},
            ExpiresIn=3600
        )
        return url
    except Exception as e:
        raise Exception(f"Failed to upload key to S3: {str(e)}")


def setup_aws_instance(
    instance_type="t3.micro",
    security_group_id="sg-09bd2a53c2f724517",
):
    """
    Sets up an AWS EC2 instance and returns its details.
    Returns a JSON with instance information and credentials.
    """
    ec2 = boto3.client("ec2", region_name="us-east-2")

    timestamp = datetime.now().strftime("%m%d-%H%M%S%f")[:-3]
    key_name = f"key-{timestamp}"

    try:
        key_pair = ec2.create_key_pair(KeyName=key_name)
        
        # Upload key to S3 instead of saving locally
        key_url = upload_to_s3(key_pair["KeyMaterial"], key_name)

        ami_id = get_ubuntu_ami()
        security_group_id = ensure_security_group()
        instance = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=instance_type,
            SecurityGroupIds=[security_group_id],
            KeyName=key_name,
            MinCount=1,
            MaxCount=1,
        )

        instance_id = instance["Instances"][0]["InstanceId"]

        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])

        response = ec2.describe_instances(InstanceIds=[instance_id])
        public_ip = response["Reservations"][0]["Instances"][0]["PublicIpAddress"]

        return {
            "instance_id": instance_id,
            "key_id": key_name,
            "username": "ubuntu",
            "ip_address": public_ip,
            "key_url": key_url,
        }

    except Exception as e:
        try:
            ec2.delete_key_pair(KeyName=key_name)
            # Delete from S3 if exists
            s3 = boto3.client('s3')
            s3.delete_object(Bucket='hng12', Key=f'keys/{key_name}.pem')
        except:
            pass
        raise Exception(f"Failed to setup AWS instance: {str(e)}")


def get_ubuntu_ami():
    """Get latest Ubuntu 22.04 AMI ID"""
    ec2 = boto3.client("ec2", region_name="us-east-2")
    response = ec2.describe_images(
        Filters=[
            {
                "Name": "name",
                "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"],
            },
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
        ],
        Owners=["099720109477"],
    )
    return sorted(
        response["Images"], key=lambda x: x["CreationDate"], reverse=True
    )[0]["ImageId"]


def ensure_security_group(group_name="default-sg"):
    """Create security group if it doesn't exist"""
    ec2 = boto3.client("ec2", region_name="us-east-2")

    vpc_response = ec2.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )
    vpc_id = vpc_response["Vpcs"][0]["VpcId"]

    try:
        response = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [group_name]}]
        )
        return response["SecurityGroups"][0]["GroupId"]
    except:
        response = ec2.create_security_group(
            GroupName=group_name,
            Description="Security group for EC2 instances",
            VpcId=vpc_id,
        )
        security_group_id = response["GroupId"]

        ec2.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
        return security_group_id

def destroy_all_instances():
    """Destroys all EC2 instances and keys in us-east-1 and us-east-2, and cleans up S3 keys"""
    regions = ['us-east-1', 'us-east-2']
    
    for region in regions:
        ec2 = boto3.client('ec2', region_name=region)
        
        # Get all instances
        instances = ec2.describe_instances()
        
        # Collect all instance IDs
        instance_ids = []
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                if instance['State']['Name'] != 'terminated':
                    instance_ids.append(instance['InstanceId'])
        
        # Terminate instances if any exist
        if instance_ids:
            try:
                ec2.terminate_instances(InstanceIds=instance_ids)
                print(f"Terminated {len(instance_ids)} instances in {region}")
            except Exception as e:
                print(f"Error terminating instances in {region}: {str(e)}")
        
        # Delete all key pairs
        try:
            keys = ec2.describe_key_pairs()
            for key in keys['KeyPairs']:
                ec2.delete_key_pair(KeyName=key['KeyName'])
                print(f"Deleted key pair {key['KeyName']} in {region}")
        except Exception as e:
            print(f"Error deleting keys in {region}: {str(e)}")
    
    # Clean up S3 keys
    try:
        s3 = boto3.client('s3')
        response = s3.list_objects_v2(Bucket='hng12-devbotops', Prefix='keys/')
        if 'Contents' in response:
            for obj in response['Contents']:
                s3.delete_object(Bucket='hng12-devbotops', Key=obj['Key'])
            print("Cleaned up keys from S3")
    except Exception as e:
        print(f"Error cleaning up S3 keys: {str(e)}")


if __name__ == "__main__":
    destroy_all_instances()
