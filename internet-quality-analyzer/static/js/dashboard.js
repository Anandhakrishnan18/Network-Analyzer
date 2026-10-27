/**
 * NetPulse.io - Internet Quality Analyzer & Troubleshooter
 * Frontend Application Dashboard Controller & Chart.js Integration
 */

// Global State
const State = {
    config: null,
    activeTimeframeHours: 1,
    latencyChart: null,
    dnsChart: null,
    isTesting: false,
    isMonitoring: false,
    selectedRunIds: [],
    activeTestRunId: null,
};

// DOM Content Loaded Entrypoint
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    initEventListeners();
    await loadConfig();
    await checkHealth();
    await checkMonitoringStatus();
    await checkAlerts();
    await refreshHistoryAndStats();
}

/**
 * Initialize all DOM event listeners
 */
function initEventListeners() {
    // Run Diagnostics Button
    const runBtn = document.getElementById('btn-run-diagnostics');
    if (runBtn) {
        runBtn.addEventListener('click', handleRunDiagnostics);
    }

    // Refresh History Button
    const refreshBtn = document.getElementById('btn-refresh-history');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => refreshHistoryAndStats());
    }

    // Export CSV Button
    const exportBtn = document.getElementById('btn-export-csv');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            window.location.href = `/api/export/csv?hours=${State.activeTimeframeHours * 7}`;
        });
    }

    // Timeframe Chips (1h, 24h, 7d)
    const timeframeChips = document.querySelectorAll('.chart-timeframe-selector .btn-chip');
    timeframeChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            timeframeChips.forEach(c => c.classList.remove('active'));
            e.currentTarget.classList.add('active');
            State.activeTimeframeHours = parseInt(e.currentTarget.dataset.hours, 10);
            refreshHistoryAndStats();
        });
    });

    // Monitoring Toggle Button
    const monitorBtn = document.getElementById('btn-toggle-monitoring');
    if (monitorBtn) {
        monitorBtn.addEventListener('click', toggleMonitoring);
    }

    // Dismiss Alerts Button
    const dismissAlertsBtn = document.getElementById('btn-dismiss-alerts');
    if (dismissAlertsBtn) {
        dismissAlertsBtn.addEventListener('click', () => {
            const banner = document.getElementById('alert-banner');
            if (banner) banner.style.display = 'none';
        });
    }

    // Compare Sessions Button
    const compareBtn = document.getElementById('btn-compare-runs');
    if (compareBtn) {
        compareBtn.addEventListener('click', openComparisonModal);
    }

    // Modal Export Buttons (Single Test & Comparison)
    const exportSingleTestBtn = document.getElementById('btn-export-single-test-json');
    if (exportSingleTestBtn) {
        exportSingleTestBtn.addEventListener('click', () => {
            if (State.activeTestRunId) {
                window.location.href = `/api/export/test/${State.activeTestRunId}/json`;
            }
        });
    }

    const exportCompareCsvBtn = document.getElementById('btn-export-compare-csv');
    if (exportCompareCsvBtn) {
        exportCompareCsvBtn.addEventListener('click', () => {
            if (State.selectedRunIds.length === 2) {
                window.location.href = `/api/export/comparison/csv?run_a=${State.selectedRunIds[0]}&run_b=${State.selectedRunIds[1]}`;
            }
        });
    }

    const exportCompareJsonBtn = document.getElementById('btn-export-compare-json');
    if (exportCompareJsonBtn) {
        exportCompareJsonBtn.addEventListener('click', () => {
            if (State.selectedRunIds.length === 2) {
                window.location.href = `/api/export/comparison/json?run_a=${State.selectedRunIds[0]}&run_b=${State.selectedRunIds[1]}`;
            }
        });
    }

    // Modal Close Listeners (Detail & Comparison)
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalOverlay = document.getElementById('modal-test-detail');
    if (modalCloseBtn && modalOverlay) {
        modalCloseBtn.addEventListener('click', () => {
            modalOverlay.style.display = 'none';
        });
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                modalOverlay.style.display = 'none';
            }
        });
    }

    const modalCompareCloseBtn = document.getElementById('modal-compare-close-btn');
    const modalCompareOverlay = document.getElementById('modal-comparison');
    if (modalCompareCloseBtn && modalCompareOverlay) {
        modalCompareCloseBtn.addEventListener('click', () => {
            modalCompareOverlay.style.display = 'none';
        });
        modalCompareOverlay.addEventListener('click', (e) => {
            if (e.target === modalCompareOverlay) {
                modalCompareOverlay.style.display = 'none';
            }
        });
    }
}

