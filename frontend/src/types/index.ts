export type ScreenType =
  | 'workspace'
  | 'editor'
  | 'debugger'
  | 'autodebug'
  | 'problems'
  | 'memory'
  | 'tests'
  | 'sessions'
  | 'reports'
  | 'settings';

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  extension?: string;
  children?: FileNode[];
}

export interface Workspace {
  id: string;
  name: string;
  path: string;
  config: {
    compiler?: string;
    std?: string;
    optimization?: string;
    cflags?: string[];
    ldflags?: string[];
    target_name?: string;
    build_mode?: string;
  };
  tree?: FileNode;
  created_at: string;
  updated_at: string;
}

export interface DiagnosticItem {
  file: string;
  line: number | null;
  column: number | null;
  severity: 'error' | 'warning' | 'note';
  message: string;
  raw: string;
  category: string;
  snippet?: string;
  analysis_kind?: string;
}

export interface BuildResult {
  success: boolean;
  returncode: number;
  binary_path: string | null;
  command: string;
  stdout: string;
  stderr: string;
  diagnostics: DiagnosticItem[];
}

export interface Breakpoint {
  id: number;
  file: string;
  line: number;
  condition: string;
  enabled: boolean;
  hit_count: number;
}

export interface Variable {
  name: string;
  type: string;
  value: string;
  status?: string;
}

export interface StackFrame {
  level: number;
  func: string;
  file: string;
  line: number | null;
  addr?: string;
}

export interface TimelineItem {
  timestamp: string;
  event: string;
  description: string;
  file?: string;
  line?: number | null;
  func?: string;
}

export interface DebugSessionSnapshot {
  session_id: string;
  state: 'NOT_STARTED' | 'STARTING' | 'RUNNING' | 'STOPPED' | 'TERMINATED' | 'CRASHED';
  executable: string;
  file?: string;
  line?: number | null;
  func?: string;
  frame_level: number;
  stop_reason?: string;
  stop_signal?: string;
  exit_code?: number | null;
  breakpoints: Breakpoint[];
  variables: Variable[];
  arguments: Variable[];
  call_stack: StackFrame[];
  timeline: TimelineItem[];
  stdout: string;
  stderr: string;
  created_at: string;
  completed_at?: string;
}

export interface Finding {
  category: string;
  title: string;
  file?: string;
  line?: number;
  column?: number;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  evidence?: string;
  confidence: string;
  suggested_action?: string;
  variables?: Variable[];
  call_stack?: StackFrame[];
}

export interface AutoDebugResult {
  success: boolean;
  verdict: string;
  stages: Array<{ stage: string; status: string; detail: string }>;
  findings: Finding[];
  binary_path?: string;
  exit_code?: number;
  signal?: string;
  report_id?: string;
}

export interface TestCase {
  id: string;
  workspace_id: string;
  name: string;
  args: string[];
  stdin_data: string;
  expected_output: string;
  expected_exit_code: number;
  last_run?: {
    passed: boolean;
    output_match: boolean;
    exit_code_match: boolean;
    timed_out: boolean;
    duration_ms: number;
    actual_stdout: string;
    actual_stderr: string;
    actual_exit_code: number;
    expected_exit_code: number;
    diff: string;
    verification?: {
      is_resolved: boolean;
      status_summary: string;
    };
  };
  created_at: string;
}

export interface ToolchainInfo {
  platform: string;
  ready: boolean;
  gcc: { available: boolean; path: string | null; version: string | null };
  gdb: { available: boolean; path: string | null; version: string | null };
  make: { available: boolean; path: string | null; version: string | null };
  strace: { available: boolean; path: string | null; version: string | null };
  clang: { available: boolean; path: string | null; version: string | null };
  valgrind: { available: boolean; path: string | null; version: string | null };
}
