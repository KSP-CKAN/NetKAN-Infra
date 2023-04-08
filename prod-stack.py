#!/usr/bin/env python3
# mypy: ignore_errors=True

import os
import sys
from troposphere import GetAtt, Output, Ref, Template, Sub, Base64
from troposphere.iam import Group, Policy, PolicyType, Role, InstanceProfile
from troposphere.sqs import Queue
from troposphere.dynamodb import Table, KeySchema, AttributeDefinition, \
    ProvisionedThroughput
from troposphere.ecs import Cluster, TaskDefinition, ContainerDefinition, \
    Service, Secret, Environment, DeploymentConfiguration, Volume, \
    Host, MountPoint, PortMapping, ContainerDependency, LinuxParameters
from troposphere.ec2 import Instance, CreditSpecification, Tag, \
    BlockDeviceMapping, EBSBlockDevice
from troposphere.cloudformation import Init, InitFile, InitFiles, \
    InitConfig, InitService, Metadata
from troposphere.events import Rule, Target, EcsParameters
from troposphere.route53 import RecordSetType

ZONE_ID = os.environ.get('CKAN_ZONEID', False)
BOT_FQDN = 'netkan.ksp-ckan.space'
EMAIL = 'domains@ksp-ckan.space'
PARAM_NAMESPACE = '/NetKAN/Indexer/'
NETKAN_REMOTES = 'ksp=git@github.com:KSP-CKAN/NetKAN.git ksp2=git@github.com:KSP-CKAN/KSP2-NetKAN.git'
NETKAN_USER = 'KSP-CKAN'
NETKAN_REPOS = 'ksp=NetKAN ksp2=KSP2-NetKAN'
CKANMETA_REMOTES = 'ksp=git@github.com:KSP-CKAN/CKAN-meta.git ksp2=git@github.com:KSP-CKAN/KSP2-CKAN-meta.git'
CKANMETA_USER = 'KSP-CKAN'
CKANMETA_REPOS = 'ksp=CKAN-meta ksp2=KSP2-CKAN-meta'
NETKAN_USER = 'KSP-CKAN'
STATUS_BUCKET = 'status.ksp-ckan.space'
status_key = 'status/netkan.json'

if not ZONE_ID:
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
inbound2 = t.add_resource(Queue("NetKANKSP2Inbound",
                                QueueName="InboundKsp2.fifo",
                                ReceiveMessageWaitTimeSeconds=20,
                                FifoQueue=True))
outbound = t.add_resource(Queue("NetKANOutbound",
                                QueueName="Outbound.fifo",
                                ReceiveMessageWaitTimeSeconds=20,
                                FifoQueue=True))
addqueue = t.add_resource(Queue("Adding",
                                QueueName="Adding.fifo",
                                ReceiveMessageWaitTimeSeconds=20,
                                FifoQueue=True))
mirrorqueue = t.add_resource(Queue("Mirroring",
                                   QueueName="Mirroring.fifo",
                                   ReceiveMessageWaitTimeSeconds=20,
                                   FifoQueue=True))


for queue in [inbound, inbound2, outbound, addqueue, mirrorqueue]:
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

INFLATION_QUEUES = Sub('ksp=${ksp} ksp2=${ksp2}', ksp=GetAtt(inbound, 'QueueName'), ksp2=GetAtt(inbound2, 'QueueName'))

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
                            GetAtt(inbound2, "Arn"),
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
                            "arn:aws:s3:::status.ksp-ckan.space/*"
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
                                ZONE_ID
                            ),
                        ]
                    }
                ],
            }
        ),
        Policy(
            PolicyName="AllowCloudWatchMetrics",
            PolicyDocument={
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": [
                            "cloudwatch:GetMetricStatistics",
                            "ec2:DescribeVolumes"
                        ],
                        "Effect": "Allow",
                        "Resource": "*"
                    }
                ]
            }
        ),
        Policy(
            PolicyName="AllowWebhooksRestart",
            PolicyDocument={
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": [
                            "ecs:ListServices",
                        ],
                        "Effect": "Allow",
                        "Resource": "*",
                    },
                    {
                        "Action": [
                            "ecs:DescribeServices",
                        ],
                        "Effect": "Allow",
                        "Resource": Sub(
                            'arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:service/NetKANCluster/${service}',
                            service=GetAtt('WebhooksService', 'Name'),
                        )
                    },
                    {
                        "Action": [
                            "ecs:UpdateService",
                        ],
                        "Effect": "Allow",
                        "Resource": Sub(
                            'arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:service/NetKANCluster/${service}',
                            service=GetAtt('WebhooksService', 'Name'),
                        )
                    },
                ]
            }
        )
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
                            "arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter${ns}*",
                            ns=PARAM_NAMESPACE
                        )
                    }
                ]
            }
        )
    ]
))

