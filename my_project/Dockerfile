# app/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy all files (including your static folder and app scripts)[cite: 1, 2, 3, 4]
COPY . .

RUN pip3 install --no-cache-dir -r requirements.txt

CMD [ "python", "server.py" ]