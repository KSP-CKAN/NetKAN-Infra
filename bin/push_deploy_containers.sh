#!/bin/bash

docker tag "kspckan/indexer" "kspckan/indexer:latest"
docker tag "kspckan/scheduler" "kspckan/indexer:scheduler"
docker push "kspckan/indexer:latest"
docker push "kspckan/scheduler:latest"
