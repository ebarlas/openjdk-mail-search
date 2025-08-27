#!/bin/bash

aws s3 cp index.html s3://barlasgarden/openjdk.html --region us-west-1

aws cloudfront create-invalidation \
--distribution-id E55WEWI99JZUV \
--paths /openjdk.html