/**
 * Check Background Monitoring Daemon Status
 */
async function checkMonitoringStatus() {
    try {
        const res = await fetch('/api/monitoring/status');
        const json = await res.json();
        if (json.status === 'success') {
            updateMonitoringUI(json.data.running, json.data.interval_seconds);
        }
    } catch (err) {
        console.error('Failed to check monitoring status:', err);
    }
}

/**
 * Toggle Periodic Monitoring On/Off
 */
async function toggleMonitoring() {
    const monitorBtn = document.getElementById('btn-toggle-monitoring');
    const intervalSelect = document.getElementById('select-monitoring-interval');
    const interval = intervalSelect ? parseInt(intervalSelect.value, 10) : 300;

    const endpoint = State.isMonitoring ? '/api/monitoring/stop' : '/api/monitoring/start';
    const payload = State.isMonitoring ? {} : { interval_seconds: interval };

    if (monitorBtn) monitorBtn.disabled = true;

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const json = await res.json();
        if (json.status === 'success') {
            await checkMonitoringStatus();
        }
    } catch (err) {
        console.error('Failed to toggle monitoring:', err);
    } finally {
        if (monitorBtn) monitorBtn.disabled = false;
    }
}

/**
 * Update Monitoring Button and Indicator in UI
 */
function updateMonitoringUI(isRunning, intervalSec) {
    State.isMonitoring = isRunning;
    const btnText = document.getElementById('btn-monitoring-text');
    const pulseDot = document.getElementById('monitoring-pulse-dot');
    const monitorBtn = document.getElementById('btn-toggle-monitoring');

    if (isRunning) {
        const mins = Math.round(intervalSec / 60);
        if (btnText) btnText.textContent = `Monitoring Active (Every ${mins}m)`;
        if (pulseDot) pulseDot.style.display = 'inline-block';
        if (monitorBtn) {
            monitorBtn.classList.remove('btn-secondary');
            monitorBtn.classList.add('btn-primary');
        }
    } else {
        if (btnText) btnText.textContent = 'Start Periodic Monitoring';
        if (pulseDot) pulseDot.style.display = 'none';
        if (monitorBtn) {
            monitorBtn.classList.remove('btn-primary');
            monitorBtn.classList.add('btn-secondary');
        }
    }
}

/**
 * Check Recent Threshold Alerts
 */
async function checkAlerts() {
    try {
        const res = await fetch('/api/alerts?limit=5');
        const json = await res.json();
        const banner = document.getElementById('alert-banner');
        const bannerText = document.getElementById('alert-banner-text');

        if (json.status === 'success' && json.data && json.data.length > 0 && banner && bannerText) {
            const latestAlert = json.data[0];
            bannerText.innerHTML = `<strong>Alert:</strong> ${escapeHtml(latestAlert.message)} <span style="font-size:0.75rem; color:var(--text-muted);">(${new Date(latestAlert.timestamp_utc).toLocaleTimeString()})</span>`;
            banner.style.display = 'flex';
        }
    } catch (err) {
        console.error('Failed to check alerts:', err);
    }
}

/**
 * Fetch system configuration and render target selection pills
 */
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        const json = await res.json();
        if (json.status === 'success') {
            State.config = json.data;
            renderTargetPills(State.config.allowed_targets);
        }
    } catch (err) {
        console.error('Failed to load configuration:', err);
    }
}

/**
 * Render interactive target pills
 */
function renderTargetPills(targets) {
    const container = document.getElementById('target-pills-list');
    if (!container) return;

    container.innerHTML = '';
    targets.forEach(t => {
        const pill = document.createElement('label');
        pill.className = 'target-pill active';
        pill.id = `pill-target-${t.id}`;
        pill.innerHTML = `
            <input type="checkbox" value="${t.id}" checked>
            <span class="target-pill-name">${escapeHtml(t.name)}</span>
            <span class="target-pill-type">${escapeHtml(t.type)}</span>
        `;

        const checkbox = pill.querySelector('input');
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                pill.classList.add('active');
            } else {
                pill.classList.remove('active');
            }
        });

        container.appendChild(pill);
    });
}

/**
 * Check backend health and update status chip
 */
async function checkHealth() {
    try {
        const res = await fetch('/api/health');
        const json = await res.json();
        const chipText = document.getElementById('interface-ip-text');
        const indicator = document.getElementById('system-indicator');

        if (json.status === 'success' && chipText) {
            chipText.textContent = `Online • ${json.data.platform}`;
            if (indicator) indicator.style.backgroundColor = 'var(--status-healthy)';
        }
    } catch (err) {
        const chipText = document.getElementById('interface-ip-text');
        const indicator = document.getElementById('system-indicator');
        if (chipText) chipText.textContent = 'Backend Offline';
        if (indicator) indicator.style.backgroundColor = 'var(--status-critical)';
    }
}

