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

# Install MongoDB locally in the container
RUN apt-get update && \
    apt-get install -y mongodb && \
    mkdir -p /data/db

# Set environment
WORKDIR /app
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Start MongoDB in the background, then run your FastAPI app
CMD mongod --fork --logpath /var/log/mongodb.log && uvicorn main:app --host 0.0.0.0 --port 7860
