#!/bin/bash

set -e

cd /root/backup

# Load FTP credentials
set -a
source /root/backup/.env
set +a

# Prevent simultaneous backup processes
exec /usr/bin/flock -n /root/backup/backup.lock \
    /usr/bin/python36 /root/backup/backup.py