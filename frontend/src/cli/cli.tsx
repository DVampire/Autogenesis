#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';

import { App } from './App.js';

function parseArgs(argv: string[]) {
  const options: { configPath?: string; connectUrl?: string; token?: string; workspace?: string } = {};
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--config') options.configPath = argv[++index];
    else if (value === '--workspace') options.workspace = argv[++index];
    else if (value === '--connect') options.connectUrl = argv[++index];
    else if (value === '--token') options.token = argv[++index];
    else if (value === '--help' || value === '-h') {
      process.stdout.write('Usage: autogenesis [--workspace path] [--config path] [--connect ws://host/ws] [--token token]\n');
      process.exit(0);
    }
  }
  return options;
}

render(<App options={parseArgs(process.argv.slice(2))} />);