# Build Account Permissions
# It's useful for the CI to be able to update services upon build, there
# is a service account with keys that will be exposed to CI for allowing
# redeployment of services.
ksp_builder_group = t.add_resource(Group("KspCkanBuilderGroup"))
builder_services = []
for service in ['Indexer', 'InflatorKsp', 'InflatorKsp2', 'Webhooks', 'Adder', 'Mirrorer']:
    builder_services.append(
        Sub(
            'arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:service/NetKANCluster/${service}',
            service=GetAtt('{}Service'.format(service), 'Name'),
        )
    )
t.add_resource(PolicyType(
    "KspCkanBuilderRole",
    PolicyName="KspCkanBuilder",
    Groups=[Ref(ksp_builder_group)],
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": [
                    "ecs:ListServices",
                ],
                "Effect": "Allow",
                "Resource": "*",
            },
            {
                "Action": [
                    "ecs:DescribeServices",
                ],
                "Effect": "Allow",
                "Resource": builder_services
            },
            {
                "Action": [
                    "ecs:UpdateService",
                ],
                "Effect": "Allow",
                "Resource": builder_services
            },
            {

                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                ],
                "Resource": [
                    "arn:aws:s3:::status.ksp-ckan.space/*"
                ],
            },
            {

                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:DeleteObject",
                ],
                "Resource": [
                    "arn:aws:s3:::ksp-ckan/*"
                ],
            },
            {

                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket",
                ],
                "Resource": [
                    "arn:aws:s3:::ksp-ckan"
                ],
            },
        ]
    }
))

# Metadata CI Permissions
# CI access for metadata actions
ksp_ci_metadata_group = t.add_resource(Group("KspCkanCiMetadataGroup"))
t.add_resource(PolicyType(
    "KspCkanCiMetadataRole",
    PolicyName="SQSMetadataInbound",
    Groups=[Ref(ksp_ci_metadata_group)],
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "sqs:SendMessage",
                    "sqs:GetQueueUrl",
                    "sqs:GetQueueAttributes",
                ],
                "Resource": [
                    GetAtt(inbound, "Arn"),
                    GetAtt(inbound2, "Arn"),
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

# Status CI Permissions
# CI access for status deployment
ksp_ci_status_group = t.add_resource(Group("KspCkanCiStatusGroup"))
t.add_resource(PolicyType(
    "KspCkanCiStatusRole",
    PolicyName="StatusDeployment",
    Groups=[Ref(ksp_ci_status_group)],
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {

                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                ],
                "Resource": [
                    "arn:aws:s3:::status.ksp-ckan.space/*"
                ],
            },
            {

                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket",
                ],
                "Resource": [
                    "arn:aws:s3:::status.ksp-ckan.space"
                ],
            },
        ],
    }
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

# ECS Volumes are a pain and I don't want to shave any more yaks
mkdir /mnt/letsencrypt
mkfs.ext4 -L CKANCACHE /dev/xvdh
mkdir -p /mnt/ckan_cache
echo "LABEL=CKANCACHE /mnt/ckan_cache ext4 defaults 0 2" >> /etc/fstab
mount -a
chown -R 1000:1000 /mnt/ckan_cache

# Docker doesn't see the new block device until restarted
service docker stop && service docker start
systemctl start ecs

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
    ImageId='ami-0e0e34cdb5fd714fc',
    InstanceType='t3.small',
    IamInstanceProfile=Ref(netkan_profile),
    KeyName='techman83_alucard',
    SecurityGroups=['ckan-bot'],
    UserData=Base64(netkan_userdata),
    # t3 instances are unlimited by default
    CreditSpecification=CreditSpecification(CPUCredits='standard'),
    Tags=[
        Tag(Key='Name', Value='NetKAN Indexer'),
        Tag(Key='Service', Value='Indexer'),
    ],
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
    BlockDeviceMappings=[
        BlockDeviceMapping(
            DeviceName='/dev/xvdh',
            Ebs=EBSBlockDevice(
                VolumeSize='100',
                VolumeType='standard',
            )
        )
    ]
)
t.add_resource(netkan_instance)

