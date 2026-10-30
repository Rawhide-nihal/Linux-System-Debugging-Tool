import React, { useState } from 'react';
import {
  Binary,
  Search,
  RefreshCw,
  Eye,
  AlertCircle
} from 'lucide-react';
import { DebugSessionSnapshot } from '../types';
import { api } from '../services/api';

interface MemoryScreenProps {
  session: DebugSessionSnapshot | null;
}

export const MemoryScreen: React.FC<MemoryScreenProps> = ({ session }) => {
  const [addressInput, setAddressInput] = useState('0x7fffffffe4f0');
  const [byteCount, setByteCount] = useState(64);
  const [memoryData, setMemoryData] = useState<any[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchMemory = async () => {
    if (!session || !addressInput.trim()) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.readMemory(session.session_id, addressInput.trim(), byteCount);
      if (res.success && res.memory) {
        setMemoryData(res.memory);
      } else {
        setErrorMsg(res.error || 'Failed to read memory from GDB.');
      }
    } catch (e: any) {
      setErrorMsg(e.message || 'Memory read error');
    } finally {
      setIsLoading(false);
    }
  };

  // Convert raw hex stream to 16-byte formatted rows
  const formatHexDump = () => {
    if (memoryData.length === 0) return [];
    const rows = [];
    for (const block of memoryData) {
      const beginAddr = parseInt(block.begin, 16) || 0;
      const hexStr = block.contents || '';
      for (let i = 0; i < hexStr.length; i += 32) {
        const chunk = hexStr.slice(i, i + 32);
        const bytes = [];
        let ascii = '';
        for (let b = 0; b < chunk.length; b += 2) {
          const byteHex = chunk.slice(b, b + 2);
          bytes.push(byteHex);
          const charCode = parseInt(byteHex, 16);
          ascii += charCode >= 32 && charCode <= 126 ? String.fromCharCode(charCode) : '.';
        }
        const rowAddr = '0x' + (beginAddr + i / 2).toString(16).padStart(12, '0');
        rows.push({ address: rowAddr, bytes, ascii });
      }
    }
    return rows;
  };

  const rows = formatHexDump();

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-slate-900 text-slate-100">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
            <Binary className="w-5 h-5 text-cyan-400" />
            <span>Memory Inspector</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Examine runtime heap, stack, and pointer addresses directly from GDB memory reads.
          </p>
        </div>

        {/* Address Search Bar */}
        <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[200px] flex items-center bg-slate-900 border border-slate-700 rounded px-3 py-1.5">
            <Search className="w-4 h-4 text-slate-400 mr-2 shrink-0" />
            <input
              type="text"
              placeholder="Address (e.g. 0x7fffffffe4f0, &num, ptr)"
              value={addressInput}
              onChange={(e) => setAddressInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fetchMemory()}
              className="w-full bg-transparent text-xs text-slate-200 outline-none font-mono"
            />
          </div>

          <div className="flex items-center space-x-2 text-xs">
            <span className="text-slate-400">Bytes:</span>
            <select
              value={byteCount}
              onChange={(e) => setByteCount(Number(e.target.value))}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
            >
              <option value={32}>32 Bytes</option>
              <option value={64}>64 Bytes</option>
              <option value={128}>128 Bytes</option>
              <option value={256}>256 Bytes</option>
            </select>
          </div>

          <button
            onClick={fetchMemory}
            disabled={!session || isLoading}
            className="flex items-center space-x-1.5 px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold disabled:opacity-40 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Read Memory</span>
          </button>
        </div>

        {errorMsg && (
          <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-800/60 text-rose-300 text-xs flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Hex Dump Table */}
        <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider pb-2 border-b border-slate-800 grid grid-cols-12 gap-2">
            <div className="col-span-3">Address</div>
            <div className="col-span-6">Hex Bytes (16 bytes / row)</div>
            <div className="col-span-3 text-right">ASCII</div>
          </div>

          <div className="pt-2 space-y-1">
            {rows.length === 0 ? (
              <div className="text-slate-300 py-6 text-center text-xs">
                {session ? 'Enter an address or pointer and click Read Memory.' : 'Start a debug session to inspect process memory.'}
              </div>
            ) : (
              rows.map((r, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 py-0.5 hover:bg-slate-900/60 px-1 rounded">
                  <div className="col-span-3 text-cyan-400">{r.address}</div>
                  <div className="col-span-6 flex space-x-1.5 text-slate-300">
                    {r.bytes.map((b, bIdx) => (
                      <span key={bIdx} className={b === '00' ? 'text-slate-300' : 'text-slate-200'}>
                        {b}
                      </span>
                    ))}
                  </div>
                  <div className="col-span-3 text-right text-emerald-400">{r.ascii}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
