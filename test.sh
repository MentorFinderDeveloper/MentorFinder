#!/bin/sh
set -e

export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-test-django-secret-key-0123456789abcdefghijklmnopqrstuvwxyz}"
export DJANGO_SECURE_SSL_REDIRECT="${DJANGO_SECURE_SSL_REDIRECT:-false}"
export DISABLE_DJANGO_SCHEDULER="${DISABLE_DJANGO_SCHEDULER:-true}"
mkdir -p xunit-reports coverage-reports

coverage run --source . -m pytest --junit-xml=xunit-reports/xunit-result.xml
ret=$?
coverage xml -o coverage-reports/coverage.xml
coverage report
exit $ret
