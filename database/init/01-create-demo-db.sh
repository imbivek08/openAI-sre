#!/bin/bash
set -e
psql -U opensre -d opensre -c "CREATE DATABASE opensre_demo;" 2>/dev/null || true
