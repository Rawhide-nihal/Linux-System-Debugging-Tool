import React, { useState, useEffect, useRef } from 'react';
import Editor, { OnMount } from '@monaco-editor/react';
import {
  FileCode,
  Folder,
  FolderOpen,
  Save,
  Hammer,
  AlertCircle,
  FilePlus,
  RefreshCw,
  Search,
  Check
} from 'lucide-react';
import { Workspace, FileNode, DiagnosticItem, Breakpoint } from '../types';
import { api } from '../services/api';

interface EditorScreenProps {
  currentWorkspace: Workspace | null;
  onBuild: () => void;
  isBuilding: boolean;
  diagnostics: DiagnosticItem[];
  breakpoints: Breakpoint[];
  onToggleBreakpoint: (file: string, line: number) => void;
  currentExecutionLine?: { file: string; line: number } | null;
}

export const EditorScreen: React.FC<EditorScreenProps> = ({
  currentWorkspace,
  onBuild,
  isBuilding,
  diagnostics,
  breakpoints,
  onToggleBreakpoint,
  currentExecutionLine
}) => {
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [modifiedFiles, setModifiedFiles] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{ file: string; line: number; content: string }>>([]);
  const [isSavedNotice, setIsSavedNotice] = useState(false);

  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);

  // Initialize with main.c or first .c file
  useEffect(() => {
    if (currentWorkspace?.tree) {
      const findFirstCFile = (node: FileNode): string | null => {
        if (node.type === 'file' && node.name.endsWith('.c')) return node.path;
        if (node.children) {
          for (const c of node.children) {
            const found = findFirstCFile(c);
            if (found) return found;
          }
        }
        return null;
      };
      const first = findFirstCFile(currentWorkspace.tree);
      if (first && openTabs.length === 0) {
        openFile(first);
      }
    }
  }, [currentWorkspace]);

  const openFile = async (filePath: string) => {
    if (!currentWorkspace) return;
    if (!openTabs.includes(filePath)) {
      setOpenTabs([...openTabs, filePath]);
    }
    setActiveFile(filePath);

    if (!fileContents[filePath]) {
      try {
        const res = await api.readFile(currentWorkspace.id, filePath);
        setFileContents((prev) => ({ ...prev, [filePath]: res.content }));
      } catch (e) {
        console.error('Failed to read file:', e);
      }
    }
  };

  const closeTab = (filePath: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = openTabs.filter((t) => t !== filePath);
    setOpenTabs(next);
    if (activeFile === filePath) {
      setActiveFile(next.length > 0 ? next[next.length - 1] : null);
    }
  };

  const saveCurrentFile = async () => {
    if (!currentWorkspace || !activeFile) return;
    const content = fileContents[activeFile] ?? '';
    try {
      await api.writeFile(currentWorkspace.id, activeFile, content);
      setModifiedFiles((prev) => {
        const next = new Set(prev);
        next.delete(activeFile);
        return next;
      });
      setIsSavedNotice(true);
      setTimeout(() => setIsSavedNotice(false), 2000);
    } catch (e) {
      alert('Failed to save file');
    }
  };

  // Keyboard shortcut Ctrl+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveCurrentFile();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentWorkspace, activeFile, fileContents]);

  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    // Listen for glyph margin clicks for breakpoint toggling
    editor.onMouseDown((e) => {
      if (e.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN) {
        const line = e.target.position?.lineNumber;
        if (line && activeFile) {
          onToggleBreakpoint(activeFile, line);
        }
      }
    });

    updateDecorations();
  };

  const updateDecorations = () => {
    if (!editorRef.current || !monacoRef.current || !activeFile) return;

    const decorations: any[] = [];

    // Breakpoint markers
    breakpoints
      .filter((bp) => bp.file.endsWith(activeFile) || activeFile.endsWith(bp.file))
      .forEach((bp) => {
        decorations.push({
          range: new monacoRef.current.Range(bp.line, 1, bp.line, 1),
          options: {
            isWholeLine: false,
            glyphMarginClassName: 'bg-rose-500 rounded-full w-2.5 h-2.5 ml-1 mt-1 cursor-pointer',
            glyphMarginHoverMessage: { value: `Breakpoint (Line ${bp.line})` }
          }
        });
      });

    // Current execution line marker (yellow/cyan highlight)
    if (
      currentExecutionLine &&
      (currentExecutionLine.file.endsWith(activeFile) || activeFile.endsWith(currentExecutionLine.file))
    ) {
      decorations.push({
        range: new monacoRef.current.Range(
          currentExecutionLine.line,
          1,
          currentExecutionLine.line,
          1
        ),
        options: {
          isWholeLine: true,
          className: 'bg-yellow-500/20 border-l-2 border-yellow-400',
          glyphMarginClassName: 'text-yellow-400 font-bold ml-1'
        }
      });
    }

    // Diagnostics squiggles
    const model = editorRef.current.getModel();
    if (model) {
      const markers = diagnostics
        .filter((d) => d.line && (d.file.endsWith(activeFile) || activeFile.endsWith(d.file)))
        .map((d) => ({
          startLineNumber: d.line!,
          startColumn: d.column || 1,
          endLineNumber: d.line!,
          endColumn: (d.column || 1) + 5,
          message: d.message,
          severity:
            d.severity === 'error'
              ? monacoRef.current.MarkerSeverity.Error
              : monacoRef.current.MarkerSeverity.Warning
        }));
      monacoRef.current.editor.setModelMarkers(model, 'compiler', markers);
    }
  };

  useEffect(() => {
    updateDecorations();
  }, [breakpoints, currentExecutionLine, diagnostics, activeFile]);

  const renderFileTree = (node: FileNode) => {
    if (node.type === 'directory') {
      return (
        <div key={node.path || node.name} className="space-y-1">
          {node.name && (
            <div className="flex items-center space-x-1.5 text-xs text-slate-400 font-medium px-2 py-1 select-none">
              <Folder className="w-3.5 h-3.5 text-cyan-400" />
              <span>{node.name}</span>
            </div>
          )}
          <div className="pl-3 space-y-0.5 border-l border-slate-800 ml-2">
            {node.children?.map(renderFileTree)}
          </div>
        </div>
      );
    }

    const isActive = activeFile === node.path;
    const isModified = modifiedFiles.has(node.path);

    return (
      <button
        key={node.path}
        onClick={() => openFile(node.path)}
        className={`w-full flex items-center justify-between px-2 py-1 rounded text-xs transition-colors ${
          isActive
            ? 'bg-cyan-500/10 text-cyan-400 font-medium'
            : 'text-slate-300 hover:bg-slate-800/60'
        }`}
      >
        <div className="flex items-center space-x-1.5 truncate">
          <FileCode className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="truncate">{node.name}</span>
        </div>
        {isModified && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />}
      </button>
    );
  };

  const handleSearch = async () => {
    if (!currentWorkspace || !searchQuery.trim()) return;
    const res = await api.searchWorkspace(currentWorkspace.id, searchQuery);
    setSearchResults(res.results);
  };

  return (
    <div className="flex-1 flex overflow-hidden bg-slate-900">
      {/* File Tree Sidebar */}
      <div className="w-56 bg-slate-950 border-r border-slate-800 flex flex-col">
        <div className="p-2.5 border-b border-slate-800 flex items-center justify-between text-xs font-semibold text-slate-400">
          <span>SOURCE EXPLORER</span>
          <div className="flex items-center space-x-1">
            <button
              onClick={saveCurrentFile}
              title="Save File (Ctrl+S)"
              className="p-1 hover:bg-slate-800 rounded text-slate-300"
            >
              {isSavedNotice ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Save className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="p-2 border-b border-slate-900">
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded px-2 py-1">
            <Search className="w-3 h-3 text-slate-400 shrink-0 mr-1.5" />
            <input
              type="text"
              placeholder="Search code..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="w-full bg-transparent text-xs text-slate-200 outline-none"
            />
          </div>
        </div>

        {/* Tree List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {searchResults.length > 0 ? (
            <div className="space-y-1">
              <div className="text-[10px] text-slate-300 uppercase px-1">
                Matches ({searchResults.length})
              </div>
              {searchResults.map((m, idx) => (
                <button
                  key={idx}
                  onClick={() => openFile(m.file)}
                  className="w-full text-left p-1.5 rounded hover:bg-slate-800 text-[11px] block text-slate-300 truncate"
                >
                  <span className="text-cyan-400">{m.file}:{m.line}</span>
                  <div className="truncate text-slate-400">{m.content}</div>
                </button>
              ))}
            </div>
          ) : currentWorkspace?.tree ? (
            renderFileTree(currentWorkspace.tree)
          ) : (
            <div className="text-xs text-slate-300 p-2">No files loaded</div>
          )}
        </div>
      </div>

      {/* Monaco Editor Center */}
      <div className="flex-1 flex flex-col bg-slate-900">
        {/* Tabs Bar */}
        <div className="h-9 bg-slate-950 border-b border-slate-800 flex items-center overflow-x-auto px-1 space-x-1 select-none">
          {openTabs.map((tab) => {
            const isTabActive = activeFile === tab;
            const isModified = modifiedFiles.has(tab);
            const fileName = tab.split('/').pop() || tab;
            return (
              <div
                key={tab}
                onClick={() => setActiveFile(tab)}
                className={`flex items-center space-x-2 px-3 py-1.5 rounded-t text-xs cursor-pointer border-t-2 transition-colors ${
                  isTabActive
                    ? 'bg-slate-900 border-cyan-400 text-slate-100 font-medium'
                    : 'bg-slate-950 border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>{fileName}</span>
                {isModified && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                <button
                  onClick={(e) => closeTab(tab, e)}
                  className="hover:text-rose-400 text-slate-300 rounded p-0.5"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>

        {/* Editor Area */}
        <div className="flex-1 relative">
          {activeFile ? (
            <Editor
              height="100%"
              theme="vs-dark"
              language="c"
              value={fileContents[activeFile] ?? ''}
              onChange={(value) => {
                if (value !== undefined) {
                  setFileContents((prev) => ({ ...prev, [activeFile]: value }));
                  setModifiedFiles((prev) => new Set(prev).add(activeFile));
                }
              }}
              onMount={handleEditorMount}
              options={{
                fontSize: 13,
                fontFamily: "'Fira Code', Consolas, monospace",
                lineNumbers: 'on',
                glyphMargin: true,
                folding: true,
                minimap: { enabled: true },
                automaticLayout: true,
                scrollBeyondLastLine: false,
                renderLineHighlight: 'all',
                fixedOverflowWidgets: true
              }}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-slate-300">
              Select or open a C source file to edit.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
