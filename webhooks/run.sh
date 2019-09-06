#!/bin/bash

mkdir -p .ssh
if [ ! -f ".ssh/id_rsa" ]; then
	echo "$SSH_KEY" > .ssh/id_rsa
	chmod 400 .ssh/id_rsa
fi

ssh-keyscan -t rsa github.com > .ssh/known_hosts

cat > .ksp-ckan << END_CONFIG
CKAN_meta=$CKAN_meta
NetKAN=$NetKAN
netkan_exe=https://ckan-travis.s3.amazonaws.com/netkan.exe
ckan_validate=https://raw.githubusercontent.com/KSP-CKAN/CKAN/master/bin/ckan-validate.py
ckan_schema=https://raw.githubusercontent.com/KSP-CKAN/CKAN/master/CKAN.schema
working=/home/netkan/CKAN-Webhooks
cache=/home/netkan/ckan_cache
GH_token=$GH_Token
IA_access=$IA_access
IA_secret=$IA_secret
IA_collection=$IA_collection
END_CONFIG

plackup -E production -s Twiggy /usr/local/bin/ckan-webhooks
