#!/bin/bash

rm -rf build && mkdir build

cp ./*.py build/

pip install requests beautifulsoup4 -t build/

cd build
zip -r ../function.zip .
cd ..

aws lambda update-function-code \
  --function-name openjdk-mail-db-updater \
  --zip-file fileb://function.zip \
  --region us-west-1