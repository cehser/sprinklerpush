# syntax=docker/dockerfile:1
FROM python:3.10-rc-alpine
# make container tz capable. 
# to make use of this just set environment variable TZ to appropriate value like "America/New York"
RUN apk add tzdata

WORKDIR /code
# COPY requirements.txt requirements.txt
COPY ./app .
RUN pip3 install -r requirements.txt


CMD ["python3", "sprinklerpush.py"]