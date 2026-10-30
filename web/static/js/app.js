/* ==========================================================================
   LDST — Linux System Debugging Tool
   Workspace Frontend Controller (web/static/js/app.js)
   All displayed diagnostics, PIDs, syscalls, errno values, /proc metrics,
   and GDB backtraces originate strictly from the backend & C engine.
   ========================================================================== */

const STATE = {
  currentView: 'dashboard',
  programs: { builtin: [], custom: [] },
  activeSessionId: null,
  pollTimer: null,
  currentResult: null,
  memChart: null,
  cpuChart: null,
  editorLastCompiledSuccess: false,
  editorLastCompiledName: '',
  interactiveSessionId: null,
  interactiveSession: null,
  interactiveBreakpoints: new Set(),
  interactiveSourceLines: [],
  interactiveLoadedProg: ''
};

const STARTER_TEMPLATES = {
  hello: `#include <stdio.h>
#include <unistd.h>

int main(void)
{
    printf("Custom LDST test program started (PID: %d)\\n", (int)getpid());
    printf("All operations completed cleanly.\\n");
    return 0;
}
`,
  file_missing: `#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

int main(void)
{
    printf("Attempting to open a nonexistent configuration file...\\n");
    int fd = open("nonexistent_config_file.conf", O_RDONLY);
    if (fd == -1) {
        fprintf(stderr, "open() failed with errno %d (%s)\\n", errno, strerror(errno));
        return 1;
    }
    close(fd);
    return 0;
}
`,
  bad_fd: `#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

int main(void)
{
    char buf[64];
    printf("Attempting read() on invalid file descriptor 42...\\n");
    ssize_t n = read(42, buf, sizeof(buf));
    if (n == -1) {
        fprintf(stderr, "read() failed: errno=%d (%s)\\n", errno, strerror(errno));
        return 1;
    }
    return 0;
}
`,
  segfault: `#include <stdio.h>

static void trigger_crash(int *ptr)
{
    /* Intentional null-pointer write to demonstrate SIGSEGV + GDB backtrace */
    *ptr = 0xDEAD;
}

int main(void)
{
    printf("Starting custom crash demonstration...\\n");
    fflush(stdout);
    int *null_ptr = NULL;
    trigger_crash(null_ptr);
    return 0;
}
`,
  cpu_mem_loop: `#define _DEFAULT_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(void)
{
    printf("Allocating memory blocks and sampling /proc over ~450ms...\\n");
    fflush(stdout);

    size_t block_sz = 4 * 1024 * 1024; /* 4 MB */
    char *buf = (char *)malloc(block_sz);
    if (!buf) return 1;

    for (int step = 1; step <= 6; ++step) {
        memset(buf, step, block_sz);
        volatile long sum = 0;
        for (long i = 0; i < 1500000L; ++i) sum += i;
        printf("Step %d/6 completed (touched 4 MB RSS)\\n", step);
        fflush(stdout);
        usleep(70000); /* 70 ms */
    }

    free(buf);
    printf("Monitoring test finished cleanly.\\n");
    return 0;
}
`
};

/* ==========================================================================
   Utility Helpers
   ========================================================================== */

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderStatusBadge(label, tone) {
  const safeLabel = escapeHtml(label || 'UNKNOWN');
  let icon = '•';
  let cls = 'badge-neutral';
  if (tone === 'success' || safeLabel === 'SUCCESS' || safeLabel === 'EXIT 0') {
    icon = '✓';
    cls = 'badge-success';
  } else if (tone === 'danger' || ['SIGSEGV', 'SIGABRT', 'SIGFPE', 'SIGTERM', 'SIGKILL', 'COMPILATION ERROR'].includes(safeLabel)) {
    icon = '✕';
    cls = 'badge-danger';
  } else if (tone === 'warning' || ['ENOENT', 'EBADF', 'EACCES', 'EINVAL', 'TIMEOUT', 'STOPPED'].includes(safeLabel)) {
    icon = '⚠';
    cls = 'badge-warning';
  }
  return `<span class="badge ${cls}"><span>${icon}</span><span>${safeLabel}</span></span>`;
}

function showToast(message, type = 'info') {
  const el = document.getElementById('globalToast');
  if (!el) return;
  el.className = `global-toast ${type === 'error' ? 'toast-error' : type === 'success' ? 'toast-success' : ''}`;
  el.innerHTML = `
    <span>${escapeHtml(message)}</span>
    <button class="modal-close-btn" onclick="document.getElementById('globalToast').classList.add('hidden')">✕</button>
  `;
  el.classList.remove('hidden');
  clearTimeout(el._hideTimer);
  el._hideTimer = setTimeout(() => el.classList.add('hidden'), 6000);
}

async function apiFetch(url, options = {}) {
  const opts = Object.assign({ headers: {} }, options);
  if (opts.body && typeof opts.body === 'object') {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

/* ==========================================================================
   Navigation & View Switching
   ========================================================================== */

const VIEW_TITLES = {
  dashboard: 'Dashboard',
  programs: 'Test Programs',
  create: 'Create / Edit C Program',
  debugger: 'Debugger',
  autodebugger: 'AutoDebugger',
  results: 'Diagnostic Results',
  reports: 'Diagnostic Reports'
};

function switchView(viewName, options = {}) {
  if (!VIEW_TITLES[viewName]) viewName = 'dashboard';
  STATE.currentView = viewName;

  document.querySelectorAll('.view-pane').forEach(p => p.classList.remove('active'));
  const targetPane = document.getElementById(`view-${viewName}`);
  if (targetPane) targetPane.classList.add('active');

  document.querySelectorAll('.side-link').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-view') === viewName);
  });

  const bc = document.getElementById('topbarCurrentSection');
  if (bc) bc.textContent = VIEW_TITLES[viewName];

  document.getElementById('appShell')?.classList.remove('mobile-open');

  if (window.location.hash !== `#${viewName}`) {
    history.replaceState(null, '', `#${viewName}`);
  }

  if (viewName === 'dashboard') {
    refreshDashboard();
  } else if (viewName === 'programs') {
    loadPrograms().then(() => {
      if (options.tab) switchProgramsTab(options.tab);
    });
  } else if (viewName === 'create') {
    updateEditorLineNumbers();
  } else if (viewName === 'debugger') {
    loadPrograms().then(() => {
      const dbgSel = document.getElementById('debuggerProgramSelect');
      if (dbgSel && (!STATE.interactiveLoadedProg || STATE.interactiveLoadedProg !== dbgSel.value)) {
        onDebuggerProgramChanged(dbgSel.value);
      }
    });
  } else if (viewName === 'autodebugger') {
    loadPrograms();
  } else if (viewName === 'reports') {
    loadReportsList();
  }
}

/* ==========================================================================
   Dashboard & Health Check
   ========================================================================== */

async function refreshToolchainStatus() {
  const { ok, data } = await apiFetch('/api/health');
  if (!ok || !data.environment) return;
  const env = data.environment;
  const tools = env.tools || {};

  const setPill = (id, available) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle('pill-off', !available);
  };
  setPill('pillGcc', tools.gcc?.available);
  setPill('pillStrace', tools.strace?.available);
  setPill('pillGdb', tools.gdb?.available);
  setPill('pillProc', env.procfs_available);

  const osText = document.getElementById('topbarOsText');
  if (osText && env.os) {
    osText.textContent = `${env.os} • 127.0.0.1:5000`;
  }
}
const refreshHealthAndAbout = refreshToolchainStatus;

