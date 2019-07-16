# Converted from SQS_With_CloudWatch_Alarms.template located at:
# http://aws.amazon.com/cloudformation/aws-cloudformation-templates/

from troposphere import GetAtt, Output, Parameter, Ref, Template, Sub
from troposphere.iam import AccessKey, Group, LoginProfile, PolicyType
from troposphere.sqs import Queue
from troposphere.dynamodb import Table, KeySchema, AttributeDefinition, ProvisionedThroughput


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
                ],
                "Resource": [
                    GetAtt(inbound, "Arn"),
                    GetAtt(outbound,"Arn")
                ]
            },
            {
                "Effect": "Allow",
                "Action":"sqs:ListQueues",
                "Resource": "*",
            },
        ],
    }
))

for queue in [inbound,outbound]:
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
                ],
                "Resource": [
                    GetAtt(dev_db,"Arn")
                ]
            },
            {
                "Effect": "Allow",
                "Action":"dynamodb:ListTables",
                "Resource": "*",
            },
        ],
    }
))

print(t.to_yaml())


