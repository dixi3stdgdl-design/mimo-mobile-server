# Development mode (minimal)
cd mimo-mobile-server
docker-compose up mimo-server

# Full stack with database
docker-compose --profile with-db up

# With caching
docker-compose --profile with-cache up

# With reverse proxy
docker-compose --profile with-proxy up

# Full monitoring stack
docker-compose --profile monitoring up

# Everything
docker-compose --profile with-db --profile with-cache --profile with-proxy --profile monitoring up

# Detached mode
docker-compose up -d

# View logs
docker-compose logs -f mimo-server

# Stop all services
docker-compose down

# Clean up everything (data included)
docker-compose down -v