t.add_resource(RecordSetType(
    "NetKANDns",
    HostedZoneId=ZONE_ID,
    Comment="NetKAN Bot DNS",
    Name=BOT_FQDN,
    Type="A",
    TTL="900",
    ResourceRecords=[GetAtt('NetKANCompute', "PublicIp")],
))

services = [
    {
        'name': 'Indexer',
        'command': 'indexer',
        'memory': '256',
        'secrets': [
            'SSH_KEY', 'GH_Token',
        ],
        'env': [
            ('CKANMETA_REMOTES', CKANMETA_REMOTES),
            ('CKAN_USER', CKANMETA_USER),
            ('CKAN_REPOS', CKANMETA_REPOS),
            ('SQS_QUEUE', GetAtt(outbound, 'QueueName')),
            ('AWS_DEFAULT_REGION', Sub('${AWS::Region}')),
        ],
        'volumes': [
            ('ckan_cache', '/home/netkan/ckan_cache'),
        ],
        'linux_parameters': LinuxParameters(InitProcessEnabled=True),
    },
    {
        'name': 'Scheduler',
        'command': 'scheduler',
        'memory': '156',
        'secrets': ['SSH_KEY', 'GH_Token'],
        'env': [
            ('INFLATION_QUEUES', INFLATION_QUEUES),
            ('NETKAN_REMOTES', NETKAN_REMOTES),
            ('CKANMETA_REMOTES', CKANMETA_REMOTES),
            ('AWS_DEFAULT_REGION', Sub('${AWS::Region}')),
        ],
        'schedule': 'rate(30 minutes)',
    },
    {
        'name': 'SchedulerWebhooksPass',
        'command': [
            'scheduler', '--group', 'webhooks',
                '--max-queued', '2000',
                '--min-cpu', '25',
                '--min-io', '60',
        ],
        'memory': '156',
        'secrets': ['SSH_KEY', 'GH_Token'],
        'env': [
            ('INFLATION_QUEUES', INFLATION_QUEUES),
            ('NETKAN_REMOTES', NETKAN_REMOTES),
            ('CKANMETA_REMOTES', CKANMETA_REMOTES),
            ('AWS_DEFAULT_REGION', Sub('${AWS::Region}')),
        ],
        'schedule': 'rate(1 day)',
    },
    {
        'name': 'CleanCache',
        'command': [
            'clean-cache',
            '--days', '30',
        ],
        'env': [],
        'volumes': [
            ('ckan_cache', '/home/netkan/ckan_cache')
        ],
        'schedule': 'rate(1 day)',
    },
    {
        'name': 'InflatorKsp',
        'image': 'kspckan/inflator',
        'memory': '256',
        'secrets': ['GH_Token'],
        'env': [
            (
                'QUEUES', Sub(
                    '${Inbound},${Outbound}',
                    Inbound=GetAtt(inbound, 'QueueName'),
                    Outbound=GetAtt(outbound, 'QueueName')
                )
            ),
            ('AWS_REGION', Sub('${AWS::Region}')),
            ('GAME', 'KSP')
        ],
        'volumes': [
            ('ckan_cache', '/home/netkan/ckan_cache')
        ]
    },
    {
        'name': 'InflatorKsp2',
        'image': 'kspckan/inflator',
        'memory': '256',
        'secrets': ['GH_Token'],
        'env': [
            (
                'QUEUES', Sub(
                    '${Inbound},${Outbound}',
                    Inbound=GetAtt(inbound2, 'QueueName'),
                    Outbound=GetAtt(outbound, 'QueueName')
                )
            ),
            ('AWS_REGION', Sub('${AWS::Region}')),
            ('GAME', 'KSP2')
        ],
        'volumes': [
            ('ckan_cache', '/home/netkan/ckan_cache')
        ]
    },
    {
        'name': 'StatusDumper',
        'command': 'export-status-s3',
        'env': [
            ('STATUS_BUCKET', STATUS_BUCKET),
            ('STATUS_KEY', status_key),
            ('STATUS_INTERVAL', '0'),
        ],
        'schedule': 'rate(5 minutes)',
    },
    {
        'name': 'DownloadCounter',
        'command': 'download-counter',
        'memory': '156',
        'secrets': [
            'SSH_KEY', 'GH_Token',
        ],
        'env': [
            ('NETKAN_REMOTES', NETKAN_REMOTES),
            ('CKANMETA_REMOTES', CKANMETA_REMOTES),
        ],
        'schedule': 'rate(1 day)',
    },
    {
        'name': 'CertBot',
        'image': 'certbot/dns-route53',
        'command': [
            'certonly', '-n', '--agree-tos', '--email',
            EMAIL, '--dns-route53', '-d', BOT_FQDN
        ],
        'volumes': [
            ('letsencrypt', '/etc/letsencrypt')
        ],
        'schedule': 'cron(0 0 ? * MON *)',
    },
    # TODO: It'd be nice to detect a new cert, this'll do for now.
    {
        'name': 'RestartWebhooks',
        'command': [
            'redeploy-service',
            '--cluster', 'NetKANCluster',
            '--service-name', 'Webhooks',
        ],
        'env': [
            ('AWS_DEFAULT_REGION', Sub('${AWS::Region}')),
        ],
        'schedule': 'cron(30 0 ? * MON *)',
    },
    {
        'name': 'TicketCloser',
        'command': 'ticket-closer',
        'env': [
            ('CKAN_USER', NETKAN_USER),
        ],
        'secrets': ['GH_Token'],
        'schedule': 'rate(1 day)',
    },
    {
        'name': 'AutoFreezer',
        'command': 'auto-freezer',
        'env': [
            ('NETKAN_REMOTES', NETKAN_REMOTES),
            ('CKAN_USER', NETKAN_USER),
            ('CKAN_REPOS', NETKAN_REPOS),
        ],
        'secrets': [
            'SSH_KEY', 'GH_Token',
        ],
        'schedule': 'rate(7 days)',
    },
    {
        'name': 'Webhooks',
        'containers': [
            {
                'name': 'webhooks',
                'entrypoint': '.local/bin/gunicorn',
                'memory': '256',
                'command': [
                    '-b', '0.0.0.0:5000', '--access-logfile', '-',
                    '--preload', 'netkan.webhooks:create_app()'
                ],
                'secrets': [
                    'XKAN_GHSECRET', 'SSH_KEY',
                ],
                'env': [
                    ('NETKAN_REMOTES', NETKAN_REMOTES),
                    ('CKANMETA_REMOTES', CKANMETA_REMOTES),
                    ('AWS_DEFAULT_REGION', Sub('${AWS::Region}')),
                    ('INFLATION_SQS_QUEUES', INFLATION_QUEUES),
                    ('ADD_SQS_QUEUE', GetAtt(addqueue, 'QueueName')),
                    ('MIRROR_SQS_QUEUE', GetAtt(mirrorqueue, 'QueueName')),
                ],
            },
            {
                'name': 'WebhooksProxy',
                'image': 'kspckan/webhooks-proxy',
                'memory': '32',
                'ports': ['80', '443'],
                'volumes': [
                    ('letsencrypt', '/etc/letsencrypt')
                ],
                'depends': ['webhooks']
            },
        ]
    },
    {
        'name': 'Adder',
        'command': 'spacedock-adder',
        'secrets': ['GH_Token', 'SSH_KEY'],
        'env': [
            ('SQS_QUEUE', GetAtt(addqueue, 'QueueName')),
            ('AWS_DEFAULT_REGION', Sub('${AWS::Region}')),
            ('NETKAN_REMOTES', NETKAN_REMOTES),
            ('CKAN_USER', NETKAN_USER),
            ('CKAN_REPOS', NETKAN_REPOS),
        ],
    },
    {
        'name': 'Mirrorer',
        'command': 'mirrorer',
        'secrets': [
            'IA_access', 'IA_secret', 'SSH_KEY', 'GH_Token'
        ],
        'env': [
            ('CKANMETA_REMOTES', CKANMETA_REMOTES),
            ('IA_COLLECTIONS', 'ksp=kspckanmods'),
            ('SQS_QUEUE', GetAtt(mirrorqueue, 'QueueName')),
            ('AWS_DEFAULT_REGION', Sub('${AWS::Region}')),
        ],
        'volumes': [
            ('ckan_cache', '/home/netkan/ckan_cache'),
        ],
    },
]