async function refreshDashboard() {
  const { ok, data } = await apiFetch('/api/dashboard');
  if (!ok) return;

  const stats = data.stats || {};
  document.getElementById('statBuiltinCount').textContent = stats.builtin_tests ?? 7;
  document.getElementById('statCustomCount').textContent = stats.custom_programs ?? 0;
  document.getElementById('statAnalysesCount').textContent = stats.total_analyses ?? 0;
  document.getElementById('statActiveCount').textContent = stats.active_processes ?? 0;

  const recent = data.recent_analyses || [];
  const container = document.getElementById('dashboardRecentContainer');
  if (!container) return;

  if (recent.length === 0) {
    container.innerHTML = `
      <div class="empty-state-card">
        <img src="/static/images/empty_analysis.jpg" alt="No Analysis Yet" class="supporting-illustration" />
        <h3 class="empty-title">NO ANALYSIS YET</h3>
        <p class="empty-desc">Select an existing test program or create your own C program to begin.</p>
        <div class="empty-actions">
          <button class="btn btn-primary" onclick="switchView('programs')">SELECT PROGRAM</button>
          <button class="btn btn-secondary" onclick="switchView('create')">CREATE PROGRAM</button>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="table-responsive">
      <table class="data-table">
        <thead>
          <tr>
            <th>Program</th>
            <th>Analysis Type</th>
            <th>Result</th>
            <th>Duration</th>
            <th>Timestamp</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          ${recent.map(r => `
            <tr>
              <td class="mono"><strong>${escapeHtml(r.program)}</strong></td>
              <td>${escapeHtml(r.analysis_type)}</td>
              <td>${renderStatusBadge(r.result_badge, r.badge_tone)}</td>
              <td class="mono">${Number(r.elapsed_ms || 0).toFixed(2)} ms</td>
              <td class="mono">${escapeHtml(r.display_time || r.timestamp)}</td>
              <td>
                <div class="table-actions">
                  <button class="btn btn-sm btn-secondary" onclick="openReportById('${escapeHtml(r.session_id)}')">View</button>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

/* ==========================================================================
   Test Programs Page (Built-in & Custom Programs)
   ========================================================================== */

function switchProgramsTab(tab) {
  const isBuiltin = tab !== 'custom';
  document.getElementById('tabBtnBuiltin')?.classList.toggle('active', isBuiltin);
  document.getElementById('tabBtnCustom')?.classList.toggle('active', !isBuiltin);
  document.getElementById('programsBuiltinPane')?.classList.toggle('hidden', !isBuiltin);
  document.getElementById('programsCustomPane')?.classList.toggle('hidden', isBuiltin);
}

async function loadPrograms() {
  const { ok, data } = await apiFetch('/api/programs');
  if (!ok) return;
  STATE.programs = data;

  const builtin = data.builtin || [];
  const custom = data.custom || [];

  const cntB = document.getElementById('tabCountBuiltin');
  const cntC = document.getElementById('tabCountCustom');
  if (cntB) cntB.textContent = builtin.length;
  if (cntC) cntC.textContent = custom.length;

  // Render Built-in Cards
  const builtinGrid = document.getElementById('programsBuiltinPane');
  if (builtinGrid) {
    builtinGrid.innerHTML = builtin.map(p => `
      <div class="program-card">
        <div>
          <div class="prog-card-top">
            <div>
              <div class="prog-title">${escapeHtml(p.title)}</div>
              <div class="prog-path">${escapeHtml(p.source_path)}</div>
            </div>
            ${renderStatusBadge(p.badge, p.badge === 'EXIT 0' ? 'success' : p.badge.startsWith('SIG') ? 'danger' : 'warning')}
          </div>
          <p class="prog-desc">${escapeHtml(p.description)}</p>
          <div class="prog-expected">
            <strong>Expected Evidence:</strong> ${escapeHtml(p.expected_outcome)}
          </div>
        </div>
        <div class="prog-actions">
          <button class="btn btn-sm btn-emerald" onclick="quickRunProgram('${escapeHtml(p.name)}')">RUN</button>
          <button class="btn btn-sm btn-blue" onclick="quickDebugProgram('${escapeHtml(p.name)}')">DEBUG</button>
          <button class="btn btn-sm btn-violet" onclick="quickAutoDebugProgram('${escapeHtml(p.name)}')">AUTODEBUG</button>
          <button class="btn btn-sm btn-secondary" onclick="viewProgramCodeModal('${escapeHtml(p.name)}')">VIEW CODE</button>
        </div>
      </div>
    `).join('');
  }

  // Render Custom Cards
  const customGrid = document.getElementById('programsCustomGrid');
  if (customGrid) {
    if (custom.length === 0) {
      customGrid.innerHTML = `
        <div class="empty-state-card" style="grid-column: 1 / -1;">
          <img src="/static/images/empty_analysis.jpg" alt="No Custom Programs" class="supporting-illustration" />
          <h3 class="empty-title">NO CUSTOM C PROGRAMS YET</h3>
          <p class="empty-desc">Create your own C program in <code>tests/</code> to compile with GCC and analyze with strace, /proc, and GDB.</p>
          <div class="empty-actions">
            <button class="btn btn-primary" onclick="openEditorForNew()">+ CREATE C PROGRAM</button>
          </div>
        </div>
      `;
    } else {
      customGrid.innerHTML = custom.map(p => {
        const statusLabel = p.compile_status === 'compiled'
          ? 'COMPILED'
          : p.compile_status === 'failed'
            ? 'COMPILE FAILED'
            : 'NEEDS COMPILE';
        const statusTone = p.compile_status === 'compiled'
          ? 'success'
          : p.compile_status === 'failed'
            ? 'danger'
            : 'warning';
        const disableExec = p.compile_status === 'failed' ? 'disabled title="Fix compilation errors first"' : '';
        return `
          <div class="program-card">
            <div>
              <div class="prog-card-top">
                <div>
                  <div class="prog-title">${escapeHtml(p.name)}</div>
                  <div class="prog-path">${escapeHtml(p.source_path)} (${p.lines} lines)</div>
                </div>
                ${renderStatusBadge(statusLabel, statusTone)}
              </div>
              <p class="prog-desc">${escapeHtml(p.description)}</p>
            </div>
            <div class="prog-actions">
              <button class="btn btn-sm btn-secondary" onclick="viewProgramCodeModal('${escapeHtml(p.name)}')">View Code</button>
              <button class="btn btn-sm btn-secondary" onclick="openEditorForProgram('${escapeHtml(p.name)}')">Edit</button>
              <button class="btn btn-sm btn-primary" onclick="compileCustomFromCard('${escapeHtml(p.name)}')">Compile</button>
              <button class="btn btn-sm btn-emerald" ${disableExec} onclick="quickRunProgram('${escapeHtml(p.name)}')">Run</button>
              <button class="btn btn-sm btn-blue" ${disableExec} onclick="quickDebugProgram('${escapeHtml(p.name)}')">Debug</button>
              <button class="btn btn-sm btn-violet" ${disableExec} onclick="quickAutoDebugProgram('${escapeHtml(p.name)}')">AutoDebug</button>
              <button class="btn btn-sm btn-danger" onclick="confirmDeleteCustomProgram('${escapeHtml(p.name)}')">Delete</button>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // Populate Debugger & AutoDebugger Dropdowns
  populateProgramSelects(builtin, custom);
}

function populateProgramSelects(builtin, custom) {
  const selects = [
    document.getElementById('debuggerProgramSelect'),
    document.getElementById('autoProgramSelect')
  ];
  selects.forEach(sel => {
    if (!sel) return;
    const prev = sel.value;
    let html = `<optgroup label="Official Built-in Test Programs">`;
    builtin.forEach(p => {
      html += `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)} — ${escapeHtml(p.title)}</option>`;
    });
    html += `</optgroup>`;
    if (custom.length > 0) {
      html += `<optgroup label="Custom User C Programs">`;
      custom.forEach(p => {
        const tag = p.compile_status === 'failed' ? ' [Compile Failed]' : '';
        html += `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)} (tests/${escapeHtml(p.name)}.c)${tag}</option>`;
      });
      html += `</optgroup>`;
    }
    sel.innerHTML = html;
    if (prev && Array.from(sel.options).some(o => o.value === prev)) {
      sel.value = prev;
    }
  });

  const dbgSel = document.getElementById('debuggerProgramSelect');
  if (dbgSel && (!STATE.interactiveLoadedProg || STATE.interactiveLoadedProg !== dbgSel.value)) {
    onDebuggerProgramChanged(dbgSel.value);
  }
}

/* ==========================================================================
   Create / Edit C Program & Real GCC Compilation (Sections 11 & 12)
   ========================================================================== */

function getEditorCode() {
  const ta = document.getElementById('cSourceTextarea');
  return ta ? ta.value : '';
}

function setEditorCode(code) {
  const ta = document.getElementById('cSourceTextarea');
  if (ta) {
    ta.value = code;
    updateEditorLineNumbers();
  }
}

function updateEditorLineNumbers() {
  const ta = document.getElementById('cSourceTextarea');
  const gutter = document.getElementById('editorLineNumbers');
  if (!ta || !gutter) return;
  const linesCount = Math.max(1, ta.value.split('\n').length);
  const nums = [];
  for (let i = 1; i <= linesCount; i++) nums.push(i);
  gutter.textContent = nums.join('\n');
  gutter.scrollTop = ta.scrollTop;
}

function jumpToEditorLine(lineNumber) {
  const ta = document.getElementById('cSourceTextarea');
  if (!ta || !lineNumber) return;
  const lines = ta.value.split('\n');
  let pos = 0;
  for (let i = 0; i < Math.min(lineNumber - 1, lines.length); i++) {
    pos += lines[i].length + 1;
  }
  const lineEnd = pos + (lines[lineNumber - 1]?.length || 0);
  ta.focus();
  ta.setSelectionRange(pos, lineEnd);
  const lineHeight = 20.8;
  ta.scrollTop = Math.max(0, (lineNumber - 5) * lineHeight);
  updateEditorLineNumbers();
}

function loadStarterTemplate(key) {
  if (!key || !STARTER_TEMPLATES[key]) return;
  setEditorCode(STARTER_TEMPLATES[key]);
  const nameIn = document.getElementById('programNameInput');
  if (nameIn && !nameIn.value.trim()) {
    nameIn.value = `custom_${key}`;
  }
  document.getElementById('editorTemplateSelect').value = '';
}

function openEditorForNew() {
  document.getElementById('editorPageTitle').textContent = 'Create New C Program';
  document.getElementById('programNameInput').value = '';
  document.getElementById('programNameInput').disabled = false;
  setEditorCode(STARTER_TEMPLATES.hello);
  resetCompilePanel();
  switchView('create');
}

async function openEditorForProgram(name) {
  const { ok, data } = await apiFetch(`/api/programs/${encodeURIComponent(name)}`);
  if (!ok) {
    showToast(data.error || 'Could not load program source.', 'error');
    return;
  }
  document.getElementById('editorPageTitle').textContent = data.is_builtin
    ? `Inspect / Clone Built-in Program: ${data.name}`
    : `Edit Custom C Program: ${data.name}`;
  const nameIn = document.getElementById('programNameInput');
  nameIn.value = data.is_builtin ? `${data.name}_custom` : data.name;
  setEditorCode(data.code || '');
  resetCompilePanel();
  switchView('create');
}

function handleResetEditor() {
  setEditorCode(STARTER_TEMPLATES.hello);
  resetCompilePanel();
}

function resetCompilePanel() {
  STATE.editorLastCompiledSuccess = false;
  const badge = document.getElementById('compileStatusBadge');
  if (badge) {
    badge.className = 'badge badge-neutral';
    badge.textContent = 'NOT COMPILED YET';
  }
  const body = document.getElementById('compileResultBody');
  if (body) {
    body.innerHTML = `<p class="muted-note">Click <strong>SAVE &amp; COMPILE</strong> to invoke <code>gcc -Wall -Wextra -std=c11 -g</code> and inspect real compiler diagnostics.</p>`;
  }
  setEditorExecButtonsEnabled(true);
}

function setEditorExecButtonsEnabled(enabled) {
  ['btnEditorRun', 'btnEditorDebug', 'btnEditorAutoDebug'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = !enabled;
  });
}

async function handleSaveProgram() {
  const name = document.getElementById('programNameInput')?.value.trim() || '';
  const code = getEditorCode();
  const { ok, data } = await apiFetch('/api/programs', {
    method: 'POST',
    body: { name, code }
  });
  if (!ok || !data.success) {
    showToast(data.error || 'Failed to save C program.', 'error');
    return false;
  }
  showToast(`Saved ${data.source_path} (${data.lines} lines). Compile with GCC before running.`, 'success');
  loadPrograms();
  return true;
}

async function handleSaveAndCompile() {
  const name = document.getElementById('programNameInput')?.value.trim() || '';
  const code = getEditorCode();
  const badge = document.getElementById('compileStatusBadge');
  const body = document.getElementById('compileResultBody');

  if (badge) {
    badge.className = 'badge badge-neutral';
    badge.textContent = 'COMPILING...';
  }

  const { ok, data } = await apiFetch('/api/compile', {
    method: 'POST',
    body: { name, code }
  });

  if (!ok && data.error_type === 'VALIDATION_ERROR') {
    if (badge) {
      badge.className = 'badge badge-danger';
      badge.textContent = '✕ VALIDATION FAILED';
    }
    if (body) {
      body.innerHTML = `<div class="diag-item"><div class="diag-msg">${escapeHtml(data.error)}</div></div>`;
    }
    setEditorExecButtonsEnabled(false);
    showToast(data.error, 'error');
    return null;
  }

  renderCompileResult(data);
  loadPrograms();
  return data;
}

function renderCompileResult(res) {
  const badge = document.getElementById('compileStatusBadge');
  const body = document.getElementById('compileResultBody');
  if (!badge || !body) return;

  const diags = res.diagnostics || [];
  const diagHtml = diags.length > 0
    ? `<div class="mt-12">
         <div class="field-label">Compiler Diagnostics (Click to jump to line)</div>
         ${diags.map(d => `
           <div class="diag-item ${d.severity === 'warning' ? 'diag-warning' : ''}" onclick="jumpToEditorLine(${Number(d.line || 1)})">
             <div class="diag-loc">${escapeHtml(d.file)}:${Number(d.line || 1)}:${Number(d.column || 1)} • ${escapeHtml(d.severity.toUpperCase())}</div>
             <div class="diag-msg">${escapeHtml(d.message)}</div>
           </div>
         `).join('')}
       </div>`
    : '';

  if (res.success) {
    STATE.editorLastCompiledSuccess = true;
    STATE.editorLastCompiledName = res.name;
    setEditorExecButtonsEnabled(true);

    badge.className = 'badge badge-success';
    badge.textContent = '✓ COMPILATION SUCCESSFUL';

    body.innerHTML = `
      <div class="kv-list">
        <div class="kv-row">
          <span class="kv-key">Status</span>
          <span class="kv-val">${renderStatusBadge('SUCCESS', 'success')}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Executable</span>
          <span class="kv-val mono">${escapeHtml(res.executable_path)}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Compiler Command</span>
          <span class="kv-val mono">${escapeHtml(res.command || 'gcc -Wall -Wextra -std=c11 -g')}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Warnings</span>
          <span class="kv-val mono">${Number(res.warnings_count || 0)}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Compile Time</span>
          <span class="kv-val mono">${Number(res.duration_ms || 0).toFixed(2)} ms</span>
        </div>
      </div>
      ${diagHtml}
      ${res.stderr ? `<pre class="terminal-box mt-12" style="min-height:90px;">${escapeHtml(res.stderr)}</pre>` : ''}
      <div class="prog-actions mt-12">
        <button class="btn btn-sm btn-emerald" onclick="quickRunProgram('${escapeHtml(res.name)}')">RUN</button>
        <button class="btn btn-sm btn-blue" onclick="quickDebugProgram('${escapeHtml(res.name)}')">DEBUG</button>
        <button class="btn btn-sm btn-violet" onclick="quickAutoDebugProgram('${escapeHtml(res.name)}')">AUTODEBUG</button>
      </div>
    `;
  } else {
    STATE.editorLastCompiledSuccess = false;
    setEditorExecButtonsEnabled(false);

    badge.className = 'badge badge-danger';
    badge.textContent = '✕ COMPILATION FAILED';

    body.innerHTML = `
      <div class="kv-list">
        <div class="kv-row">
          <span class="kv-key">Status</span>
          <span class="kv-val">${renderStatusBadge('COMPILATION ERROR', 'danger')}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Errors / Warnings</span>
          <span class="kv-val mono">${Number(res.errors_count || 1)} error(s), ${Number(res.warnings_count || 0)} warning(s)</span>
        </div>
      </div>
      ${diagHtml}
      <div class="mt-12">
        <div class="field-label">Raw GCC Diagnostic Output</div>
        <pre class="terminal-box" style="min-height:140px;color:#fca5a5;">${escapeHtml(res.stderr || res.error || 'GCC compilation failed.')}</pre>
      </div>
    `;
  }
}

async function handleEditorAction(actionType) {
  const compRes = await handleSaveAndCompile();
  if (!compRes || !compRes.success) {
    showToast('Cannot execute: fix GCC compilation errors first.', 'error');
    return;
  }
  const progName = compRes.name;
  if (actionType === 'run') {
    quickRunProgram(progName);
  } else if (actionType === 'debug') {
    quickDebugProgram(progName);
  } else if (actionType === 'autodebug') {
    quickAutoDebugProgram(progName);
  }
}

async function compileCustomFromCard(name) {
  const { data } = await apiFetch('/api/compile', {
    method: 'POST',
    body: { name }
  });
  if (data.success) {
    showToast(`Compiled tests/${name} successfully (${data.warnings_count || 0} warnings).`, 'success');
  } else {
    showToast(`Compilation failed for ${name}. Opening editor to inspect diagnostics.`, 'error');
    await openEditorForProgram(name);
    renderCompileResult(data);
  }
  loadPrograms();
}

/* ==========================================================================
   Quick Execution & Modal Actions
   ========================================================================== */

async function viewProgramCodeModal(name) {
  const { ok, data } = await apiFetch(`/api/programs/${encodeURIComponent(name)}`);
  if (!ok) {
    showToast(data.error || 'Failed to read source file.', 'error');
    return;
  }
  const linesHtml = (data.lines || []).map((ln, idx) => `
    <div class="code-line-row">
      <span class="code-line-num">${idx + 1}</span>
      <span class="code-line-text">${escapeHtml(ln)}</span>
    </div>
  `).join('');

  openModal(
    `Source Code — ${data.source_path}`,
    `<div class="code-snippet-box">${linesHtml}</div>`,
    `
      <button class="btn btn-secondary" onclick="closeModal()">Close</button>
      <button class="btn btn-blue" onclick="closeModal(); quickDebugProgram('${escapeHtml(data.name)}')">Debug Program</button>
      <button class="btn btn-violet" onclick="closeModal(); quickAutoDebugProgram('${escapeHtml(data.name)}')">AutoDebug</button>
    `
  );
}

function confirmDeleteCustomProgram(name) {
  openModal(
    `Delete Custom Program — ${name}`,
    `<p>Are you sure you want to permanently delete <code>tests/${escapeHtml(name)}.c</code> and its compiled binary?</p>`,
    `
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn btn-danger" onclick="executeDeleteCustomProgram('${escapeHtml(name)}')">Confirm Delete</button>
    `
  );
}

async function executeDeleteCustomProgram(name) {
  closeModal();
  const { ok, data } = await apiFetch(`/api/programs/${encodeURIComponent(name)}`, {
    method: 'DELETE'
  });
  if (ok && data.success) {
    showToast(`Deleted custom program '${name}'.`, 'success');
    loadPrograms();
  } else {
    showToast(data.error || 'Could not delete program.', 'error');
  }
}

async function quickRunProgram(name) {
  const { ok, data } = await apiFetch('/api/run', {
    method: 'POST',
    body: { program: name, async: false }
  });
  if (!ok || !data.success) {
    showToast(data.error || 'Execution failed.', 'error');
    return;
  }
  STATE.currentResult = data;
  renderDetailedResults(data);
  switchView('results');
}

function quickDebugProgram(name) {
  switchView('debugger');
  setTimeout(() => {
    const sel = document.getElementById('debuggerProgramSelect');
    if (sel) sel.value = name;
    runDebuggerSession(name);
  }, 60);
}

function quickAutoDebugProgram(name) {
  switchView('autodebugger');
  setTimeout(() => {
    const sel = document.getElementById('autoProgramSelect');
    if (sel) sel.value = name;
    runAutoDebuggerSession(name);
  }, 60);
}

/* ==========================================================================
   Debugger Session Execution & Live /proc Charting (Sections 13 & 14)
   ========================================================================== */

function initDebuggerCharts() {
  const memCanvas = document.getElementById('dbgMemoryChart');
  const cpuCanvas = document.getElementById('dbgCpuChart');
  if (!memCanvas || !cpuCanvas || typeof Chart === 'undefined') return;

  if (STATE.memChart) STATE.memChart.destroy();
  if (STATE.cpuChart) STATE.cpuChart.destroy();

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 150 },
    plugins: {
      legend: { labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } } }
    },
    scales: {
      x: {
        ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
        grid: { color: 'rgba(148,163,184,0.08)' }
      },
      y: {
        beginAtZero: true,
        ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
        grid: { color: 'rgba(148,163,184,0.08)' }
      }
    }
  };

  STATE.memChart = new Chart(memCanvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'VmRSS (Resident KB)',
          data: [],
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.15)',
          fill: true,
          tension: 0.25
        },
        {
          label: 'VmSize (Virtual KB)',
          data: [],
          borderColor: '#3b82f6',
          backgroundColor: 'transparent',
          borderDash: [4, 4],
          tension: 0.25
        }
      ]
    },
    options: commonOptions
  });

  STATE.cpuChart = new Chart(cpuCanvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'CPU Usage (%)',
          data: [],
          borderColor: '#8b5cf6',
          backgroundColor: 'rgba(139, 92, 246, 0.18)',
          fill: true,
          tension: 0.25
        }
      ]
    },
    options: commonOptions
  });
}

function updateDebuggerCharts(samples, shortNote = '') {
  const noteEl = document.getElementById('dbgMonitorSampleNote');
  if (noteEl) {
    if (!samples || samples.length === 0) {
      noteEl.textContent = 'Process completed before /proc samples were collected.';
    } else if (samples.length === 1) {
      noteEl.textContent = shortNote || 'Process completed in 1 sample window (single /proc snapshot captured).';
    } else {
      noteEl.textContent = `Captured ${samples.length} real /proc telemetry samples.`;
    }
  }

  if (samples && samples.length > 0) {
    const latest = samples[samples.length - 1];
    document.getElementById('dbgLiveVmSize').textContent = `${latest.vm_size_kb} KB`;
    document.getElementById('dbgLiveVmRss').textContent = `${latest.vm_rss_kb} KB`;
    document.getElementById('dbgLiveThreads').textContent = latest.threads || 1;
    document.getElementById('dbgLiveFds').textContent = latest.open_fds >= 0 ? latest.open_fds : '—';
  }

  if (!STATE.memChart || !STATE.cpuChart) {
    initDebuggerCharts();
  }
  if (!STATE.memChart || !STATE.cpuChart) return;

  const labels = (samples || []).map(s => `${Number(s.elapsed_ms).toFixed(0)}ms`);
  const rssData = (samples || []).map(s => s.vm_rss_kb);
  const vmData = (samples || []).map(s => s.vm_size_kb);
  const cpuData = (samples || []).map(s => s.cpu_percent);

  STATE.memChart.data.labels = labels;
  STATE.memChart.data.datasets[0].data = rssData;
  STATE.memChart.data.datasets[1].data = vmData;
  STATE.memChart.update();

  STATE.cpuChart.data.labels = labels;
  STATE.cpuChart.data.datasets[0].data = cpuData;
  STATE.cpuChart.update();
}

/* ==========================================================================
   Interactive Source-Level GDB Debugger Controller (GDB/MI)
   ========================================================================== */

async function onDebuggerProgramChanged(progName) {
  const prog = progName || document.getElementById('debuggerProgramSelect')?.value || 'math_step';
  STATE.interactiveLoadedProg = prog;

  // Fetch source code
  const { ok, data } = await apiFetch(`/api/programs/${encodeURIComponent(prog)}`);
  if (!ok) {
    showToast(`Could not load source for ${prog}`, 'error');
    return;
  }

  STATE.interactiveSourceLines = data.lines || [];
  STATE.interactiveBreakpoints = new Set();
  STATE.interactiveSessionId = null;
  STATE.interactiveSession = null;

  // Update file info header
  const fileLabel = document.getElementById('dbgCurrentFileLabel');
  if (fileLabel) fileLabel.textContent = data.source_path || `tests/${prog}.c`;
  const funcBadge = document.getElementById('dbgCurrentFuncBadge');
  if (funcBadge) funcBadge.textContent = 'main()';

  // Render pristine source code
  renderSourceViewer(STATE.interactiveSourceLines, null, STATE.interactiveBreakpoints, false);

  // Reset status displays
  setDebuggerPill('IDLE', 'badge-neutral');
  const statState = document.getElementById('dbgStatState');
  if (statState) statState.textContent = 'NOT_STARTED';
  const statPid = document.getElementById('dbgStatPid');
  if (statPid) statPid.textContent = '—';
  const statFunc = document.getElementById('dbgStatFunc');
  if (statFunc) statFunc.textContent = '—';
  const statLine = document.getElementById('dbgStatLine');
  if (statLine) statLine.textContent = '—';
  const statReason = document.getElementById('dbgStatReason');
  if (statReason) statReason.textContent = 'Ready to debug. Click START DEBUGGING to break at main().';
  const sourceStats = document.getElementById('dbgSourceStats');
  if (sourceStats) sourceStats.textContent = `Source loaded (${STATE.interactiveSourceLines.length} lines). Click line number to toggle breakpoints.`;
  const sourceCoords = document.getElementById('dbgSourceCoords');
  if (sourceCoords) sourceCoords.textContent = 'Ln —, Col —';

  // Reset inspector tables
  const varsBody = document.getElementById('dbgVariablesBody');
  if (varsBody) varsBody.innerHTML = '<tr><td colspan="3" class="text-muted text-center py-8">Start debugging to inspect variables</td></tr>';
  const varsCount = document.getElementById('dbgVarsCount');
  if (varsCount) varsCount.textContent = '0 variables';

  const argsBody = document.getElementById('dbgArgumentsBody');
  if (argsBody) argsBody.innerHTML = '<tr><td colspan="2" class="text-muted text-center py-8">No arguments in current frame</td></tr>';

  const stackList = document.getElementById('dbgCallStackList');
  if (stackList) stackList.innerHTML = '<div class="empty-stack-placeholder">Stack empty. Execution not started.</div>';

  // Reset bottom panels
  const stdoutBox = document.getElementById('dbgStdoutBox');
  if (stdoutBox) stdoutBox.textContent = '[Program stdout will appear here]';
  const stderrBox = document.getElementById('dbgStderrBox');
  if (stderrBox) stderrBox.textContent = '[Program stderr will appear here]';
  const crashCard = document.getElementById('dbgCrashCardContainer');
  if (crashCard) crashCard.innerHTML = '<div class="clean-note"><span class="status-dot dot-emerald"></span><span>No signals or crashes detected. Program running cleanly.</span></div>';
  const sigBadge = document.getElementById('dbgSignalBadge');
  if (sigBadge) sigBadge.classList.add('hidden');

  // Reset buttons
  setDebuggerButtonsState('NOT_STARTED');
}

function renderSourceViewer(lines, currentLine, activeBreakpoints, isCrash) {
  const container = document.getElementById('dbgSourceContainer');
  if (!container) return;

  if (!lines || lines.length === 0) {
    container.innerHTML = '<div class="p-16 text-muted text-center">No source code available.</div>';
    return;
  }

  const bps = activeBreakpoints instanceof Set ? activeBreakpoints : new Set(activeBreakpoints || []);

  const html = lines.map((lineText, idx) => {
    const lineNum = idx + 1;
    const isCurrent = (lineNum === currentLine);
    const hasBp = bps.has(lineNum);
    const rowClass = isCurrent
      ? (isCrash ? 'source-line-row crash-line' : 'source-line-row active-line')
      : 'source-line-row';

    const bpMarker = hasBp
      ? '<span class="bp-dot" title="Active Breakpoint (Click to remove)"></span>'
      : '<span class="bp-placeholder" title="Click to set breakpoint"></span>';

    const activePointer = isCurrent ? '&gt;' : '';

    return `
      <div class="${rowClass}" id="dbgSourceLine_${lineNum}">
        <div class="source-gutter" onclick="toggleBreakpoint(${lineNum});" title="Line ${lineNum} (Click to toggle breakpoint)">
          <span class="bp-marker">${bpMarker}</span>
          <span class="source-line-num">${lineNum}</span>
        </div>
        <div class="source-active-indicator">${activePointer}</div>
        <div class="source-code-text">${escapeHtml(lineText)}</div>
      </div>
    `;
  }).join('');

  container.innerHTML = html;

  if (currentLine && currentLine > 0) {
    const activeEl = document.getElementById(`dbgSourceLine_${currentLine}`);
    if (activeEl) {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
}

async function toggleBreakpoint(line) {
  const bps = STATE.interactiveBreakpoints || (STATE.interactiveBreakpoints = new Set());
  const hasBp = bps.has(line);

  if (STATE.interactiveSessionId && STATE.interactiveSession && (STATE.interactiveSession.state === 'STOPPED' || STATE.interactiveSession.state === 'RUNNING')) {
    if (hasBp) {
      // Find breakpoint ID
      const bpObj = (STATE.interactiveSession.breakpoints || []).find(b => b.line === line);
      const bpid = bpObj ? bpObj.id : null;
      if (bpid) {
        const { ok } = await apiFetch('/api/debugger/breakpoint', {
          method: 'POST',
          body: { session_id: STATE.interactiveSessionId, action: 'remove', breakpoint_id: bpid }
        });
        if (ok) {
          bps.delete(line);
          showToast(`Removed breakpoint at line ${line}`, 'info');
        }
      } else {
        bps.delete(line);
      }
    } else {
      const { ok, data } = await apiFetch('/api/debugger/breakpoint', {
        method: 'POST',
        body: { session_id: STATE.interactiveSessionId, action: 'add', line: line }
      });
      if (ok && data.success) {
        const actualLine = data.breakpoint ? data.breakpoint.line : line;
        bps.add(actualLine);
        showToast(`Breakpoint #${data.breakpoint?.id || ''} set at line ${actualLine}`, 'success');
      } else {
        showToast(data.error || 'Failed to set breakpoint.', 'error');
      }
    }
  } else {
    // Pre-session toggle
    if (hasBp) {
      bps.delete(line);
      showToast(`Removed breakpoint at line ${line}`, 'info');
    } else {
      bps.add(line);
      showToast(`Breakpoint marked at line ${line} (will activate upon Start Debugging)`, 'success');
    }
  }

  renderSourceViewer(
    STATE.interactiveSourceLines,
    STATE.interactiveSession?.current_line,
    bps,
    STATE.interactiveSession?.state === 'SIGNALED'
  );
}

