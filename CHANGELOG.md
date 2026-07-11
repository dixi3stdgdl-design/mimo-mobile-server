# Changelog

All notable changes to MiMo Mobile Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.0.0] - 2026-07-06

### Added
- Initial release — Python WebSocket server for MiMo Mobile
- HTTP ADB endpoints (`/api/adb/devices`, `/api/adb/exec`, `/api/adb/connect`) with CORS support
- Host ADB binary mounting in Docker container
- Docker + GHCR deployment workflow
- Structured logging and Prometheus metrics
- Watchdog crash safety and port conflict handling
- Comprehensive testing suite and docker-compose for development
- GitHub Actions CI/CD pipelines
