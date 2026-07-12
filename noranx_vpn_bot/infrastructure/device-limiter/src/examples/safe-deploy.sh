#!/bin/bash
# Safe Deployment Script for Low-RAM Servers (1GB VPS)
# This script builds the binary locally using Docker and deploys it to the server

set -e

echo "🚀 Starting SAFE Deployment..."

# Configuration
SERVER_USER="${SERVER_USER:-root}"
SERVER_IP="${SERVER_IP:-your-server-ip}"
SERVER_PATH="${SERVER_PATH:-/root/marzban-device-limiter}"

# Step 1: Build binary using Docker (local machine)
echo "🔨 Building binary using Docker (golang:1.22-alpine)..."
docker run --rm \
    -v "$(pwd):/app" \
    -w /app \
    golang:1.22-alpine \
    sh -c "apk add --no-cache git && go build -ldflags='-s -w' -o device-limit ./cmd/device-limit"

if [ ! -f "device-limit" ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ Binary built successfully ($(du -h device-limit | cut -f1))"

# Step 2: Upload to server
echo "📤 Uploading to server..."
scp device-limit "${SERVER_USER}@${SERVER_IP}:${SERVER_PATH}/"
scp Dockerfile.release "${SERVER_USER}@${SERVER_IP}:${SERVER_PATH}/"
scp docker-compose.release.yml "${SERVER_USER}@${SERVER_IP}:${SERVER_PATH}/"

# Step 3: Start service on server
echo "🐳 Starting Docker container on server..."
ssh "${SERVER_USER}@${SERVER_IP}" "cd ${SERVER_PATH} && docker compose -f docker-compose.release.yml up -d --build"

# Cleanup local binary
rm -f device-limit

echo "🎉 Safe Deployment Complete!"
echo "Check status: ssh ${SERVER_USER}@${SERVER_IP} 'docker ps | grep marzban-device-limiter'"