/**
 * Handle On-Demand Diagnostic Test Execution
 */
async function handleRunDiagnostics() {
    if (State.isTesting) return;

    // Gather selected targets
    const checkedPills = document.querySelectorAll('#target-pills-list input[type="checkbox"]:checked');
    const selectedTargets = Array.from(checkedPills).map(cb => cb.value);

    if (selectedTargets.length === 0) {
        alert('Please select at least one target to test.');
        return;
    }

    const probeCountSelect = document.getElementById('select-probe-count');
    const probeCount = probeCountSelect ? parseInt(probeCountSelect.value, 10) : 5;

    // Set UI to testing state
    setTestingState(true);

    try {
        const res = await fetch('/api/tests', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                targets: selectedTargets,
                probe_count: probeCount,
            }),
        });

        const json = await res.json();

        if (json.status === 'success') {
            const runData = json.data;
            updateDashboardWithRun(runData);
            await refreshHistoryAndStats();
        } else {
            alert(`Diagnostic test error: ${json.message}`);
        }
    } catch (err) {
        console.error('Diagnostic execution error:', err);
        alert('Failed to communicate with diagnostic backend.');
    } finally {
        setTestingState(false);
    }
}

/**
 * Toggle testing button spinner and state
 */
function setTestingState(isTesting) {
    State.isTesting = isTesting;
    const btn = document.getElementById('btn-run-diagnostics');
    const spinner = document.getElementById('btn-spinner');
    const icon = document.getElementById('btn-play-icon');
    const text = document.getElementById('btn-run-text');

    if (btn) btn.disabled = isTesting;
    if (spinner) spinner.style.display = isTesting ? 'inline-block' : 'none';
    if (icon) icon.style.display = isTesting ? 'none' : 'inline-block';
    if (text) text.textContent = isTesting ? 'Testing Network...' : 'Run Diagnostics';
}

/**
 * Update all metric cards, troubleshooting panel, and charts with fresh run data
 */
function updateDashboardWithRun(run) {
    // 1. Overall Status Card
    const statusCard = document.getElementById('kpi-card-status');
    const statusVal = document.getElementById('val-overall-status');
    const lastTestedVal = document.getElementById('val-last-tested');

    if (statusVal) {
        statusVal.textContent = capitalizeFirstLetter(run.overall_status);
    }
    if (statusCard) {
        statusCard.className = `kpi-card status-card status-${run.overall_status}`;
    }
    if (lastTestedVal) {
        const timeStr = new Date(run.timestamp_utc).toLocaleTimeString();
        lastTestedVal.textContent = `Tested at ${timeStr} (${run.duration_seconds}s)`;
    }

    // 2. Compute Metric Card Averages from external hosts
    const samples = run.metric_samples || [];
    const extSamples = samples.filter(s => s.target_type !== 'gateway');
    const gwSample = samples.find(s => s.target_type === 'gateway');

    // Latency
    const validLatencies = extSamples.map(s => s.latency_avg_ms).filter(v => v !== null && v !== undefined);
    const avgLatency = validLatencies.length ? (validLatencies.reduce((a, b) => a + b, 0) / validLatencies.length).toFixed(1) : (gwSample?.latency_avg_ms?.toFixed(1) || '--');
    setText('val-latency', avgLatency);

    // Jitter
    const validJitters = extSamples.map(s => s.jitter_ms).filter(v => v !== null && v !== undefined);
    const avgJitter = validJitters.length ? (validJitters.reduce((a, b) => a + b, 0) / validJitters.length).toFixed(1) : (gwSample?.jitter_ms?.toFixed(1) || '--');
    setText('val-jitter', avgJitter);

    // Packet Loss
    const allLosses = samples.map(s => s.packet_loss_pct).filter(v => v !== null && v !== undefined);
    const maxLoss = allLosses.length ? Math.max(...allLosses).toFixed(1) : '0.0';
    setText('val-loss', maxLoss);

    // DNS Lookup
    const validDns = extSamples.map(s => s.dns_lookup_time_ms).filter(v => v !== null && v !== undefined);
    const avgDns = validDns.length ? (validDns.reduce((a, b) => a + b, 0) / validDns.length).toFixed(1) : '--';
    setText('val-dns', avgDns);

    // TCP Handshake
    const validTcp = extSamples.map(s => s.tcp_handshake_time_ms).filter(v => v !== null && v !== undefined);
    const avgTcp = validTcp.length ? (validTcp.reduce((a, b) => a + b, 0) / validTcp.length).toFixed(1) : '--';
    setText('val-tcp', avgTcp);

    // 3. Troubleshooting Panel
    renderTroubleshootingFindings(run.findings || [], run.summary);

    // 4. Render DNS Comparative Benchmark Chart
    if (run.dns_benchmarks && run.dns_benchmarks.length) {
        renderDnsBenchmarkChart(run.dns_benchmarks);
    }
}

