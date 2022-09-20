#!/bin/bash

set -x
set -e

cd /data

find /data /config /server -print

java /config/user_jvm_args.txt