# To be able to schedule tasks, the scheduler needs to be allowed to perform
# the tasks.
scheduler_resources = []
for task in [
        x.get('name') for x in services if x.get('schedule', None) is not None]:
    scheduler_resources.append(Sub(
        'arn:aws:ecs:*:${AWS::AccountId}:task-definition/NetKANBot${Task}:*',
        Task=task
    ))
netkan_scheduler_role = t.add_resource(Role(
    "NetKANProdSchedulerRole",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "events.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    },
    Policies=[
        Policy(
            PolicyName="AllowEcsTaskScheduling",
            PolicyDocument={
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ecs:RunTask"
                        ],
                        "Resource": scheduler_resources,
                        "Condition": {
                            "ArnLike": {
                                "ecs:cluster": GetAtt('NetKANCluster', 'Arn')
                            }
                        }
                    },
                    {
                        "Effect": "Allow",
                        "Action": "iam:PassRole",
                        "Resource": [
                            "*"
                        ],
                        "Condition": {
                            "StringLike": {
                                "iam:PassedToService": "ecs-tasks.amazonaws.com"
                            }
                        }
                    }
                ]
            }
        )
    ]
))


for service in services:
    name = service['name']
    schedule = service.get('schedule')
    containers = service.get('containers', [service])
    task = TaskDefinition(
        '{}Task'.format(name),
        ContainerDefinitions=[],
        Family=Sub('${AWS::StackName}${name}', name=name),
        ExecutionRoleArn=Ref(netkan_ecs_role),
        Volumes=[],
        DependsOn=[],
    )

    for container in containers:
        secrets = [
            'DISCORD_WEBHOOK_ID', 'DISCORD_WEBHOOK_TOKEN',
            *container.get('secrets', [])
        ]
        envs = container.get('env', [])
        entrypoint = container.get('entrypoint')
        command = container.get('command')
        volumes = container.get('volumes', [])
        ports = container.get('ports', [])
        depends = container.get('depends', [])
        linux_parameters = container.get('linux_parameters')
        definition = ContainerDefinition(
            Image=container.get('image', 'kspckan/netkan'),
            Memory=container.get('memory', '128'),
            Name=container['name'],
            Secrets=[
                Secret(
                    Name=x,
                    ValueFrom='{}{}'.format(
                        PARAM_NAMESPACE, x
                    )
                ) for x in secrets
            ],
            Environment=[
                Environment(
                    Name=x[0], Value=x[1]
                ) for x in envs
            ],
            MountPoints=[],
            PortMappings=[],
            DependsOn=[],
            Links=[],
        )
        if entrypoint:
            entrypoint = entrypoint if isinstance(
                entrypoint, list) else [entrypoint]
            definition.EntryPoint = entrypoint
        if command:
            command = command if isinstance(command, list) else [command]
            definition.Command = command
        if linux_parameters:
            definition.LinuxParameters = linux_parameters
        for volume in volumes:
            volume_name = '{}{}'.format(
                name,
                ''.join([i for i in volume[0].capitalize() if i.isalpha()])
            )
            task.Volumes.append(
                Volume(
                    Name=volume_name,
                    Host=Host(
                        SourcePath=('/mnt/{}'.format(volume[0]))
                    )
                )
            )
            definition.MountPoints.append(
                MountPoint(
                    ContainerPath=volume[1],
                    SourceVolume=volume_name
                )
            )
        for port in ports:
            definition.PortMappings.append(
                PortMapping(
                    ContainerPort=port,
                    HostPort=port,
                    Protocol='tcp',
                )
            )
        for depend in depends:
            definition.DependsOn.append(
                ContainerDependency(
                    Condition='START',
                    ContainerName=depend,
                )
            )
            definition.Links.append(depend)
        task.ContainerDefinitions.append(definition)
    t.add_resource(task)

    if schedule:
        target = Target(
            Id="{}-Schedule".format(name),
            Arn=GetAtt(netkan_ecs, 'Arn'),
            RoleArn=GetAtt(netkan_scheduler_role, 'Arn'),
            EcsParameters=EcsParameters(
                TaskDefinitionArn=Ref(task)
            )
        )
        t.add_resource(Rule(
            '{}Rule'.format(name),
            Description='{} scheduled task'.format(name),
            ScheduleExpression=schedule,
            Targets=[target],
        ))
        continue

    t.add_resource(Service(
        '{}Service'.format(name),
        Cluster='NetKANCluster',
        DesiredCount=1,
        TaskDefinition=Ref(task),
        # Allow for in place service redeployments
        DeploymentConfiguration=DeploymentConfiguration(
            MaximumPercent=100,
            MinimumHealthyPercent=0
        ),
        DependsOn=['NetKANCluster']
    ))

print(t.to_yaml())
