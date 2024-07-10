FROM python:3.10.9-alpine
ENV PYTHONUNBUFFERED 1
ENV GIT_PYTHON_REFRESH=quiet

WORKDIR /usr/src/puzzup

RUN pip install --upgrade pip
RUN pip install poetry
RUN poetry config virtualenvs.create false
COPY pyproject.toml poetry.lock ./
RUN poetry install
