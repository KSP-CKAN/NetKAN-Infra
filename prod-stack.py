# Converted from SQS_With_CloudWatch_Alarms.template located at:
# http://aws.amazon.com/cloudformation/aws-cloudformation-templates/

from troposphere import GetAtt, Output, Ref, Template, Sub, Base64
from troposphere.iam import Policy, Role, InstanceProfile
from troposphere.sqs import Queue
from troposphere.dynamodb import Table, KeySchema, AttributeDefinition, \
    ProvisionedThroughput
from troposphere.ecs import Cluster, TaskDefinition, ContainerDefinition, \
    Service, Secret
from troposphere.ec2 import Instance, CreditSpecification
from troposphere.cloudformation import Init, InitFile, InitFiles, \
    InitConfig, InitService, Metadata
import os
import sys

zone_id = os.environ.get('CKAN_ZONEID', False)
subnet_id = os.environ.get('CKAN_SUBNET', False)
status_fqdn = 'status.test.ksp-ckan.space'

if not zone_id:
    print('Zone ID Required from EnvVar `CKAN_ZONEID`')
    sys.exit()

t = Template()

t.set_description("Generate NetKAN Infrastructure CF Template")

# Inbound + Outbound SQS Queues
# Inbound: Scheduler Write, Inflation Read
# Outbound: Inflator Write, Indexer Read
inbound = t.add_resource(Queue("NetKANInbound",
                               QueueName="Inbound.fifo",
                               ReceiveMessageWaitTimeSeconds=20,
                               FifoQueue=True))
outbound = t.add_resource(Queue("NetKANOutbound",
                                QueueName="Outbound.fifo",
                                ReceiveMessageWaitTimeSeconds=20,
                                FifoQueue=True))


for queue in [inbound, outbound]:
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


# DyanamoDB: NetKAN Status
netkan_db = t.add_resource(Table(
    "NetKANStatus",
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
    TableName="NetKANStatus",
    ProvisionedThroughput=ProvisionedThroughput(
        # The free tier allows for 25 R/W Capacity Units
        # 5 allocated already for dev testing
        ReadCapacityUnits=20,
        WriteCapacityUnits=20
    )
))

t.add_output(Output(
    "TableName",
    Value=Ref(netkan_db),
    Description="Table name of the newly create DynamoDB table",
))


# Instance Role for Prod Indexing Instance to be able to
# access the relevant AWS resources. We can lock it all
# down to the container level, but this is unnecessary for
# now.
netkan_role = t.add_resource(Role(
    "NetKANProdRole",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": [
                        "ec2.amazonaws.com"
                    ]
                },
                "Action": [
                    "sts:AssumeRole"
                ]
            }
        ]
    },
    ManagedPolicyArns=[
        "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role",
    ],
    Policies=[
        Policy(
            PolicyName="SQSProdPolicy",
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
                            GetAtt(outbound, "Arn")
                        ]
                    },
                    {
                        "Effect": "Allow",
                        "Action": "sqs:ListQueues",
                        "Resource": "*",
                    },
                ],
            }
        ),
        Policy(
            PolicyName="DynamoDBProdPolicy",
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
                            GetAtt(netkan_db, "Arn")
                        ]
                    },
                    {
                        "Effect": "Allow",
                        "Action": "dynamodb:ListTables",
                        "Resource": "*",
                    },
                ],
            }
        ),
        Policy(
            PolicyName="S3StatusAccessProd",
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
                            "arn:aws:s3:::status.ksp-ckan.org/*"
                        ]
                    },
                ],
            }
        ),
        Policy(
            PolicyName="CertbotProd",
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
        ),
    ]
))

netkan_profile = t.add_resource(InstanceProfile(
    "NetKANProdProfile",
    Roles=[Ref(netkan_role)]
))

# To Access the Secrets manager, the ecs agent needs to AsssumeRole permission
# regardless of what the instance can access.
netkan_ecs_role = t.add_resource(Role(
    "NetKANProdEcsRole",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ecs-tasks.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    },
    Policies=[
        Policy(
            PolicyName="AllowParameterAccess",
            PolicyDocument={
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ssm:DescribeParameters"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ssm:GetParameters"
                        ],
                        "Resource": Sub(
                            "arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/Test"
                        )
                    }
                ]
            }
        )
    ]
))

