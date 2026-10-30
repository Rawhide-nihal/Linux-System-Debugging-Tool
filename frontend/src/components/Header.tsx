import React from 'react';
import {
  Terminal,
  Hammer,
  Play,
  Pause,
  FastForward,
  CornerDownRight,
  ArrowRight,
  CornerUpRight,
  Square,
  RefreshCw,
  FolderOpen,
  Cpu,
  Moon,
  Sun
} from 'lucide-react';
import { Workspace, DebugSessionSnapshot, ToolchainInfo } from '../types';

interface HeaderProps {
  currentWorkspace: Workspace | null;
  workspaces: Workspace[];
  onSelectWorkspace: (ws: Workspace) => void;
  activeSession: DebugSessionSnapshot | null;
  toolchain: ToolchainInfo | null;
  onBuild: () => void;
  isBuilding: boolean;
  onStartDebug: () => void;
  onStepOver: () => void;
  onStepInto: () => void;
  onStepOut: () => void;
  onContinue: () => void;
  onPause: () => void;
  onStop: () => void;
  isDark: boolean;
  onToggleTheme: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentWorkspace,
  workspaces,
  onSelectWorkspace,
  activeSession,
  toolchain,
  onBuild,
  isBuilding,
  onStartDebug,
  onStepOver,
  onStepInto,
  onStepOut,
  onContinue,
  onPause,
  onStop,
  isDark,
  onToggleTheme
}) => {
  const isDebugging = activeSession && activeSession.state !== 'TERMINATED';
  const isStopped = activeSession?.state === 'STOPPED' || activeSession?.state === 'CRASHED';

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-900/95 backdrop-blur px-4 flex items-center justify-between select-none z-30">
      {/* Brand & Project Selector */}
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2 text-cyan-400 font-bold tracking-tight text-base">
          <Terminal className="w-5 h-5 text-cyan-400" />
          <span>Linux Debugger</span>
        </div>

        {/* Project Dropdown */}
        <div className="flex items-center space-x-2 bg-slate-800/80 px-2.5 py-1 rounded border border-slate-700/60 text-xs">
          <FolderOpen className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={currentWorkspace?.id || ''}
            onChange={(e) => {
              const ws = workspaces.find((w) => w.id === e.target.value);
              if (ws) onSelectWorkspace(ws);
            }}
            className="bg-transparent text-slate-200 outline-none cursor-pointer max-w-[140px] truncate"
          >
            {workspaces.map((ws) => (
              <option key={ws.id} value={ws.id} className="bg-slate-900 text-slate-200">
                {ws.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Primary Debugging Action Controls */}
      <div className="flex items-center space-x-1.5 bg-slate-950/60 px-2 py-1 rounded-md border border-slate-800">
        <button
          onClick={onBuild}
          disabled={!currentWorkspace || isBuilding}
          title="Build Project (gcc -g -O0)"
          className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium disabled:opacity-40 transition-colors"
        >
          <Hammer className={`w-3.5 h-3.5 ${isBuilding ? 'animate-spin text-amber-400' : 'text-slate-300'}`} />
          <span>Build</span>
        </button>

        <div className="w-[1px] h-4 bg-slate-800 mx-1" />

        {!isDebugging ? (
          <button
            onClick={onStartDebug}
            disabled={!currentWorkspace}
            title="Start Interactive Debugging (GDB)"
            className="flex items-center space-x-1 px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors"
          >
            <Play className="w-3.5 h-3.5 fill-white" />
            <span>Debug</span>
          </button>
        ) : (
          <>
            <button
              onClick={onContinue}
              disabled={!isStopped}
              title="Continue Execution (-exec-continue)"
              className="p-1.5 rounded hover:bg-slate-800 text-emerald-400 disabled:opacity-30 transition-colors"
            >
              <FastForward className="w-4 h-4 fill-emerald-400" />
            </button>
            <button
              onClick={onPause}
              disabled={isStopped}
              title="Pause Execution (SIGINT)"
              className="p-1.5 rounded hover:bg-slate-800 text-amber-400 disabled:opacity-30 transition-colors"
            >
              <Pause className="w-4 h-4 fill-amber-400" />
            </button>
            <button
              onClick={onStepOver}
              disabled={!isStopped}
              title="Step Over (-exec-next)"
              className="p-1.5 rounded hover:bg-slate-800 text-blue-400 disabled:opacity-30 transition-colors"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={onStepInto}
              disabled={!isStopped}
              title="Step Into (-exec-step)"
              className="p-1.5 rounded hover:bg-slate-800 text-cyan-400 disabled:opacity-30 transition-colors"
            >
              <CornerDownRight className="w-4 h-4" />
            </button>
            <button
              onClick={onStepOut}
              disabled={!isStopped}
              title="Step Out (-exec-finish)"
              className="p-1.5 rounded hover:bg-slate-800 text-indigo-400 disabled:opacity-30 transition-colors"
            >
              <CornerUpRight className="w-4 h-4" />
            </button>
            <button
              onClick={onStop}
              title="Stop Debugging (-gdb-exit)"
              className="p-1.5 rounded hover:bg-slate-800 text-rose-400 transition-colors"
            >
              <Square className="w-4 h-4 fill-rose-400" />
            </button>
          </>
        )}
      </div>

      {/* Toolchain Readiness & Theme */}
      <div className="flex items-center space-x-3 text-xs">
        <div className="flex items-center space-x-1.5 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/40 text-slate-300">
          <Cpu className="w-3.5 h-3.5 text-cyan-400" />
          <span>{toolchain?.platform || 'Detecting...'}</span>
          {toolchain?.ready && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
        </div>

        <button
          onClick={onToggleTheme}
          title="Toggle Theme"
          className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
        >
          {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
        </button>
      </div>
    </header>
  );
};
