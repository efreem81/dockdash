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

function showToast(type, message) {
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
    }, 3000);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
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
                <div class="webhook-item">
                    <div class="webhook-info">
                        <strong>${escapeHtml(w.name)}</strong>
                        <span class="webhook-type">${w.webhook_type}</span>
                        <span class="webhook-status ${w.enabled ? 'enabled' : 'disabled'}">${w.enabled ? '✅' : '❌'}</span>
                    </div>
                    <div class="webhook-actions">
                        <button class="btn btn-secondary btn-xs" onclick="editWebhook(${w.id})">✏️</button>
                        <button class="btn btn-danger btn-xs" onclick="deleteWebhook(${w.id})">🗑️</button>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p class="empty-text">No webhooks configured</p>';
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

async function deleteWebhook(id) {
    if (!confirm('Delete this webhook?')) return;
    
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
// Cleanup Functions
// =============================================================================

async function pruneContainers() {
    if (!confirm('Remove all stopped containers?')) return;
    await doPrune('/api/containers/prune', 'containers');
}

async function pruneImages() {
    if (!confirm('Remove unused images?')) return;
    await doPrune('/api/images/prune', 'images');
}

async function pruneVolumes() {
    if (!confirm('Remove unused volumes? This may cause data loss!')) return;
    await doPrune('/api/volumes/prune', 'volumes');
}

async function pruneAll() {
    if (!confirm('Remove ALL unused containers, images, and volumes? This cannot be undone!')) return;
    await doPrune('/api/system/prune', 'resources');
}

async function doPrune(url, type) {
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: csrfHeaders()
        });
        const result = await response.json();
        
        if (result.success) {
            const space = result.space_reclaimed_human || result.total_space_reclaimed_human || '0 B';
            showToast('success', `Cleaned ${type}. Reclaimed: ${space}`);
        } else {
            showToast('error', result.error);
        }
    } catch (error) {
        showToast('error', `Failed to prune ${type}`);
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
            showToast('error', result.error);
        }
    } catch (error) {
        showToast('error', 'Failed to delete image');
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
        document.getElementById('monitoringIndicator').textContent = isRunning ? '✅' : '⏸️';
        document.getElementById('monitoringText').textContent = isRunning ? 'Monitoring active' : 'Monitoring stopped';
        document.getElementById('startMonitoringBtn').style.display = isRunning ? 'none' : 'inline-block';
        document.getElementById('stopMonitoringBtn').style.display = isRunning ? 'inline-block' : 'none';
        document.getElementById('cpuThreshold').value = data.cpu_threshold || 80;
        document.getElementById('memoryThreshold').value = data.memory_threshold || 85;
    } catch (error) {
        document.getElementById('monitoringText').textContent = 'Failed to load status';
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
            showToast('error', data.error);
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
            showToast('error', data.error);
        }
    } catch (error) {
        showToast('error', 'Failed to stop monitoring');
    }
}

async function updateThresholds() {
    const cpu = parseInt(document.getElementById('cpuThreshold').value);
    const memory = parseInt(document.getElementById('memoryThreshold').value);
    
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
            showToast('error', data.error);
        }
    } catch (error) {
        showToast('error', 'Failed to update thresholds');
    }
}

// =============================================================================
// Vulnerability Scanning Functions
// =============================================================================

async function loadScannerStatus() {
    try {
        const response = await fetch('/api/vulnerabilities/status');
        const data = await response.json();
        
        const statusEl = document.getElementById('scannerText');
        if (data.available) {
            statusEl.innerHTML = '✅ Trivy scanner is available';
            document.getElementById('scanBtn').disabled = false;
        } else {
            statusEl.innerHTML = '⚠️ Trivy not installed. <a href="https://trivy.dev" target="_blank">Install Trivy</a>';
            document.getElementById('scanBtn').disabled = true;
        }
    } catch (error) {
        document.getElementById('scannerText').textContent = '❌ Failed to check scanner status';
    }
}

async function scanImage() {
    const image = document.getElementById('scanImage').value.trim();
    if (!image) {
        showToast('error', 'Please enter an image name');
        return;
    }
    
    const severity = document.getElementById('scanSeverity').value;
    const btn = document.getElementById('scanBtn');
    const resultsDiv = document.getElementById('scanResults');
    const contentDiv = document.getElementById('scanResultsContent');
    
    btn.disabled = true;
    btn.textContent = '⏳ Scanning...';
    resultsDiv.style.display = 'block';
    contentDiv.innerHTML = '<div class="loading">Scanning image for vulnerabilities...</div>';
    
    try {
        const response = await fetch(`/api/vulnerabilities/scan?image=${encodeURIComponent(image)}&severity=${severity}`);
        const data = await response.json();
        
        if (data.success) {
            const summary = data.summary;
            let html = `
                <div class="scan-summary">
                    <span class="severity-badge critical">${summary.critical} Critical</span>
                    <span class="severity-badge high">${summary.high} High</span>
                    <span class="severity-badge medium">${summary.medium} Medium</span>
                    <span class="severity-badge low">${summary.low} Low</span>
                </div>
            `;
            
            if (data.vulnerabilities && data.vulnerabilities.length > 0) {
                html += `
                    <table class="inspect-table vuln-table">
                        <thead>
                            <tr><th>ID</th><th>Severity</th><th>Package</th><th>Fixed In</th></tr>
                        </thead>
                        <tbody>
                            ${data.vulnerabilities.slice(0, 50).map(v => `
                                <tr class="severity-row-${v.severity.toLowerCase()}">
                                    <td><a href="https://nvd.nist.gov/vuln/detail/${v.id}" target="_blank">${escapeHtml(v.id)}</a></td>
                                    <td><span class="severity-badge ${v.severity.toLowerCase()}">${v.severity}</span></td>
                                    <td>${escapeHtml(v.package)}@${escapeHtml(v.version)}</td>
                                    <td>${v.fixed_version || 'N/A'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
                if (data.vulnerabilities.length > 50) {
                    html += `<p class="text-muted">Showing first 50 of ${data.vulnerabilities.length} vulnerabilities</p>`;
                }
            } else {
                html += '<p class="success-text">✅ No vulnerabilities found!</p>';
            }
            
            contentDiv.innerHTML = html;
        } else {
            contentDiv.innerHTML = `<p class="error">${escapeHtml(data.error)}</p>`;
        }
    } catch (error) {
        contentDiv.innerHTML = '<p class="error">Failed to scan image</p>';
    } finally {
        btn.disabled = false;
        btn.textContent = '🔍 Scan Image';
    }
}

// =============================================================================
// Initialize on Page Load
// =============================================================================

document.addEventListener('DOMContentLoaded', function() {
    loadWebhooks();
    loadMonitoringStatus();
    loadScannerStatus();
});
