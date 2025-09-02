#!/bin/bash

aws s3 cp index.html s3://barlasgarden/openjdk.html --region us-west-1

aws s3 cp index.html s3://barlasgarden/openjdk/index.html --region us-west-1
aws s3 cp favicon.ico s3://barlasgarden/openjdk/favicon.ico --region us-west-1
aws s3 cp favicon.svg s3://barlasgarden/openjdk/favicon.svg --region us-west-1

aws cloudfront create-invalidation \
--distribution-id E55WEWI99JZUV \
--paths /openjdk.html

aws cloudfront create-invalidation \
--distribution-id E2P5D8BHEG1CMT \
--paths /index.html