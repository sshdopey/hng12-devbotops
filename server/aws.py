import boto3
import os
from datetime import datetime


def setup_aws_instance(
    ami_id="ami-0e1bed4f06a3b463d",
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
