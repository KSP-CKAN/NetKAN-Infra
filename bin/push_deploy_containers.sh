#!/bin/bash

# Indexer
docker tag "kspckan/netkan" "kspckan/netkan:latest"
docker push "kspckan/netkan:latest"

# Webhooks Proxy
docker pull "kspckan/webhooks-proxy" || true
docker build nginx/. -t kspckan/webhooks-proxy
docker tag "kspckan/webhooks-proxy" "kspckan/webhooks-proxy:latest"
docker push "kspckan/webhooks-proxy:latest"

# Restart Services
docker run \
	-e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
	-e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
	-e AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION" \
	"kspckan/netkan" redeploy-service --cluster \
	NetKANCluster --service-name Indexer
docker run \
	-e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
	-e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
	-e AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION" \
	"kspckan/netkan" redeploy-service --cluster \
	NetKANCluster --service-name Webhooks
docker run \
	-e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
	-e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
	-e AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION" \
	"kspckan/netkan" redeploy-service --cluster \
	NetKANCluster --service-name Adder
docker run \
	-e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
	-e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
	-e AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION" \
	"kspckan/netkan" redeploy-service --cluster \
	NetKANCluster --service-name Mirrorer
