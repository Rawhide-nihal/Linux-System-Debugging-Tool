import React, { useState, useEffect } from 'react';
import {
  FileText,
  Download,
  CheckCircle,
  AlertTriangle,
  ArrowRight
} from 'lucide-react';
import { Workspace } from '../types';
import { api } from '../services/api';

interface ReportsScreenProps {
  currentWorkspace: Workspace | null;
}

export const ReportsScreen: React.FC<ReportsScreenProps> = ({ currentWorkspace }) => {
  const [reports, setReports] = useState<any[]>([]);

  useEffect(() => {
    api.listReports(currentWorkspace?.id).then(setReports).catch(() => {});
  }, [currentWorkspace]);

  const handleDownloadMarkdown = async (reportId: string, title: string) => {
    const md = await api.exportReportMarkdown(reportId);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.replace(/\s+/g, '_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
            <FileText className="w-5 h-5 text-cyan-400" />
            <span>Diagnostic Reports</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Export structured debugging reports containing evidence, signals, and recommended fixes.
          </p>
        </div>

        <div className="space-y-4">
          {reports.length === 0 ? (
            <div className="p-12 text-center rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
              No reports generated yet. Run AutoDebugger to produce an investigation report.
            </div>
          ) : (
            reports.map((r) => (
              <div
                key={r.id}
                className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-bold text-slate-100">{r.title}</h2>
                    <div className="text-[11px] text-slate-400 mt-0.5">{r.summary}</div>
                  </div>

                  <button
                    onClick={() => handleDownloadMarkdown(r.id, r.title)}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Export Markdown</span>
                  </button>
                </div>

                <div className="space-y-2 pt-2 border-t border-slate-900">
                  <div className="text-[11px] font-semibold text-slate-300 uppercase">
                    Findings ({r.findings?.length || 0})
                  </div>
                  {r.findings?.map((f: any, fIdx: number) => (
                    <div
                      key={fIdx}
                      className="p-2.5 rounded bg-slate-900/60 border border-slate-850 text-xs space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-200">{f.title}</span>
                        <span className="text-[10px] text-cyan-400 font-mono">
                          {f.file}:{f.line}
                        </span>
                      </div>
                      {f.evidence && (
                        <div className="text-[11px] text-slate-400 font-mono">{f.evidence}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
