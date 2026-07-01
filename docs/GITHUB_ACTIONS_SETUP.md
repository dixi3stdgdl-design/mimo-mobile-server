# MiMo Mobile Server - GitHub Actions Setup

## Quick Start

```bash
# 1. Create workflows directory
mkdir -p .github/workflows

# 2. Copy workflow files
cp docs/workflows/*.yml .github/workflows/

# 3. Commit
git add .github/
git commit -m "ci: setup GitHub Actions workflows"

# 4. Push
git push origin main
```

## Workflow Triggers

### CI Workflow (ci.yml)
- **On push to**: main, develop
- **On PR to**: main, develop
- **Files monitored**: server.py, tests/**, workflows
- **Runs**:
  - Python linting (3.10, 3.11, 3.12, 3.13)
  - Unit tests
  - Coverage reports
  - Security scans

### Docker Workflow (docker.yml)
- **On push to**: main, tags (v*)
- **On workflow_dispatch**: Manual trigger
- **Builds & Pushes**:
  - Docker Hub: `dixi3stdgdl-design/mimo-server`
  - GHCR: `ghcr.io/dixi3stdgdl-design/mimo-mobile-server`

### Release Workflow (release.yml)
- **On push tags**: v* (e.g., v2.0.0)
- **On workflow_dispatch**: Manual trigger with version input
- **Creates**: GitHub Release with changelog
- **Uploads**: Source code artifacts

## Required Secrets

Add these secrets to GitHub (Settings > Secrets and variables > Actions):

| Secret | Value | Required |
|--------|-------|----------|
| `DOCKER_USERNAME` | Docker Hub username | Optional* |
| `DOCKER_PASSWORD` | Docker Hub token | Optional* |
| `GITHUB_TOKEN` | Auto-provided | ✅ |

*Docker Hub credentials are optional. If not provided, Docker workflow will skip Docker Hub push.

## Setup Instructions

### 1. Create Workflows

Copy the YAML files to `.github/workflows/`:

```bash
mkdir -p .github/workflows
cp .github/workflows/*.yml .github/workflows/
git add .github/
git commit -m "ci: add GitHub Actions workflows"
git push
```

### 2. Add Docker Hub Secrets (Optional)

```bash
# Get Docker Hub token: https://hub.docker.com/settings/security
gh secret set DOCKER_USERNAME --body "your-docker-username"
gh secret set DOCKER_PASSWORD --body "your-docker-token"
```

### 3. Verify Workflows

```bash
gh workflow list
gh workflow view ci.yml
gh workflow view docker.yml
```

### 4. Manual Triggers (Optional)

```bash
# Trigger CI
gh workflow run ci.yml --ref main

# Trigger Docker build
gh workflow run docker.yml --ref main

# Trigger release
gh workflow run release.yml --ref main -f version=v2.0.0
```

## Viewing Results

### GitHub UI
1. Go to repository
2. Click "Actions" tab
3. Select workflow
4. View job logs

### CLI
```bash
# List recent runs
gh run list

# View specific run
gh run view <run-id> --log

# View workflow
gh workflow view ci.yml --all
```

## Troubleshooting

### Workflow not triggering

```bash
# Check branch protection rules
# (Settings > Branches > Branch protection rules)

# Ensure workflow file is valid YAML
yaml-lint .github/workflows/ci.yml

# Check path filters
# Workflow only runs if matching paths changed
```

### Tests failing

```bash
# Run tests locally first
python3 -m pytest tests/ -v

# Check Python version
python3 --version

# Install test dependencies
pip install pytest pytest-cov pytest-asyncio
```

### Docker build failing

```bash
# Build locally
docker build -t mimo-server:test .

# Check Dockerfile syntax
dockerfile-lint Dockerfile

# View build logs
git push && gh run watch  # Watch workflow run
```

## Status Badges

Add to README.md:

```markdown
[![CI Status](https://github.com/dixi3stdgdl-design/mimo-mobile-server/actions/workflows/ci.yml/badge.svg)](https://github.com/dixi3stdgdl-design/mimo-mobile-server/actions/workflows/ci.yml)

[![Docker Build](https://github.com/dixi3stdgdl-design/mimo-mobile-server/actions/workflows/docker.yml/badge.svg)](https://github.com/dixi3stdgdl-design/mimo-mobile-server/actions/workflows/docker.yml)

[![Latest Release](https://img.shields.io/github/v/release/dixi3stdgdl-design/mimo-mobile-server?style=flat-square)](https://github.com/dixi3stdgdl-design/mimo-mobile-server/releases)
```

## Best Practices

### ✅ DO
- Commit workflow files to main branch
- Use `permissions` to limit scope
- Cache dependencies (pip, docker layers)
- Matrix test across Python versions
- Use semantic versioning for tags (v2.0.0)
- Add branch protection rules

### ❌ DON'T
- Store secrets in workflow files
- Use `ubuntu-latest` without specifying version
- Run `pip install` without cache
- Deploy without passing tests
- Force push to main (creates incomplete workflows)

## Advanced Configuration

### Skip CI for specific commits

```bash
git commit -m "docs: update README [skip ci]"
```

### Require CI to pass before merge

Settings > Branch protection rules > Require status checks to pass

### Auto-format code on PR

Add to ci.yml:
```yaml
- name: Auto-format with black
  run: black server.py
  
- name: Commit changes
  run: |
    git config user.name "GitHub Actions"
    git config user.email "actions@github.com"
    git add .
    git commit -m "style: auto-format with black" || true
    git push
```

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Secrets Management](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [act - Run workflows locally](https://github.com/nektos/act)
