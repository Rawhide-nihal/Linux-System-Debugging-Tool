import React, { useState, useEffect } from 'react';
import {
  History,
  CheckCircle,
  AlertOctagon,
  Clock,
  Terminal,
  FileCode,
  ArrowRight
} from 'lucide-react';
import { Workspace } from '../types';

interface SessionsScreenProps {
  currentWorkspace: Workspace | null;
}

export const SessionsScreen: React.FC<SessionsScreenProps> = ({ currentWorkspace }) => {
  const [sessions, setSessions] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api/debugger/sessions' + (currentWorkspace ? `?workspace_id=${currentWorkspace.id}` : ''))
      .then((res) => res.json())
      .then((data) => setSessions(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [currentWorkspace]);

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
            <History className="w-5 h-5 text-cyan-400" />
            <span>Debug Session History</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Historical record of interactive GDB debug sessions, breakpoints, and runtime outcomes.
          </p>
        </div>

        <div className="space-y-3">
          {sessions.length === 0 ? (
            <div className="p-12 text-center rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
              No previous debug sessions recorded for this workspace.
            </div>
          ) : (
            sessions.map((sess) => (
              <div
                key={sess.id}
                className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-2 hover:border-slate-700 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        sess.status === 'CRASHED'
                          ? 'bg-rose-500/20 text-rose-400'
                          : sess.status === 'STOPPED'
                          ? 'bg-amber-500/20 text-amber-400'
                          : 'bg-emerald-500/20 text-emerald-400'
                      }`}
                    >
                      {sess.status}
                    </span>
                    <span className="font-mono text-xs font-semibold text-slate-200">
                      {sess.executable?.split('/').pop() || sess.id}
                    </span>
                  </div>

                  <div className="text-[11px] text-slate-300 font-mono">
                    {sess.start_time?.slice(0, 19).replace('T', ' ')}
                  </div>
                </div>

                <div className="text-xs text-slate-400 flex items-center space-x-4">
                  {sess.signal_info && (
                    <span className="text-rose-400 font-semibold">Signal: {sess.signal_info}</span>
                  )}
                  {sess.exit_code !== null && <span>Exit code: {sess.exit_code}</span>}
                  <span>Breakpoints: {sess.breakpoints?.length || 0}</span>
                  <span>Steps recorded: {sess.timeline?.length || 0}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
