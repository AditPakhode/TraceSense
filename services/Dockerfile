FROM python:3.12-slim

ARG SERVICE_DIR

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

COPY services/common ./common
COPY services/${SERVICE_DIR}/app.py ./app.py

EXPOSE 8080

CMD ["python", "app.py"]

