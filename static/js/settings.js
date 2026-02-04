/* =============================================================================
   DockDash - Settings Page JavaScript
   ============================================================================= */

// =============================================================================
// Utility Functions
// =============================================================================

function csrfHeaders() {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    return token ? { 'X-CSRFToken': token } : {};
}

function showToast(type, message, duration = 3000) {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// =============================================================================
// Tab Navigation
// =============================================================================

function showSettingsTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.settings-tabs .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.settings-tab-content').forEach(content => {
        content.style.display = 'none';
    });
    document.getElementById(`tab-${tabName}`).style.display = 'block';
    
    // Store preference
    localStorage.setItem('dockdash-settings-tab', tabName);
}

// =============================================================================
// Webhook Functions
// =============================================================================

async function loadWebhooks() {
    try {
        const response = await fetch('/api/webhooks');
        const data = await response.json();
        
        const container = document.getElementById('webhooksList');
        if (data.webhooks && data.webhooks.length > 0) {
            container.innerHTML = data.webhooks.map(w => `
                <div class="webhook-item ${w.enabled ? '' : 'disabled'}">
                    <div class="webhook-info">
                        <div class="webhook-header">
                            <strong>${escapeHtml(w.name)}</strong>
                            <span class="webhook-type-badge">${w.webhook_type}</span>
                        </div>
                        <div class="webhook-alerts">
                            ${w.alert_container_stop ? '<span class="alert-tag">⏹️ Stop</span>' : ''}
                            ${w.alert_container_start ? '<span class="alert-tag">▶️ Start</span>' : ''}
                            ${w.alert_health_unhealthy ? '<span class="alert-tag">❤️ Health</span>' : ''}
                            <span class="alert-tag">📊 CPU ${w.alert_cpu_threshold}%</span>
                            <span class="alert-tag">📊 Mem ${w.alert_memory_threshold}%</span>
                        </div>
                    </div>
                    <div class="webhook-actions">
                        <button class="btn btn-secondary btn-sm" onclick="editWebhook(${w.id})" title="Edit">✏️</button>
                        <button class="btn btn-secondary btn-sm" onclick="testWebhookById(${w.id})" title="Test">🧪</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteWebhook(${w.id})" title="Delete">🗑️</button>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = `
                <div class="empty-state-small">
                    <p>No webhooks configured yet.</p>
                    <p class="text-muted">Add a webhook to receive alerts for container events.</p>
                </div>
            `;
        }
    } catch (error) {
        document.getElementById('webhooksList').innerHTML = '<p class="error">Failed to load webhooks</p>';
    }
}

function showAddWebhook() {
    document.getElementById('webhookModalTitle').textContent = '➕ Add Webhook';
    document.getElementById('webhookId').value = '';
    document.getElementById('webhookName').value = '';
    document.getElementById('webhookType').value = 'discord';
    document.getElementById('webhookUrl').value = '';
    document.getElementById('alertStop').checked = true;
    document.getElementById('alertStart').checked = false;
    document.getElementById('alertHealth').checked = true;
    document.getElementById('alertCpu').value = 90;
    document.getElementById('alertMemory').value = 90;
    document.getElementById('webhookModal').style.display = 'flex';
}

async function editWebhook(id) {
    try {
        const response = await fetch('/api/webhooks');
        const data = await response.json();
        const webhook = data.webhooks?.find(w => w.id === id);
        
        if (!webhook) {
            showToast('error', 'Webhook not found');
            return;
        }
        
        document.getElementById('webhookModalTitle').textContent = '✏️ Edit Webhook';
        document.getElementById('webhookId').value = webhook.id;
        document.getElementById('webhookName').value = webhook.name || '';
        document.getElementById('webhookType').value = webhook.webhook_type || 'discord';
        document.getElementById('webhookUrl').value = webhook.webhook_url || '';
        document.getElementById('alertStop').checked = webhook.alert_container_stop !== false;
        document.getElementById('alertStart').checked = webhook.alert_container_start === true;
        document.getElementById('alertHealth').checked = webhook.alert_health_unhealthy !== false;
        document.getElementById('alertCpu').value = webhook.alert_cpu_threshold || 90;
        document.getElementById('alertMemory').value = webhook.alert_memory_threshold || 90;
        document.getElementById('webhookModal').style.display = 'flex';
    } catch (error) {
        showToast('error', 'Failed to load webhook');
    }
}

function closeWebhookModal(e) {
    if (e && e.target && e.target.id !== 'webhookModal') return;
    document.getElementById('webhookModal').style.display = 'none';
}

async function saveWebhook() {
    const id = document.getElementById('webhookId').value;
    const data = {
        name: document.getElementById('webhookName').value,
        webhook_type: document.getElementById('webhookType').value,
        webhook_url: document.getElementById('webhookUrl').value,
        alert_container_stop: document.getElementById('alertStop').checked,
        alert_container_start: document.getElementById('alertStart').checked,
        alert_health_unhealthy: document.getElementById('alertHealth').checked,
        alert_cpu_threshold: parseInt(document.getElementById('alertCpu').value),
        alert_memory_threshold: parseInt(document.getElementById('alertMemory').value),
        enabled: true
    };
    
    if (!data.name || !data.webhook_url) {
        showToast('error', 'Name and URL are required');
        return;
    }
    
    try {
        const url = id ? `/api/webhook/${id}` : '/api/webhook';
        const method = id ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        
        if (result.success) {
            showToast('success', id ? 'Webhook updated' : 'Webhook created');
            closeWebhookModal();
            loadWebhooks();
        } else {
            showToast('error', result.error);
        }
    } catch (error) {
        showToast('error', 'Failed to save webhook');
    }
}

async function testWebhook() {
    const webhookType = document.getElementById('webhookType').value;
    const webhookUrl = document.getElementById('webhookUrl').value;
    
    if (!webhookUrl) {
        showToast('error', 'URL is required');
        return;
    }
    
    showToast('info', 'Sending test notification...');
    
    try {
        const response = await fetch('/api/webhook/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ webhook_type: webhookType, webhook_url: webhookUrl })
        });
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Test notification sent!');
        } else {
            showToast('error', result.error || 'Test failed');
        }
    } catch (error) {
        showToast('error', 'Failed to send test');
    }
}

async function testWebhookById(id) {
    showToast('info', 'Sending test notification...');
    
    try {
        const response = await fetch(`/api/webhook/${id}/test`, {
            method: 'POST',
            headers: csrfHeaders()
        });
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Test notification sent!');
        } else {
            showToast('error', result.error || 'Test failed');
        }
    } catch (error) {
        showToast('error', 'Failed to send test');
    }
}

async function deleteWebhook(id) {
    if (!confirm('Delete this webhook?\\n\\nYou will no longer receive notifications from it.')) return;
    
    showToast('info', 'Deleting webhook...');
    
    try {
        const response = await fetch(`/api/webhook/${id}`, {
            method: 'DELETE',
            headers: csrfHeaders()
        });
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Webhook deleted');
            loadWebhooks();
        } else {
            showToast('error', result.error);
        }
    } catch (error) {
        showToast('error', 'Failed to delete webhook');
    }
}

// =============================================================================
// Image Update Check Functions
// =============================================================================

async function loadUpdateCheckStatus() {
    try {
        const response = await fetch('/api/updates/settings');
        const data = await response.json();
        
        const indicator = document.getElementById('updateCheckIndicator');
        const statusText = document.getElementById('updateCheckStatusText');
        const lastCheckInfo = document.getElementById('lastUpdateCheckInfo');
        
        if (indicator) indicator.textContent = '✅';
        if (statusText) statusText.textContent = 'Update checks available';
        
        if (data.success && data.settings) {
            loadUpdateSettings(data.settings);
            if (data.settings.last_check_completed) {
                const lastCheck = new Date(data.settings.last_check_completed);
                const imagesCount = data.settings.last_check_images_count || 0;
                const updatesFound = data.settings.images_with_updates || 0;
                if (lastCheckInfo) {
                    lastCheckInfo.textContent = `Last check: ${lastCheck.toLocaleString()} (${imagesCount} images, ${updatesFound} updates)`;
                }
            } else if (lastCheckInfo) {
                lastCheckInfo.textContent = 'No checks completed yet';
            }
        }
    } catch (error) {
        const statusText = document.getElementById('updateCheckStatusText');
        if (statusText) statusText.textContent = '❌ Failed to load update check status';
    }
}

function loadUpdateSettings(settings) {
    const updateEnabled = document.getElementById('updateCheckEnabled');
    const scheduleType = document.getElementById('updateScheduleType');
    const scheduleHour = document.getElementById('updateScheduleHour');
    const scheduleMinute = document.getElementById('updateScheduleMinute');
    const scheduleDay = document.getElementById('updateScheduleDay');
    
    if (updateEnabled) updateEnabled.checked = settings.enabled || false;
    if (scheduleType) scheduleType.value = settings.schedule_type || 'daily';
    if (scheduleHour) scheduleHour.value = settings.schedule_hour ?? 4;
    if (scheduleMinute) scheduleMinute.value = settings.schedule_minute ?? 0;
    if (scheduleDay) scheduleDay.value = settings.schedule_day ?? 0;
    
    updateUpdateScheduleUI();
}

function updateUpdateScheduleUI() {
    const scheduleType = document.getElementById('updateScheduleType');
    const dayGroup = document.getElementById('updateDayGroup');
    if (scheduleType && dayGroup) {
        dayGroup.style.display = scheduleType.value === 'weekly' ? 'block' : 'none';
    }
}

function updateUpdateSchedule() {
    // Just update UI when checkbox is toggled
    updateUpdateScheduleUI();
}

async function saveUpdateSettings() {
    const data = {
        enabled: document.getElementById('updateCheckEnabled')?.checked || false,
        schedule_type: document.getElementById('updateScheduleType')?.value || 'daily',
        schedule_hour: parseInt(document.getElementById('updateScheduleHour')?.value || 4),
        schedule_minute: parseInt(document.getElementById('updateScheduleMinute')?.value || 0),
        schedule_day: parseInt(document.getElementById('updateScheduleDay')?.value || 0)
    };
    
    try {
        const response = await fetch('/api/updates/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...csrfHeaders()
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('success', 'Update check settings saved');
        } else {
            showToast('error', result.error || 'Failed to save settings');
        }
    } catch (error) {
        showToast('error', 'Failed to save settings');
    }
}

async function runUpdateCheck() {
    const btn = document.getElementById('runUpdateCheckBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Checking...';
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/updates/check-all', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...csrfHeaders()
            },
            body: JSON.stringify({})
        });
        
        const result = await response.json();
        if (result.success) {
            const msg = `Checked ${result.images_checked} images. ${result.updates_found} update(s) available.`;
            showToast('success', msg);
            loadUpdateCheckStatus();
        } else {
            showToast('error', result.error || 'Failed to check updates');
        }
    } catch (error) {
        showToast('error', 'Failed to check updates');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// =============================================================================
// Vulnerability Scanning Functions
// =============================================================================

async function loadScannerStatus() {
    try {
        const response = await fetch('/api/vulnerabilities/status');
        const data = await response.json();
        
        const indicator = document.getElementById('scannerIndicator');
        const statusText = document.getElementById('scannerStatusText');
        const lastScanInfo = document.getElementById('lastScanInfo');
        const scanBtn = document.getElementById('fullScanBtn');
        
        if (data.available) {
            indicator.textContent = '✅';
            statusText.textContent = 'Trivy scanner is available';
            if (scanBtn) scanBtn.disabled = false;
        } else {
            indicator.textContent = '❌';
            statusText.innerHTML = 'Trivy not installed. <a href="https://trivy.dev" target="_blank">Install Trivy</a>';
            if (scanBtn) scanBtn.disabled = true;
        }
        
        // Load scan settings and show last scan info
        if (data.settings) {
            loadScanSettings(data.settings);
            if (data.settings.last_scan_completed) {
                const lastScan = new Date(data.settings.last_scan_completed);
                const imagesCount = data.settings.last_scan_images_count || 0;
                lastScanInfo.textContent = `Last scan: ${lastScan.toLocaleString()} (${imagesCount} images)`;
            } else {
                lastScanInfo.textContent = 'No scans completed yet';
            }
        } else {
            lastScanInfo.textContent = '';
        }
    } catch (error) {
        const statusText = document.getElementById('scannerStatusText');
        if (statusText) {
            statusText.textContent = '❌ Failed to check scanner status';
        }
    }
}

function loadScanSettings(settings) {
    const scanEnabled = document.getElementById('scanEnabled');
    const scheduleType = document.getElementById('scheduleType');
    const scheduleHour = document.getElementById('scheduleHour');
    const scheduleMinute = document.getElementById('scheduleMinute');
    const scheduleDay = document.getElementById('scheduleDay');
    const severityFilter = document.getElementById('severityFilter');
    const logLevel = document.getElementById('logLevel');
    
    if (scanEnabled) scanEnabled.checked = settings.enabled || false;
    if (scheduleType) scheduleType.value = settings.schedule_type || 'daily';
    if (scheduleHour) scheduleHour.value = settings.schedule_hour ?? 3;
    if (scheduleMinute) scheduleMinute.value = settings.schedule_minute ?? 0;
    if (scheduleDay) scheduleDay.value = settings.schedule_day ?? 0;
    if (severityFilter) severityFilter.value = settings.severity_filter || 'CRITICAL,HIGH,MEDIUM,LOW';
    if (logLevel) logLevel.value = settings.log_level || 'INFO';
    
    updateScheduleUI();
}

function updateScheduleUI() {
    const scheduleType = document.getElementById('scheduleType');
    const dayGroup = document.getElementById('dayGroup');
    if (scheduleType && dayGroup) {
        dayGroup.style.display = scheduleType.value === 'weekly' ? 'block' : 'none';
    }
}

async function saveScanSettings() {
    const data = {
        enabled: document.getElementById('scanEnabled')?.checked || false,
        schedule_type: document.getElementById('scheduleType')?.value || 'daily',
        schedule_hour: parseInt(document.getElementById('scheduleHour')?.value || 3),
        schedule_minute: parseInt(document.getElementById('scheduleMinute')?.value || 0),
        schedule_day: parseInt(document.getElementById('scheduleDay')?.value || 0),
        severity_filter: document.getElementById('severityFilter')?.value || 'CRITICAL,HIGH,MEDIUM,LOW',
        log_level: document.getElementById('logLevel')?.value || 'INFO'
    };
    
    try {
        const response = await fetch('/api/vulnerabilities/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Scan settings saved');
        } else {
            showToast('error', result.error || 'Failed to save settings');
        }
    } catch (error) {
        showToast('error', 'Failed to save settings');
    }
}


// =============================================================================
// Application Logging Settings
// =============================================================================

async function loadAppLogSettings() {
    const sel = document.getElementById('appLogLevel');
    if (!sel) return;

    try {
        const response = await fetch('/api/logging/settings');
        const data = await response.json();
        if (data.success && data.settings && data.settings.log_level) {
            sel.value = data.settings.log_level;
        }
    } catch (error) {
        // Non-fatal; keep default UI state.
    }
}

async function saveAppLogSettings() {
    const level = document.getElementById('appLogLevel')?.value || 'INFO';

    try {
        const response = await fetch('/api/logging/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ log_level: level })
        });
        const result = await response.json();

        if (result.success) {
            showToast('success', `App log level set to ${result.settings?.log_level || level}`);
        } else {
            showToast('error', result.error || 'Failed to save app log level');
        }
    } catch (error) {
        showToast('error', 'Failed to save app log level');
    }
}

async function runFullScan() {
    const btn = document.getElementById('fullScanBtn');
    const progressDiv = document.getElementById('scanProgress');
    const progressFill = document.getElementById('scanProgressFill');
    const progressText = document.getElementById('scanProgressText');
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Starting...';
    }
    if (progressDiv) progressDiv.style.display = 'block';
    if (progressFill) progressFill.style.width = '0%';
    if (progressText) progressText.textContent = 'Starting scan...';
    
    try {
        const response = await fetch('/api/vulnerabilities/scan-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({})
        });
        const data = await response.json();
        
        if (data.success) {
            const summary = data.total_summary || {};
            if (progressText) {
                progressText.textContent = 
                    `Complete! ${data.images_scanned || 0} images scanned. ` +
                    `${summary.critical || 0}C / ${summary.high || 0}H / ${summary.medium || 0}M / ${summary.low || 0}L`;
            }
            if (progressFill) progressFill.style.width = '100%';
            
            showToast('success', `Scan complete! Found ${summary.critical || 0} Critical, ${summary.high || 0} High vulnerabilities.`);
            
            // Refresh status after a delay
            setTimeout(() => loadScannerStatus(), 1000);
        } else {
            showToast('error', data.error || 'Scan failed');
            if (progressDiv) progressDiv.style.display = 'none';
        }
    } catch (error) {
        console.error('Scan error:', error);
        showToast('error', 'Failed to start scan: ' + (error.message || 'Network error'));
        if (progressDiv) progressDiv.style.display = 'none';
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '▶️ Scan Now';
        }
    }
}

// =============================================================================
// Monitoring Functions
// =============================================================================

async function loadMonitoringStatus() {
    try {
        const response = await fetch('/api/monitoring/status');
        const data = await response.json();
        
        const isRunning = data.running;
        const indicator = document.getElementById('monitoringIndicator');
        const statusText = document.getElementById('monitoringStatusText');
        const startBtn = document.getElementById('startMonitoringBtn');
        const stopBtn = document.getElementById('stopMonitoringBtn');
        const cpuThreshold = document.getElementById('cpuThreshold');
        const memoryThreshold = document.getElementById('memoryThreshold');
        
        if (indicator) indicator.textContent = isRunning ? '✅' : '⏸️';
        if (statusText) statusText.textContent = isRunning ? 'Monitoring active' : 'Monitoring stopped';
        if (startBtn) startBtn.style.display = isRunning ? 'none' : 'inline-block';
        if (stopBtn) stopBtn.style.display = isRunning ? 'inline-block' : 'none';
        if (cpuThreshold) cpuThreshold.value = data.cpu_threshold || 80;
        if (memoryThreshold) memoryThreshold.value = data.memory_threshold || 85;
    } catch (error) {
        const statusText = document.getElementById('monitoringStatusText');
        if (statusText) statusText.textContent = 'Failed to load status';
    }
}

async function startMonitoring() {
    try {
        const response = await fetch('/api/monitoring/start', {
            method: 'POST',
            headers: csrfHeaders()
        });
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Monitoring started');
            loadMonitoringStatus();
        } else {
            showToast('error', data.error || 'Failed to start monitoring');
        }
    } catch (error) {
        showToast('error', 'Failed to start monitoring');
    }
}

async function stopMonitoring() {
    try {
        const response = await fetch('/api/monitoring/stop', {
            method: 'POST',
            headers: csrfHeaders()
        });
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Monitoring stopped');
            loadMonitoringStatus();
        } else {
            showToast('error', data.error || 'Failed to stop monitoring');
        }
    } catch (error) {
        showToast('error', 'Failed to stop monitoring');
    }
}

async function updateThresholds() {
    const cpuThreshold = document.getElementById('cpuThreshold');
    const memoryThreshold = document.getElementById('memoryThreshold');
    
    const cpu = parseInt(cpuThreshold?.value || 80);
    const memory = parseInt(memoryThreshold?.value || 85);
    
    try {
        const response = await fetch('/api/monitoring/thresholds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ cpu_threshold: cpu, memory_threshold: memory })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Thresholds updated');
        } else {
            showToast('error', data.error || 'Failed to update thresholds');
        }
    } catch (error) {
        showToast('error', 'Failed to update thresholds');
    }
}

// =============================================================================
// Cleanup Functions
// =============================================================================

async function pruneContainers() {
    if (!confirm('Remove all stopped containers?\n\nThis will delete containers that are not currently running.')) return;
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span> Pruning...';
    btn.disabled = true;
    await doPrune('/api/containers/prune', 'containers', btn, originalText);
}

async function pruneImages() {
    if (!confirm('Remove unused images?\n\nThis will delete images not used by any container.')) return;
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span> Pruning...';
    btn.disabled = true;
    await doPrune('/api/images/prune', 'images', btn, originalText);
}

async function pruneVolumes() {
    if (!confirm('⚠️ Remove unused volumes?\n\nWARNING: This may cause permanent data loss!\nVolumes not attached to any container will be deleted.')) return;
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span> Pruning...';
    btn.disabled = true;
    await doPrune('/api/volumes/prune', 'volumes', btn, originalText);
}

async function pruneAll() {
    if (!confirm('⚠️ FULL SYSTEM CLEANUP\n\nThis will remove:\n• All stopped containers\n• All unused images\n• All unused volumes (data loss!)\n\nThis cannot be undone. Continue?')) return;
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span> Pruning...';
    btn.disabled = true;
    await doPrune('/api/system/prune', 'resources', btn, originalText);
}

async function doPrune(url, type, btn, originalText) {
    showToast('info', `Pruning ${type}...`);
    
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: csrfHeaders()
        });
        const result = await response.json();
        
        if (result.success) {
            const space = result.space_reclaimed_human || result.total_space_reclaimed_human || '0 B';
            showToast('success', `Cleaned ${type}. Reclaimed: ${space}`, 5000);
        } else {
            showToast('error', result.error || `Failed to prune ${type}`);
        }
    } catch (error) {
        showToast('error', `Failed to prune ${type}`);
    } finally {
        if (btn && originalText) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
}

// =============================================================================
// Images Modal Functions
// =============================================================================

async function showImagesModal() {
    document.getElementById('imagesModal').style.display = 'flex';
    document.getElementById('imagesContent').innerHTML = '<div class="loading">Loading images...</div>';
    
    try {
        const response = await fetch('/api/images');
        const data = await response.json();
        
        if (data.success && data.images) {
            const html = `
                <table class="inspect-table">
                    <thead>
                        <tr><th>Tags</th><th>Size</th><th>Created</th><th>Actions</th></tr>
                    </thead>
                    <tbody>
                        ${data.images.map(img => `
                            <tr>
                                <td>${img.tags.length ? img.tags.map(t => escapeHtml(t)).join('<br>') : '<em>untagged</em>'}</td>
                                <td>${img.size_human}</td>
                                <td>${img.created}</td>
                                <td>
                                    <button class="btn btn-danger btn-xs" onclick="deleteImage('${img.id}')">🗑️</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
            document.getElementById('imagesContent').innerHTML = html;
        } else {
            document.getElementById('imagesContent').innerHTML = '<p>No images found</p>';
        }
    } catch (error) {
        document.getElementById('imagesContent').innerHTML = '<p class="error">Failed to load images</p>';
    }
}

function closeImagesModal(e) {
    if (e && e.target && e.target.id !== 'imagesModal') return;
    document.getElementById('imagesModal').style.display = 'none';
}

async function deleteImage(imageId) {
    if (!confirm('Delete this image?')) return;
    
    try {
        const response = await fetch(`/api/image/${imageId}/delete`, {
            method: 'POST',
            headers: csrfHeaders()
        });
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Image deleted');
            showImagesModal();
        } else {
            showToast('error', result.error || 'Failed to delete image');
        }
    } catch (error) {
        showToast('error', 'Failed to delete image');
    }
}

// =============================================================================
// Initialize on Page Load
// =============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Restore last active tab
    const savedTab = localStorage.getItem('dockdash-settings-tab');
    if (savedTab) {
        const tabBtn = document.querySelector(`.settings-tabs .tab-btn[onclick*="${savedTab}"]`);
        if (tabBtn) tabBtn.click();
    }
    
    // Load all data
    loadWebhooks();
    loadMonitoringStatus();
    loadScannerStatus();
    loadUpdateCheckStatus();
    loadAppLogSettings();
});