async function startInteractiveDebugger() {
  const prog = document.getElementById('debuggerProgramSelect')?.value || 'math_step';
  const startBtn = document.getElementById('btnDbgStart');
  if (startBtn) startBtn.disabled = true;

  setDebuggerPill('COMPILING / LAUNCHING...', 'badge-warning');
  const statReason = document.getElementById('dbgStatReason');
  if (statReason) statReason.textContent = 'Compiling with gcc -Wall -Wextra -std=c11 -g -O0 and launching under GDB...';

  const bps = Array.from(STATE.interactiveBreakpoints || []);

  const { ok, data } = await apiFetch('/api/debugger/start', {
    method: 'POST',
    body: { program: prog, breakpoints: bps }
  });

  if (!ok || !data.success) {
    if (startBtn) startBtn.disabled = false;
    setDebuggerPill('START FAILED', 'badge-danger');
    const errText = data.error || 'Failed to start debugger session.';
    if (statReason) statReason.textContent = errText;
    showToast(errText.length > 80 ? errText.substring(0, 80) + '...' : errText, 'error');

    if (data.compilation && data.compilation.output) {
      const errBox = document.getElementById('dbgStderrBox');
      if (errBox) errBox.textContent = data.compilation.output;
      switchDbgBottomTab('output');
    }
    return;
  }

  STATE.interactiveSessionId = data.session.session_id;
  STATE.interactiveSession = data.session;
  updateInteractiveDebuggerUI(data.session);
  showToast(`Interactive debugging active for tests/${prog}. Stopped at main().`, 'success');
}

