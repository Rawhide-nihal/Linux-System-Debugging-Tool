import React, { useState, useEffect, useRef } from 'react';
import {
  ScreenType,
  Workspace,
  DebugSessionSnapshot,
  ToolchainInfo,
  DiagnosticItem,
  Breakpoint
} from './types';
import { api } from './services/api';

import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { WorkspaceScreen } from './screens/WorkspaceScreen';
import { EditorScreen } from './screens/EditorScreen';
import { DebuggerScreen } from './screens/DebuggerScreen';
import { AutoDebuggerScreen } from './screens/AutoDebuggerScreen';
import { ProblemsScreen } from './screens/ProblemsScreen';
import { MemoryScreen } from './screens/MemoryScreen';
import { TestCasesScreen } from './screens/TestCasesScreen';
import { SessionsScreen } from './screens/SessionsScreen';
import { ReportsScreen } from './screens/ReportsScreen';
import { SettingsScreen } from './screens/SettingsScreen';

export const App: React.FC = () => {
  const [activeScreen, setActiveScreen] = useState<ScreenType>('workspace');
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspace, setCurrentWorkspace] = useState<Workspace | null>(null);
  const [toolchain, setToolchain] = useState<ToolchainInfo | null>(null);

  // Active debug session state
  const [activeSession, setActiveSession] = useState<DebugSessionSnapshot | null>(null);
  const [isBuilding, setIsBuilding] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticItem[]>([]);
  const [breakpoints, setBreakpoints] = useState<Breakpoint[]>([]);
  const [isDark, setIsDark] = useState(true);

  // Highlighted execution line in editor
  const [currentExecutionLine, setCurrentExecutionLine] = useState<{ file: string; line: number } | null>(null);

  const socketRef = useRef<WebSocket | null>(null);

  // Initial load
  useEffect(() => {
    loadWorkspaces();
    loadToolchain();
  }, []);

  const loadWorkspaces = async () => {
    try {
      const list = await api.listWorkspaces();
      setWorkspaces(list);
      if (list.length > 0 && !currentWorkspace) {
        const fullWs = await api.getWorkspace(list[0].id);
        setCurrentWorkspace(fullWs);
      }
    } catch (e) {
      console.error('Failed to load workspaces:', e);
    }
  };

  const loadToolchain = async () => {
    try {
      const tc = await api.getToolchain();
      setToolchain(tc);
    } catch (e) {
      console.error('Failed to fetch toolchain:', e);
    }
  };

  const handleSelectWorkspace = async (ws: Workspace) => {
    const fullWs = await api.getWorkspace(ws.id);
    setCurrentWorkspace(fullWs);
    // Fetch diagnostics for new workspace
    triggerBuild(fullWs.id);
  };

  // Build Project
  const triggerBuild = async (wsId?: string) => {
    const id = wsId || currentWorkspace?.id;
    if (!id) return;
    setIsBuilding(true);
    try {
      const res = await api.buildProject(id, { target_name: 'app_debug' });
      setDiagnostics(res.diagnostics);
      if (!res.success && res.diagnostics.some((d) => d.severity === 'error')) {
        // If there are errors, automatically switch or notify
      }
    } catch (e: any) {
      console.error(e);
    } finally {
      setIsBuilding(false);
    }
  };

  // Start Interactive Debugger
  const handleStartDebug = async () => {
    if (!currentWorkspace) return;
    try {
      // First ensure binary is built
      const buildRes = await api.buildProject(currentWorkspace.id, { target_name: 'app_debug' });
      setDiagnostics(buildRes.diagnostics);
      if (!buildRes.success) {
        alert('Build failed! Check the Problems tab before debugging.');
        setActiveScreen('problems');
        return;
      }

      // Create new GDB session
      const snapshot = await api.createDebugSession(currentWorkspace.id, 'app_debug');
      setActiveSession(snapshot);
      setActiveScreen('debugger');

      // Connect WebSocket for streaming events
      connectWebSocket(snapshot.session_id);

      // Start inferior execution
      const startRes = await api.startDebugSession(snapshot.session_id);
      if (startRes.snapshot) {
        setActiveSession(startRes.snapshot);
      }
    } catch (e: any) {
      alert('Failed to start debugger: ' + e.message);
    }
  };

  // WebSocket for asynchronous GDB events
  const connectWebSocket = (sessionId: string) => {
    if (socketRef.current) {
      socketRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/debugger/${sessionId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === 'stopped') {
          setActiveSession((prev) => (prev ? { ...prev, ...msg.data, state: 'STOPPED' } : prev));
          if (msg.data?.file && msg.data?.line) {
            setCurrentExecutionLine({ file: msg.data.file, line: msg.data.line });
          }
        } else if (msg.event === 'state_changed') {
          setActiveSession((prev) => (prev ? { ...prev, state: msg.data.state } : prev));
        } else if (msg.event === 'breakpoint_added') {
          setBreakpoints((prev) => [...prev, msg.data]);
        }
      } catch (err) {
        console.error('WS parse error:', err);
      }
    };

    socketRef.current = ws;
  };

  // Stepping controls
  const handleStepOver = async () => {
    if (!activeSession) return;
    await api.stepOver(activeSession.session_id);
    const snap = await api.getDebugSession(activeSession.session_id);
    setActiveSession(snap);
    if (snap.file && snap.line) {
      setCurrentExecutionLine({ file: snap.file, line: snap.line });
    }
  };

  const handleStepInto = async () => {
    if (!activeSession) return;
    await api.stepInto(activeSession.session_id);
    const snap = await api.getDebugSession(activeSession.session_id);
    setActiveSession(snap);
    if (snap.file && snap.line) {
      setCurrentExecutionLine({ file: snap.file, line: snap.line });
    }
  };

  const handleStepOut = async () => {
    if (!activeSession) return;
    await api.stepOut(activeSession.session_id);
    const snap = await api.getDebugSession(activeSession.session_id);
    setActiveSession(snap);
    if (snap.file && snap.line) {
      setCurrentExecutionLine({ file: snap.file, line: snap.line });
    }
  };

  const handleContinue = async () => {
    if (!activeSession) return;
    await api.continueDebug(activeSession.session_id);
    const snap = await api.getDebugSession(activeSession.session_id);
    setActiveSession(snap);
  };

  const handlePause = async () => {
    if (!activeSession) return;
    await api.pauseDebug(activeSession.session_id);
    const snap = await api.getDebugSession(activeSession.session_id);
    setActiveSession(snap);
  };

  const handleStop = async () => {
    if (!activeSession) return;
    await api.terminateSession(activeSession.session_id);
    setActiveSession(null);
    setCurrentExecutionLine(null);
  };

  const handleToggleBreakpoint = async (file: string, line: number) => {
    if (!activeSession) return;
    const existing = breakpoints.find((b) => (b.file.endsWith(file) || file.endsWith(b.file)) && b.line === line);
    if (existing) {
      await api.deleteBreakpoint(activeSession.session_id, existing.id);
      setBreakpoints(breakpoints.filter((b) => b.id !== existing.id));
    } else {
      const bp = await api.addBreakpoint(activeSession.session_id, file, line);
      setBreakpoints([...breakpoints, bp]);
    }
  };

  const navigateToSource = (file: string, line: number) => {
    setCurrentExecutionLine({ file, line });
    setActiveScreen('editor');
  };

  return (
    <div className={`h-screen w-screen flex flex-col overflow-hidden ${isDark ? 'dark bg-slate-950 text-slate-100' : 'bg-slate-900 text-slate-100'}`}>
      <Header
        currentWorkspace={currentWorkspace}
        workspaces={workspaces}
        onSelectWorkspace={handleSelectWorkspace}
        activeSession={activeSession}
        toolchain={toolchain}
        onBuild={() => triggerBuild()}
        isBuilding={isBuilding}
        onStartDebug={handleStartDebug}
        onStepOver={handleStepOver}
        onStepInto={handleStepInto}
        onStepOut={handleStepOut}
        onContinue={handleContinue}
        onPause={handlePause}
        onStop={handleStop}
        isDark={isDark}
        onToggleTheme={() => setIsDark(!isDark)}
      />

      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          activeScreen={activeScreen}
          onSelectScreen={setActiveScreen}
          problemsCount={diagnostics.length}
          testCount={0}
        />

        <main className="flex-1 flex overflow-hidden">
          {activeScreen === 'workspace' && (
            <WorkspaceScreen
              workspaces={workspaces}
              currentWorkspace={currentWorkspace}
              onSelectWorkspace={handleSelectWorkspace}
              onRefreshWorkspaces={loadWorkspaces}
              onNavigate={setActiveScreen}
            />
          )}

          {activeScreen === 'editor' && (
            <EditorScreen
              currentWorkspace={currentWorkspace}
              onBuild={() => triggerBuild()}
              isBuilding={isBuilding}
              diagnostics={diagnostics}
              breakpoints={breakpoints}
              onToggleBreakpoint={handleToggleBreakpoint}
              currentExecutionLine={currentExecutionLine}
            />
          )}

          {activeScreen === 'debugger' && (
            <DebuggerScreen
              currentWorkspace={currentWorkspace}
              session={activeSession}
              onStepOver={handleStepOver}
              onStepInto={handleStepInto}
              onStepOut={handleStepOut}
              onContinue={handleContinue}
              onPause={handlePause}
              onStop={handleStop}
              onRestart={handleStartDebug}
              onToggleBreakpoint={handleToggleBreakpoint}
            />
          )}

          {activeScreen === 'autodebug' && (
            <AutoDebuggerScreen
              currentWorkspace={currentWorkspace}
              onNavigate={setActiveScreen}
              onSetExecutionTarget={(file, line) => setCurrentExecutionLine({ file, line })}
            />
          )}

          {activeScreen === 'problems' && (
            <ProblemsScreen
              diagnostics={diagnostics}
              onNavigateToSource={navigateToSource}
              onNavigate={setActiveScreen}
            />
          )}

          {activeScreen === 'memory' && (
            <MemoryScreen session={activeSession} />
          )}

          {activeScreen === 'tests' && (
            <TestCasesScreen
              currentWorkspace={currentWorkspace}
              onNavigate={setActiveScreen}
            />
          )}

          {activeScreen === 'sessions' && (
            <SessionsScreen currentWorkspace={currentWorkspace} />
          )}

          {activeScreen === 'reports' && (
            <ReportsScreen currentWorkspace={currentWorkspace} />
          )}

          {activeScreen === 'settings' && (
            <SettingsScreen
              toolchain={toolchain}
              onRefreshToolchain={loadToolchain}
            />
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
