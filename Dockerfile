FROM python:3.9.18
ENV PYTHONUNBUFFERED 1

WORKDIR /usr/src/puzzup

RUN pip install --upgrade pip
RUN pip install poetry
RUN poetry config virtualenvs.create false
COPY pyproject.toml poetry.lock ./
RUN poetry install
