# NetKAN Infrastructure

The NetKAN Infrastructure Project is a re-write of the original monolithic NetKAN-bot, with the goal of easier maintenance, a faster code to deployment pipeline, infrastructure as code.

## Theory of operation

We use a modern microservice architecture to continuously index new mods and mod updates as the upstream mod files change. The microservices communicate via the AWS SQS system.

### Microservices

#### Inflator

The core of the system, it has the job to _inflate_ NetKAN metadata to CKAN metadata as described in the [Schema] and [Spec].

[Spec]: https://github.com/KSP-CKAN/CKAN/blob/master/Spec.md
[Schema]: https://github.com/KSP-CKAN/CKAN/blob/master/CKAN.schema

#### Indexer

The Indexer takes inflated metadata and, if the metadata is different to currently existing one, or entirely new, pushes it to the [metadata repository]. It also updates the status database.

[metadata repository]: https://github.com/KSP-CKAN/CKAN-meta

#### Scheduler

Every once in a while, the Scheduler kicks off and submits NetKAN metadata for the Inflator to work with.

#### Webhooks

The webhooks provide a web server that responds to messages from other hosts and services, usually by queueing a module to be inflated by the Inflator.

#### Download Counter

When started, it goes through the entire NetKAN metadata repository and collects the download counts for each of those mods, then commits them to the [metadata repository].

#### Status Page

The status page shows the current status of the inflation for each mod: Time of last inflation, time of last indexing, or errors that occurred during inflation. It accesses a DynamoDB database in the background.

### Containers

Container        | Image                  | Repo            | Code
---------------- | ---------------------- | --------------- | ----
Inflator         | kspckan/inflator       | CKAN            | [Netkan/Processors/QueueHandler.cs]
Scheduler        | kspckan/netkan         | NetKAN-Infra    | [netkan/netkan/scheduler.py]
Indexer          | kspckan/netkan         | NetKAN-Infra    | [netkan/netkan/indexer.py]
Download Counter | kspckan/netkan         | NetKAN-Infra    | [netkan/netkan/download_counter.py]
Status Dumper    | kspckan/netkan         | NetKAN-Infra    | [netkan/netkan/cli.py]
[Webhooks]       | kspckan/netkan         | NetKAN-Infra    | [netkan/netkan/webhooks]
Webhooks Proxy   | kspckan/webhooks-proxy | NetKAN-Infra    |
Cert Bot         | certbot/dns-route53    | certbot/certbot |

[Webhooks]: #Webhooks

[Netkan/Processors/QueueHandler.cs]: https://github.com/KSP-CKAN/CKAN/blob/master/Netkan/Processors/QueueHandler.cs
[netkan/netkan/scheduler.py]: https://github.com/KSP-CKAN/NetKAN-Infra/blob/master/netkan/netkan/scheduler.py
[netkan/netkan/indexer.py]: https://github.com/KSP-CKAN/NetKAN-Infra/blob/master/netkan/netkan/indexer.py
[netkan/netkan/download_counter.py]: https://github.com/KSP-CKAN/NetKAN-Infra/blob/master/netkan/netkan/download_counter.py
[netkan/netkan/cli.py]: https://github.com/KSP-CKAN/NetKAN-Infra/blob/master/netkan/netkan/cli.py
[netkan/netkan/webhooks]: https://github.com/KSP-CKAN/NetKAN-Infra/blob/master/netkan/netkan/webhooks

### Queues

The individual services communicate via Amazon's SQS (Simple Queue Service) system where needed. The Scheduler sends the netkans as SQS message to an SQS queue, where the Inflator picks them up and inflates them to ckan metadata. The Inflator again sends the resulting metadata via another queue to the Indexer.

#### Inbound.fifo

Message Attribute | Usage
----------------- | -----
Releases          | Number of releases to inflate, for modules with backports

Payload: JSON contents of .netkan to inflate

#### Outbound.fifo

Message Attribute | Usage
----------------- | -----
ModIdentifier     | The identifier of the module
Staged            | "true" to commit to new branch and submit a pull request
Success           | "true" if inflation succeeded, "false" if there was an error
CheckTime         | The datetime when the inflation happened, in ISO 8601 format
FileName          | Name of file to create or update, usually `identifier-version.ckan`
ErrorMessage      | Explanation of why inflation failed if Success is "false", omitted otherwise
StagingReason     | Body for pull request if Staged is "true", omitted otherwise

Payload: JSON contents of .ckan file to index

### Webhooks

The webhooks run on https://netkan.ksp-ckan.space/ and are firewalled to only a few servers that we know need to access them (so they're not going to work if you try them in your browser).

Route                     | Parameters                                          | Usage
------------------------- | --------------------------------------------------- | -----
/inflate                  | POST body: `{"identifiers": [ "Id1", "Id2", ... ]}` | Inflate the given modules (used by SpaceDock-Notify)
/sd/inflate               | POST form: `mod_id=1234&event_type=update`          | Inflate modules with the given SpaceDock ID
/gh/inflate               | See the [push API]                                  | Inflate modules after commits to NetKAN
/gh/release?identifier=Id | See the [release API]                               | Inflate a module when a new release is uploaded to GitHub

[push API]: https://developer.github.com/v3/activity/events/types/#pushevent
[release API]: https://developer.github.com/v3/activity/events/types/#releaseevent

## Developing

How to set up a local development environment

## References

- https://github.com/KSP-CKAN/CKAN/issues/2789
- https://hub.docker.com/u/kspckan
- https://hub.docker.com/r/kspckan/inflator

## Performing Updates

**Updating the Stack:**

```bash
aws cloudformation update-stack --stack-name DevQueues --template-body "`python dev-stack.py`" --capabilities CAPABILITY_IAM --profile ckan --region us-west-2
```
