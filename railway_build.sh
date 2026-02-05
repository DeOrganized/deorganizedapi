#!/bin/bash

# Railway build script
python manage.py collectstatic --noinput
python manage.py migrate --noinput
