#!/usr/bin/env bash
cd /django-rq

ls -ld ../.. $PWD/*

python manage.py rqworker default