# Indexer Compute
# We could utilise an autoscaling group, but that is way
# more complicated for our use case. If at some point we'd
# to scale the service beyond a single instance (due to some
# infrastructure sponsorship) it wouldn't take more than
# adding an AutoScalingGroup + LoadBalancer to scale this.
netkan_ecs = t.add_resource(
    Cluster('NetKANCluster', ClusterName='NetKANCluster')
)

netkan_userdata = Sub("""
#!/bin/bash -xe
echo ECS_CLUSTER=NetKANCluster > /etc/ecs/ecs.config
yum install -y aws-cfn-bootstrap
# Install the files and packages from the metadata
/opt/aws/bin/cfn-init -v --stack ${AWS::StackName} \
--resource NetKANCompute --region ${AWS::Region}
# Start up the cfn-hup daemon to listen for changes
# to the metadata
/opt/aws/bin/cfn-hup || error_exit 'Failed to start cfn-hup
# Signal the status from cfn-init
/opt/aws/bin/cfn-signal -e $? --stack ${AWS::StackName} \
--resource NetKANCompute --region ${AWS::Region}
""")

cfn_hup = InitFile(
    content=Sub(
        "[main]\nstack=${AWS::StackId}\nregion=${AWS::Region}\n"
    ),
    mode='000400',
    owner='root',
    group='root'
)
reloader = InitFile(
    content=Sub("""
[cfn-auto-reloader-hook]
triggers=post.add, post.update
path=Resources.NetKANCompute.Metadata.AWS::CloudFormation::Init
action=/opt/aws/bin/cfn-init -s ${AWS::StackId} -r NetKANCompute --region ${AWS::Region}
runas=root
""")
)
docker = InitFile(
    content="""
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "20m",
        "max-file": "3"
    }
}
""")
cfn_service = InitService(
    enabled=True,
    ensureRunning=True,
    files=[
        '/etc/cfn/cfn-hup.conf',
        '/etc/cfn/hooks.d/cfn-auto-reloader.conf',
    ]
)
docker_service = InitService(
    enabled=True,
    ensureRunning=True,
    files=['/etc/docker/daemon.json']
)
netkan_instance = Instance(
    'NetKANCompute',
    # ECS Optimised us-west-2
    ImageId='ami-0e434a58221275ed4',
    InstanceType='t3.micro',
    IamInstanceProfile=Ref(netkan_profile),
    KeyName='techman83_alucard',
    SecurityGroups=['ckan-bot'],
    UserData=Base64(netkan_userdata),
    # t3 instances are unlimited by default
    CreditSpecification=CreditSpecification(CPUCredits='standard'),
    Metadata=Metadata(Init({
        'config': InitConfig(
            files=InitFiles({
                '/etc/cfn/cfn-hup.conf': cfn_hup,
                '/etc/cfn/hooks.d/cfn-auto-reloader.conf': reloader,
                '/etc/docker/daemon.json': docker,
            })
        ),
        'services': {
            'sysvinit': {
                'cfn': cfn_service,
                'docker': docker_service,
            }
        },
    })),
)
t.add_resource(netkan_instance)

test_task = TaskDefinition(
    "TestTask",
    ContainerDefinitions=[
        ContainerDefinition(
            Image="chentex/random-logger",
            Memory="16",
            Name="Test",
            Secrets=[
                Secret(Name='TestVar', ValueFrom='Test'),
            ]
        )
    ],
    Family=Sub('${AWS::StackName}TestTask'),
    ExecutionRoleArn=Ref(netkan_ecs_role),
)
t.add_resource(test_task)
test_service = Service(
    'TestService',
    Cluster='NetKANCluster',
    DesiredCount=1,
    TaskDefinition=Ref(test_task),
    DependsOn=['NetKANCluster'],
)
t.add_resource(test_service)

print(t.to_yaml())
