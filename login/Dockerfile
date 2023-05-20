FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install jinja2
RUN pip install opentracing jaeger-client
RUN pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger
COPY . .
EXPOSE 5000

CMD ["python", "app.py"]