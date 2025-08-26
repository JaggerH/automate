# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is "Automate" - a process injection-based extractor for automatic cookie and data extraction from web services like NetEase Cloud Music and Quark Cloud Storage. It uses mitmproxy's process injection capabilities to intercept HTTP traffic from target applications and extract authentication cookies automatically.

## Rules

Before creating or modifying a function, first clarify:

Objective – what the function is supposed to achieve.

Inputs and outputs – the expected parameters and return values.

Based on the file path, for example:
```
src/extractors/base_extractor.py
```
the corresponding test file should be:
```
src/tests/extractors/base_extractor.py
```
Generate unit test cases for the function to be modified. The test functions should be named as:
```
test_<function_name>
```
## Common Commands

### Environment Setup
```bash
# Create conda environment
conda env create -f environment.yaml
conda activate automate

# Or install with pip
pip install -r requirements.txt

```

### Running the Application
```bash
conda activate automate

# Start process injection (one-time mode)
python main.py

# Start daemon mode - continuous process monitoring
python main.py --daemon

# Start daemon mode with silent output
python main.py --daemon --silent

# Show status and statistics
python main.py --status

# Clean up old session data (>7 days)
python main.py --cleanup

```

### Development & Testing
```bash
# Reproduce flows from debug data
python -m src.utils.flow_reproducer "data\debug"

# Run specific tests (using unittest module)
python -m unittest tests.extractors.test_netease_playlist_extractor -v

# For conda environment testing
call conda activate automate
C:/Users/Jagger/anaconda3/envs/automate/python.exe -m unittest tests.extractors.test_netease_playlist_extractor -v
```

## Architecture Overview

### Core Components

**Process Injection System (`src/core/process_inject.py`)**
- Main mitmproxy addon that handles process injection mode
- Detects target processes (cloudmusic.exe, QuarkCloudDrive.exe) using psutil
- Routes traffic to appropriate extractors based on domain matching
- Supports both daemon and one-time execution modes

**Extractors Framework (`src/extractors/`)**
- `BaseExtractor`: Abstract base class for service-specific cookie extractors
- `QuarkExtractor`: Quark Cloud Storage cookie extraction logic  
- Each extractor handles domain-specific cookie formats and timing constraints
- Extractors process both request and response phases

**Configuration System**
- `config/services.yaml`: Service definitions, domains, extraction intervals, output paths, and feature toggles
- `src/utils/config_loader.py`: Centralized configuration management with hot reload
- `config/logging.yaml`: Logging configuration (if exists)
- Configuration supports per-service process name mapping and feature flags

**Data Management (`src/core/csv_manager.py`)**
- Tracks extraction status and timestamps per service
- Manages proxy session logs and statistics
- Implements time-based extraction control (prevents excessive extraction)
- Stores data in `data/extraction_status.csv` and `data/proxy_sessions.csv`

### Process Injection Flow
```
[Target Process] → [mitmproxy PID injection] → [ProcessInject Addon]
                              ↓
                    [Domain-based Routing]
                              ↓
                  [Service-specific Extractors]
                              ↓
                    [Cookie & Data Extraction]
                              ↓
                      [Save to JSON files]
```

### Key Features

**Selective Processing**: Only intercepts traffic to configured domains (e.g., music.163.com), other requests pass through transparently.

**Time-Based Extraction**: Prevents excessive cookie extraction using configurable intervals (e.g., every 5 minutes for NetEase).

**Process Detection**: Automatically detects target processes using psutil and supports daemon mode for continuous monitoring.

**Output Compatibility**: NetEase cookies saved in `data/outputs/netease/cookies/` directory with structured JSON format.

## Configuration

### Key Configuration Files

**`config/services.yaml`**: Defines which services to monitor
- Enable/disable services
- Domain lists for traffic filtering  
- Cookie extraction intervals
- Output file paths and formats

**`config/logging.yaml`**: Logging configuration (if exists)
- Log levels and formats for different components
- Console and file output settings

### Output Files Structure
- **NetEase Cookies**: `data/outputs/netease/cookie.json` (standard format)
- **NetEase Playlists**: `data/outputs/netease/playlists/` (JSON files per playlist)
- **Quark**: `data/outputs/quark/cookie.json` (standard format)
- **Status**: `data/extraction_status.csv` (service status tracking)
- **Sessions**: `data/proxy_sessions.csv` (proxy session logs)
- **Debug Data**: `data/debug/` (request/response captures for troubleshooting)

## Adding New Services

1. Create new extractor in `src/extractors/` inheriting from `BaseExtractor`
2. Implement `handle_request()` and `handle_response()` methods
3. Add service configuration in `config/services.yaml` with domains and features
4. Register extractor in `ProcessInject._init_extractors()` method
5. Add process name mapping in service config if needed

## Windows-Specific Notes

- UTF-8 encoding is explicitly configured for Windows console compatibility
- Batch files provided for common operations with proper encoding
- Certificate storage in `temp_certs/` directory for SSL interception
- Uses `chcp 65001` for proper Chinese character display

## Development Environment

- Python 3.8+ required (configured for 3.11 in environment.yaml)
- Primary dependency: mitmproxy 10.2.2 for HTTP interception and process injection
- Windows-optimized with proper UTF-8 encoding support
- Testing uses unittest module and flow reproduction utilities
- Debug data capture in `data/debug/` for flow analysis and reproduction

## Flow Reproduction for Debugging

The project includes a flow reproduction system for debugging extraction issues:

```bash
# Reproduce specific flows from debug data
python -m src.utils.flow_reproducer "data\debug"
```

**Flow Reproducer (`src/utils/flow_reproducer.py`)**
- Recreates HTTPFlow objects from captured JSON debug data
- Allows testing extraction logic without running live traffic
- Useful for debugging specific request/response patterns
- Supports batch processing of debug files