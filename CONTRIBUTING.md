# Contributing to DT-RAM

Thank you for contributing to the **Digital-Twin-Assisted Resource Management (DT-RAM)** project.

## Development Workflow & Environment Setup

### 1. Repository Hygiene & Git Rules
- Ensure you do not commit confidential information (`.env`, secrets, credentials) or large binary artifacts (`node_modules/`, virtual environments, dataset dumps, model checkpoints `*.pt`).
- Always verify your staging status with `git status` before committing.
- Commit messages should be concise, semantic, and describe what the change achieves.

### 2. Python Services (Prediction, RL, Simulation, Safety)
To prevent dependency pollution and ensure cross-platform reproducibility:
1. **Always use a dedicated virtual environment:**
   ```bash
   # Linux/macOS
   python3 -m venv venv
   source venv/bin/activate

   # Windows PowerShell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
2. **Install dependencies strictly via pip3:**
   ```bash
   pip3 install --upgrade pip
   pip3 install -r requirements.txt
   ```
3. **Freeze new dependencies:**
   When adding packages, update `requirements.txt`:
   ```bash
   pip3 freeze > requirements.txt
   ```

### 3. Node.js Services (API Gateway, Experiment Service)
- Node.js >= 18.x and npm >= 9.x required.
- Install dependencies inside each service folder:
  ```bash
  cd services/<service-name>
  npm install
  ```

### 4. Go Services (Infrastructure Controller, Telemetry Agent, Twin Manager)
- Go >= 1.21 required.
- Synchronize and tidy modules:
  ```bash
  cd services/<service-name>
  go mod tidy
  ```

## Branching & Pull Requests
1. Create a descriptive feature or bugfix branch: `feature/<component-name>` or `fix/<issue-name>`.
2. Open a Pull Request using the repository PR template.
3. Ensure all tests and lint checks pass before requesting reviews from code owners.