/**
 * Render structured troubleshooting findings
 */
function renderTroubleshootingFindings(findings, summary) {
    const summaryText = document.getElementById('diagnostic-summary-text');
    if (summaryText && summary) {
        summaryText.textContent = summary;
    }

    const countBadge = document.getElementById('findings-count-badge');
    if (countBadge) {
        countBadge.textContent = `${findings.length} ${findings.length === 1 ? 'Finding' : 'Findings'}`;
    }

    const listContainer = document.getElementById('findings-list');
    if (!listContainer) return;

    if (!findings || findings.length === 0) {
        listContainer.innerHTML = `
            <div class="empty-state-panel">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                </svg>
                <p>No active anomalies detected.</p>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = '';

    findings.forEach(f => {
        const card = document.createElement('div');
        card.className = `finding-card severity-${f.severity}`;

        // Causes list
        const causesHtml = (f.possible_causes || []).map(c => `<li>${escapeHtml(c)}</li>`).join('');
        // Recommendations list
        const recsHtml = (f.recommendations || []).map(r => `<li>${escapeHtml(r)}</li>`).join('');

        card.innerHTML = `
            <div class="finding-header">
                <div class="finding-symptom">${escapeHtml(f.symptom)}</div>
                <div class="finding-badges">
                    <span class="badge badge-${f.severity}">${escapeHtml(f.severity)}</span>
                    <span class="badge badge-confidence">${escapeHtml(f.confidence)} Confidence</span>
                </div>
            </div>

            <!-- Evidence Section -->
            <div class="finding-section">
                <span class="finding-section-title">Quantitative Telemetry Evidence:</span>
                <pre class="finding-evidence-pre">${escapeHtml(JSON.stringify(f.evidence, null, 2))}</pre>
            </div>

            <!-- Possible Causes -->
            <div class="finding-section">
                <span class="finding-section-title">Possible Root Causes:</span>
                <ul class="finding-list-items">
                    ${causesHtml}
                </ul>
            </div>

            <!-- Actionable Recommendations -->
            <div class="finding-section">
                <span class="finding-section-title">Recommended Troubleshooting Steps:</span>
                <ul class="finding-list-items">
                    ${recsHtml}
                </ul>
            </div>

            <!-- Diagnostic Limitations -->
            ${f.limitations ? `
                <div class="finding-limitations">
                    <strong>Limitation:</strong> ${escapeHtml(f.limitations)}
                </div>
            ` : ''}
        `;

        listContainer.appendChild(card);
    });
}

/**
 * Refresh historical sessions table and timeline graph
 */
async function refreshHistoryAndStats() {
    try {
        const [historyRes, statsRes] = await Promise.all([
            fetch(`/api/history?hours=${State.activeTimeframeHours}&limit=50`),
            fetch(`/api/stats?hours=${State.activeTimeframeHours}`),
        ]);

        const historyJson = await historyRes.json();
        const statsJson = await statsRes.json();

        if (historyJson.status === 'success') {
            const runs = historyJson.data || [];
            renderHistoryTable(runs);
            renderLatencyTimelineChart(runs);

            // If we have runs and haven't loaded current test yet, show latest in cards
            if (runs.length > 0 && !State.isTesting) {
                const latestRun = runs[0];
                // Fetch full details of the latest run to populate dashboard cards
                const detailRes = await fetch(`/api/tests/${latestRun.id}`);
                const detailJson = await detailRes.json();
                if (detailJson.status === 'success') {
                    updateDashboardWithRun(detailJson.data);
                }
            }
        }
    } catch (err) {
        console.error('Failed to refresh history and stats:', err);
    }
}

/**
 * Render Historical Sessions Table
 */
function renderHistoryTable(runs) {
    const tbody = document.getElementById('history-table-body');
    if (!tbody) return;

    if (runs.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center" style="padding: 2rem; color: var(--text-muted);">
                    No recorded test runs within the selected timeframe. Click "Run Diagnostics" to record a test.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = '';
    runs.forEach(r => {
        const tr = document.createElement('tr');
        const dateStr = new Date(r.timestamp_utc).toLocaleString();

        const samples = r.samples || [];
        const gw = samples.find(s => s.target_type === 'gateway');
        const ext = samples.filter(s => s.target_type !== 'gateway');

        const gwLat = gw && gw.latency_avg_ms !== null ? `${gw.latency_avg_ms.toFixed(1)} ms` : '--';
        const extLats = ext.map(s => s.latency_avg_ms).filter(v => v !== null);
        const extLat = extLats.length ? `${(extLats.reduce((a, b) => a + b, 0) / extLats.length).toFixed(1)} ms` : '--';

        const jitters = samples.map(s => s.jitter_ms).filter(v => v !== null);
        const jitterStr = jitters.length ? `${(jitters.reduce((a, b) => a + b, 0) / jitters.length).toFixed(1)} ms` : '--';

        const losses = samples.map(s => s.packet_loss_pct).filter(v => v !== null);
        const lossStr = losses.length ? `${Math.max(...losses).toFixed(0)}%` : '0%';
        const isChecked = State.selectedRunIds.includes(r.id);

        tr.innerHTML = `
            <td style="text-align: center;">
                <input type="checkbox" class="compare-checkbox" value="${r.id}" ${isChecked ? 'checked' : ''} onchange="handleCompareCheckboxChange(this, ${r.id})">
            </td>
            <td class="font-mono">#${r.id}</td>
            <td>${escapeHtml(dateStr)}</td>
            <td><span class="status-pill ${r.overall_status}">${escapeHtml(r.overall_status)}</span></td>
            <td>${escapeHtml(r.trigger_type)}</td>
            <td class="font-mono">${gwLat}</td>
            <td class="font-mono">${extLat}</td>
            <td class="font-mono">${jitterStr}</td>
            <td class="font-mono">${lossStr}</td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="viewTestRunDetail(${r.id})">
                    View
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

/**
 * Handle Run Selection Checkbox for Head-to-Head Comparison
 */
window.handleCompareCheckboxChange = function(cb, runId) {
    if (cb.checked) {
        if (State.selectedRunIds.length >= 2) {
            alert('You can select a maximum of 2 test sessions for comparison. Uncheck one first.');
            cb.checked = false;
            return;
        }
        State.selectedRunIds.push(runId);
    } else {
        State.selectedRunIds = State.selectedRunIds.filter(id => id !== runId);
    }

    const compareBtn = document.getElementById('btn-compare-runs');
    if (compareBtn) {
        compareBtn.style.display = State.selectedRunIds.length === 2 ? 'inline-flex' : 'none';
    }
};

/**
 * Open Head-to-Head Comparison Modal
 */
window.openComparisonModal = async function() {
    if (State.selectedRunIds.length !== 2) return;
    const [idA, idB] = State.selectedRunIds;

    try {
        const res = await fetch(`/api/compare?run_a=${idA}&run_b=${idB}`);
        const json = await res.json();
        if (json.status !== 'success') {
            alert(`Comparison error: ${json.message}`);
            return;
        }

        const data = json.data;
        const modal = document.getElementById('modal-comparison');
        const title = document.getElementById('modal-compare-title');
        const subtitle = document.getElementById('modal-compare-subtitle');
        const body = document.getElementById('modal-compare-body');

        if (title) title.textContent = `Differential Comparison: Run #${data.run_a.id} vs Run #${data.run_b.id}`;
        if (subtitle) {
            subtitle.textContent = `Baseline: ${new Date(data.run_a.timestamp_utc).toLocaleString()} | Compare: ${new Date(data.run_b.timestamp_utc).toLocaleString()}`;
        }

        if (body) {
            const deltas = data.aggregate_deltas;
            const formatDelta = (val, unit, lowerIsBetter = true) => {
                if (val === null || val === undefined) return '--';
                const sign = val > 0 ? '+' : '';
                const isGood = lowerIsBetter ? val < 0 : val > 0;
                const isNeutral = val === 0;
                const color = isNeutral ? 'var(--text-muted)' : (isGood ? 'var(--status-healthy)' : 'var(--status-critical)');
                return `<span style="color: ${color}; font-weight: 700;">${sign}${val}${unit}</span>`;
            };

            const targetsHtml = data.target_comparisons.map(tc => {
                const d = tc.deltas;
                return `
                    <tr>
                        <td><strong>${escapeHtml(tc.target_name)}</strong></td>
                        <td class="font-mono">${tc.run_a.latency_avg_ms !== null ? tc.run_a.latency_avg_ms + 'ms' : '--'}</td>
                        <td class="font-mono">${tc.run_b.latency_avg_ms !== null ? tc.run_b.latency_avg_ms + 'ms' : '--'}</td>
                        <td class="font-mono">${formatDelta(d.latency_avg_ms, 'ms')}</td>
                        <td class="font-mono">${tc.run_a.packet_loss_pct}%</td>
                        <td class="font-mono">${tc.run_b.packet_loss_pct}%</td>
                        <td class="font-mono">${formatDelta(d.packet_loss_pct, '%')}</td>
                    </tr>
                `;
            }).join('');

            body.innerHTML = `
                <!-- Trend Header Box -->
                <div style="background: rgba(255,255,255,0.03); border-left: 4px solid var(--cyan-primary); padding: 1rem 1.25rem; border-radius: var(--radius-sm); margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <h3 style="font-size: 1.05rem; color: var(--text-bright);">Comparative Performance Summary</h3>
                        <span class="status-pill ${data.trend === 'improved' ? 'healthy' : (data.trend === 'degraded' ? 'critical' : 'warning')}">${escapeHtml(data.trend)}</span>
                    </div>
                    <p style="font-size: 0.88rem; color: var(--text-secondary); line-height: 1.5;">${escapeHtml(data.summary)}</p>
                </div>

                <!-- Aggregate Delta KPI Grid -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
                    <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 1rem;">
                        <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">Avg Latency Delta</div>
                        <div style="font-size: 1.5rem; font-family: var(--font-mono); margin-top: 0.25rem;">
                            ${formatDelta(deltas.avg_latency_delta_ms, 'ms')}
                        </div>
                    </div>
                    <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 1rem;">
                        <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">Packet Loss Delta</div>
                        <div style="font-size: 1.5rem; font-family: var(--font-mono); margin-top: 0.25rem;">
                            ${formatDelta(deltas.avg_loss_delta_pct, '%')}
                        </div>
                    </div>
                    <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 1rem;">
                        <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">Jitter Delta</div>
                        <div style="font-size: 1.5rem; font-family: var(--font-mono); margin-top: 0.25rem;">
                            ${formatDelta(deltas.avg_jitter_delta_ms, 'ms')}
                        </div>
                    </div>
                </div>

                <!-- Target-by-Target Delta Comparison Table -->
                <h4 style="font-size: 0.95rem; margin-bottom: 0.75rem; color: var(--text-bright);">Per-Target Quantitative Variance</h4>
                <div class="table-responsive">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Target Destination</th>
                                <th>Run #${data.run_a.id} Latency</th>
                                <th>Run #${data.run_b.id} Latency</th>
                                <th>&Delta; Latency</th>
                                <th>Run #${data.run_a.id} Loss</th>
                                <th>Run #${data.run_b.id} Loss</th>
                                <th>&Delta; Loss</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${targetsHtml}
                        </tbody>
                    </table>
                </div>

                <div style="margin-top: 1rem; font-size: 0.75rem; color: var(--text-muted); border-top: 1px dashed var(--border-subtle); padding-top: 0.5rem;">
                    * Delta values represent (Run B - Run A). A negative delta in latency, jitter, or loss represents an improvement in the second test session.
                </div>
            `;
        }

        if (modal) modal.style.display = 'flex';
    } catch (err) {
        console.error('Failed to open comparison modal:', err);
    }
};

/**
 * View Detailed Test Run Modal
 */
window.viewTestRunDetail = async function(runId) {
    try {
        State.activeTestRunId = runId;

        const [runRes, destRes] = await Promise.all([
            fetch(`/api/tests/${runId}`),
            fetch(`/api/compare/destinations?run_id=${runId}`).catch(() => null),
        ]);

        const json = await runRes.json();
        if (json.status !== 'success') return;

        let destData = null;
        if (destRes && destRes.ok) {
            const destJson = await destRes.json();
            if (destJson.status === 'success') {
                destData = destJson.data;
            }
        }

        const run = json.data;
        const modal = document.getElementById('modal-test-detail');
        const title = document.getElementById('modal-title');
        const subtitle = document.getElementById('modal-subtitle');
        const body = document.getElementById('modal-body');

        if (title) title.textContent = `Test Run #${run.id} Details`;
        if (subtitle) subtitle.textContent = `Executed on ${new Date(run.timestamp_utc).toLocaleString()} (${run.duration_seconds}s)`;

        if (body) {
            const samplesHtml = (run.metric_samples || []).map(s => `
                <div class="card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                        <strong>${escapeHtml(s.target_name)} (${escapeHtml(s.target_type)})</strong>
                        <span class="status-pill ${s.status}">${escapeHtml(s.status)}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.5rem; font-size: 0.8rem; font-family: var(--font-mono);">
                        <div>Avg Latency: ${s.latency_avg_ms !== null ? s.latency_avg_ms + ' ms' : '--'}</div>
                        <div>Jitter: ${s.jitter_ms !== null ? s.jitter_ms + ' ms' : '--'}</div>
                        <div>Packet Loss: ${s.packet_loss_pct}%</div>
                        <div>Probes: ${s.probes_received}/${s.probes_sent}</div>
                        <div>DNS Time: ${s.dns_lookup_time_ms !== null ? s.dns_lookup_time_ms + ' ms' : '--'}</div>
                        <div>TCP Handshake: ${s.tcp_handshake_time_ms !== null ? s.tcp_handshake_time_ms + ' ms' : '--'}</div>
                    </div>
                    ${s.samples && s.samples.length ? `
                        <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-muted);">
                            Sequential Probes: [${s.samples.map(val => val !== null ? val + 'ms' : 'Dropped').join(', ')}]
                        </div>
                    ` : ''}
                </div>
            `).join('');

            // Build Destination Comparison Table if available
            let destinationComparisonHtml = '';
            if (destData && destData.all_destinations && destData.all_destinations.length) {
                const rows = destData.all_destinations.map(d => {
                    const wanStr = d.wan_penalty_ms !== null ? `+${d.wan_penalty_ms} ms` : (d.target_type === 'gateway' ? '(LAN Baseline)' : '--');
                    const tcpStr = d.tcp_overhead_ms !== null ? (d.tcp_overhead_ms >= 0 ? `+${d.tcp_overhead_ms} ms` : `${d.tcp_overhead_ms} ms`) : '--';
                    return `
                        <tr>
                            <td><strong>${escapeHtml(d.target_name)}</strong></td>
                            <td><span style="font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(d.target_type)}</span></td>
                            <td class="font-mono">${d.latency_avg_ms !== null ? d.latency_avg_ms + ' ms' : '--'}</td>
                            <td class="font-mono" style="color: ${d.target_type === 'gateway' ? 'var(--status-healthy)' : 'var(--cyan-primary)'};">${wanStr}</td>
                            <td class="font-mono">${tcpStr}</td>
                            <td><span class="status-pill ${d.status}">${escapeHtml(d.status)}</span></td>
                        </tr>
                    `;
                }).join('');

                destinationComparisonHtml = `
                    <div style="margin-bottom: 1.5rem;">
                        <h3 style="font-size: 1rem; margin-bottom: 0.75rem; color: var(--cyan-primary);">
                            Destination Comparison & WAN Overhead Analysis
                        </h3>
                        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
                            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-subtle); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.8rem;">
                                <span style="color: var(--text-muted);">Hop-1 Gateway RTT:</span>
                                <strong class="font-mono" style="color: var(--status-healthy); margin-left: 0.25rem;">${destData.gateway_baseline_ms !== null ? destData.gateway_baseline_ms + ' ms' : 'N/A'}</strong>
                            </div>
                            ${destData.fastest_destination ? `
                                <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-subtle); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.8rem;">
                                    <span style="color: var(--text-muted);">Fastest Destination:</span>
                                    <strong style="color: var(--cyan-primary); margin-left: 0.25rem;">${escapeHtml(destData.fastest_destination.target_name)} (${destData.fastest_destination.latency_avg_ms} ms)</strong>
                                </div>
                            ` : ''}
                            ${destData.fastest_dns_resolver ? `
                                <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-subtle); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.8rem;">
                                    <span style="color: var(--text-muted);">Fastest DNS:</span>
                                    <strong style="color: var(--status-healthy); margin-left: 0.25rem;">${escapeHtml(destData.fastest_dns_resolver.target_name)} (${destData.fastest_dns_resolver.dns_lookup_time_ms} ms)</strong>
                                </div>
                            ` : ''}
                        </div>
                        <div class="table-responsive">
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>Destination</th>
                                        <th>Type</th>
                                        <th>L3 Latency</th>
                                        <th>WAN Penalty (&Delta; vs Gateway)</th>
                                        <th>L4 TCP Overhead (&Delta; vs ICMP)</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${rows}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }

            body.innerHTML = `
                <div>
                    <h3 style="font-size: 1rem; margin-bottom: 0.75rem; color: var(--cyan-primary);">Diagnostic Findings (${run.findings.length})</h3>
                    <div style="margin-bottom: 1.5rem;">
                        ${run.findings.length ? run.findings.map(f => `
                            <div style="background: rgba(255,255,255,0.02); border-left: 3px solid var(--cyan-primary); padding: 0.75rem; margin-bottom: 0.5rem; border-radius: 4px;">
                                <strong>${escapeHtml(f.symptom)}</strong>
                                <p style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                    <strong>Recommendation:</strong> ${(f.recommendations || []).join('; ')}
                                </p>
                            </div>
                        `).join('') : '<p style="font-size: 0.85rem; color: var(--text-muted);">No anomalies or degradation detected in this session.</p>'}
                    </div>

                    ${destinationComparisonHtml}

                    <h3 style="font-size: 1rem; margin-bottom: 0.75rem; color: var(--cyan-primary);">Per-Target Telemetry Breakdown</h3>
                    <div>${samplesHtml}</div>
                </div>
            `;
        }

        if (modal) modal.style.display = 'flex';
    } catch (err) {
        console.error('Failed to load run details:', err);
    }
};

/**
 * Render Chart.js Historical Timeline (Latency & Loss)
 */
function renderLatencyTimelineChart(runs) {
    const ctx = document.getElementById('latencyTimelineChart');
    if (!ctx) return;

    // Sort chronologically ascending for timeline
    const sortedRuns = [...runs].reverse();
    const labels = sortedRuns.map(r => new Date(r.timestamp_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

    const gatewayLatencies = sortedRuns.map(r => {
        const gw = (r.samples || []).find(s => s.target_type === 'gateway');
        return gw && gw.latency_avg_ms !== null ? gw.latency_avg_ms : null;
    });

    const externalLatencies = sortedRuns.map(r => {
        const ext = (r.samples || []).filter(s => s.target_type !== 'gateway');
        const lats = ext.map(s => s.latency_avg_ms).filter(v => v !== null);
        return lats.length ? (lats.reduce((a, b) => a + b, 0) / lats.length) : null;
    });

    const packetLosses = sortedRuns.map(r => {
        const losses = (r.samples || []).map(s => s.packet_loss_pct).filter(v => v !== null);
        return losses.length ? Math.max(...losses) : 0;
    });

    if (State.latencyChart) {
        State.latencyChart.destroy();
    }

    State.latencyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.length ? labels : ['No Data'],
            datasets: [
                {
                    label: 'Local Gateway Latency (ms)',
                    data: gatewayLatencies,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: false,
                    pointRadius: 3,
                },
                {
                    label: 'External Targets Latency (ms)',
                    data: externalLatencies,
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: false,
                    pointRadius: 3,
                },
                {
                    label: 'Max Packet Loss (%)',
                    data: packetLosses,
                    borderColor: '#ef4444',
                    borderDash: [5, 5],
                    borderWidth: 1.5,
                    yAxisID: 'y1',
                    pointRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
                },
                y: {
                    title: { display: true, text: 'Latency (ms)', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
                    suggestedMin: 0,
                },
                y1: {
                    position: 'right',
                    title: { display: true, text: 'Loss (%)', color: '#ef4444' },
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#ef4444', font: { family: 'JetBrains Mono', size: 10 } },
                    suggestedMin: 0,
                    suggestedMax: 100,
                }
            }
        }
    });
}

/**
 * Render Comparative DNS Resolver Bar Chart
 */
function renderDnsBenchmarkChart(benchmarks) {
    const ctx = document.getElementById('dnsBenchmarkChart');
    if (!ctx) return;

    const labels = benchmarks.map(b => b.resolver_name);
    const data = benchmarks.map(b => b.avg_ms);

    if (State.dnsChart) {
        State.dnsChart.destroy();
    }

    State.dnsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'DNS Resolution Time (ms)',
                data: data,
                backgroundColor: [
                    'rgba(99, 102, 241, 0.65)',
                    'rgba(56, 189, 248, 0.65)',
                    'rgba(16, 185, 129, 0.65)',
                ],
                borderColor: [
                    '#6366f1',
                    '#38bdf8',
                    '#10b981',
                ],
                borderWidth: 1.5,
                borderRadius: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.parsed.y !== null ? ctx.parsed.y + ' ms' : 'Failed'}`
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
                },
                y: {
                    title: { display: true, text: 'Resolution Time (ms)', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
                    suggestedMin: 0,
                }
            }
        }
    });
}

// Utility Helpers
function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function capitalizeFirstLetter(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}
