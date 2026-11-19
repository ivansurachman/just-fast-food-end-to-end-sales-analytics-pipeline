#!/bin/sh
# Create the two buckets the pipeline expects. Safe to run more than once:
# s3.bucket.create on an existing bucket reports it and exits without failing
# the script. Run as a one-shot container after SeaweedFS is healthy.
set -eu

master="${WEED_MASTER:-seaweedfs:9333}"
filer="${WEED_FILER:-seaweedfs:8888}"

existing=$(printf 's3.bucket.list\n' | weed shell -master="${master}" -filer="${filer}")

for bucket in jff-raw jff-lake; do
  if printf '%s\n' "${existing}" | grep -Eq "(^|[[:space:]])${bucket}([[:space:]]|$)"; then
    echo "bucket ${bucket} already exists"
  else
    printf 's3.bucket.create -name %s\n' "${bucket}" | weed shell -master="${master}" -filer="${filer}"
  fi
done

printf 's3.bucket.list\n' | weed shell -master="${master}" -filer="${filer}"
