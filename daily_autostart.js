#!/usr/bin/env node
/**
 * Daily Auto-Start Launcher
 * Sets up macOS launchd for 6AM auto-start and runs daily maintenance
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = __dirname;
const PLIST_SOURCE = path.join(PROJECT_ROOT, 'com.volt-records.omni-studio.plist');
const PLIST_DEST = path.join(process.env.HOME, 'Library', 'LaunchAgents', 'com.volt-records.omni-studio.plist');
const LOG_DIR = path.join(PROJECT_ROOT, 'logs');

function log(msg) {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] ${msg}\n`;
  fs.appendFileSync(path.join(LOG_DIR, 'daily_autostart.log'), line);
  console.log(line.trim());
}

function runCommand(cmd, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { 
      cwd: PROJECT_ROOT, 
      stdio: ['ignore', 'pipe', 'pipe'],
      ...options 
    });
    
    let stdout = '', stderr = '';
    child.stdout.on('data', d => stdout += d.toString());
    child.stderr.on('data', d => stderr += d.toString());
    
    child.on('close', code => {
      if (code === 0) resolve(stdout);
      else reject(new Error(`${cmd} failed (${code}): ${stderr || stdout}`));
    });
  });
}

async function installLaunchAgent() {
  log('Installing launchd agent...');
  
  // Read and update plist with correct paths
  let plist = fs.readFileSync(PLIST_SOURCE, 'utf8');
  plist = plist.replace(/\/Users\/mtb\/pinokio\/api\/omni-studio/g, PROJECT_ROOT);
  fs.writeFileSync(PLIST_DEST, plist);
  
  // Load the agent
  await runCommand('launchctl', ['load', '-w', PLIST_DEST]);
  log('✅ LaunchAgent installed and loaded');
}

async function uninstallLaunchAgent() {
  log('Uninstalling launchd agent...');
  try {
    await runCommand('launchctl', ['unload', '-w', PLIST_DEST]);
    if (fs.existsSync(PLIST_DEST)) fs.unlinkSync(PLIST_DEST);
    log('✅ LaunchAgent uninstalled');
  } catch (e) {
    log(`Note: ${e.message}`);
  }
}

async function runDailyMaintenance() {
  log('Running daily maintenance...');
  
  // 1. Run disk cleaner via dashboard API
  try {
    await runCommand('curl', ['-X', 'POST', 'http://127.0.0.1:8500/api/cleaner/run']);
    log('✅ Disk cleaner triggered');
  } catch (e) {
    log(`Disk cleaner: ${e.message} (dashboard may not be running)`);
  }
  
  // 2. Scan music library for new samples
  try {
    await runCommand('curl', ['-X', 'POST', 'http://127.0.0.1:8500/api/samples/scan']);
    log('✅ Sample library scan triggered');
  } catch (e) {
    log(`Sample scan: ${e.message}`);
  }
  
  // 3. Run Kimi Daily extraction if transcripts exist
  // (would check for new transcripts in ingest folder)
  
  log('Daily maintenance complete');
}

async function enableAutostart() {
  log('=== ENABLING DAILY AUTO-START ===');
  await installLaunchAgent();
  log('✅ Omni Studio will auto-start at 6:00 AM daily');
  log('📋 LaunchAgent: ~/Library/LaunchAgents/com.volt-records.omni-studio.plist');
}

async function disableAutostart() {
  log('=== DISABLING DAILY AUTO-START ===');
  await uninstallLaunchAgent();
  log('✅ Auto-start disabled');
}

async function runNow() {
  log('=== MANUAL DAILY START ===');
  await runDailyMaintenance();
  log('Use "Start" button in UI to launch the studio');
}

async function main() {
  const action = process.argv[2] || 'enable';
  
  switch (action) {
    case 'enable':
      await enableAutostart();
      break;
    case 'disable':
      await disableAutostart();
      break;
    case 'run':
      await runNow();
      break;
    case 'maintenance':
      await runDailyMaintenance();
      break;
    default:
      console.log('Usage: node daily_autostart.js [enable|disable|run|maintenance]');
  }
}

if (require.main === module) {
  main().catch(err => {
    log(`FATAL: ${err.message}`);
    process.exit(1);
  });
}

module.exports = { installLaunchAgent, uninstallLaunchAgent, runDailyMaintenance };