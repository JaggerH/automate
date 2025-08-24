# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is "Automate" - an intelligent proxy service for automatic cookie extraction from web services like NetEase Cloud Music and Quark Cloud Storage. It operates as a chain proxy that can integrate with upstream proxies like Clash, intercepting HTTP traffic to extract authentication cookies automatically.

## Common Commands

### Environment Setup
```bash
# Create conda environment
conda env create -f environment.yaml
conda activate automate

# Or install with pip
pip install -r requirements.txt

# Install HTTPS-specific dependencies (Windows)
install_https_deps.bat
```

### Running the Application
```bash
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

# Windows batch file helpers
start_daemon.bat          # Start daemon mode with UI
start_daemon_silent.bat   # Start daemon mode silently

# Debug mode with verbose cookie logging
start_debug.bat
# Or directly: python debug_proxy.py

# Run with UTF-8 encoding (Windows helper)
run_utf8.bat python main.py
```

### Development & Testing
```bash
# Test proxy functionality
python test_proxy.py

# Test specific genius proxy features
python start_genius_proxy.py
```

## Architecture Overview

### Core Components

**Smart Chain Proxy (`src/core/smart_proxy.py`)**
- Main mitmproxy addon that handles HTTP traffic interception
- Manages upstream proxy detection and routing
- Coordinates cookie extraction across different services
- Implements selective filtering - only processes configured domains

**Upstream Detection (`src/core/upstream_detector.py`)**
- Auto-detects running Clash or other proxy services
- Implements fallback to direct connection if upstream unavailable
- Supports multiple upstream ports and protocols (HTTP/SOCKS5)

**Extractors Framework (`src/extractors/`)**
- `BaseExtractor`: Abstract base class for service-specific cookie extractors
- `NeteaseExtractor`: NetEase Cloud Music cookie extraction logic
- `QuarkExtractor`: Quark Cloud Storage cookie extraction logic
- Each extractor handles domain-specific cookie formats and timing constraints

**Configuration System**
- `config/proxy_config.yaml`: Proxy settings, upstream detection, performance tuning
- `config/services.yaml`: Service definitions, domains, extraction intervals, output paths
- `src/utils/config_loader.py`: Centralized configuration management with hot reload

**Data Management (`src/core/csv_manager.py`)**
- Tracks extraction status and timestamps per service
- Manages proxy session logs and statistics
- Implements time-based extraction control (prevents excessive extraction)
- Stores data in `data/extraction_status.csv` and `data/proxy_sessions.csv`

### Traffic Flow
```
[Client App] → [Automate:8080] → [Upstream Proxy:7897] → [Target Server]
                     ↓                    ↓
               Cookie Extraction    Rule-based Routing
                     ↓
             Save to JSON files
```

### Key Features

**Selective Processing**: Only intercepts traffic to configured domains (e.g., music.163.com), other requests pass through transparently.

**Time-Based Extraction**: Prevents excessive cookie extraction using configurable intervals (e.g., every 5 minutes for NetEase).

**Chain Proxy Integration**: Automatically detects and chains with Clash or other upstream proxies for seamless integration with existing proxy setups.

**Output Compatibility**: NetEase cookies saved in `../music-sync/config/auto_cookie.json` format for integration with music-sync project.

## Configuration

### Key Configuration Files

**`config/services.yaml`**: Defines which services to monitor
- Enable/disable services
- Domain lists for traffic filtering  
- Cookie extraction intervals
- Output file paths and formats

**`config/proxy_config.yaml`**: Proxy behavior settings
- Listen ports (8080 with fallbacks 8081-8083)
- Upstream proxy detection ports (7897-7899)
- Performance tuning (timeouts, concurrency)
- SSL certificate handling

### Output Files Structure
- **NetEase**: `../music-sync/config/auto_cookie.json` (music-sync compatible format)
- **Quark**: `data/outputs/quark_cookie.json` (standard format)
- **Status**: `data/extraction_status.csv` (service status tracking)
- **Sessions**: `data/proxy_sessions.csv` (proxy session logs)

## Adding New Services

1. Create new extractor in `src/extractors/` inheriting from `BaseExtractor`
2. Implement `extract_from_request()` and `extract_from_response()` methods
3. Add service configuration in `config/services.yaml`
4. Register extractor in `SmartChainProxy._init_extractors()` method

## Windows-Specific Notes

- UTF-8 encoding is explicitly configured for Windows console compatibility
- Batch files provided for common operations with proper encoding
- Certificate storage in `temp_certs/` directory for SSL interception
- Uses `chcp 65001` for proper Chinese character display

## Development Environment

- Python 3.8+ required (configured for 3.11 in environment.yaml)
- Primary dependency: mitmproxy 10.2.2 for HTTP interception
- Windows-optimized with batch file launchers
- No traditional test framework - uses direct execution scripts for testing