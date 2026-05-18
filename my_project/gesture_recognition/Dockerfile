FROM python:3.12-slim

WORKDIR /app

# Copy only requirements first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code and assets
COPY . .

# Ensure the output directory exists
RUN mkdir -p image_sequence

CMD ["python","server.py"]