FROM python:3.10-slim
WORKDIR /app
COPY Decision/requirements.txt ./Decision/requirements.txt
RUN pip install --no-cache-dir -r Decision/requirements.txt
COPY Decision/. ./Decision/
COPY Control/tools.json ./Control/tools.json
EXPOSE 8000
ENV PYTHONPATH=/app/Decision
CMD ["uvicorn", "Decision.main:app", "--host", "0.0.0.0", "--port", "8000"]