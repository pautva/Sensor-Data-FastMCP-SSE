# MCP Server Setup Guide

This project provides a FastMCP server that can be run in different modes depending on your target application.

## 🚀 Quick Start

### For Desktop MCP Clients (Claude Desktop, etc.)

Run the server directly for native MCP protocol communication:

```bash
python server/main.py
```

**Use this when:**
- Integrating with Claude Desktop
- Using other MCP-compatible desktop applications
- You need direct stdio/native MCP transport

### For Web Applications (Open WebUI, etc.)

Run the server with MCPO wrapper for HTTP-based communication:

```bash
uvx mcpo --port 8000 -- fastmcp run server/main.py
```

**Use this when:**
- Integrating with Open WebUI or other web applications
- You need HTTP REST API access to your MCP server
- Running in containerized or cloud environments

**Access your server at:** `http://localhost:8000`

## 📦 Desktop Extension (DXT) Packaging

For distributing your MCP server as a desktop extension, use Anthropic's DXT toolkit:

### Installation
```bash
npm install -g @anthropic-ai/dxt
```

### Package Your Server
```bash
dxt init
dxt pack
```

**Learn more:** [Desktop Extensions Documentation](https://www.anthropic.com/engineering/desktop-extensions)

## 🔧 Configuration

### Desktop Integration
Add your server configuration to your MCP client's settings (e.g., Claude Desktop's `claude_desktop_config.json`).

### Web Integration
Configure your web application to connect to `http://localhost:8000` (or your chosen port).

## 📋 Requirements

- Python 3.8+
- FastMCP framework
- For web deployment: `uvx` and `mcpo`
- For desktop packaging: Node.js and `@anthropic-ai/dxt`