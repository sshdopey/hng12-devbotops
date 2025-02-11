import boto3
import os
from datetime import datetime


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

    key_dir = os.path.expanduser("~/.aws/keys")
    os.makedirs(key_dir, exist_ok=True)
    key_path = os.path.join(key_dir, f"{key_name}.pem")

    try:
        key_pair = ec2.create_key_pair(KeyName=key_name)

        with open(key_path, "w") as key_file:
            key_file.write(key_pair["KeyMaterial"])
        os.chmod(key_path, 0o400)

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
        public_ip = response["Reservations"][0]["Instances"][0][
            "PublicIpAddress"
        ]

        return {
            "instance_id": instance_id,
            "key_id": key_name,
            "username": "ubuntu",
            "ip_address": public_ip,
            "key_path": key_path,
        }

    except Exception as e:
        try:
            ec2.delete_key_pair(KeyName=key_name)
            if os.path.exists(key_path):
                os.remove(key_path)
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
                "Values": [
                    "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
                ],
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
    """Destroys all EC2 instances in us-east-1 and us-east-2"""
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
                
if __name__ == "__main__":
    destroy_all_instances()