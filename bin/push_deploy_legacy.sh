#!/bin/bash

# Legacy Webhooks
docker pull "kspckan/webhooks" || true
docker build webhooks/. -t kspckan/webhooks
docker tag "kspckan/webhooks" "kspckan/webhooks:latest"
docker push "kspckan/webhooks:latest"

