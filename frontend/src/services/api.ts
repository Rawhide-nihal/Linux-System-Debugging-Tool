import {
  Workspace,
  BuildResult,
  DebugSessionSnapshot,
  Breakpoint,
  AutoDebugResult,
  TestCase,
  ToolchainInfo,
  DiagnosticItem
} from '../types';

const API_BASE = '/api';

export const api = {
  // Workspaces
  async listWorkspaces(): Promise<Workspace[]> {
    const res = await fetch(`${API_BASE}/workspaces/`);
    return res.json();
  },

  async getWorkspace(id: string): Promise<Workspace> {
    const res = await fetch(`${API_BASE}/workspaces/${id}`);
    return res.json();
  },

  async createWorkspace(name: string, template: string = 'basic_app'): Promise<Workspace> {
    const res = await fetch(`${API_BASE}/workspaces/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, template })
    });
    return res.json();
  },

  async deleteWorkspace(id: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/workspaces/${id}`, { method: 'DELETE' });
    return res.json();
  },

  async readFile(wsId: string, path: string): Promise<{ path: string; content: string }> {
    const res = await fetch(`${API_BASE}/workspaces/${wsId}/file?path=${encodeURIComponent(path)}`);
    return res.json();
  },

  async writeFile(wsId: string, path: string, content: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/workspaces/${wsId}/file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content })
    });
    return res.json();
  },

  async searchWorkspace(wsId: string, query: string): Promise<{ results: Array<{ file: string; line: number; content: string }> }> {
    const res = await fetch(`${API_BASE}/workspaces/${wsId}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    return res.json();
  },

  async importZip(file: File, name: string): Promise<Workspace> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    const res = await fetch(`${API_BASE}/workspaces/import-zip`, {
      method: 'POST',
      body: formData
    });
    return res.json();
  },

  // Compiler
  async buildProject(wsId: string, options?: { target_name?: string; cflags?: string[]; build_mode?: string; selected_file?: string }): Promise<BuildResult> {
    const res = await fetch(`${API_BASE}/compiler/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: wsId, ...options })
    });
    return res.json();
  },

  // Static Analysis
  async runStaticAnalysis(wsId: string, targetFile?: string): Promise<{ total_findings: number; findings: DiagnosticItem[] }> {
    const res = await fetch(`${API_BASE}/analysis/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: wsId, target_file: targetFile })
    });
    return res.json();
  },

  // Debugger
  async createDebugSession(wsId: string, executableName: string = 'app_debug'): Promise<DebugSessionSnapshot> {
    const res = await fetch(`${API_BASE}/debugger/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: wsId, executable_name: executableName })
    });
    return res.json();
  },

  async getDebugSession(sessionId: string): Promise<DebugSessionSnapshot> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}`);
    return res.json();
  },

  async startDebugSession(sessionId: string, args?: string[]): Promise<{ success: boolean; snapshot: DebugSessionSnapshot }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ args })
    });
    return res.json();
  },

  async stepOver(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/step-over`, { method: 'POST' });
    return res.json();
  },

  async stepInto(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/step-into`, { method: 'POST' });
    return res.json();
  },

  async stepOut(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/step-out`, { method: 'POST' });
    return res.json();
  },

  async continueDebug(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/continue`, { method: 'POST' });
    return res.json();
  },

  async pauseDebug(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/pause`, { method: 'POST' });
    return res.json();
  },

  async runToCursor(sessionId: string, file: string, line: number): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/run-to-cursor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file, line })
    });
    return res.json();
  },

  async addBreakpoint(sessionId: string, file: string, line: number, condition?: string): Promise<Breakpoint> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/breakpoints`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file, line, condition })
    });
    return res.json();
  },

  async deleteBreakpoint(sessionId: string, bpId: number): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/breakpoints/${bpId}`, { method: 'DELETE' });
    return res.json();
  },

  async selectFrame(sessionId: string, level: number): Promise<{ success: boolean; snapshot: DebugSessionSnapshot }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/frames/${level}`, { method: 'POST' });
    return res.json();
  },

  async evaluateExpression(sessionId: string, expression: string): Promise<{ success: boolean; expression: string; value?: string; error?: string }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expression })
    });
    return res.json();
  },

  async readMemory(sessionId: string, address: string, count: number = 64): Promise<{ success: boolean; address: string; memory?: any[]; error?: string }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, count })
    });
    return res.json();
  },

  async sendStdin(sessionId: string, inputText: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/stdin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input_text: inputText })
    });
    return res.json();
  },

  async terminateSession(sessionId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/debugger/sessions/${sessionId}/terminate`, { method: 'POST' });
    return res.json();
  },

  // AutoDebugger
  async runAutoDebug(wsId: string, options?: { target_name?: string; args?: string[]; enable_strace?: boolean }): Promise<AutoDebugResult> {
    const res = await fetch(`${API_BASE}/autodebug/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: wsId, ...options })
    });
    return res.json();
  },

  // Test Cases
  async listTests(wsId: string): Promise<TestCase[]> {
    const res = await fetch(`${API_BASE}/tests/${wsId}`);
    return res.json();
  },

  async createTestCase(wsId: string, testData: { name: string; args?: string[]; stdin_data?: string; expected_output?: string; expected_exit_code?: number }): Promise<{ id: string; success: boolean }> {
    const res = await fetch(`${API_BASE}/tests/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: wsId, ...testData })
    });
    return res.json();
  },

  async deleteTestCase(tcId: string): Promise<{ success: boolean }> {
    const res = await fetch(`${API_BASE}/tests/${tcId}`, { method: 'DELETE' });
    return res.json();
  },

  async runTestCase(tcId: string, targetName: string = 'app_debug'): Promise<any> {
    const res = await fetch(`${API_BASE}/tests/${tcId}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_name: targetName })
    });
    return res.json();
  },

  // Reports
  async listReports(wsId?: string): Promise<any[]> {
    const url = wsId ? `${API_BASE}/reports/?workspace_id=${wsId}` : `${API_BASE}/reports/`;
    const res = await fetch(url);
    return res.json();
  },

  async getReport(reportId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/reports/${reportId}`);
    return res.json();
  },

  async exportReportMarkdown(reportId: string): Promise<string> {
    const res = await fetch(`${API_BASE}/reports/${reportId}/export/markdown`);
    return res.text();
  },

  // Settings & Toolchain
  async getToolchain(): Promise<ToolchainInfo> {
    const res = await fetch(`${API_BASE}/settings/toolchain`);
    return res.json();
  }
};
