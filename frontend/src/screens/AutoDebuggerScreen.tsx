import React, { useState } from 'react';
import {
  Sparkles,
  Play,
  CheckCircle,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  ShieldAlert,
  FileCode,
  Activity,
  Layers
} from 'lucide-react';
import { Workspace, AutoDebugResult, ScreenType } from '../types';
import { api } from '../services/api';

interface AutoDebuggerScreenProps {
  currentWorkspace: Workspace | null;
  onNavigate: (screen: ScreenType) => void;
  onSetExecutionTarget?: (file: string, line: number) => void;
}

export const AutoDebuggerScreen: React.FC<AutoDebuggerScreenProps> = ({
  currentWorkspace,
  onNavigate,
  onSetExecutionTarget
}) => {
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<AutoDebugResult | null>(null);
  const [enableStrace, setEnableStrace] = useState(true);

  const handleRunInvestigation = async () => {
    if (!currentWorkspace) return;
    setIsRunning(true);
    setResult(null);
    try {
      const res = await api.runAutoDebug(currentWorkspace.id, {
        target_name: 'app_debug',
        enable_strace: enableStrace
      });
      setResult(res);
    } catch (e: any) {
      alert('Investigation failed: ' + e.message);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Banner */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
              <Sparkles className="w-5 h-5 text-cyan-400" />
              <span>AutoDebugger Automated Investigation</span>
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Multi-stage forensic pipeline: Static Analysis, GDB Trapping, Signal Inspection, and Syscall Tracing.
            </p>
          </div>

          <div className="flex items-center space-x-4">
            <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={enableStrace}
                onChange={(e) => setEnableStrace(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-cyan-500"
              />
              <span>Enable strace System Call Tracing</span>
            </label>

            <button
              onClick={handleRunInvestigation}
              disabled={!currentWorkspace || isRunning}
              className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold disabled:opacity-40 transition-colors shadow-lg shadow-cyan-950/50"
            >
              <Play className={`w-4 h-4 fill-white ${isRunning ? 'animate-spin' : ''}`} />
              <span>{isRunning ? 'Analyzing Execution...' : 'Run Investigation'}</span>
            </button>
          </div>
        </div>

        {/* Progress Stages */}
        {result?.stages && (
          <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
            <div className="text-xs font-semibold text-slate-300 flex items-center space-x-2 mb-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <span>Investigation Pipeline</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {result.stages.map((st, i) => (
                <div key={i} className="p-2.5 rounded bg-slate-900 border border-slate-800 text-xs">
                  <div className="flex items-center space-x-1.5 text-cyan-400 font-medium">
                    <CheckCircle className="w-3.5 h-3.5" />
                    <span>{st.stage}</span>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1 truncate">{st.detail}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Verdict Badge */}
        {result && (
          <div
            className={`p-4 rounded-lg border flex items-center justify-between ${
              result.verdict === 'CRITICAL_ISSUES_FOUND'
                ? 'bg-rose-950/20 border-rose-800/60 text-rose-300'
                : result.verdict === 'WARNINGS_FOUND'
                ? 'bg-amber-950/20 border-amber-800/60 text-amber-300'
                : 'bg-emerald-950/20 border-emerald-800/60 text-emerald-300'
            }`}
          >
            <div className="flex items-center space-x-3">
              {result.verdict === 'CRITICAL_ISSUES_FOUND' ? (
                <AlertOctagon className="w-6 h-6 text-rose-400 shrink-0" />
              ) : (
                <CheckCircle className="w-6 h-6 text-emerald-400 shrink-0" />
              )}
              <div>
                <div className="font-bold text-sm tracking-wide">
                  VERDICT: {result.verdict.replace(/_/g, ' ')}
                </div>
                <div className="text-xs opacity-80 mt-0.5">
                  Discovered {result.findings.length} verifiable diagnostic findings based on real runtime and static evidence.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Findings List */}
        {result?.findings && (
          <div className="space-y-3">
            <div className="text-sm font-semibold text-slate-200">
              Discovered Findings ({result.findings.length})
            </div>

            {result.findings.map((f, i) => (
              <div
                key={i}
                className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-3 hover:border-slate-700 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        f.severity === 'CRITICAL'
                          ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                          : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                      }`}
                    >
                      {f.severity}
                    </span>
                    <span className="font-bold text-sm text-slate-100">{f.title}</span>
                  </div>

                  {f.file && f.line && (
                    <button
                      onClick={() => {
                        onSetExecutionTarget?.(f.file!, f.line!);
                        onNavigate('editor');
                      }}
                      className="flex items-center space-x-1 text-xs text-cyan-400 hover:text-cyan-300"
                    >
                      <span>Jump to {f.file}:{f.line}</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {f.evidence && (
                  <div className="p-2.5 rounded bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300">
                    <div className="text-[10px] text-slate-300 uppercase mb-1">Evidence:</div>
                    <pre className="whitespace-pre-wrap">{f.evidence}</pre>
                  </div>
                )}

                {f.suggested_action && (
                  <div className="text-xs text-slate-300">
                    <span className="text-cyan-400 font-semibold">Suggested Action: </span>
                    {f.suggested_action}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
