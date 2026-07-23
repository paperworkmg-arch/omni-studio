#!/usr/bin/env node
/**
 * Proactive System Launcher
 * Runs the fully autonomous proactive system
 */

const { spawn } = require('child_process')
const path = require('path')

const SCRIPT_PATH = path.join(__dirname, 'app', 'omni-source', 'proactive_system.py')

const child = spawn('python3', [SCRIPT_PATH], {
  cwd: path.join(__dirname, 'app', 'omni-source'),
  stdio: 'inherit',
  env: {
    ...process.env,
    PYTHONPATH: path.join(__dirname, 'app', 'omni-source')
  }
})

child.on('error', (err) => {
  console.error('Failed to start proactive system:', err)
  process.exit(1)
})

child.on('close', (code) => {
  console.log(`Proactive system exited with code ${code}`)
  process.exit(code)
})

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down proactive system...')
  child.kill('SIGINT')
})

process.on('SIGTERM', () => {
  child.kill('SIGTERM')
})