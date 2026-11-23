#!/bin/sh
# Create the two buckets the pipeline expects. Safe to run more than once: creating a bucket that
# exists reports it and does not fail. Run as a one-shot container after SeaweedFS is healthy.
#
# The SeaweedFS healthcheck answers while the master is still campaigning for raft leadership, and in
# that window `weed shell` fails with "raft.Server: Not current leader" (seen on 23 Nov). Each call is
# therefore retried a few times before the container gives up.
set -eu

master="${WEED_MASTER:-seaweedfs:9333}"
filer="${WEED_FILER:-seaweedfs:8888}"
MAX_ATTEMPTS=5
RETRY_SLEEP_SECONDS=3

weed_shell() {
    command_text="${1}"
    attempt=0
    while true; do
        attempt=$((attempt + 1))
        if output=$(printf '%s\n' "${command_text}" | weed shell -master="${master}" -filer="${filer}" 2>&1); then
            printf '%s\n' "${output}"
            return 0
        fi
        if [ "${attempt}" -ge "${MAX_ATTEMPTS}" ]; then
            echo "weed shell failed after ${MAX_ATTEMPTS} attempts:" >&2
            printf '%s\n' "${output}" >&2
            return 1
        fi
        echo "weed shell attempt ${attempt} failed, retrying in ${RETRY_SLEEP_SECONDS}s" >&2
        sleep "${RETRY_SLEEP_SECONDS}"
    done
}

existing=$(weed_shell 's3.bucket.list')

for bucket in jff-raw jff-lake; do
    if printf '%s\n' "${existing}" | grep -Eq "(^|[[:space:]])${bucket}([[:space:]]|$)"; then
        echo "bucket ${bucket} already exists"
    else
        weed_shell "s3.bucket.create -name ${bucket}"
    fi
done

weed_shell 's3.bucket.list'
