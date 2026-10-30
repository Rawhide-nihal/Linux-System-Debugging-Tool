import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  XCircle,
  Play,
  Plus,
  Trash2,
  Bug,
  Clock,
  ArrowRight,
  ShieldCheck,
  FileText
} from 'lucide-react';
import { Workspace, TestCase, ScreenType } from '../types';
import { api } from '../services/api';

interface TestCasesScreenProps {
  currentWorkspace: Workspace | null;
  onNavigate: (screen: ScreenType) => void;
  onLaunchDebugWithArgs?: (args: string[], stdin: string) => void;
}

export const TestCasesScreen: React.FC<TestCasesScreenProps> = ({
  currentWorkspace,
  onNavigate,
  onLaunchDebugWithArgs
}) => {
  const [tests, setTests] = useState<TestCase[]>([]);
  const [isRunning, setIsRunning] = useState<Record<string, boolean>>({});
  const [showAddModal, setShowAddModal] = useState(false);

  // New test form state
  const [newName, setNewName] = useState('');
  const [newArgs, setNewArgs] = useState('');
  const [newStdin, setNewStdin] = useState('');
  const [newExpectedOut, setNewExpectedOut] = useState('');
  const [newExpectedExit, setNewExpectedExit] = useState(0);

  const fetchTests = async () => {
    if (!currentWorkspace) return;
    try {
      const data = await api.listTests(currentWorkspace.id);
      setTests(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchTests();
  }, [currentWorkspace]);

  const handleCreateTest = async () => {
    if (!currentWorkspace || !newName.trim()) return;
    const argsArr = newArgs.trim() ? newArgs.trim().split(/\s+/) : [];
    await api.createTestCase(currentWorkspace.id, {
      name: newName.trim(),
      args: argsArr,
      stdin_data: newStdin,
      expected_output: newExpectedOut,
      expected_exit_code: Number(newExpectedExit)
    });
    setShowAddModal(false);
    setNewName('');
    setNewArgs('');
    setNewStdin('');
    setNewExpectedOut('');
    fetchTests();
  };

  const handleRunTest = async (testId: string) => {
    setIsRunning((prev) => ({ ...prev, [testId]: true }));
    try {
      await api.runTestCase(testId);
      await fetchTests();
    } catch (e: any) {
      alert('Execution failed: ' + e.message);
    } finally {
      setIsRunning((prev) => ({ ...prev, [testId]: false }));
    }
  };

  const handleRunAll = async () => {
    for (const t of tests) {
      await handleRunTest(t.id);
    }
  };

  const handleDeleteTest = async (testId: string) => {
    await api.deleteTestCase(testId);
    fetchTests();
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
              <CheckCircle2 className="w-5 h-5 text-blue-400" />
              <span>Logic Bug Test Cases & Verification</span>
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Verify program correctness against expected inputs, outputs, and exit codes.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleRunAll}
              disabled={tests.length === 0}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium disabled:opacity-40 transition-colors"
            >
              <Play className="w-3.5 h-3.5 fill-slate-200" />
              <span>Run All Tests</span>
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              disabled={!currentWorkspace}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold disabled:opacity-40 transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>New Test Case</span>
            </button>
          </div>
        </div>

        {/* Test Creation Modal */}
        {showAddModal && (
          <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-4">
            <h2 className="text-sm font-semibold text-slate-200">Define New Test Case</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Test Case Name</label>
                <input
                  type="text"
                  placeholder="e.g. Boundary marks check, Factorial of 5"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white outline-none"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">CLI Arguments (space-separated)</label>
                <input
                  type="text"
                  placeholder="e.g. --verbose input.dat"
                  value={newArgs}
                  onChange={(e) => setNewArgs(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white outline-none font-mono"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">Standard Input (stdin)</label>
                <textarea
                  placeholder="Data provided to stdin (e.g. 35\n)"
                  value={newStdin}
                  onChange={(e) => setNewStdin(e.target.value)}
                  rows={3}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white outline-none font-mono"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">Expected Output (stdout)</label>
                <textarea
                  placeholder="Expected output string"
                  value={newExpectedOut}
                  onChange={(e) => setNewExpectedOut(e.target.value)}
                  rows={3}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white outline-none font-mono"
                />
              </div>
            </div>

            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateTest}
                disabled={!newName.trim()}
                className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold disabled:opacity-40"
              >
                Save Test Case
              </button>
            </div>
          </div>
        )}

        {/* Tests List */}
        <div className="space-y-4">
          {tests.length === 0 ? (
            <div className="p-12 text-center rounded-lg bg-slate-950 border border-slate-800 text-slate-300">
              No test cases created for this workspace yet. Click "New Test Case" to add one.
            </div>
          ) : (
            tests.map((t) => {
              const run = t.last_run;
              return (
                <div
                  key={t.id}
                  className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      {run ? (
                        run.passed ? (
                          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                        ) : (
                          <XCircle className="w-5 h-5 text-rose-400" />
                        )
                      ) : (
                        <div className="w-5 h-5 rounded-full border border-slate-700 flex items-center justify-center text-[10px] text-slate-400">
                          -
                        </div>
                      )}
                      <div>
                        <div className="text-sm font-bold text-slate-100">{t.name}</div>
                        {run && (
                          <div className="text-[11px] text-slate-400 flex items-center space-x-2 mt-0.5">
                            <span>Status: {run.passed ? 'PASSED' : 'FAILED'}</span>
                            <span>•</span>
                            <span>Duration: {run.duration_ms}ms</span>
                            <span>•</span>
                            <span>Exit Code: {run.actual_exit_code}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleRunTest(t.id)}
                        disabled={isRunning[t.id]}
                        className="flex items-center space-x-1 px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium"
                      >
                        <Play className="w-3 h-3 fill-slate-200" />
                        <span>{isRunning[t.id] ? 'Running...' : 'Run'}</span>
                      </button>

                      <button
                        onClick={() => handleDeleteTest(t.id)}
                        className="p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-rose-400"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Verification Banner if verified */}
                  {run?.verification && (
                    <div className="p-2.5 rounded bg-emerald-950/30 border border-emerald-800/50 text-xs text-emerald-300 flex items-center space-x-2">
                      <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span>{run.verification.status_summary}</span>
                    </div>
                  )}

                  {/* Diff Viewer if failed */}
                  {run && !run.passed && run.diff && (
                    <div className="p-3 rounded bg-slate-900 border border-slate-800 text-xs font-mono space-y-1">
                      <div className="text-[10px] text-slate-300 uppercase font-semibold">Output Diff (- Expected, + Actual):</div>
                      <pre className="text-rose-400 whitespace-pre-wrap">{run.diff}</pre>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
