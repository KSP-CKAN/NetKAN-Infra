#!/usr/bin/env python3

import click
import boto3

@click.command()
@click.option('--queue', default='OutboundDev.fifo', help='SQS Queue to poll for metadata')
@click.option('--metadata', help='Queue Path/Url for Submitting Metadata', required=True,  envvar='METADATA_REPO')
def run(queue, metadata):
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=queue)
    print(queue.url)


if __name__ == '__main__':
    run()