async function stepDebugger(action) {
  if (!STATE.interactiveSessionId) return;

  setStepButtonsDisabled(true);
  setDebuggerPill('● RUNNING...', 'badge-primary');

  const endpoint = `/api/debugger/${action.replace('_', '-')}`;
  const { ok, data } = await apiFetch(endpoint, {
    method: 'POST',
    body: { session_id: STATE.interactiveSessionId }
  });

  if (!ok || !data.success) {
    setStepButtonsDisabled(false);
    showToast(data.error || `Step action '${action}' failed.`, 'error');
    return;
  }

  STATE.interactiveSession = data.session;
  updateInteractiveDebuggerUI(data.session);
}

async function stopInteractiveDebugger() {
  if (!STATE.interactiveSessionId) return;
  const { ok, data } = await apiFetch('/api/debugger/stop', {
    method: 'POST',
    body: { session_id: STATE.interactiveSessionId }
  });
  if (ok && data.session) {
    STATE.interactiveSession = data.session;
    updateInteractiveDebuggerUI(data.session);
  }
  showToast('Debugging session stopped by user.', 'info');
}

async function selectCallStackFrame(frameLevel) {
  if (!STATE.interactiveSessionId) return;
  const { ok, data } = await apiFetch('/api/debugger/select-frame', {
    method: 'POST',
    body: { session_id: STATE.interactiveSessionId, frame: frameLevel }
  });
  if (ok && data.success) {
    STATE.interactiveSession = data.session;
    updateInteractiveDebuggerUI(data.session);
  }
}

async function saveDebuggerReport() {
  if (!STATE.interactiveSessionId) return;
  const { ok, data } = await apiFetch('/api/debugger/save-report', {
    method: 'POST',
    body: { session_id: STATE.interactiveSessionId }
  });
  if (ok && data.success) {
    showToast(`Diagnostic report saved successfully (ID: ${data.report?.session_id || 'saved'}).`, 'success');
  } else {
    showToast(data.error || 'Failed to save diagnostic report.', 'error');
  }
}

function updateInteractiveDebuggerUI(s) {
  if (!s) return;

  // 1. Update toolbar button availability
  setDebuggerButtonsState(s.state);

  // 2. Update status badge & pill
  if (s.state === 'STOPPED') {
    setDebuggerPill(s.stop_category === 'BREAKPOINT' ? 'BREAKPOINT HIT' : 'STOPPED', 'badge-warning');
  } else if (s.state === 'SIGNALED') {
    setDebuggerPill(s.signal_info ? `${s.signal_info.signal_name} (CRASH)` : 'CRASHED', 'badge-danger');
  } else if (s.state === 'EXITED') {
    setDebuggerPill(s.exit_code === 0 ? 'EXIT 0 (CLEAN)' : `EXIT ${s.exit_code}`, s.exit_code === 0 ? 'badge-success' : 'badge-warning');
  } else if (s.state === 'USER_TERMINATED') {
    setDebuggerPill('STOPPED BY USER', 'badge-neutral');
  } else {
    setDebuggerPill(s.state, 'badge-neutral');
  }

  // 3. Update session status card
  const statState = document.getElementById('dbgStatState');
  if (statState) statState.textContent = s.state;
  const statPid = document.getElementById('dbgStatPid');
  if (statPid) statPid.textContent = s.pid ? String(s.pid) : '—';
  const statFunc = document.getElementById('dbgStatFunc');
  if (statFunc) statFunc.textContent = `${s.current_func || 'main'}()`;
  const statLine = document.getElementById('dbgStatLine');
  if (statLine) statLine.textContent = `${s.current_file || ''}:${s.current_line || '—'}`;
  const statReason = document.getElementById('dbgStatReason');
  if (statReason) statReason.textContent = s.stop_reason || 'Debugger stopped';

  // 4. Update source code viewer
  if (s.source && s.source.lines) {
    STATE.interactiveSourceLines = s.source.lines;
  }
  const bps = STATE.interactiveBreakpoints || (STATE.interactiveBreakpoints = new Set());
  (s.breakpoints || []).forEach(b => bps.add(b.line));
  renderSourceViewer(STATE.interactiveSourceLines, s.current_line, bps, s.state === 'SIGNALED');

  const fileLabel = document.getElementById('dbgCurrentFileLabel');
  if (fileLabel) fileLabel.textContent = s.current_file || `tests/${s.program}.c`;
  const funcBadge = document.getElementById('dbgCurrentFuncBadge');
  if (funcBadge) funcBadge.textContent = `${s.current_func || 'main'}()`;
  const sourceStats = document.getElementById('dbgSourceStats');
  if (sourceStats) {
    sourceStats.textContent = `File: ${s.current_file} • Stopped at line ${s.current_line || '—'} in ${s.current_func || 'main'}()`;
  }
  const sourceCoords = document.getElementById('dbgSourceCoords');
  if (sourceCoords) sourceCoords.textContent = `Ln ${s.current_line || '—'}, Col 1`;

  // 5. Update local variables table
  const varsBody = document.getElementById('dbgVariablesBody');
  const varsCount = document.getElementById('dbgVarsCount');
  if (varsBody) {
    const vars = s.variables || [];
    if (varsCount) varsCount.textContent = `${vars.length} variable${vars.length === 1 ? '' : 's'}`;
    if (vars.length === 0) {
      varsBody.innerHTML = '<tr><td colspan="3" class="text-muted text-center py-8">No local variables in scope</td></tr>';
    } else {
      varsBody.innerHTML = vars.map(v => `
        <tr>
          <td class="font-semibold text-sky-400">${escapeHtml(v.name)}</td>
          <td class="text-muted">${escapeHtml(v.type || '—')}</td>
          <td class="font-mono ${v.status === 'unavailable' ? 'text-muted' : 'text-emerald-400'}">${escapeHtml(v.value)}</td>
        </tr>
      `).join('');
    }
  }

  // 6. Update function arguments table
  const argsBody = document.getElementById('dbgArgumentsBody');
  if (argsBody) {
    const args = s.arguments || [];
    if (args.length === 0) {
      argsBody.innerHTML = '<tr><td colspan="2" class="text-muted text-center py-8">No arguments in current frame</td></tr>';
    } else {
      argsBody.innerHTML = args.map(a => `
        <tr>
          <td class="font-semibold text-amber-400">${escapeHtml(a.name)}</td>
          <td class="font-mono text-emerald-400">${escapeHtml(a.value)}</td>
        </tr>
      `).join('');
    }
  }

  // 7. Update call stack list
  const stackList = document.getElementById('dbgCallStackList');
  if (stackList) {
    const frames = s.call_stack || [];
    if (frames.length === 0) {
      stackList.innerHTML = '<div class="empty-stack-placeholder">Stack empty. Execution terminated.</div>';
    } else {
      stackList.innerHTML = frames.map(f => `
        <div class="stack-frame-item ${f.is_current ? 'current' : ''}" onclick="selectCallStackFrame(${f.level})" title="Click to inspect frame #${f.level}">
          <span>#${f.level} <strong>${escapeHtml(f.func)}()</strong></span>
          <span class="text-muted text-xs mono">${escapeHtml(f.file)}:${f.line || '?'}</span>
        </div>
      `).join('');
    }
  }

  // 8. Update bottom panels
  const stdoutBox = document.getElementById('dbgStdoutBox');
  if (stdoutBox) stdoutBox.textContent = s.program_output?.stdout || '[No STDOUT produced yet]';
  const stderrBox = document.getElementById('dbgStderrBox');
  if (stderrBox) stderrBox.textContent = s.program_output?.stderr || '[No STDERR produced yet]';

  // Errors & Signals Tab
  const crashCard = document.getElementById('dbgCrashCardContainer');
  const sigBadge = document.getElementById('dbgSignalBadge');
  if (s.signal_info) {
    if (sigBadge) sigBadge.classList.remove('hidden');
    if (crashCard) {
      crashCard.innerHTML = `
        <div class="crash-card-wrap">
          <div class="crash-card-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            <span>FATAL RUNTIME SIGNAL: ${escapeHtml(s.signal_info.signal_name)}</span>
          </div>
          <p class="text-sm">${escapeHtml(s.signal_info.signal_meaning)} • ${escapeHtml(s.signal_info.summary)}</p>
          <div class="field-label mt-8">Crashing Source Statement (Line ${s.signal_info.crashing_line}):</div>
          <div class="crash-statement-box">&gt; ${s.signal_info.crashing_line} | ${escapeHtml(s.signal_info.crashing_statement || '*ptr = 42;')}</div>
          <div class="field-label mt-8">Crash Location:</div>
          <div class="mono text-xs text-secondary">${escapeHtml(s.signal_info.crashing_file)}:${s.signal_info.crashing_line} in function ${escapeHtml(s.signal_info.crashing_func)}()</div>
        </div>
      `;
    }
    // Switch to signals tab so crash attribution is immediately visible
    switchDbgBottomTab('signals');
  } else {
    if (sigBadge) sigBadge.classList.add('hidden');
    if (crashCard) {
      crashCard.innerHTML = '<div class="clean-note"><span class="status-dot dot-emerald"></span><span>No signals or crashes detected. Program running cleanly.</span></div>';
    }
  }

  // System Call Evidence Tab
  const scSummary = document.getElementById('dbgSyscallSummaryStrip');
  const scBody = document.getElementById('dbgSyscallBody');
  if (s.syscall_evidence && s.syscall_evidence.total_syscalls > 0) {
    const sc = s.syscall_evidence;
    if (scSummary) {
      scSummary.innerHTML = `
        <div class="live-metrics-chips">
          <span class="mini-metric">Total Syscalls: <strong>${sc.total_syscalls}</strong></span>
          <span class="mini-metric">Failures: <strong class="${sc.total_failures > 0 ? 'text-amber' : ''}">${sc.total_failures}</strong></span>
          <span class="mini-metric">Signals Detected: <strong>${(sc.signals || []).length}</strong></span>
        </div>
      `;
    }
    if (scBody) {
      const fails = sc.grouped_failures || [];
      if (fails.length === 0) {
        scBody.innerHTML = '<tr><td colspan="4" class="text-muted text-center py-8">All captured system calls executed cleanly without errno failures.</td></tr>';
      } else {
        scBody.innerHTML = fails.map(f => `
          <tr>
            <td class="font-semibold text-rose-400">${escapeHtml(f.syscall)}</td>
            <td class="text-muted font-mono text-xs">${Number(f.count)} call(s) with ${escapeHtml(f.errno_name)}</td>
            <td><span class="badge badge-warning">${escapeHtml(f.errno_name)}</span> <span class="text-xs text-muted">(${escapeHtml(f.description)})</span></td>
            <td class="font-mono text-xs text-secondary">${escapeHtml(f.sample_args || '—')}</td>
          </tr>
        `).join('');
      }
    }
  }

  // Timeline Tab
  const timelineContainer = document.getElementById('dbgTimelineContainer');
  if (timelineContainer) {
    const tl = s.timeline || [];
    if (tl.length === 0) {
      timelineContainer.innerHTML = '<div class="text-muted py-8 text-center">No debugger events recorded yet.</div>';
    } else {
      timelineContainer.innerHTML = tl.map(item => `
        <div class="timeline-item">
          <span class="timeline-time">${escapeHtml(item.timestamp)}</span>
          <span class="timeline-event-tag">${escapeHtml(item.event)}</span>
          <span class="timeline-desc">${escapeHtml(item.description)}</span>
        </div>
      `).join('');
    }
  }
}

