FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/cblm
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY module_builder/pyproject.toml ./
COPY module_builder/app ./app
RUN pip install --no-cache-dir .
COPY module_builder/templates ./templates
COPY module_builder/workflows ./workflows
COPY module_builder/template "/templates"
COPY launcher ./launcher
COPY saas ./saas
COPY ["CBLM_builder(non-quali)/cblm_app", "/cblm/cblm_app"]
COPY ["CBLM_builder(non-quali)/Templates", "/cblm/Templates"]
COPY ["CBLM_builder(non-quali)/Prompts.xlsx", "/cblm/Prompts.xlsx"]
COPY ["CBLM_builder(non-quali)/tests", "/cblm/tests"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 CMD curl -fsS http://localhost:8080/health || exit 1
CMD ["uvicorn", "launcher.main:app", "--host", "0.0.0.0", "--port", "8080"]
