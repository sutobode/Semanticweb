FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY sparql ./sparql
COPY ontology ./ontology
RUN pip install --no-cache-dir \
      rdflib==7.1.3 \
      requests==2.32.3 \
    && pip install --no-cache-dir --no-deps -e .

EXPOSE 8000
CMD ["python", "-m", "vietheritage.web.server"]