function setDebuggerButtonsState(state) {
  const isStopped = (state === 'STOPPED');
  const isRunning = (state === 'RUNNING');
  const isFinished = (state === 'EXITED' || state === 'SIGNALED' || state === 'USER_TERMINATED' || state === 'NOT_STARTED');

  const btnStart = document.getElementById('btnDbgStart');
  if (btnStart) btnStart.disabled = isStopped || isRunning;

  const btnNext = document.getElementById('btnDbgNext');
  if (btnNext) btnNext.disabled = !isStopped;

  const btnStepInto = document.getElementById('btnDbgStepInto');
  if (btnStepInto) btnStepInto.disabled = !isStopped;

  const btnStepOut = document.getElementById('btnDbgStepOut');
  if (btnStepOut) btnStepOut.disabled = !isStopped;

  const btnContinue = document.getElementById('btnDbgContinue');
  if (btnContinue) btnContinue.disabled = !isStopped;

  const btnStop = document.getElementById('btnDbgStop');
  if (btnStop) btnStop.disabled = isFinished;

  const btnSaveReport = document.getElementById('btnDbgSaveReport');
  if (btnSaveReport) btnSaveReport.disabled = (state === 'NOT_STARTED');
}

function setStepButtonsDisabled(disabled) {
  ['btnDbgNext', 'btnDbgStepInto', 'btnDbgStepOut', 'btnDbgContinue'].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.disabled = disabled;
  });
}

function setDebuggerPill(text, badgeClass) {
  const p1 = document.getElementById('dbgLiveStatePill');
  if (p1) {
    p1.className = `badge ${badgeClass}`;
    p1.textContent = text;
  }
  const p2 = document.getElementById('dbgHeaderStatusBadge');
  if (p2) {
    p2.className = `badge ${badgeClass}`;
    p2.textContent = text;
  }
}

