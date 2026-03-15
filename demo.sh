#!/bin/bash

# OpenClaw Demo - Send message via CLI
# Uses the built-in agent command which handles authentication internally

set -e

OPENCLAW_CLI="/home/jrf/openclaw/node_modules/openclaw/openclaw.mjs"
MESSAGE="${1:-What is the capital of India?}"

echo "🦞 Sending message to OpenClaw agent..."
echo "Message: $MESSAGE"
echo ""

# Call the agent command which automatically uses the configured gateway
# Using a consistent session ID for reproducible results
node "$OPENCLAW_CLI" agent --message "$MESSAGE" --session-id "demo-session" --json --timeout 30

echo ""
echo "✓ Done"
