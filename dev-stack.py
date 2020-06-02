# Converted from SQS_With_CloudWatch_Alarms.template located at:
# http://aws.amazon.com/cloudformation/aws-cloudformation-templates/

import os
import sys
from troposphere import GetAtt, Output, Ref, Sub, Template
from troposphere.iam import Group, PolicyType
from troposphere.sqs import Queue
from troposphere.dynamodb import Table, KeySchema, AttributeDefinition, \
    ProvisionedThroughput
from troposphere.s3 import Bucket

zone_id = os.environ.get('CKAN_DEV_ZONEID', False)

if not zone_id:
    print('Zone ID Required from EnvVar `CKAN_DEV_ZONEID`')
    sys.exit()

t = Template()

t.set_description("Generate NetKAN Infrastructure CF Template")

inbound = t.add_resource(Queue("InboundDev",
                               QueueName="InboundDev.fifo",
                               ReceiveMessageWaitTimeSeconds=20,
                               FifoQueue=True))
outbound = t.add_resource(Queue("OutboundDev",
                                QueueName="OutboundDev.fifo",
                                ReceiveMessageWaitTimeSeconds=20,
                                FifoQueue=True))
addqueue = t.add_resource(Queue("Adding",
                                QueueName="AddingDev.fifo",
                                ReceiveMessageWaitTimeSeconds=20,
                                FifoQueue=True))
mirrorqueue = t.add_resource(Queue("Mirroring",
                                   QueueName="MirroringDev.fifo",
                                   ReceiveMessageWaitTimeSeconds=20,
                                   FifoQueue=True))

queue_dev_group = t.add_resource(Group("QueueDevGroup"))
t.add_resource(PolicyType(
    "QueueDevPolicies",
    PolicyName="QueueDevUsers",
    Groups=[Ref(queue_dev_group)],
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "sqs:SendMessage",
                    "sqs:DeleteMessage",
                    "sqs:PurgeQueue",
                    "sqs:ReceiveMessage",
                    "sqs:GetQueueUrl",
                    "sqs:GetQueueAttributes",
                ],
                "Resource": [
                    GetAtt(inbound, "Arn"),
                    GetAtt(outbound, "Arn"),
                    GetAtt(addqueue, "Arn"),
                    GetAtt(mirrorqueue, "Arn"),
                ]
            },
            {
                "Effect": "Allow",
                "Action": "sqs:ListQueues",
                "Resource": "*",
            },
        ],
    }
))

for queue in [inbound, outbound, addqueue, mirrorqueue]:
    t.add_output([
        Output(
            "{}QueueURL".format(queue.title),
            Description="{} SQS Queue URL".format(queue.title),
            Value=Ref(queue)
        ),
        Output(
            "{}QueueARN".format(queue.title),
            Description="ARN of {} SQS Queue".format(queue.title),
            Value=GetAtt(queue, "Arn")
        ),
    ])

dev_db = t.add_resource(Table(
    "DevNetKANStatus",
    AttributeDefinitions=[
        AttributeDefinition(
            AttributeName="ModIdentifier",
            AttributeType="S"
        ),
    ],
    KeySchema=[
        KeySchema(
            AttributeName="ModIdentifier",
            KeyType="HASH"
        )
    ],
    TableName="DevNetKANStatus",
    ProvisionedThroughput=ProvisionedThroughput(
        ReadCapacityUnits=5,
        WriteCapacityUnits=5
    )
))

t.add_output(Output(
    "TableName",
    Value=Ref(dev_db),
    Description="Table name of the newly create DynamoDB table",
))

t.add_resource(PolicyType(
    "DbDevPolicies",
    PolicyName="DbDevUsers",
    Groups=[Ref(queue_dev_group)],
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:DescribeTable",
                    "dynamodb:GetItem",
                    "dynamodb:Query",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Scan",
                    "dynamodb:BatchWriteItem",
                ],
                "Resource": [
                    GetAtt(dev_db, "Arn")
                ]
            },
            {
                "Effect": "Allow",
                "Action": "dynamodb:ListTables",
                "Resource": "*",
            },
        ],
    }
))

s3_bucket = t.add_resource(
    Bucket("CkanTestStatus", BucketName="ckan-test-status")
)

t.add_output(Output(
    "TestCkanStatus",
    Value=Ref(s3_bucket),
    Description="Name of S3 bucket to hold test status file"
))

t.add_resource(PolicyType(
    "S3TestBucket",
    PolicyName="S3TestBucketAccess",
    Groups=[Ref(queue_dev_group)],
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                ],
                "Resource": [
                    Sub("${Bucket}/*", Bucket=GetAtt(s3_bucket, "Arn"))
                ]
            },
        ],
    }
))

t.add_resource(PolicyType(
    "CertBotAccess",
    PolicyName="CertBotAccess",
    Groups=[Ref(queue_dev_group)],
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "route53:ListHostedZones",
                    "route53:GetChange"
                ],
                "Resource": [
                    "*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "route53:ChangeResourceRecordSets"
                ],
                "Resource": [
                    "arn:aws:route53:::hostedzone/{}".format(
                        zone_id
                    ),
                ]
            }
        ],
    }
))

print(t.to_yaml())
