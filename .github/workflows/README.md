# GitHub Actions CI/CD Workflows for MiMo Mobile Server

## Workflows Overview

This directory contains GitHub Actions workflows for:
- Continuous Integration (testing, linting)
- Continuous Deployment (Docker builds, releases)
- Code quality analysis
- Security scanning

## Workflow Files

### 1. `ci.yml` - Continuous Integration

**Triggers**: Push to main/develop, Pull Requests

**Jobs**:
- Python linting (pylint, black)
- Unit tests (pytest)
- Code coverage report
- Security scan (bandit)

### 2. `docker.yml` - Docker Build & Push

**Triggers**: Push to main, Git tags (v*)

**Jobs**:
- Build Docker image
- Push to Docker Hub
- Push to GitHub Container Registry

### 3. `release.yml` - Release Automation

**Triggers**: Git tags (v*)

**Jobs**:
- Create GitHub Release
- Generate changelog
- Attach artifacts

## Local Testing

```bash
# Run CI locally with act
act push -j test
act push -j lint
act push -j docker
```

## Configuration

Secrets needed in GitHub:
- `DOCKER_USERNAME`: Docker Hub username
- `DOCKER_PASSWORD`: Docker Hub token
- `GITHUB_TOKEN`: Auto-provided by GitHub Actions

## Manual Triggers

Workflows can be triggered manually from GitHub Actions tab or via CLI:

```bash
gh workflow run ci.yml --ref main
gh workflow run docker.yml --ref main
gh workflow run release.yml --ref v2.0.0
```
