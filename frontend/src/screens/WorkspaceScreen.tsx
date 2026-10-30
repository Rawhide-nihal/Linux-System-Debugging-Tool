import React, { useState } from 'react';
import {
  FolderPlus,
  Upload,
  Folder,
  Layers,
  FileCode,
  CheckCircle,
  Trash2,
  ArrowRight
} from 'lucide-react';
import { Workspace, ScreenType } from '../types';
import { api } from '../services/api';

interface WorkspaceScreenProps {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  onSelectWorkspace: (ws: Workspace) => void;
  onRefreshWorkspaces: () => void;
  onNavigate: (screen: ScreenType) => void;
}

export const WorkspaceScreen: React.FC<WorkspaceScreenProps> = ({
  workspaces,
  currentWorkspace,
  onSelectWorkspace,
  onRefreshWorkspaces,
  onNavigate
}) => {
  const [newProjectName, setNewProjectName] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState('basic_app');
  const [isCreating, setIsCreating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const templates = [
    {
      id: 'basic_app',
      name: 'Single-File C Program',
      desc: 'Standard C application calculating factorial recursively with clean logic.'
    },
    {
      id: 'multi_file_calc',
      name: 'Multi-File Modular Project',
      desc: 'Multi-module project with header files, calc library, and official Makefile.'
    },
    {
      id: 'segfault_repro',
      name: 'Pointer Crash Reproducer',
      desc: 'Reproducible NULL pointer dereference crash to inspect SIGSEGV and call stack.'
    },
    {
      id: 'logic_bug_boundary',
      name: 'Boundary Logic Bug Target',
      desc: 'Failing conditional boundary check (marks > 35 vs >= 35) to verify test cases.'
    },
    {
      id: 'interactive_menu',
      name: 'Interactive Terminal I/O Menu',
      desc: 'Menu-driven loop with scanf() to test genuine interactive stdin in terminal.'
    }
  ];

  const handleCreate = async () => {
    if (!newProjectName.trim()) return;
    setIsCreating(true);
    try {
      const ws = await api.createWorkspace(newProjectName.trim(), selectedTemplate);
      onRefreshWorkspaces();
      onSelectWorkspace(ws);
      setNewProjectName('');
      onNavigate('editor');
    } catch (e: any) {
      alert('Failed to create workspace: ' + e.message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleZipUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    try {
      const name = file.name.replace(/\.zip$/i, '');
      const ws = await api.importZip(file, name);
      onRefreshWorkspaces();
      onSelectWorkspace(ws);
      onNavigate('editor');
    } catch (err: any) {
      setUploadError(err.message || 'ZIP extraction error');
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Delete this workspace and all files?')) {
      await api.deleteWorkspace(id);
      onRefreshWorkspaces();
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
            <Layers className="w-5 h-5 text-cyan-400" />
            <span>Project Workspaces</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Create or import real Linux C projects with full source trees, compilation, and interactive debugging.
          </p>
        </div>

        {/* Current Active Workspace Pill */}
        {currentWorkspace && (
          <div className="p-4 rounded-lg bg-cyan-950/30 border border-cyan-800/50 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <CheckCircle className="w-5 h-5 text-cyan-400" />
              <div>
                <div className="text-sm font-semibold text-white">Active Project: {currentWorkspace.name}</div>
                <div className="text-xs text-slate-400 font-mono">{currentWorkspace.path}</div>
              </div>
            </div>
            <button
              onClick={() => onNavigate('editor')}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors"
            >
              <span>Open in Editor</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Create New Workspace */}
          <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-4">
            <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
              <FolderPlus className="w-4 h-4 text-emerald-400" />
              <span>Create New C Project</span>
            </h2>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Project Name</label>
                <input
                  type="text"
                  placeholder="e.g. system_monitor, math_eval"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Starter Template</label>
                <div className="space-y-2">
                  {templates.map((t) => (
                    <label
                      key={t.id}
                      className={`block p-2.5 rounded border cursor-pointer text-xs transition-colors ${
                        selectedTemplate === t.id
                          ? 'border-cyan-500 bg-cyan-500/10'
                          : 'border-slate-800 bg-slate-900 hover:border-slate-700'
                      }`}
                    >
                      <input
                        type="radio"
                        name="template"
                        value={t.id}
                        checked={selectedTemplate === t.id}
                        onChange={() => setSelectedTemplate(t.id)}
                        className="hidden"
                      />
                      <div className="font-medium text-slate-200">{t.name}</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">{t.desc}</div>
                    </label>
                  ))}
                </div>
              </div>

              <button
                onClick={handleCreate}
                disabled={!newProjectName.trim() || isCreating}
                className="w-full py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold disabled:opacity-40 transition-colors"
              >
                {isCreating ? 'Creating...' : 'Initialize Project'}
              </button>
            </div>
          </div>

          {/* Import ZIP & Workspace List */}
          <div className="space-y-6">
            {/* Import ZIP */}
            <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-3">
              <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
                <Upload className="w-4 h-4 text-blue-400" />
                <span>Import C Project Archive</span>
              </h2>
              <p className="text-xs text-slate-400">
                Upload a ZIP archive containing C source files, headers, and Makefiles. Extracted safely with path traversal protection.
              </p>
              <label className="flex items-center justify-center border-2 border-dashed border-slate-700 hover:border-cyan-500/60 rounded-lg p-4 cursor-pointer transition-colors bg-slate-900/50">
                <input type="file" accept=".zip" onChange={handleZipUpload} className="hidden" />
                <div className="text-center">
                  <FileCode className="w-6 h-6 text-slate-400 mx-auto mb-1" />
                  <span className="text-xs text-slate-300 font-medium">Select .ZIP Archive</span>
                </div>
              </label>
              {uploadError && <div className="text-xs text-rose-400">{uploadError}</div>}
            </div>

            {/* Existing Workspaces */}
            <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 space-y-3">
              <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
                <Folder className="w-4 h-4 text-slate-400" />
                <span>Recent Workspaces</span>
              </h2>

              <div className="space-y-2 max-h-60 overflow-y-auto">
                {workspaces.length === 0 ? (
                  <div className="text-xs text-slate-300 py-3 text-center">No projects created yet.</div>
                ) : (
                  workspaces.map((ws) => (
                    <div
                      key={ws.id}
                      onClick={() => {
                        onSelectWorkspace(ws);
                        onNavigate('editor');
                      }}
                      className={`flex items-center justify-between p-2.5 rounded border cursor-pointer transition-colors ${
                        currentWorkspace?.id === ws.id
                          ? 'border-cyan-500 bg-cyan-950/20'
                          : 'border-slate-800 bg-slate-900 hover:border-slate-700'
                      }`}
                    >
                      <div>
                        <div className="text-xs font-medium text-slate-200">{ws.name}</div>
                        <div className="text-[10px] text-slate-300 font-mono truncate max-w-xs">{ws.path}</div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={(e) => handleDelete(ws.id, e)}
                          title="Delete Workspace"
                          className="p-1 rounded hover:bg-slate-800 text-slate-300 hover:text-rose-400 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
