#!/bin/bash
# Exit on error
set -e

# AWS CLI configuration check
if ! aws sts get-caller-identity &>/dev/null; then
    echo "Error: AWS CLI is not configured. Please run 'aws configure' first."
    exit 1
fi

# Variables
AMI_ID="ami-0e1bed4f06a3b463d"
INSTANCE_TYPE="t2.micro"  # Default instance type, modify as needed
SECURITY_GROUP_ID="sg-09bd2a53c2f724517"
KEY_NAME="key-$(date +%Y%m%d-%H%M%S)"
KEY_PATH="$HOME/.aws/keys/${KEY_NAME}.pem"

# Create keys directory if it doesn't exist
mkdir -p "$HOME/.aws/keys"

# Create key pair and save to file
echo "Creating new key pair..."
aws ec2 create-key-pair \
    --key-name "$KEY_NAME" \
    --query 'KeyMaterial' \
    --output text > "$KEY_PATH"

# Set correct permissions for key file
chmod 400 "$KEY_PATH"

# Launch EC2 instance
echo "Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --security-group-ids "$SECURITY_GROUP_ID" \
    --key-name "$KEY_NAME" \
    --query 'Instances[0].InstanceId' \
    --output text)

# Wait for instance to be running
echo "Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# Get instance public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

# Print connection information
echo -e "\n=== EC2 Instance Details ==="
echo "Instance ID: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo "Username: ubuntu"
echo "SSH Key Path: $KEY_PATH"
echo -e "\nTo connect, use: ssh -i $KEY_PATH ubuntu@$PUBLIC_IP"

# Add cleanup instructions
echo -e "\nTo terminate this instance later, run:"
echo "aws ec2 terminate-instances --instance-ids $INSTANCE_ID"
echo "aws ec2 delete-key-pair --key-name $KEY_NAME"