function switchDbgBottomTab(tabName) {
  const tabs = ['output', 'signals', 'syscalls', 'timeline'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tabDbg${capitalizeWord(t)}`);
    const pane = document.getElementById(`dbgPane${capitalizeWord(t)}`);
    const active = (t === tabName);
    if (btn) btn.classList.toggle('active', active);
    if (pane) pane.classList.toggle('hidden', !active);
  });
}

function capitalizeWord(s) {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Backward compatibility alias for quickDebugProgram
function runDebuggerSession(progName) {
  quickDebugProgram(progName || document.getElementById('debuggerProgramSelect')?.value);
}

function pollActiveSession(sessionId, mode) {
  clearInterval(STATE.pollTimer);
  STATE.pollTimer = setInterval(async () => {
    const { ok, data } = await apiFetch(`/api/session/${encodeURIComponent(sessionId)}`);
    if (!ok) {
      clearInterval(STATE.pollTimer);
      return;
    }

    if (mode === 'debugger') {
      document.getElementById('dbgStatPid').textContent = data.pid || '—';
      document.getElementById('dbgStatPpid').textContent = data.ppid || '—';
      document.getElementById('dbgStatProcState').textContent = data.process_state || 'Running';
      document.getElementById('dbgStatElapsed').textContent = `${Number(data.elapsed_ms || 0).toFixed(2)} ms`;
      if (data.timeline_samples) {
        updateDebuggerCharts(data.timeline_samples);
      }
      const outText = [
        `$ Executing ${data.executable_path || data.program}`,
        data.program_stdout ? `\n--- Program STDOUT ---\n${data.program_stdout}` : '',
        data.program_stderr ? `\n--- Program STDERR ---\n${data.program_stderr}` : ''
      ].filter(Boolean).join('\n');
      document.getElementById('dbgLiveTerminal').textContent = outText;
    } else if (mode === 'autodebugger') {
      if (data.stages) renderAutoStages(data.stages);
    }

    if (data.state === 'completed' || data.state === 'error') {
      clearInterval(STATE.pollTimer);
      if (mode === 'debugger') {
        finishDebuggerLiveUI(data);
      } else {
        finishAutoDebuggerLiveUI(data);
      }
    }
  }, 160);
}

function finishDebuggerLiveUI(data) {
  STATE.currentResult = data;
  document.getElementById('btnStartDebugger')?.classList.remove('hidden');
  document.getElementById('btnStopDebugger')?.classList.add('hidden');
  document.getElementById('dbgViewFullResultWrap')?.classList.remove('hidden');

  const badge = document.getElementById('dbgLiveStateBadge');
  if (badge) {
    badge.outerHTML = `<span id="dbgLiveStateBadge">${renderStatusBadge(data.result_badge, data.badge_tone)}</span>`;
  }

  document.getElementById('dbgStatPid').textContent = data.pid || '—';
  document.getElementById('dbgStatPpid').textContent = data.ppid || '—';
  document.getElementById('dbgStatProcState').textContent = data.termination_type || 'Completed';
  document.getElementById('dbgStatElapsed').textContent = `${Number(data.elapsed_ms || 0).toFixed(2)} ms`;

  const pstats = data.process_stats || {};
  updateDebuggerCharts(pstats.timeline || [], pstats.short_process_note);
  if (pstats.peak_vm_size_kb) {
    document.getElementById('dbgLiveVmSize').textContent = `${pstats.peak_vm_size_kb} KB`;
    document.getElementById('dbgLiveVmRss').textContent = `${pstats.peak_vm_rss_kb} KB`;
    document.getElementById('dbgLiveThreads').textContent = pstats.peak_threads || 1;
    document.getElementById('dbgLiveFds').textContent = pstats.peak_open_fds >= 0 ? pstats.peak_open_fds : '—';
  }

  const termParts = [`$ Executing ${data.executable_path}`];
  if (data.program_stdout) {
    termParts.push(`\n--- Target STDOUT ---\n${data.program_stdout.trimEnd()}`);
  }
  if (data.program_stderr) {
    termParts.push(`\n--- Target STDERR ---\n${data.program_stderr.trimEnd()}`);
  }
  if (data.debugger_output) {
    termParts.push(`\n--- LDST C Debugger Engine Output ---\n${data.debugger_output.trimEnd()}`);
  }
  document.getElementById('dbgLiveTerminal').textContent = termParts.join('\n');

  renderDetailedResults(data);
}

async function stopActiveSession() {
  if (!STATE.activeSessionId) return;
  const { data } = await apiFetch(`/api/session/${encodeURIComponent(STATE.activeSessionId)}/stop`, {
    method: 'POST'
  });
  showToast(data.message || 'Sent stop signal to session.', 'info');
}

/* ==========================================================================
   AutoDebugger Execution & 6-Stage Investigation UI (Sections 17 & 18)
   ========================================================================== */

function renderAutoStages(stages) {
  const list = document.getElementById('autoStagesList');
  if (!list || !stages) return;
  list.innerHTML = stages.map(st => {
    const cls = st.status === 'completed'
      ? 'stage-completed'
      : st.status === 'running'
        ? 'stage-running'
        : st.status === 'skipped' || st.status === 'not_required'
          ? 'stage-skipped'
          : '';
    const icon = st.status === 'completed'
      ? '✓'
      : st.status === 'running'
        ? '●'
        : st.id;
    return `
      <div class="stage-item ${cls}">
        <span class="stage-indicator">${icon}</span>
        <div class="stage-body">
          <div class="stage-name">${escapeHtml(st.name)}</div>
          <div class="stage-detail">${escapeHtml(st.detail || '')}</div>
        </div>
      </div>
    `;
  }).join('');
}

async function runAutoDebuggerSession(overrideProgram = null) {
  const prog = overrideProgram || document.getElementById('autoProgramSelect')?.value;
  if (!prog) {
    showToast('Please select a target program.', 'error');
    return;
  }
  const enableGdb = document.getElementById('optAutoGdb')?.checked ?? true;

  document.getElementById('btnStartAutoDebug')?.classList.add('hidden');
  document.getElementById('btnStopAutoDebug')?.classList.remove('hidden');
  document.getElementById('btnAutoOpenFullTabs')?.classList.add('hidden');
  document.getElementById('autoDiagnosisHeroWrap').innerHTML = '';
  document.getElementById('autoLiveTerminal').textContent = `$ Launching LDST AutoDebugger for tests/${prog}...\n`;

  const { ok, data } = await apiFetch('/api/autodebug', {
    method: 'POST',
    body: {
      program: prog,
      enable_gdb: enableGdb,
      async: true
    }
  });

  if (!ok || data.success === false) {
    document.getElementById('btnStartAutoDebug')?.classList.remove('hidden');
    document.getElementById('btnStopAutoDebug')?.classList.add('hidden');
    document.getElementById('autoLiveTerminal').textContent =
      `$ AutoDebugger could not start:\n${data.error || 'Unknown error'}\n` +
      (data.compilation?.stderr ? `\n--- GCC Output ---\n${data.compilation.stderr}` : '');
    showToast(data.error || 'AutoDebugger failed.', 'error');
    return;
  }

  STATE.activeSessionId = data.session_id;
  if (data.stages) renderAutoStages(data.stages);

  if (data.state === 'completed') {
    finishAutoDebuggerLiveUI(data);
  } else {
    pollActiveSession(data.session_id, 'autodebugger');
  }
}

function finishAutoDebuggerLiveUI(data) {
  STATE.currentResult = data;
  document.getElementById('btnStartAutoDebug')?.classList.remove('hidden');
  document.getElementById('btnStopAutoDebug')?.classList.add('hidden');
  document.getElementById('btnAutoOpenFullTabs')?.classList.remove('hidden');

  if (data.stages) renderAutoStages(data.stages);

  const termParts = [];
  if (data.program_stdout) termParts.push(`--- Target STDOUT ---\n${data.program_stdout.trimEnd()}`);
  if (data.program_stderr) termParts.push(`--- Target STDERR ---\n${data.program_stderr.trimEnd()}`);
  if (data.debugger_output) termParts.push(`--- AutoDebugger Engine Stream ---\n${data.debugger_output.trimEnd()}`);
  document.getElementById('autoLiveTerminal').textContent = termParts.join('\n\n');

  // Render Crash / Clean / Failure Card in AutoDebugger view (Sections 18 & 19)
  const heroWrap = document.getElementById('autoDiagnosisHeroWrap');
  if (heroWrap) {
    heroWrap.innerHTML = buildAutoDiagnosisCardHtml(data);
  }

  renderDetailedResults(data);
}

function buildAutoDiagnosisCardHtml(data) {
  const isCrash = Boolean(data.terminated_by_signal);
  const isClean = !isCrash && data.exit_code === 0 && !data.detected_error;
  const gdb = data.gdb_analysis || {};
  const srcEv = data.source_evidence;

  let bannerClass = 'banner-warning';
  let headerTitle = `DIAGNOSIS: ${data.overall_status || data.result_badge}`;
  let badgeTag = 'DIAGNOSIS';
  let badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;

  if (isCrash) {
    bannerClass = 'banner-danger';
    headerTitle = 'PROGRAM CRASHED';
    badgeTag = data.signal_name || 'SIGSEGV';
    badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"></polygon><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
  } else if (isClean) {
    bannerClass = 'banner-success';
    headerTitle = 'CLEAN EXECUTION';
    badgeTag = 'EXIT 0';
    badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`;
  } else if (data.detected_error) {
    bannerClass = 'banner-danger';
    headerTitle = `SYSTEM CALL ERROR — ${data.detected_error.errno_name}`;
    badgeTag = data.detected_error.errno_name || 'ERRNO';
    badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
  }

  const snippetHtml = srcEv && srcEv.snippet
    ? `<div class="mt-12">
         <div class="field-label">SOURCE CONTEXT (${escapeHtml(srcEv.file)}:${srcEv.line} — ${escapeHtml(srcEv.attribution)})</div>
         <div class="code-snippet-box">
           ${srcEv.snippet.map(s => `
             <div class="code-line-row ${s.is_target ? 'line-highlight' : ''}">
               <span class="code-line-num">${s.line}</span>
               <span class="code-line-text">${escapeHtml(s.code)}</span>
             </div>
           `).join('')}
         </div>
       </div>`
    : '';

  const gdbHtml = isCrash
    ? `<div class="mt-12">
         <div class="field-label">GDB BACKTRACE (${escapeHtml(gdb.status_label || '')})</div>
         <pre class="terminal-box" style="min-height:90px;max-height:180px;">${escapeHtml(gdb.backtrace || gdb.status_label || 'GDB unavailable.')}</pre>
       </div>`
    : '';

  return `
    <div class="panel-card">
      <div class="results-hero-banner ${bannerClass}">
        <div>
          <div style="margin-bottom:8px;">${renderStatusBadge(data.result_badge, data.badge_tone)}</div>
          <h2 class="view-title" style="font-size:20px;">${escapeHtml(headerTitle)}</h2>
          <p class="view-subtitle">
            Program: <code>${escapeHtml(data.executable_path)}</code> •
            PID: <code>${escapeHtml(data.pid)}</code> •
            Duration: <code>${Number(data.elapsed_ms || 0).toFixed(2)} ms</code> •
            Exit/Signal: <code>${escapeHtml(isCrash ? `${data.signal_name} (${data.signal_number})` : `Exit ${data.exit_code}`)}</code>
          </p>
        </div>
        <div class="banner-badge-box">
          <div class="banner-badge-icon">${badgeIcon}</div>
          <span class="banner-badge-label">${escapeHtml(badgeTag)}</span>
        </div>
      </div>

      <div class="results-two-col">
        <div class="panel-card" style="margin-bottom:0;">
          <div class="panel-header"><h3 class="panel-title">OBSERVED FACTS</h3></div>
          <ul class="arch-list" style="margin-bottom:0;">
            ${(data.observed_facts || []).map(f => `<li>${escapeHtml(f)}</li>`).join('')}
          </ul>
        </div>
        <div class="panel-card" style="margin-bottom:0;">
          <div class="panel-header"><h3 class="panel-title">DIAGNOSTIC INTERPRETATION</h3></div>
          <p style="color:#ffffff;font-weight:600;margin-bottom:10px;">Likely Cause:</p>
          <p style="color:var(--text-secondary);margin-bottom:14px;">${escapeHtml(data.diagnosis)}</p>
          <p style="color:#ffffff;font-weight:600;margin-bottom:6px;">Recommended Next Step:</p>
          <p style="color:var(--text-secondary);">${escapeHtml(data.next_step)}</p>
        </div>
      </div>

      ${gdbHtml}
      ${snippetHtml}
    </div>
  `;
}

/* ==========================================================================
   6-Tab Detailed Results Page (Sections 15, 16, 18, 19)
   ========================================================================== */

function switchResultTab(tabId) {
  document.querySelectorAll('[data-rtab]').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-rtab') === tabId);
  });
  ['summary', 'syscalls', 'procinfo', 'output', 'source', 'rawlogs'].forEach(id => {
    const pane = document.getElementById(`rtab-${id}`);
    if (pane) pane.classList.toggle('hidden', id !== tabId);
  });
}

