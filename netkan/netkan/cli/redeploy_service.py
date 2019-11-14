import click
import boto3


@click.command()
@click.option(
    '--cluster', help='ECS Cluster running the service'
)
@click.option(
    '--service-name', help='Name of ECS Service to restart'
)
def redeploy_service(cluster, service_name):
    click.secho(
        'Forcing redeployment of {}:{}'.format(cluster, service_name),
        fg='green'
    )
    client = boto3.client('ecs')
    services = client.list_services(maxResults=100,
                                    cluster=cluster)['serviceArns']
    try:
        service = list(filter(lambda i: service_name in i, services))[0]
    except IndexError:
        available = '\n    - '.join(
            [f.split('/')[1].split('-')[1] for f in services]
        )
        raise click.UsageError(
            "Service '{}' not found. Available services:\n    - {}".format(
                service, available)
        )
    client.update_service(
        cluster=cluster,
        service=service,
        forceNewDeployment=True
    )
    click.secho('Waiting for service to become stable...', fg='green')
    waiter = client.get_waiter('services_stable')
    waiter.wait(
        cluster=cluster,
        services=[service]
    )
    click.secho('Service Redeployed', fg='green')
