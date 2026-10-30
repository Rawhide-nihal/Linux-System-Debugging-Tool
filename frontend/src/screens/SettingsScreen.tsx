import React, { useState, useEffect } from 'react';
import {
  Settings as SettingsIcon,
  Cpu,
  CheckCircle,
  XCircle,
  Shield,
  Sliders,
  Terminal,
  RefreshCw
} from 'lucide-react';
import { ToolchainInfo } from '../types';
import { api } from '../services/api';

interface SettingsScreenProps {
  toolchain: ToolchainInfo | null;
  onRefreshToolchain: () => void;
}

export const SettingsScreen: React.FC<SettingsScreenProps> = ({
  toolchain,
  onRefreshToolchain
}) => {
  const [cStandard, setCStandard] = useState('c11');
  const [optLevel, setOptLevel] = useState('0');
  const [timeoutSec, setTimeoutSec] = useState(15);
  const [isSaved, setIsSaved] = useState(false);

  const handleSave = () => {
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const toolsList = [
    { name: 'GCC (GNU Compiler Collection)', info: toolchain?.gcc, required: true },
    { name: 'GDB (GNU Project Debugger)', info: toolchain?.gdb, required: true },
    { name: 'GNU Make Build Automation', info: toolchain?.make, required: true },
    { name: 'strace System Call Tracer', info: toolchain?.strace, required: false },
    { name: 'Clang / LLVM Compiler', info: toolchain?.clang, required: false },
    { name: 'Valgrind Memory Debugger', info: toolchain?.valgrind, required: false }
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
            <SettingsIcon className="w-5 h-5 text-cyan-400" />
            <span>Debugger & Toolchain Settings</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Configure Linux execution environments, compiler standards, and verify local toolchain readiness.
          </p>
        </div>

        {/* Toolchain Health Status */}
        <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-sm font-semibold text-slate-200">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>Host & Toolchain Verification ({toolchain?.platform || 'Unknown'})</span>
            </div>
            <button
              onClick={onRefreshToolchain}
              className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-850 hover:bg-slate-800 text-slate-300 text-xs"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Re-check</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {toolsList.map((t, idx) => {
              const isAvail = t.info?.available;
              return (
                <div
                  key={idx}
                  className={`p-3 rounded-lg border text-xs flex items-start justify-between ${
                    isAvail
                      ? 'bg-slate-900/60 border-slate-800 text-slate-200'
                      : 'bg-rose-950/20 border-rose-900/40 text-slate-400'
                  }`}
                >
                  <div className="space-y-1">
                    <div className="font-semibold flex items-center space-x-1.5">
                      <span>{t.name}</span>
                      {t.required && <span className="text-[10px] text-amber-400 font-bold">(Core)</span>}
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono truncate max-w-xs">
                      {isAvail ? t.info?.version || t.info?.path : 'Not detected in PATH'}
                    </div>
                  </div>

                  {isAvail ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Compiler & Build Settings */}
        <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-4">
          <div className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
            <Sliders className="w-4 h-4 text-cyan-400" />
            <span>Default Compiler & Standard</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">C Language Standard</label>
              <select
                value={cStandard}
                onChange={(e) => setCStandard(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white"
              >
                <option value="c11">ISO C11 (-std=c11, Default)</option>
                <option value="c99">ISO C99 (-std=c99)</option>
                <option value="c17">ISO C17 (-std=c17)</option>
                <option value="c23">ISO C23 (-std=c23)</option>
                <option value="gnu11">GNU11 (-std=gnu11)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1">Optimization Level</label>
              <select
                value={optLevel}
                onChange={(e) => setOptLevel(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white"
              >
                <option value="0">-O0 (No Optimization, Ideal for GDB Stepping)</option>
                <option value="1">-O1 (Minimal Optimization)</option>
                <option value="2">-O2 (Release Optimization)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Execution Sandbox Limits */}
        <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-4">
          <div className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            <span>Execution Sandbox & Safety Limits</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Max Execution Timeout (Seconds)</label>
              <input
                type="number"
                value={timeoutSec}
                onChange={(e) => setTimeoutSec(Number(e.target.value))}
                min={2}
                max={60}
                className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white"
              />
            </div>
            <div className="text-xs text-slate-400 flex items-center pt-5">
              <span>Automatically terminates runaway infinite loops or hung target processes.</span>
            </div>
          </div>

          <div className="pt-2">
            <button
              onClick={handleSave}
              className="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold"
            >
              {isSaved ? 'Settings Applied!' : 'Save Configuration'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
