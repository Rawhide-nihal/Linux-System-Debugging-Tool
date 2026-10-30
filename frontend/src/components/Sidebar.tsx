import React from 'react';
import {
  FolderGit2,
  Code2,
  Bug,
  Sparkles,
  AlertTriangle,
  Binary,
  CheckCircle2,
  History,
  FileText,
  Settings as SettingsIcon
} from 'lucide-react';
import { ScreenType } from '../types';

interface SidebarProps {
  activeScreen: ScreenType;
  onSelectScreen: (screen: ScreenType) => void;
  problemsCount: number;
  testCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeScreen,
  onSelectScreen,
  problemsCount,
  testCount
}) => {
  const items: Array<{ id: ScreenType; label: string; icon: React.FC<any>; badge?: number; badgeColor?: string }> = [
    { id: 'workspace', label: 'Workspace', icon: FolderGit2 },
    { id: 'editor', label: 'Source Editor', icon: Code2 },
    { id: 'debugger', label: 'Debugger', icon: Bug },
    { id: 'autodebug', label: 'AutoDebugger', icon: Sparkles },
    { id: 'problems', label: 'Problems', icon: AlertTriangle, badge: problemsCount, badgeColor: 'bg-rose-500' },
    { id: 'memory', label: 'Memory Inspector', icon: Binary },
    { id: 'tests', label: 'Test Cases', icon: CheckCircle2, badge: testCount, badgeColor: 'bg-blue-500' },
    { id: 'sessions', label: 'Debug Sessions', icon: History },
    { id: 'reports', label: 'Reports', icon: FileText },
    { id: 'settings', label: 'Settings', icon: SettingsIcon }
  ];

  return (
    <aside className="w-16 md:w-56 bg-slate-950 border-r border-slate-800 flex flex-col justify-between select-none">
      <div className="py-3 flex flex-col space-y-1">
        <div className="hidden md:block px-4 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-300">
          Workbench
        </div>
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = activeScreen === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectScreen(item.id)}
              className={`flex items-center justify-between px-3 md:px-4 py-2 mx-1.5 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              <div className="flex items-center space-x-3">
                <Icon className={`w-4 h-4 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
                <span className="hidden md:inline">{item.label}</span>
              </div>
              {item.badge !== undefined && item.badge > 0 && (
                <span
                  className={`hidden md:inline-flex items-center px-1.5 py-0.2 rounded-full text-[10px] font-bold text-white ${
                    item.badgeColor || 'bg-slate-700'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="p-3 border-t border-slate-900 hidden md:block">
        <div className="text-[11px] text-slate-300 font-mono">
          Environment: Linux GDB/MI3
        </div>
      </div>
    </aside>
  );
};
