#!/usr/bin/env node

/**
 * OpenClaw Simple Agent Test
 * 
 * Uses the OpenClaw CLI's built-in agent command which:
 * - Handles authentication internally
 * - Uses the configured gateway
 * - No dependency issues with dist chunks
 * - Works permanently and reliably
 */

const { execSync } = require('child_process');
const path = require('path');

const OPENCLAW_CLI = path.join(__dirname, 'node_modules', 'openclaw', 'openclaw.mjs');
const MESSAGE = 'What is the capital of India?';
const SESSION_ID = 'ts-demo-session';

async function connect() {
  try {
    console.log('🦞 OpenClaw Agent Test');
    console.log(`Sending message: "${MESSAGE}"`);
    console.log('');

    // Use the OpenClaw CLI agent command
    const command = `node "${OPENCLAW_CLI}" agent --message "${MESSAGE}" --session-id "${SESSION_ID}" --json --timeout 30`;
    
    const output = execSync(command, {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    // Parse the JSON response
    const response = JSON.parse(output);

    // Extract and display the agent's response
    if (response.result?.payloads?.[0]?.text) {
      console.log('--- AGENT RESPONSE ---');
      console.log(response.result.payloads[0].text);
      console.log('----------------------');
      
      if (response.result.meta?.durationMs) {
        console.log(`\nResponse time: ${response.result.meta.durationMs}ms`);
      }
      
      if (response.result.meta?.agentMeta?.model) {
        console.log(`Model: ${response.result.meta.agentMeta.model}`);
      }
    } else {
      console.error('No response text received');
      process.exit(1);
    }

  } catch (error) {
    const message = error.message || String(error);
    if (message.includes('credit balance')) {
      // Handle the specific case of low credits
      console.error('API Error: Low credit balance');
      console.error('Please go to Plans & Billing to upgrade or purchase credits');
    } else if (message.includes('ENOENT')) {
      console.error('Error: OpenClaw CLI not found at', OPENCLAW_CLI);
    } else {
      console.error('Error:', message);
    }
    process.exit(1);
  }
}

connect().catch(console.error);
