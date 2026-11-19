#!/bin/sh
# Render the single SeaweedFS S3 identity from the container environment and
# start the all-in-one server (master, volume, filer, S3 gateway).
#
# Keep the credentials alphanumeric: they are written into a JSON document and
# SeaweedFS does not escape them.
set -eu

: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"

config=/tmp/s3.json
cat > "${config}" <<EOF
{
  "identities": [
    {
      "name": "jff",
      "credentials": [
        { "accessKey": "${S3_ACCESS_KEY}", "secretKey": "${S3_SECRET_KEY}" }
      ],
      "actions": ["Admin", "Read", "List", "Tagging", "Write"]
    }
  ]
}
EOF

exec weed server \
  -dir=/data \
  -s3 \
  -s3.port=8333 \
  -s3.config="${config}"
