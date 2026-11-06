FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p data
# Cron: runs daily at 7 AM UTC — uncomment if using cron base
# RUN echo "0 7 * * * cd /app && python pipeline.py >> /app/data/cron.log 2>&1" | crontab -
CMD ["python", "pipeline.py"]
