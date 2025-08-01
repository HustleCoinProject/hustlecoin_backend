# Use the official Python 3.10.9 image
#FROM python:3.10.9

# Copy the current directory contents into the container at .
#COPY . .

# Set the working directory to /
#WORKDIR /

# Install requirements.txt 
#RUN pip install --no-cache-dir --upgrade -r /requirements.txt

# Start the FastAPI app on port 7860, the default port expected by Spaces
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]




# --- new below
FROM python:3.10

# Install dependencies for MongoDB repo
RUN apt-get update && \
    apt-get install -y gnupg curl

# Add MongoDB GPG key and repo
RUN curl -fsSL https://pgp.mongodb.com/server-6.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-6.0.gpg && \
    echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/6.0 main" | tee /etc/apt/sources.list.d/mongodb-org-6.0.list

# Install MongoDB
RUN apt-get update && \
    apt-get install -y mongodb-org && \
    mkdir -p /data/db

# Set working directory
WORKDIR /app
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Start MongoDB in background and launch FastAPI
CMD mongod --fork --logpath /var/log/mongodb.log && uvicorn app:app --host 0.0.0.0 --port 7860