function renderDetailedResults(data) {
  if (!data) return;
  document.getElementById('resultsEmptyState')?.classList.add('hidden');
  document.getElementById('resultsContentWrap')?.classList.remove('hidden');

  document.getElementById('resultsPageHeading').textContent = `Diagnostic Results — ${data.program}`;
  document.getElementById('resultsPageSubheading').textContent =
    `Session ${data.session_id} • ${data.analysis_type} • ${data.display_time || data.timestamp}`;

  const actionsEl = document.getElementById('resultsHeaderActions');
  if (actionsEl) {
    actionsEl.innerHTML = `
      <a class="btn btn-sm btn-secondary" href="/api/reports/${encodeURIComponent(data.session_id)}/export/txt" download>Export TXT</a>
      <a class="btn btn-sm btn-secondary" href="/api/reports/${encodeURIComponent(data.session_id)}/export/json" download>Export JSON</a>
      <button class="btn btn-sm btn-blue" onclick="quickDebugProgram('${escapeHtml(data.program)}')">Re-Run Debugger</button>
      <button class="btn btn-sm btn-violet" onclick="quickAutoDebugProgram('${escapeHtml(data.program)}')">Re-Run AutoDebugger</button>
    `;
  }

  // Top Status Banner
  const isCrash = Boolean(data.terminated_by_signal);
  const isClean = !isCrash && data.exit_code === 0 && !data.detected_error;
  const bannerEl = document.getElementById('resultsHeroBanner');
  if (bannerEl) {
    let bClass = 'banner-warning';
    let bHeading = data.overall_status || 'Execution Completed';
    let bSub = '';
    let badgeTag = 'COMPLETED';
    let badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;

    if (isClean) {
      bClass = 'banner-success';
      bHeading = 'CLEAN EXECUTION';
      bSub = `Program completed normally. Exit code: 0 • Signal: None • Relevant failed system calls: 0`;
      badgeTag = 'EXIT 0';
      badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`;
    } else if (isCrash) {
      bClass = 'banner-danger';
      bHeading = `PROGRAM CRASHED — ${data.signal_name} (${data.signal_number})`;
      bSub = data.signal_description || 'Abnormal process termination by signal.';
      badgeTag = data.signal_name || 'CRASH';
      badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"></polygon><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
    } else if (data.detected_error) {
      bClass = 'banner-danger';
      bHeading = `DETECTED ERROR — ${data.detected_error.syscall}() failed with ${data.detected_error.errno_name}`;
      bSub = `errno ${data.detected_error.errno_code}: ${data.detected_error.description}`;
      badgeTag = data.detected_error.errno_name || 'ERRNO';
      badgeIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    } else {
      bSub = `Exit status: ${data.exit_code ?? 'N/A'} • Termination: ${data.termination_type}`;
    }

    bannerEl.className = `results-hero-banner ${bClass}`;
    bannerEl.innerHTML = `
      <div>
        <div style="margin-bottom:8px;">${renderStatusBadge(data.result_badge, data.badge_tone)}</div>
        <h2 class="view-title" style="font-size:20px;">${escapeHtml(bHeading)}</h2>
        <p class="view-subtitle">${escapeHtml(bSub)}</p>
      </div>
      <div class="banner-badge-box">
        <div class="banner-badge-icon">${badgeIcon}</div>
        <span class="banner-badge-label">${escapeHtml(badgeTag)}</span>
      </div>
    `;
  }

  // TAB 1: SUMMARY
  const err = data.detected_error;
  const pstats = data.process_stats || {};
  const sc = data.syscall_analysis || {};
  const srcEv = data.source_evidence;

  const detectedErrorCardHtml = err && err.syscall
    ? `<div class="panel-card detected-error-card">
         <div class="panel-header">
           <h3 class="panel-title">DETECTED ERROR</h3>
           ${renderStatusBadge(`${err.errno_name} (${err.errno_code})`, 'danger')}
         </div>
         <div class="kv-list">
           <div class="kv-row"><span class="kv-key">Failed Operation</span><span class="kv-val mono">${escapeHtml(err.syscall)}() failed</span></div>
           <div class="kv-row"><span class="kv-key">Return Value</span><span class="kv-val mono">-1</span></div>
           <div class="kv-row"><span class="kv-key">Error (errno)</span><span class="kv-val mono">${escapeHtml(err.errno_name)} (${err.errno_code})</span></div>
           <div class="kv-row"><span class="kv-key">Description</span><span class="kv-val">${escapeHtml(err.description)}</span></div>
         </div>
         <div class="mt-12">
           <div class="field-label">Raw strace Evidence</div>
           <pre class="terminal-box" style="min-height:54px;padding:10px;">${escapeHtml(err.evidence || err.raw || '')}</pre>
         </div>
       </div>`
    : `<div class="panel-card">
         <div class="panel-header"><h3 class="panel-title">ERROR / ERRNO STATUS</h3></div>
         <p class="view-subtitle">
           ${isCrash
             ? `Process terminated abnormally with signal <code>${escapeHtml(data.signal_name)} (${data.signal_number})</code>.`
             : 'No relevant failed system calls were detected during execution.'}
         </p>
       </div>`;

  const sourceEvidenceHtml = srcEv && srcEv.snippet
    ? `<div class="panel-card">
         <div class="panel-header">
           <h3 class="panel-title">SOURCE EVIDENCE</h3>
           <span class="mini-pill">${escapeHtml(srcEv.file)}:${srcEv.line} (${escapeHtml(srcEv.attribution)})</span>
         </div>
         <div class="code-snippet-box">
           ${srcEv.snippet.map(s => `
             <div class="code-line-row ${s.is_target ? 'line-highlight' : ''}">
               <span class="code-line-num">${s.line}</span>
               <span class="code-line-text">${escapeHtml(s.code)}</span>
             </div>
           `).join('')}
         </div>
       </div>`
    : `<div class="panel-card">
         <div class="panel-header"><h3 class="panel-title">SOURCE EVIDENCE</h3></div>
         <p class="view-subtitle">No specific failing source line was attributed for this run. Open the <strong>SOURCE</strong> tab to inspect <code>${escapeHtml(data.source_path)}</code>.</p>
       </div>`;

  document.getElementById('rtab-summary').innerHTML = `
    <div class="results-two-col">
      <div class="panel-card">
        <div class="panel-header"><h3 class="panel-title">EXECUTION SUMMARY</h3></div>
        <div class="kv-list">
          <div class="kv-row"><span class="kv-key">Program</span><span class="kv-val mono">${escapeHtml(data.program)}</span></div>
          <div class="kv-row"><span class="kv-key">Source File</span><span class="kv-val mono">${escapeHtml(data.source_path)}</span></div>
          <div class="kv-row"><span class="kv-key">Executable</span><span class="kv-val mono">${escapeHtml(data.executable_path)}</span></div>
          <div class="kv-row"><span class="kv-key">Target PID / PPID</span><span class="kv-val mono">${escapeHtml(data.pid ?? 'Unavailable')} / ${escapeHtml(data.ppid ?? 'Unavailable')}</span></div>
          <div class="kv-row"><span class="kv-key">Start Time</span><span class="kv-val mono">${escapeHtml(data.start_time)}</span></div>
          <div class="kv-row"><span class="kv-key">End Time</span><span class="kv-val mono">${escapeHtml(data.end_time)}</span></div>
          <div class="kv-row"><span class="kv-key">Execution Duration</span><span class="kv-val mono">${Number(data.elapsed_ms || 0).toFixed(2)} ms</span></div>
          <div class="kv-row"><span class="kv-key">Termination Type</span><span class="kv-val">${escapeHtml(data.termination_type)}</span></div>
          <div class="kv-row"><span class="kv-key">Exit Status</span><span class="kv-val mono">${escapeHtml(data.exit_code ?? 'N/A')}</span></div>
          <div class="kv-row"><span class="kv-key">Signal</span><span class="kv-val mono">${escapeHtml(data.signal_name ? `${data.signal_name} (${data.signal_number})` : 'None')}</span></div>
          <div class="kv-row"><span class="kv-key">Compilation Status</span><span class="kv-val">${data.compilation?.success !== false ? '✓ Compiled' : '✕ Failed'}</span></div>
          <div class="kv-row"><span class="kv-key">Analysis Engine</span><span class="kv-val mono">${escapeHtml(data.analysis_type)}</span></div>
        </div>
      </div>

      <div>
        ${detectedErrorCardHtml}
        <div class="panel-card">
          <div class="panel-header"><h3 class="panel-title">PROCESS STATISTICS (/proc)</h3></div>
          <div class="kv-list">
            <div class="kv-row"><span class="kv-key">Peak VmSize</span><span class="kv-val mono">${pstats.peak_vm_size_kb ? `${pstats.peak_vm_size_kb} KB` : 'Unavailable'}</span></div>
            <div class="kv-row"><span class="kv-key">Peak VmRSS</span><span class="kv-val mono">${pstats.peak_vm_rss_kb ? `${pstats.peak_vm_rss_kb} KB` : 'Unavailable'}</span></div>
            <div class="kv-row"><span class="kv-key">Peak Threads</span><span class="kv-val mono">${pstats.peak_threads || 'Unavailable'}</span></div>
            <div class="kv-row"><span class="kv-key">Peak Open FDs</span><span class="kv-val mono">${pstats.peak_open_fds >= 0 ? pstats.peak_open_fds : 'Unavailable'}</span></div>
            <div class="kv-row"><span class="kv-key">Monitoring Samples</span><span class="kv-val mono">${pstats.samples_count ?? 0}</span></div>
            <div class="kv-row"><span class="kv-key">Total Captured Syscalls</span><span class="kv-val mono">${sc.available ? sc.total_syscalls : 'Not captured'}</span></div>
            <div class="kv-row"><span class="kv-key">Relevant Failed Syscalls</span><span class="kv-val mono">${sc.available ? sc.relevant_failures : 'Not captured'}</span></div>
          </div>
        </div>
      </div>
    </div>

    ${sourceEvidenceHtml}

    <div class="results-two-col">
      <div class="panel-card">
        <div class="panel-header"><h3 class="panel-title">OBSERVED FACTS</h3></div>
        <ul class="arch-list">
          ${(data.observed_facts || []).map(f => `<li>${escapeHtml(f)}</li>`).join('')}
        </ul>
      </div>
      <div class="panel-card">
        <div class="panel-header"><h3 class="panel-title">DIAGNOSTIC INTERPRETATION</h3></div>
        <p style="font-weight:600;color:#fff;margin-bottom:6px;">Diagnosis:</p>
        <p style="color:var(--text-secondary);margin-bottom:14px;">${escapeHtml(data.diagnosis)}</p>
        <p style="font-weight:600;color:#fff;margin-bottom:6px;">Recommended Next Step:</p>
        <p style="color:var(--text-secondary);">${escapeHtml(data.next_step)}</p>
      </div>
    </div>
  `;

  // TAB 2: SYSTEM CALLS (Section 16)
  if (!sc.available) {
    document.getElementById('rtab-syscalls').innerHTML = `
      <div class="panel-card">
        <div class="panel-header"><h3 class="panel-title">SYSTEM CALL ANALYSIS</h3></div>
        <p class="view-subtitle">System-call tracing was disabled or not captured for this session. Run with <strong>Debugger</strong> or <strong>AutoDebugger</strong> with tracing enabled.</p>
      </div>
    `;
  } else {
    const grouped = sc.grouped_failures || [];
    document.getElementById('rtab-syscalls').innerHTML = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">Total Captured Syscalls</span></div>
          <div class="stat-value">${sc.total_syscalls}</div>
          <div class="stat-meta">Parsed from ${escapeHtml(data.trace_file || 'strace')}</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">Relevant Failures</span></div>
          <div class="stat-value">${sc.relevant_failures}</div>
          <div class="stat-meta">Target program syscall errors</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">Loader / Setup Probing</span></div>
          <div class="stat-value">${sc.loader_noise_failures}</div>
          <div class="stat-meta">Conservatively filtered startup calls</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">Total Return = -1 Calls</span></div>
          <div class="stat-value">${sc.total_failures}</div>
          <div class="stat-meta">All failed syscalls in raw trace</div>
        </div>
      </div>

      <div class="panel-card">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">Grouped Failed System Calls</h3>
            <span class="panel-hint">Click any row to inspect return value, errno description, and raw strace lines</span>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="switchResultTab('rawlogs')">VIEW RAW TRACE</button>
        </div>

        ${grouped.length === 0
          ? `<p class="view-subtitle">No failed system calls (return = -1) were recorded in the trace.</p>`
          : `<div class="table-responsive">
               <table class="data-table">
                 <thead>
                   <tr>
                     <th>System Call</th>
                     <th>Result</th>
                     <th>errno</th>
                     <th>Description</th>
                     <th>Classification</th>
                     <th>Count</th>
                   </tr>
                 </thead>
                 <tbody>
                   ${grouped.map((g, idx) => `
                     <tr style="cursor:pointer;" onclick="document.getElementById('sc-exp-${idx}').classList.toggle('hidden')">
                       <td class="mono"><strong>${escapeHtml(g.syscall)}</strong></td>
                       <td class="mono">${escapeHtml(g.result)}</td>
                       <td>${renderStatusBadge(`${g.errno_name} (${g.errno_code})`, g.is_noise ? 'neutral' : 'danger')}</td>
                       <td>${escapeHtml(g.description)}</td>
                       <td><span class="mini-pill ${g.is_noise ? 'pill-off' : ''}">${escapeHtml(g.classification)}</span></td>
                       <td class="mono"><strong>${g.count}</strong></td>
                     </tr>
                     <tr id="sc-exp-${idx}" class="${g.is_noise ? 'hidden' : ''}">
                       <td colspan="6" style="background:var(--bg-deep-navy);padding:12px 16px;">
                         <div class="field-label">Raw strace Evidence for ${escapeHtml(g.syscall)} → ${escapeHtml(g.errno_name)}</div>
                         <pre class="terminal-box" style="min-height:60px;max-height:160px;padding:10px;">${escapeHtml((g.evidence_lines || []).join('\n'))}</pre>
                       </td>
                     </tr>
                   `).join('')}
                 </tbody>
               </table>
             </div>`
        }
      </div>
    `;
  }

  // TAB 3: PROCESS INFO
  const timeline = pstats.timeline || [];
  document.getElementById('rtab-procinfo').innerHTML = `
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-top"><span class="stat-label">Peak VmSize</span></div>
        <div class="stat-value">${pstats.peak_vm_size_kb ? `${pstats.peak_vm_size_kb} KB` : 'Unavailable'}</div>
        <div class="stat-meta">Virtual address space peak</div>
      </div>
      <div class="stat-card">
        <div class="stat-top"><span class="stat-label">Peak VmRSS</span></div>
        <div class="stat-value">${pstats.peak_vm_rss_kb ? `${pstats.peak_vm_rss_kb} KB` : 'Unavailable'}</div>
        <div class="stat-meta">Resident physical memory peak</div>
      </div>
      <div class="stat-card">
        <div class="stat-top"><span class="stat-label">Peak Threads</span></div>
        <div class="stat-value">${pstats.peak_threads || 'Unavailable'}</div>
        <div class="stat-meta">From /proc/&lt;pid&gt;/status</div>
      </div>
      <div class="stat-card">
        <div class="stat-top"><span class="stat-label">Peak Open FDs</span></div>
        <div class="stat-value">${pstats.peak_open_fds >= 0 ? pstats.peak_open_fds : 'Unavailable'}</div>
        <div class="stat-meta">Counted in /proc/&lt;pid&gt;/fd</div>
      </div>
    </div>

    <div class="panel-card">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">Collected /proc Monitoring Samples (${timeline.length})</h3>
          <span class="panel-hint">${escapeHtml(pstats.short_process_note || 'Real snapshots read from /proc during execution')}</span>
        </div>
      </div>
      ${timeline.length === 0
        ? `<p class="view-subtitle">Process completed before periodic /proc samples could be collected.</p>`
        : `<div class="table-responsive">
             <table class="data-table">
               <thead>
                 <tr>
                   <th>Sample #</th>
                   <th>Elapsed (ms)</th>
                   <th>PID</th>
                   <th>PPID</th>
                   <th>State</th>
                   <th>CPU %</th>
                   <th>VmSize (KB)</th>
                   <th>VmRSS (KB)</th>
                   <th>Threads</th>
                   <th>Open FDs</th>
                 </tr>
               </thead>
               <tbody>
                 ${timeline.map(pt => `
                   <tr>
                     <td class="mono">${pt.sample_index}</td>
                     <td class="mono">${Number(pt.elapsed_ms).toFixed(2)} ms</td>
                     <td class="mono">${pt.pid}</td>
                     <td class="mono">${pt.ppid}</td>
                     <td class="mono">${escapeHtml(pt.state)}</td>
                     <td class="mono">${Number(pt.cpu_percent || 0).toFixed(1)}%</td>
                     <td class="mono">${pt.vm_size_kb}</td>
                     <td class="mono">${pt.vm_rss_kb}</td>
                     <td class="mono">${pt.threads}</td>
                     <td class="mono">${pt.open_fds >= 0 ? pt.open_fds : '—'}</td>
                   </tr>
                 `).join('')}
               </tbody>
             </table>
           </div>`
      }
    </div>
  `;

  // TAB 4: PROGRAM OUTPUT
  document.getElementById('rtab-output').innerHTML = `
    <div class="results-two-col">
      <div class="panel-card">
        <div class="panel-header"><h3 class="panel-title">Target Program STDOUT</h3></div>
        <pre class="terminal-box">${escapeHtml(data.program_stdout || '(No standard output produced by target program)')}</pre>
      </div>
      <div class="panel-card">
        <div class="panel-header"><h3 class="panel-title">Target Program STDERR</h3></div>
        <pre class="terminal-box">${escapeHtml(data.program_stderr || '(No standard error output produced by target program)')}</pre>
      </div>
    </div>
    <div class="panel-card">
      <div class="panel-header"><h3 class="panel-title">LDST C Engine Diagnostic Output</h3></div>
      <pre class="terminal-box">${escapeHtml(data.debugger_output || '(Direct run mode)')}</pre>
    </div>
  `;

  // TAB 5: SOURCE
  const srcLines = (data.source_code || '').split('\n');
  const hlLine = srcEv?.line || 0;
  document.getElementById('rtab-source').innerHTML = `
    <div class="panel-card">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">Source File: <code>${escapeHtml(data.source_path)}</code></h3>
          <span class="panel-hint">${hlLine ? `Highlighted line ${hlLine} (${escapeHtml(srcEv.attribution)})` : 'Full C source code'}</span>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="openEditorForProgram('${escapeHtml(data.program)}')">Open in Editor</button>
      </div>
      <div class="code-snippet-box">
        ${srcLines.map((ln, idx) => `
          <div class="code-line-row ${(idx + 1) === hlLine ? 'line-highlight' : ''}">
            <span class="code-line-num">${idx + 1}</span>
            <span class="code-line-text">${escapeHtml(ln)}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  // TAB 6: RAW LOGS
  const gdb = data.gdb_analysis || {};
  document.getElementById('rtab-rawlogs').innerHTML = `
    <div class="panel-card">
      <div class="panel-header">
        <h3 class="panel-title">Raw strace System-Call Trace (${escapeHtml(data.trace_file || 'Not enabled')})</h3>
      </div>
      <pre class="terminal-box" style="max-height:420px;">${escapeHtml(sc.raw_trace || 'No strace log recorded for this session.')}</pre>
    </div>

    <div class="panel-card">
      <div class="panel-header">
        <h3 class="panel-title">Raw GDB Output (${escapeHtml(gdb.status_label || 'Not run')})</h3>
      </div>
      <pre class="terminal-box">${escapeHtml(gdb.raw_output || gdb.backtrace || gdb.status_label || 'GDB was not required for this session.')}</pre>
    </div>
  `;
}

/* ==========================================================================
   System Monitor View (/proc)
   ========================================================================== */

async function refreshSystemMonitor() {
  const { ok, data } = await apiFetch('/api/monitor');
  if (!ok) return;

  const mem = data.memory || {};
  const load = data.loadavg || {};

  document.getElementById('monMemPercent').textContent = `${mem.used_percent ?? 0}%`;
  document.getElementById('monMemDetail').textContent =
    `${Math.round((mem.used_kb || 0) / 1024)} MB / ${Math.round((mem.total_kb || 0) / 1024)} MB`;

  document.getElementById('monLoadAvg').textContent =
    `${Number(load.load_1m || 0).toFixed(2)} / ${Number(load.load_5m || 0).toFixed(2)} / ${Number(load.load_15m || 0).toFixed(2)}`;
  document.getElementById('monLoadTasks').textContent =
    `Scheduling entities: ${load.scheduling_entities || '—'}`;

  const upSec = Number(data.uptime_seconds || 0);
  const hrs = Math.floor(upSec / 3600);
  const mins = Math.floor((upSec % 3600) / 60);
  document.getElementById('monUptime').textContent = `${hrs}h ${mins}m`;
  document.getElementById('monActiveSessions').textContent = (data.active_debug_sessions || []).length;

  const tbody = document.getElementById('monitorProcessTableBody');
  if (tbody) {
    const procs = data.user_processes || [];
    if (procs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9">No user processes found in /proc.</td></tr>`;
    } else {
      tbody.innerHTML = procs.map(p => `
        <tr>
          <td class="mono"><strong>${p.pid}</strong></td>
          <td class="mono">${p.ppid}</td>
          <td class="mono">${escapeHtml(p.name)}</td>
          <td class="mono">${escapeHtml(p.state)}</td>
          <td class="mono">${p.vm_size_kb}</td>
          <td class="mono">${p.vm_rss_kb}</td>
          <td class="mono">${p.threads}</td>
          <td class="mono">${p.open_fds >= 0 ? p.open_fds : '—'}</td>
          <td class="mono" style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(p.cmdline)}</td>
        </tr>
      `).join('');
    }
  }
}

/* ==========================================================================
   Reports View (Section 21)
   ========================================================================== */

async function loadReportsList() {
  const q = document.getElementById('reportsSearchInput')?.value.trim() || '';
  const type = document.getElementById('reportsTypeFilter')?.value || 'all';
  const result = document.getElementById('reportsResultFilter')?.value || 'ALL';

  const url = `/api/reports?q=${encodeURIComponent(q)}&type=${encodeURIComponent(type)}&result=${encodeURIComponent(result)}`;
  const { ok, data } = await apiFetch(url);
  if (!ok) return;

  const reports = data.reports || [];
  const container = document.getElementById('reportsListContainer');
  if (!container) return;

  if (reports.length === 0) {
    container.innerHTML = `
      <div class="empty-state-card">
        <img src="/static/images/empty_analysis.jpg" alt="No Reports Found" class="supporting-illustration" />
        <h3 class="empty-title">NO MATCHING REPORTS</h3>
        <p class="empty-desc">Run the Debugger or AutoDebugger on any C program to generate persistent diagnostic reports.</p>
        <div class="empty-actions">
          <button class="btn btn-primary" onclick="switchView('debugger')">OPEN DEBUGGER</button>
          <button class="btn btn-secondary" onclick="switchView('autodebugger')">OPEN AUTODEBUGGER</button>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="table-responsive">
      <table class="data-table">
        <thead>
          <tr>
            <th>Report ID</th>
            <th>Program</th>
            <th>Analysis Type</th>
            <th>Result</th>
            <th>Duration</th>
            <th>Date / Time</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${reports.map(r => `
            <tr>
              <td class="mono">${escapeHtml(r.session_id)}</td>
              <td class="mono"><strong>${escapeHtml(r.program)}</strong></td>
              <td>${escapeHtml(r.analysis_type)}</td>
              <td>${renderStatusBadge(r.result_badge, r.badge_tone)}</td>
              <td class="mono">${Number(r.elapsed_ms || 0).toFixed(2)} ms</td>
              <td class="mono">${escapeHtml(r.display_time || r.timestamp)}</td>
              <td>
                <div class="table-actions">
                  <button class="btn btn-sm btn-primary" onclick="openReportById('${escapeHtml(r.session_id)}')">VIEW</button>
                  <a class="btn btn-sm btn-secondary" href="/api/reports/${encodeURIComponent(r.session_id)}/export/txt" download>TXT</a>
                  <a class="btn btn-sm btn-secondary" href="/api/reports/${encodeURIComponent(r.session_id)}/export/json" download>JSON</a>
                  <button class="btn btn-sm btn-danger" onclick="confirmDeleteReport('${escapeHtml(r.session_id)}')">DELETE</button>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

async function openReportById(sessionId) {
  const { ok, data } = await apiFetch(`/api/reports/${encodeURIComponent(sessionId)}`);
  if (!ok) {
    showToast(data.error || 'Could not load report.', 'error');
    return;
  }
  STATE.currentResult = data;
  renderDetailedResults(data);
  switchView('results');
}

function confirmDeleteReport(sessionId) {
  openModal(
    `Delete Diagnostic Report`,
    `<p>Are you sure you want to permanently delete report <code>${escapeHtml(sessionId)}</code>?</p>`,
    `
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn btn-danger" onclick="executeDeleteReport('${escapeHtml(sessionId)}')">Confirm Delete</button>
    `
  );
}

async function executeDeleteReport(sessionId) {
  closeModal();
  const { ok, data } = await apiFetch(`/api/reports/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE'
  });
  if (ok && data.success) {
    showToast(`Deleted report ${sessionId}.`, 'success');
    loadReportsList();
    refreshDashboard();
  } else {
    showToast(data.error || 'Failed to delete report.', 'error');
  }
}

/* ==========================================================================
   Modal Helpers & Initialization
   ========================================================================== */

function openModal(title, bodyHtml, footerHtml) {
  document.getElementById('appModalTitle').textContent = title;
  document.getElementById('appModalBody').innerHTML = bodyHtml;
  document.getElementById('appModalFooter').innerHTML = footerHtml;
  document.getElementById('appModalOverlay').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('appModalOverlay')?.classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
  // Sidebar navigation listeners
  document.querySelectorAll('.side-link').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.getAttribute('data-view');
      if (view) switchView(view);
    });
  });

  document.getElementById('sidebarCollapseBtn')?.addEventListener('click', () => {
    document.getElementById('appShell')?.classList.toggle('sidebar-collapsed');
  });

  document.getElementById('mobileMenuBtn')?.addEventListener('click', () => {
    document.getElementById('appShell')?.classList.toggle('mobile-open');
  });

  // Code Editor listeners (Tab key, line numbers, cursor line/col)
  const ta = document.getElementById('cSourceTextarea');
  if (ta) {
    ta.value = STARTER_TEMPLATES.hello;
    updateEditorLineNumbers();

    ta.addEventListener('input', updateEditorLineNumbers);
    ta.addEventListener('scroll', () => {
      const gutter = document.getElementById('editorLineNumbers');
      if (gutter) gutter.scrollTop = ta.scrollTop;
    });
    ta.addEventListener('keydown', e => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        ta.value = ta.value.substring(0, start) + '    ' + ta.value.substring(end);
        ta.selectionStart = ta.selectionEnd = start + 4;
        updateEditorLineNumbers();
      }
    });
    const updateCursorPos = () => {
      const textUpToCursor = ta.value.substring(0, ta.selectionStart);
      const lines = textUpToCursor.split('\n');
      const ln = lines.length;
      const col = lines[lines.length - 1].length + 1;
      const posEl = document.getElementById('editorStatusRight');
      if (posEl) posEl.textContent = `Line ${ln}, Col ${col}`;
    };
    ta.addEventListener('keyup', updateCursorPos);
    ta.addEventListener('click', updateCursorPos);
  }

  refreshToolchainStatus();
  loadPrograms();

  const initialHash = (window.location.hash || '#dashboard').replace('#', '');
  switchView(VIEW_TITLES[initialHash] ? initialHash : 'dashboard');
});
