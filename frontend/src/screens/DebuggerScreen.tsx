import React, { useState, useEffect, useRef } from 'react';
import Editor, { OnMount } from '@monaco-editor/react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import {
  Play,
  Pause,
  ArrowRight,
  CornerDownRight,
  CornerUpRight,
  FastForward,
  Square,
  RefreshCw,
  Eye,
  Plus,
  Trash2,
  ListTree,
  Activity,
  Terminal as TerminalIcon,
  Clock,
  Code
} from 'lucide-react';
import { DebugSessionSnapshot, Workspace, Breakpoint, Variable, StackFrame } from '../types';
import { api } from '../services/api';

interface DebuggerScreenProps {
  currentWorkspace: Workspace | null;
  session: DebugSessionSnapshot | null;
  onStepOver: () => void;
  onStepInto: () => void;
  onStepOut: () => void;
  onContinue: () => void;
  onPause: () => void;
  onStop: () => void;
  onRestart: () => void;
  onToggleBreakpoint: (file: string, line: number) => void;
}

export const DebuggerScreen: React.FC<DebuggerScreenProps> = ({
  currentWorkspace,
  session,
  onStepOver,
  onStepInto,
  onStepOut,
  onContinue,
  onPause,
  onStop,
  onRestart,
  onToggleBreakpoint
}) => {
  const [activeRightTab, setActiveRightTab] = useState<'vars' | 'watches' | 'stack' | 'breakpoints'>('vars');
  const [activeBottomTab, setActiveBottomTab] = useState<'terminal' | 'console' | 'timeline'>('terminal');

  // Watch expressions
  const [watches, setWatches] = useState<Array<{ expr: string; value?: string; error?: string }>>([
    { expr: 'argc' }
  ]);
  const [newWatchExpr, setNewWatchExpr] = useState('');

  // Source code viewer state
  const [sourceCode, setSourceCode] = useState<string>('');
  const [displayedFile, setDisplayedFile] = useState<string>('');

  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermInstance = useRef<XTerm | null>(null);
  const fitAddon = useRef<FitAddon | null>(null);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);

  // Initialize xterm.js
  useEffect(() => {
    if (!terminalRef.current || xtermInstance.current) return;

    const term = new XTerm({
      cursorBlink: true,
      fontSize: 12,
      fontFamily: "'Fira Code', Consolas, monospace",
      theme: {
        background: '#020617',
        foreground: '#f8fafc',
        cursor: '#38bdf8'
      }
    });

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(terminalRef.current);
    fit.fit();

    xtermInstance.current = term;
    fitAddon.current = fit;

    term.writeln('\x1b[1;36m[Debugger Console / Terminal Attached]\x1b[0m');
    term.writeln('Standard I/O stream connected.');

    // User typing in terminal sends to inferior stdin
    term.onData((data) => {
      if (session) {
        api.sendStdin(session.session_id, data);
      }
    });

    const handleResize = () => fit.fit();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      term.dispose();
      xtermInstance.current = null;
    };
  }, []);

  // Update terminal when stdout arrives
  useEffect(() => {
    if (session?.stdout && xtermInstance.current) {
      // Just ensure terminal is up to date
    }
  }, [session?.stdout]);

  // Load source file when stopped at a line
  useEffect(() => {
    if (!session || !currentWorkspace) return;
    const targetFile = session.file || 'main.c';
    const cleanPath = targetFile.split('/').pop() || targetFile;

    if (cleanPath !== displayedFile) {
      setDisplayedFile(cleanPath);
      api.readFile(currentWorkspace.id, cleanPath).then((res) => {
        if (res?.content) {
          setSourceCode(res.content);
        }
      }).catch(() => {});
    }
  }, [session?.file, currentWorkspace]);

  // Evaluate watches on stop
  useEffect(() => {
    if (session?.state === 'STOPPED' && watches.length > 0) {
      watches.forEach(async (w, idx) => {
        const res = await api.evaluateExpression(session.session_id, w.expr);
        setWatches((prev) => {
          const next = [...prev];
          if (next[idx]) {
            next[idx] = { expr: w.expr, value: res.value, error: res.error };
          }
          return next;
        });
      });
    }
  }, [session?.state, session?.line]);

  // Monaco Editor decorations (Current execution arrow + breakpoints)
  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    updateDecorations();
  };

  const updateDecorations = () => {
    if (!editorRef.current || !monacoRef.current) return;

    const decorations: any[] = [];

    // Breakpoint markers
    session?.breakpoints.forEach((bp) => {
      decorations.push({
        range: new monacoRef.current.Range(bp.line, 1, bp.line, 1),
        options: {
          isWholeLine: false,
          glyphMarginClassName: 'bg-rose-500 rounded-full w-2.5 h-2.5 ml-1 mt-1 cursor-pointer',
          glyphMarginHoverMessage: { value: `Breakpoint Line ${bp.line}` }
        }
      });
    });

    // Execution line
    if (session?.line) {
      decorations.push({
        range: new monacoRef.current.Range(session.line, 1, session.line, 1),
        options: {
          isWholeLine: true,
          className: session.state === 'CRASHED' ? 'bg-rose-950/40 border-l-2 border-rose-500' : 'bg-yellow-500/20 border-l-2 border-yellow-400',
          glyphMarginClassName: 'text-yellow-400 font-bold ml-1'
        }
      });
      editorRef.current.revealLineInCenter(session.line);
    }

    editorRef.current.createDecorationsCollection(decorations);
  };

  useEffect(() => {
    updateDecorations();
  }, [session?.line, session?.state, session?.breakpoints, sourceCode]);

  const addWatch = async () => {
    if (!newWatchExpr.trim() || !session) return;
    const expr = newWatchExpr.trim();
    setNewWatchExpr('');
    const evalRes = await api.evaluateExpression(session.session_id, expr);
    setWatches([...watches, { expr, value: evalRes.value, error: evalRes.error }]);
  };

  const removeWatch = (idx: number) => {
    setWatches(watches.filter((_, i) => i !== idx));
  };

  const isStopped = session?.state === 'STOPPED' || session?.state === 'CRASHED';

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-slate-900">
      {/* Top Debugger Status Banner */}
      <div className="h-10 bg-slate-950 border-b border-slate-800 px-4 flex items-center justify-between text-xs">
        <div className="flex items-center space-x-3">
          <span
            className={`px-2 py-0.5 rounded text-[11px] font-bold ${
              session?.state === 'STOPPED'
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                : session?.state === 'RUNNING'
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                : session?.state === 'CRASHED'
                ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                : 'bg-slate-800 text-slate-400'
            }`}
          >
            {session?.state || 'IDLE'}
          </span>

          {session?.stop_signal && (
            <span className="text-rose-400 font-bold flex items-center space-x-1">
              <span>Fault: {session.stop_signal}</span>
            </span>
          )}

          {session?.file && (
            <span className="text-slate-300 font-mono">
              {displayedFile}:{session.line || 0} ({session.func || 'main'})
            </span>
          )}
        </div>

        {/* Execution control toolbar buttons */}
        <div className="flex items-center space-x-2">
          <button
            onClick={onContinue}
            disabled={!isStopped}
            title="Continue (F5)"
            className="flex items-center space-x-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 disabled:opacity-30"
          >
            <FastForward className="w-3.5 h-3.5 fill-emerald-400" />
            <span>Continue</span>
          </button>
          <button
            onClick={onPause}
            disabled={isStopped}
            title="Pause (SIGINT)"
            className="flex items-center space-x-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-400 disabled:opacity-30"
          >
            <Pause className="w-3.5 h-3.5 fill-amber-400" />
            <span>Pause</span>
          </button>
          <button
            onClick={onStepOver}
            disabled={!isStopped}
            title="Step Over (F10)"
            className="flex items-center space-x-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-blue-400 disabled:opacity-30"
          >
            <ArrowRight className="w-3.5 h-3.5" />
            <span>Step Over</span>
          </button>
          <button
            onClick={onStepInto}
            disabled={!isStopped}
            title="Step Into (F11)"
            className="flex items-center space-x-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-400 disabled:opacity-30"
          >
            <CornerDownRight className="w-3.5 h-3.5" />
            <span>Step Into</span>
          </button>
          <button
            onClick={onStepOut}
            disabled={!isStopped}
            title="Step Out (Shift+F11)"
            className="flex items-center space-x-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-400 disabled:opacity-30"
          >
            <CornerUpRight className="w-3.5 h-3.5" />
            <span>Step Out</span>
          </button>
          <button
            onClick={onStop}
            title="Stop Session"
            className="p-1 rounded bg-slate-800 hover:bg-rose-950 text-rose-400"
          >
            <Square className="w-3.5 h-3.5 fill-rose-400" />
          </button>
        </div>
      </div>

      {/* Main split workbench area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Source execution viewer */}
        <div className="flex-1 flex flex-col border-r border-slate-800">
          <div className="h-8 bg-slate-950 border-b border-slate-800 px-3 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center space-x-2">
              <Code className="w-3.5 h-3.5 text-cyan-400" />
              <span>{displayedFile || 'Source Viewer'}</span>
            </div>
            {session?.line && <span className="text-yellow-400 font-mono">Stopped at line {session.line}</span>}
          </div>
          <div className="flex-1 relative">
            <Editor
              height="100%"
              theme="vs-dark"
              language="c"
              value={sourceCode || '// Start debugging to load active execution frame.'}
              onMount={handleEditorMount}
              options={{
                readOnly: true,
                fontSize: 13,
                fontFamily: "'Fira Code', Consolas, monospace",
                lineNumbers: 'on',
                glyphMargin: true,
                automaticLayout: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                renderLineHighlight: 'all'
              }}
            />
          </div>
        </div>

        {/* Right Debug Inspection Sidebar */}
        <div className="w-80 bg-slate-950 flex flex-col border-l border-slate-800">
          {/* Tabs */}
          <div className="h-8 bg-slate-900 border-b border-slate-800 flex items-center px-1 space-x-1 select-none text-[11px]">
            <button
              onClick={() => setActiveRightTab('vars')}
              className={`px-2.5 py-1 rounded ${
                activeRightTab === 'vars' ? 'bg-slate-800 text-cyan-400 font-medium' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Variables ({session?.variables.length || 0})
            </button>
            <button
              onClick={() => setActiveRightTab('watches')}
              className={`px-2.5 py-1 rounded ${
                activeRightTab === 'watches' ? 'bg-slate-800 text-cyan-400 font-medium' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Watches ({watches.length})
            </button>
            <button
              onClick={() => setActiveRightTab('stack')}
              className={`px-2.5 py-1 rounded ${
                activeRightTab === 'stack' ? 'bg-slate-800 text-cyan-400 font-medium' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Call Stack ({session?.call_stack.length || 0})
            </button>
            <button
              onClick={() => setActiveRightTab('breakpoints')}
              className={`px-2.5 py-1 rounded ${
                activeRightTab === 'breakpoints' ? 'bg-slate-800 text-cyan-400 font-medium' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Breakpoints
            </button>
          </div>

          {/* Panel Contents */}
          <div className="flex-1 overflow-y-auto p-3 text-xs">
            {activeRightTab === 'vars' && (
              <div className="space-y-3">
                <div>
                  <div className="text-[10px] font-semibold text-slate-300 uppercase mb-1">Local Variables</div>
                  {session?.variables.length === 0 ? (
                    <div className="text-slate-300 italic">No locals available</div>
                  ) : (
                    <div className="space-y-1 font-mono">
                      {session?.variables.map((v, i) => (
                        <div key={i} className="flex items-center justify-between p-1.5 rounded bg-slate-900/60 border border-slate-800">
                          <span className="text-cyan-400 font-medium">{v.name}</span>
                          <span className="text-slate-400 text-[10px]">{v.type}</span>
                          <span className={`font-semibold ${v.value.includes('NULL') ? 'text-rose-400' : 'text-emerald-300'}`}>
                            {v.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {session?.arguments && session.arguments.length > 0 && (
                  <div>
                    <div className="text-[10px] font-semibold text-slate-300 uppercase mb-1">Function Arguments</div>
                    <div className="space-y-1 font-mono">
                      {session.arguments.map((a, i) => (
                        <div key={i} className="flex items-center justify-between p-1.5 rounded bg-slate-900/60 border border-slate-800">
                          <span className="text-blue-400">{a.name}</span>
                          <span className="text-slate-300">{a.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeRightTab === 'watches' && (
              <div className="space-y-3">
                <div className="flex items-center space-x-1">
                  <input
                    type="text"
                    placeholder="Expression (e.g. i * 2, ptr)"
                    value={newWatchExpr}
                    onChange={(e) => setNewWatchExpr(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addWatch()}
                    className="flex-1 bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs text-white outline-none"
                  />
                  <button onClick={addWatch} className="p-1 rounded bg-cyan-600 text-white">
                    <Plus className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="space-y-1 font-mono">
                  {watches.map((w, i) => (
                    <div key={i} className="flex items-center justify-between p-1.5 rounded bg-slate-900 border border-slate-800">
                      <div>
                        <div className="text-slate-300 font-medium">{w.expr}</div>
                        <div className={`text-[11px] ${w.error ? 'text-rose-400' : 'text-emerald-300'}`}>
                          {w.error || w.value || '<not evaluated>'}
                        </div>
                      </div>
                      <button onClick={() => removeWatch(i)} className="text-slate-300 hover:text-rose-400">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeRightTab === 'stack' && (
              <div className="space-y-1 font-mono">
                {session?.call_stack.map((frame) => (
                  <button
                    key={frame.level}
                    onClick={() => session && api.selectFrame(session.session_id, frame.level)}
                    className={`w-full text-left p-2 rounded border block transition-colors ${
                      session.frame_level === frame.level
                        ? 'border-cyan-500 bg-cyan-950/20 text-white'
                        : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-850'
                    }`}
                  >
                    <div className="font-semibold text-cyan-400">#{frame.level} {frame.func}()</div>
                    <div className="text-[10px] text-slate-400 truncate">{frame.file}:{frame.line}</div>
                  </button>
                ))}
              </div>
            )}

            {activeRightTab === 'breakpoints' && (
              <div className="space-y-2">
                {session?.breakpoints.map((bp) => (
                  <div key={bp.id} className="p-2 rounded bg-slate-900 border border-slate-800 flex items-center justify-between">
                    <div>
                      <div className="font-mono text-slate-200">{bp.file}:{bp.line}</div>
                      {bp.condition && <div className="text-[10px] text-amber-400">cond: {bp.condition}</div>}
                      <div className="text-[10px] text-slate-300">Hits: {bp.hit_count}</div>
                    </div>
                    <button
                      onClick={() => session && api.deleteBreakpoint(session.session_id, bp.id)}
                      className="text-slate-300 hover:text-rose-400"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Panel (Terminal / Console / Timeline) */}
      <div className="h-44 bg-slate-950 border-t border-slate-800 flex flex-col">
        <div className="h-7 bg-slate-900 border-b border-slate-800 flex items-center px-2 space-x-1 select-none text-[11px]">
          <button
            onClick={() => setActiveBottomTab('terminal')}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded ${
              activeBottomTab === 'terminal' ? 'bg-slate-800 text-cyan-400 font-medium' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TerminalIcon className="w-3.5 h-3.5" />
            <span>Program Terminal</span>
          </button>
          <button
            onClick={() => setActiveBottomTab('console')}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded ${
              activeBottomTab === 'console' ? 'bg-slate-800 text-cyan-400 font-medium' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Debug Log</span>
          </button>
          <button
            onClick={() => setActiveBottomTab('timeline')}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded ${
              activeBottomTab === 'timeline' ? 'bg-slate-800 text-cyan-400 font-medium' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Execution Timeline</span>
          </button>
        </div>

        <div className="flex-1 overflow-hidden relative p-1">
          <div
            ref={terminalRef}
            className={`h-full w-full ${activeBottomTab === 'terminal' ? 'block' : 'hidden'}`}
          />

          {activeBottomTab === 'console' && (
            <div className="h-full overflow-y-auto font-mono text-xs text-slate-300 p-2 space-y-1">
              <div>Output Stream:</div>
              <pre className="text-emerald-400">{session?.stdout || '<no output yet>'}</pre>
              {session?.stderr && <pre className="text-rose-400">{session.stderr}</pre>}
            </div>
          )}

          {activeBottomTab === 'timeline' && (
            <div className="h-full overflow-y-auto p-2 space-y-1 text-xs">
              {session?.timeline.map((item, idx) => (
                <div key={idx} className="flex items-center space-x-2 text-slate-300 font-mono">
                  <span className="text-slate-300 text-[10px]">{item.timestamp}</span>
                  <span className="text-cyan-400 font-semibold">[{item.event}]</span>
                  <span>{item.description}</span>
                  {item.line && <span className="text-slate-400">(line {item.line})</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
