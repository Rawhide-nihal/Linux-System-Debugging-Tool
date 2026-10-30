import React, { useState } from 'react';
import {
  AlertTriangle,
  AlertCircle,
  Info,
  Filter,
  ArrowRight,
  FileCode
} from 'lucide-react';
import { DiagnosticItem, ScreenType } from '../types';

interface ProblemsScreenProps {
  diagnostics: DiagnosticItem[];
  onNavigateToSource: (file: string, line: number) => void;
  onNavigate: (screen: ScreenType) => void;
}

export const ProblemsScreen: React.FC<ProblemsScreenProps> = ({
  diagnostics,
  onNavigateToSource,
  onNavigate
}) => {
  const [filterSeverity, setFilterSeverity] = useState<'all' | 'error' | 'warning'>('all');

  const filtered = diagnostics.filter((d) => {
    if (filterSeverity === 'all') return true;
    return d.severity === filterSeverity;
  });

  const errorCount = diagnostics.filter((d) => d.severity === 'error').length;
  const warningCount = diagnostics.filter((d) => d.severity === 'warning').length;

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              <span>Diagnostics & Problems</span>
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Collected compiler errors, warnings, and static-analysis findings.
            </p>
          </div>

          {/* Severity Filters */}
          <div className="flex items-center space-x-2 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            <button
              onClick={() => setFilterSeverity('all')}
              className={`px-3 py-1 rounded font-medium ${
                filterSeverity === 'all' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              All ({diagnostics.length})
            </button>
            <button
              onClick={() => setFilterSeverity('error')}
              className={`px-3 py-1 rounded font-medium ${
                filterSeverity === 'error' ? 'bg-rose-500/20 text-rose-400' : 'text-slate-400 hover:text-rose-400'
              }`}
            >
              Errors ({errorCount})
            </button>
            <button
              onClick={() => setFilterSeverity('warning')}
              className={`px-3 py-1 rounded font-medium ${
                filterSeverity === 'warning' ? 'bg-amber-500/20 text-amber-400' : 'text-slate-400 hover:text-amber-400'
              }`}
            >
              Warnings ({warningCount})
            </button>
          </div>
        </div>

        {/* Problems Table / List */}
        {filtered.length === 0 ? (
          <div className="p-12 text-center rounded-lg bg-slate-950 border border-slate-800 text-slate-300 space-y-2">
            <FileCode className="w-8 h-8 text-slate-400 mx-auto" />
            <div className="text-sm font-semibold">No problems detected</div>
            <div className="text-xs">Active source files compiled cleanly with no compiler diagnostics.</div>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((d, idx) => (
              <div
                key={idx}
                onClick={() => {
                  if (d.line) {
                    onNavigateToSource(d.file, d.line);
                    onNavigate('editor');
                  }
                }}
                className="p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-cyan-500/60 cursor-pointer transition-all flex items-start justify-between space-x-4"
              >
                <div className="flex items-start space-x-3">
                  {d.severity === 'error' ? (
                    <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  )}
                  <div className="space-y-1">
                    <div className="text-xs font-semibold text-slate-200">{d.message}</div>
                    {d.snippet && (
                      <pre className="text-[11px] font-mono text-slate-400 bg-slate-900 px-2 py-1 rounded border border-slate-850 whitespace-pre">
                        {d.snippet}
                      </pre>
                    )}
                    <div className="flex items-center space-x-2 text-[10px] text-slate-300 font-mono">
                      <span>{d.file}:{d.line || 0}:{d.column || 0}</span>
                      <span>•</span>
                      <span className="uppercase text-slate-300">{d.category}</span>
                    </div>
                  </div>
                </div>

                {d.line && (
                  <div className="flex items-center space-x-1 text-xs text-cyan-400 shrink-0">
                    <span>Jump</span>
                    <ArrowRight className="w-3.5 h-3.5" />
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
