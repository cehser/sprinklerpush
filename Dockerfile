# syntax=docker/dockerfile:1
FROM python:3.7-alpine
WORKDIR /code
# COPY requirements.txt requirements.txt
COPY ./app .
RUN pip3 install -r requirements.txt

CMD ["python3", "sprinklerpush.py"]