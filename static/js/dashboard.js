/* =============================================================================
   DockDash - Dashboard Page JavaScript
   ============================================================================= */

// Scope every dashboard API request to the selected Docker endpoint.
const _dockdashNativeFetch = window.fetch.bind(window);
window.fetch = function(input, init) {
    const endpointId = document.querySelector('.dashboard')?.dataset.endpointId;
    if (endpointId && endpointId !== 'all' && typeof input === 'string' && input.startsWith('/api/') && !input.includes('endpoint_id=')) {
        input += `${input.includes('?') ? '&' : '?'}endpoint_id=${encodeURIComponent(endpointId)}`;
    }
    return _dockdashNativeFetch(input, init);
};

// =============================================================================
// State Management
// =============================================================================

let currentView = 'card';
let currentPage = 1;
let pageSize = 25;
let sortField = 'name';
let sortDirection = 'asc';
let searchTerm = '';
let allContainers = [];
let filteredContainers = [];

// =============================================================================
// Utility Functions
// =============================================================================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func.apply(this, args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function getCsrfToken() {
    const el = document.querySelector('meta[name="csrf-token"]');
    return el ? el.getAttribute('content') : null;
}

function csrfHeaders() {
    const token = getCsrfToken();
    return token ? { 'X-CSRFToken': token } : {};
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function setButtonLoading(btn, loading, originalText = null) {
    if (!btn) return;
    if (loading) {
        btn._originalText = btn.innerHTML;
        btn.classList.add('loading');
        btn.disabled = true;
    } else {
        btn.classList.remove('loading');
        btn.disabled = false;
        if (originalText !== null) {
            btn.innerHTML = originalText;
        } else if (btn._originalText) {
            btn.innerHTML = btn._originalText;
        }
    }
}

function confirmAction(message, dangerLevel = 'normal') {
    // For dangerous actions, require typing confirmation in future
    // For now, use confirm() with clear messaging
    return confirm(message);
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

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Gather all containers from DOM
    const cards = document.querySelectorAll('.container-card[data-name]');
    cards.forEach(card => {
        allContainers.push({
            element: card,
            name: card.dataset.name,
            status: card.dataset.status,
            image: card.dataset.image,
            created: card.dataset.created,
            id: card.dataset.id,
            endpointName: (card.dataset.endpointName || '').toLowerCase(),
            key: card.dataset.key || card.dataset.id
        });
    });

    // Restore saved preferences
    const savedView = localStorage.getItem('dockdash-view');
    const savedPageSize = localStorage.getItem('dockdash-pageSize');
    const savedSort = localStorage.getItem('dockdash-sort');

    if (savedView === 'table') {
        setView('table');
    }
    if (savedPageSize) {
        pageSize = savedPageSize === 'all' ? 'all' : parseInt(savedPageSize);
        document.getElementById('pageSizeSelect').value = savedPageSize;
    }
    if (savedSort) {
        const [field, dir] = savedSort.split('-');
        sortField = field;
        sortDirection = dir;
        document.getElementById('sortSelect').value = savedSort;
    }

    // Restore saved filter state from sessionStorage
    restoreFilterState();

    // Initial render
    filteredContainers = [...allContainers];
    applySort();
    renderContainers();

    // Probe visible links to upgrade http -> https where appropriate
    scheduleProbeVisibleLinks();

    // Setup search input
    const searchInput = document.getElementById('searchInput');
    const searchShortcut = document.querySelector('.search-shortcut');

    searchInput.addEventListener('input', debounce(function() {
        searchTerm = this.value.toLowerCase().trim();
        document.getElementById('searchClear').style.display = searchTerm ? 'block' : 'none';
        if (searchShortcut) searchShortcut.style.display = searchTerm ? 'none' : '';
        currentPage = 1;
        filterContainers();
        renderContainers();
    }, 200));

    // Hide shortcut when focused
    searchInput.addEventListener('focus', function() {
        if (searchShortcut) searchShortcut.style.display = 'none';
    });
    searchInput.addEventListener('blur', function() {
        if (searchShortcut && !this.value) searchShortcut.style.display = '';
    });

    // Keyboard shortcut for search
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            searchInput.focus();
        }
        if (e.key === 'Escape' && document.activeElement === searchInput) {
            clearSearch();
            searchInput.blur();
        }
    });

    // Stopped containers filter (loads stopped containers when enabled)
    const stoppedFilter = document.getElementById('filterStopped');
    const dashboardEl = document.querySelector('.dashboard');
    if (stoppedFilter) {
        stoppedFilter.addEventListener('change', function() {
            const pageShowAll = dashboardEl?.dataset.showAll === 'true';
            if (this.checked && !pageShowAll) {
                const url = new URL(window.location.href);
                url.searchParams.set('show_all', 'true');
                window.location.href = url.toString();
                return;
            }
            if (!this.checked && pageShowAll) {
                const url = new URL(window.location.href);
                url.searchParams.set('show_all', 'false');
                window.location.href = url.toString();
                return;
            }
            applyFilters();
        });

        if (stoppedFilter.checked) {
            applyFilters();
        }
    }

    // Logs follow checkbox
    document.addEventListener('change', function(e) {
        if (e.target && e.target.id === 'logsFollow') {
            startLogsFollow();
        }
    });
});

// =============================================================================
// View Toggle
// =============================================================================

function setView(view) {
    currentView = view;
    const cardView = document.getElementById('containerGrid');
    const tableView = document.getElementById('containerTable');
    const cardBtn = document.getElementById('cardViewBtn');
    const tableBtn = document.getElementById('tableViewBtn');

    if (view === 'table') {
        cardView.style.display = 'none';
        tableView.style.display = 'block';
        cardBtn.classList.remove('active');
        tableBtn.classList.add('active');
    } else {
        cardView.style.display = 'grid';
        tableView.style.display = 'none';
        cardBtn.classList.add('active');
        tableBtn.classList.remove('active');
    }
    localStorage.setItem('dockdash-view', view);
    renderContainers();
    scheduleProbeVisibleLinks();
}

// =============================================================================
// Search Functionality
// =============================================================================

function clearSearch() {
    document.getElementById('searchInput').value = '';
    document.getElementById('searchClear').style.display = 'none';
    searchTerm = '';
    currentPage = 1;
    filterContainers();
    renderContainers();
}

function filterContainers() {
    if (!searchTerm) {
        filteredContainers = [...allContainers];
    } else {
        filteredContainers = allContainers.filter(c =>
            c.name.includes(searchTerm) ||
            c.image.includes(searchTerm) ||
            c.status.includes(searchTerm) ||
            c.id.includes(searchTerm) ||
            c.endpointName.includes(searchTerm)
        );
    }
    applySort();
}

// =============================================================================
// Sort Functionality
// =============================================================================

function sortContainers() {
    const value = document.getElementById('sortSelect').value;
    const [field, dir] = value.split('-');
    sortField = field;
    sortDirection = dir;
    localStorage.setItem('dockdash-sort', value);
    applySort();
    renderContainers();
}

function sortByColumn(field) {
    if (sortField === field) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortField = field;
        sortDirection = 'asc';
    }

    // Update dropdown
    const sortValue = `${field}-${sortDirection}`;
    const select = document.getElementById('sortSelect');
    const option = select.querySelector(`option[value="${sortValue}"]`);
    if (option) {
        select.value = sortValue;
    }

    localStorage.setItem('dockdash-sort', sortValue);
    applySort();
    renderContainers();
    updateSortIcons();
}

function applySort() {
    filteredContainers.sort((a, b) => {
        let valA, valB;

        if (sortField === 'status') {
            // Custom sort: running first or last
            const statusOrder = { 'running': 0, 'paused': 1, 'exited': 2, 'stopped': 2 };
            valA = statusOrder[a.status] ?? 3;
            valB = statusOrder[b.status] ?? 3;
        } else if (sortField === 'created') {
            valA = a.created;
            valB = b.created;
        } else {
            valA = a[sortField] || '';
            valB = b[sortField] || '';
        }

        if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
        if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
        return 0;
    });
}

function updateSortIcons() {
    document.querySelectorAll('.sort-icon').forEach(icon => {
        icon.textContent = '↕';
        icon.classList.remove('active');
    });

    const activeIcon = document.getElementById(`sort-${sortField}`);
    if (activeIcon) {
        activeIcon.textContent = sortDirection === 'asc' ? '↑' : '↓';
        activeIcon.classList.add('active');
    }
}

// =============================================================================
// Pagination
// =============================================================================

function changePageSize() {
    const value = document.getElementById('pageSizeSelect').value;
    pageSize = value === 'all' ? 'all' : parseInt(value);
    localStorage.setItem('dockdash-pageSize', value);
    currentPage = 1;
    renderContainers();
}

function changePage(delta) {
    const totalPages = getTotalPages();
    currentPage = Math.max(1, Math.min(totalPages, currentPage + delta));
    renderContainers();
}

function getTotalPages() {
    if (pageSize === 'all') return 1;
    return Math.ceil(filteredContainers.length / pageSize);
}

function getPagedContainers() {
    if (pageSize === 'all') return filteredContainers;
    const start = (currentPage - 1) * pageSize;
    return filteredContainers.slice(start, start + pageSize);
}

// =============================================================================
// Render Containers
// =============================================================================

function renderContainers() {
    const pagedContainers = getPagedContainers();
    const totalPages = getTotalPages();
    const total = filteredContainers.length;

    // Update pagination info
    const start = total === 0 ? 0 : (currentPage - 1) * (pageSize === 'all' ? total : pageSize) + 1;
    const end = pageSize === 'all' ? total : Math.min(currentPage * pageSize, total);

    document.getElementById('showingStart').textContent = start;
    document.getElementById('showingEnd').textContent = end;
    document.getElementById('totalFiltered').textContent = total;
    document.getElementById('currentPage').textContent = currentPage;
    document.getElementById('totalPages').textContent = totalPages;

    const currentPageBottom = document.getElementById('currentPageBottom');
    const totalPagesBottom = document.getElementById('totalPagesBottom');
    if (currentPageBottom) currentPageBottom.textContent = currentPage;
    if (totalPagesBottom) totalPagesBottom.textContent = totalPages;

    // Update button states
    const prevDisabled = currentPage <= 1;
    const nextDisabled = currentPage >= totalPages;
    document.getElementById('prevPage').disabled = prevDisabled;
    document.getElementById('nextPage').disabled = nextDisabled;

    const prevPageBottom = document.getElementById('prevPageBottom');
    const nextPageBottom = document.getElementById('nextPageBottom');
    if (prevPageBottom) prevPageBottom.disabled = prevDisabled;
    if (nextPageBottom) nextPageBottom.disabled = nextDisabled;

    // Show/hide pagination if not needed
    const paginationNeeded = totalPages > 1;
    document.getElementById('paginationControls').style.visibility = paginationNeeded ? 'visible' : 'hidden';

    const bottomPagination = document.getElementById('bottomPagination');
    if (bottomPagination) bottomPagination.style.display = paginationNeeded ? 'flex' : 'none';

    // Get set of visible container IDs
    const visibleKeys = new Set(pagedContainers.map(c => c.key));

    // Render card view
    const cardGrid = document.getElementById('containerGrid');
    const cards = cardGrid.querySelectorAll('.container-card[data-id]');
    cards.forEach(card => {
        card.style.display = visibleKeys.has(card.dataset.key || card.dataset.id) ? '' : 'none';
    });

    // Render table view
    const tableBody = document.getElementById('tableBody');
    if (tableBody) {
        const rows = tableBody.querySelectorAll('tr[data-id]');
        rows.forEach(row => {
            row.style.display = visibleKeys.has(row.dataset.key || row.dataset.id) ? '' : 'none';
        });
    }

    // Show/hide empty states
    const hasResults = pagedContainers.length > 0;
    const hasContainers = allContainers.length > 0;

    document.getElementById('emptyState').style.display = (!hasContainers && !searchTerm) ? 'flex' : 'none';
    document.getElementById('noResultsState').style.display = (!hasResults && searchTerm) ? 'flex' : 'none';

    const tableNoResults = document.getElementById('tableNoResults');
    if (tableNoResults) {
        tableNoResults.style.display = (!hasResults && searchTerm) ? 'flex' : 'none';
    }

    // Reorder DOM elements to match sort order
    if (currentView === 'card') {
        pagedContainers.forEach(c => {
            const card = cardGrid.querySelector(`.container-card[data-key="${c.key}"]`);
            if (card) cardGrid.appendChild(card);
        });
    } else if (tableBody) {
        pagedContainers.forEach(c => {
            const row = tableBody.querySelector(`tr[data-key="${c.key}"]`);
            if (row) tableBody.appendChild(row);
        });
    }

    updateSortIcons();

    // Probe visible links after pagination/filtering changes
    scheduleProbeVisibleLinks();
}

function refreshContainers() {
    location.reload();
}

// =============================================================================
// Link Probing (HTTP vs HTTPS)
// =============================================================================

let _probeQueueTimer = null;
let _probeInFlight = 0;
const _probeMaxConcurrency = 6;
const _probeResults = new Map();
const _probePromises = new Map();

function scheduleProbeVisibleLinks() {
    if (_probeQueueTimer) clearTimeout(_probeQueueTimer);
    _probeQueueTimer = setTimeout(runProbeQueue, 150);
}

function runProbeQueue() {
    const visibleLinks = Array.from(document.querySelectorAll('.probe-link'))
        .filter(a => a.offsetParent !== null);

    for (const a of visibleLinks) {
        const host = a.dataset.host;
        const port = a.dataset.port;
        if (!host || !port) continue;
        const key = `${host}:${port}`;

        // If we already probed this host:port, apply to all matching anchors.
        if (_probeResults.has(key)) {
            applyProbeResultToAnchors(host, port, _probeResults.get(key));
            continue;
        }

        // Avoid duplicating in-flight probes.
        if (_probePromises.has(key)) continue;

        _probePromises.set(key, enqueueProbe(host, port, key));
    }
}

function applyProbeResultToAnchor(anchorEl, data) {
    const schemeEl = anchorEl.querySelector('.link-scheme');
    const portEl = anchorEl.querySelector('.link-port');

    if (data.web && data.url) {
        anchorEl.href = data.url;
        anchorEl.classList.remove('is-nonweb');
        anchorEl.classList.toggle('is-https', data.scheme === 'https');
        if (schemeEl) schemeEl.textContent = data.scheme === 'https' ? 'https' : 'http';
        if (portEl) portEl.textContent = `:${data.port}`;
        anchorEl.setAttribute('target', '_blank');
        anchorEl.setAttribute('rel', 'noopener noreferrer');
        anchorEl.style.pointerEvents = '';
        anchorEl.removeAttribute('aria-disabled');
        anchorEl.removeAttribute('tabindex');
        anchorEl.title = 'Open in new tab';
    } else {
        // Not an HTTP(S) service; show as a plain port chip
        anchorEl.removeAttribute('href');
        anchorEl.classList.add('is-nonweb');
        anchorEl.classList.remove('is-https');
        if (schemeEl) schemeEl.textContent = 'tcp';
        if (portEl) portEl.textContent = `:${data.port}`;
        anchorEl.style.pointerEvents = 'none';
        anchorEl.setAttribute('aria-disabled', 'true');
        anchorEl.setAttribute('tabindex', '-1');
        anchorEl.title = 'Not an HTTP service';
    }
}

function applyProbeResultToAnchors(host, port, data) {
    const anchors = Array.from(document.querySelectorAll('.probe-link'))
        .filter(a => a.dataset.host === host && a.dataset.port === port);
    anchors.forEach(a => applyProbeResultToAnchor(a, data));
}

function enqueueProbe(host, port, key) {
    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
    const attempt = async () => {
        while (_probeInFlight >= _probeMaxConcurrency) {
            await sleep(100);
        }

        _probeInFlight += 1;
        try {
            const resp = await fetch(`/api/link/probe?host=${encodeURIComponent(host)}&port=${encodeURIComponent(port)}`);
            const data = await resp.json();
            if (!data || !data.success) return;

            _probeResults.set(key, data);
            applyProbeResultToAnchors(host, port, data);
        } catch (e) {
            // Leave as default http
        } finally {
            _probeInFlight -= 1;
            _probePromises.delete(key);
        }
    };

    // Kick off and return the promise so callers can avoid duplicates.
    const p = attempt();
    return p;
}

// =============================================================================
// Logs Viewer
// =============================================================================

let _logsContainerId = null;
let _logsContainerName = null;
let _logsInterval = null;

function openLogs(id, name) {
    _logsContainerId = id;
    _logsContainerName = name;
    document.getElementById('logsTitle').textContent = `📜 Logs — ${name}`;
    document.getElementById('logsOutput').textContent = 'Loading…';
    document.getElementById('logsModal').style.display = 'flex';
    refreshLogs();
    startLogsFollow();
}

function closeLogs(e) {
    if (e && e.target && e.target.id !== 'logsModal') return;
    document.getElementById('logsModal').style.display = 'none';
    stopLogsFollow();
    _logsContainerId = null;
    _logsContainerName = null;
}

function startLogsFollow() {
    stopLogsFollow();
    const follow = document.getElementById('logsFollow');
    if (!follow || !follow.checked) return;
    _logsInterval = setInterval(() => {
        const modalVisible = document.getElementById('logsModal').style.display !== 'none';
        if (!modalVisible) return;
        refreshLogs(true);
    }, 2000);
}

function stopLogsFollow() {
    if (_logsInterval) {
        clearInterval(_logsInterval);
        _logsInterval = null;
    }
}

async function refreshLogs(silent = false) {
    if (!_logsContainerId) return;
    const tail = document.getElementById('logsTail')?.value || '200';
    try {
        const resp = await fetch(`/api/container/${_logsContainerId}/logs?tail=${encodeURIComponent(tail)}&timestamps=1`);
        const data = await resp.json();
        if (!data.success) {
            document.getElementById('logsOutput').textContent = data.error || 'Failed to load logs';
            return;
        }
        const out = document.getElementById('logsOutput');
        const wasNearBottom = out.scrollTop + out.clientHeight >= out.scrollHeight - 40;
        out.textContent = data.logs || '';
        if (silent && !wasNearBottom) return;
        out.scrollTop = out.scrollHeight;
    } catch (err) {
        if (!silent) {
            document.getElementById('logsOutput').textContent = 'Failed to load logs';
        }
    }
}

async function copyLogs() {
    const text = document.getElementById('logsOutput').textContent || '';
    try {
        await navigator.clipboard.writeText(text);
        showToast('success', 'Logs copied to clipboard');
    } catch (e) {
        showToast('error', 'Failed to copy logs');
    }
}

// =============================================================================
// Container Actions
// =============================================================================

async function restartContainer(id, name) {
    if (!confirmAction(`Restart container "${name}"?\n\nThe container will briefly stop and start again.`)) return;

    showToast('info', `Restarting ${name}...`);

    try {
        const response = await fetch(`/api/container/${id}/restart`, { method: 'POST', headers: csrfHeaders() });
        const data = await response.json();

        if (data.success) {
            showToast('success', data.message);
            await waitForContainerStatus(id, ['running'], 8000);
            location.reload();
        } else {
            showToast('error', data.error);
        }
    } catch (error) {
        showToast('error', 'Failed to restart container');
    }
}

async function stopContainer(id, name) {
    if (!confirmAction(`Stop container "${name}"?\n\nThe container will be gracefully stopped.`)) return;

    showToast('info', `Stopping ${name}...`);

    try {
        const response = await fetch(`/api/container/${id}/stop`, { method: 'POST', headers: csrfHeaders() });
        const data = await response.json();

        if (data.success) {
            showToast('success', data.message);
            await waitForContainerStatus(id, ['exited', 'stopped'], 8000);
            location.reload();
        } else {
            showToast('error', data.error);
        }
    } catch (error) {
        showToast('error', 'Failed to stop container');
    }
}

async function startContainer(id, name) {
    showToast('info', `Starting ${name}...`);

    try {
        const response = await fetch(`/api/container/${id}/start`, { method: 'POST', headers: csrfHeaders() });
        const data = await response.json();

        if (data.success) {
            showToast('success', data.message);
            await waitForContainerStatus(id, ['running'], 8000);
            location.reload();
        } else {
            showToast('error', data.error);
        }
    } catch (error) {
        showToast('error', 'Failed to start container');
    }
}

async function removeContainer(id, name) {
    if (!confirmAction(`⚠️ DELETE container "${name}"?\n\nThis will permanently remove the container.\nVolumes and data may be lost. This cannot be undone.`, 'danger')) return;

    showToast('info', `Removing ${name}...`);

    try {
        const response = await fetch(`/api/container/${id}/remove`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ force: false })
        });
        const data = await response.json();

        if (data.success) {
            showToast('success', data.message);
            location.reload();
        } else {
            showToast('error', data.error);
        }
    } catch (error) {
        showToast('error', 'Failed to remove container');
    }
}

async function recreateContainer(id, name) {
    if (!confirmAction(`Recreate container "${name}"?\n\nThis will:\n• Pull the latest image\n• Stop and remove the current container\n• Create a new container with the same config\n• Rescan for vulnerabilities`)) return;

    showToast('info', `Recreating ${name}... This may take a moment.`, 5000);

    try {
        const response = await fetch(`/api/container/${id}/recreate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ pull_latest: true })
        });
        const data = await response.json();

        if (data.success) {
            let msg = data.message;
            if (data.pulled_new_image) {
                msg += ' (new image pulled)';
                // Show vulnerability scan results if available
                if (data.vulnerability_scan) {
                    const scan = data.vulnerability_scan;
                    msg += ` — CVEs: ${scan.critical || 0}C/${scan.high || 0}H/${scan.medium || 0}M/${scan.low || 0}L`;
                }
            }
            showToast('success', msg);
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast('error', data.error);
        }
    } catch (error) {
        showToast('error', 'Failed to recreate container');
    }
}

async function waitForContainerStatus(id, expectedStatuses, maxMs) {
    const start = Date.now();
    const dashboardEl = document.querySelector('.dashboard');
    const showAll = (dashboardEl?.dataset.showAll === 'true' || document.getElementById('filterStopped')?.checked) ? 'true' : 'false';
    while ((Date.now() - start) < maxMs) {
        try {
            const resp = await fetch(`/api/containers?show_all=${showAll}`);
            const containers = await resp.json();
            const c = (containers || []).find(x => x.id === id);
            if (!c) {
                // If container is gone (e.g., stopped and show_all=false), treat as done.
                if (!showAll) return true;
            } else if (expectedStatuses.includes(c.status)) {
                return true;
            }
        } catch (e) {
            // ignore
        }
        await new Promise(r => setTimeout(r, 800));
    }
    return false;
}

// =============================================================================
// Image Update Checking
// =============================================================================

let imageUpdateCache = {};

// Load stored update status on page load
async function loadStoredUpdates() {
    try {
        const response = await fetch('/api/updates/status');
        const data = await response.json();

        if (data.success && data.updates) {
            imageUpdateCache = data.updates;
            displayImageUpdates(data.updates);
        }
    } catch (error) {
        console.error('Error loading stored updates:', error);
    }
}

async function checkAllImageUpdates() {
    const btn = document.getElementById('checkUpdatesBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span> Checking...';
    btn.disabled = true;

    // Collect all unique images from containers
    const imageSet = new Set();
    document.querySelectorAll('[data-image-full]').forEach(el => {
        const img = el.dataset.imageFull;
        if (img && img !== 'unknown') {
            imageSet.add(img);
        }
    });

    const images = Array.from(imageSet);

    if (images.length === 0) {
        showToast('info', 'No images to check');
        btn.innerHTML = originalText;
        btn.disabled = false;
        return;
    }

    try {
        const response = await fetch('/api/images/check-updates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...csrfHeaders()
            },
            body: JSON.stringify({ images })
        });

        const data = await response.json();

        if (data.success) {
            imageUpdateCache = data.results;
            displayImageUpdates(data.results);
        } else {
            showToast('error', data.error || 'Failed to check updates');
        }
    } catch (error) {
        console.error('Error checking updates:', error);
        showToast('error', 'Failed to check image updates');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

function displayImageUpdates(results) {
    let updateCount = 0;
    const containersWithUpdates = new Set();
    const errorCount = Object.values(results).filter(result => result?.error).length;

    // Update all badges in card view and set data attributes
    document.querySelectorAll('.container-card').forEach(card => {
        const image = card.dataset.imageFull;
        const result = results[image];
        const hasUpdate = result && result.has_update === true;

        // Set data attribute for filtering
        card.dataset.hasUpdate = hasUpdate ? 'true' : 'false';

        if (hasUpdate) {
            updateCount++;
            containersWithUpdates.add(card.dataset.id);
        }

        // Update badge
        const badge = card.querySelector('.update-badge');
        if (badge) {
            if (hasUpdate) {
                badge.style.display = 'inline-flex';
                badge.title = `Update available!\nLocal: ${result.local_digest?.substring(0, 20)}...\nRemote: ${result.remote_digest?.substring(0, 20)}...`;
            } else {
                badge.style.display = 'none';
            }
        }

        // Show/hide the Update button
        const updateBtn = card.querySelector('.update-container-btn');
        if (updateBtn) {
            updateBtn.style.display = hasUpdate ? 'inline-flex' : 'none';
        }
    });

    // Update image row icons in card view
    document.querySelectorAll('.container-card .image-value').forEach(span => {
        const image = span.dataset.image;
        const result = results[image];
        const icon = span.querySelector('.image-update-icon');
        if (icon) {
            if (result && result.has_update === true) {
                icon.textContent = '⬆️';
                icon.title = 'Update available!';
                icon.style.display = 'inline';
                icon.style.cursor = 'pointer';
            } else if (result && result.has_update === false) {
                icon.textContent = '✅';
                icon.title = 'Up to date';
                icon.style.display = 'inline';
            } else if (result && result.error) {
                icon.textContent = '❓';
                icon.title = result.error;
                icon.style.display = 'inline';
            } else {
                icon.style.display = 'none';
            }
        }
    });

    // Update table view - set data attributes and badges
    document.querySelectorAll('#tableBody tr').forEach(row => {
        const image = row.dataset.imageFull;
        const result = results[image];
        const hasUpdate = result && result.has_update === true;

        row.dataset.hasUpdate = hasUpdate ? 'true' : 'false';

        const badge = row.querySelector('.update-badge');
        if (badge) {
            if (hasUpdate) {
                badge.style.display = 'inline';
                badge.title = 'Update available!';
            } else {
                badge.style.display = 'none';
            }
        }
    });

    // Update header count
    const countContainer = document.getElementById('updateCount');
    const countValue = document.getElementById('updateCountValue');
    if (countContainer && countValue) {
        if (updateCount > 0) {
            countContainer.style.display = 'inline';
            countValue.textContent = updateCount;
        } else {
            countContainer.style.display = 'none';
        }
    }

    // Show/hide Update All button
    const updateAllBtn = document.getElementById('updateAllBtn');
    const updateAllCount = document.getElementById('updateAllCount');
    if (updateAllBtn && updateAllCount) {
        if (updateCount > 0) {
            updateAllBtn.style.display = 'inline-flex';
            updateAllCount.textContent = updateCount;
        } else {
            updateAllBtn.style.display = 'none';
        }
    }

    // Only show toast if this was a fresh check (not loaded from storage)
    if (Object.keys(results).length > 0 && document.getElementById('checkUpdatesBtn')?.disabled === false) {
        if (errorCount > 0) {
            showToast('warning', `${updateCount} update${updateCount === 1 ? '' : 's'} found; ${errorCount} image check${errorCount === 1 ? '' : 's'} could not complete`);
        } else if (updateCount > 0) {
            showToast('info', `${updateCount} image update${updateCount > 1 ? 's' : ''} available`);
        } else {
            showToast('success', 'All images are up to date');
        }
    }
}

// Check a single image (for lazy loading on hover or similar)
async function checkSingleImageUpdate(image) {
    if (imageUpdateCache[image]) {
        return imageUpdateCache[image];
    }

    try {
        const response = await fetch(`/api/image/check-update?image=${encodeURIComponent(image)}`);
        const data = await response.json();
        imageUpdateCache[image] = data;
        return data;
    } catch (error) {
        console.error('Error checking image update:', error);
        return null;
    }
}

// =============================================================================
// Container Stats
// =============================================================================

async function toggleStats(containerId) {
    const statsDiv = document.getElementById(`stats-${containerId}`);
    if (!statsDiv) return;

    if (statsDiv.style.display === 'none') {
        statsDiv.style.display = 'block';
        await refreshStats(containerId);
    } else {
        statsDiv.style.display = 'none';
    }
}

async function refreshStats(containerId) {
    const statsDiv = document.getElementById(`stats-${containerId}`);
    if (!statsDiv) return;

    try {
        const response = await fetch(`/api/container/${containerId}/stats`);
        const data = await response.json();

        if (data.success) {
            const stats = data.stats;
            statsDiv.querySelector('.cpu-stat').textContent = `${stats.cpu_percent}%`;
            statsDiv.querySelector('.mem-stat').textContent = `${stats.memory_usage_human} / ${stats.memory_limit_human}`;
            statsDiv.querySelector('.cpu-fill').style.width = `${Math.min(stats.cpu_percent, 100)}%`;
            statsDiv.querySelector('.mem-fill').style.width = `${stats.memory_percent}%`;

            // Color coding
            statsDiv.querySelector('.cpu-fill').className = `stat-fill cpu-fill ${stats.cpu_percent > 80 ? 'high' : stats.cpu_percent > 50 ? 'medium' : ''}`;
            statsDiv.querySelector('.mem-fill').className = `stat-fill mem-fill ${stats.memory_percent > 80 ? 'high' : stats.memory_percent > 50 ? 'medium' : ''}`;
        }
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

// =============================================================================
// Execute Command
// =============================================================================

let currentExecContainer = null;

function openExec(containerId, containerName) {
    currentExecContainer = containerId;
    document.getElementById('execTitle').textContent = `💻 Execute: ${containerName}`;
    document.getElementById('execCommand').value = '';
    document.getElementById('execWorkdir').value = '';
    document.getElementById('execOutput').textContent = '';
    document.getElementById('execModal').style.display = 'flex';
    document.getElementById('execCommand').focus();
}

function closeExec(e) {
    if (e && e.target && e.target.id !== 'execModal') return;
    document.getElementById('execModal').style.display = 'none';
    currentExecContainer = null;
}

async function runExec() {
    if (!currentExecContainer) return;

    const command = document.getElementById('execCommand').value.trim();
    const workdir = document.getElementById('execWorkdir').value.trim();

    if (!command) {
        showToast('error', 'Command is required');
        return;
    }

    const output = document.getElementById('execOutput');
    output.textContent = 'Running...';

    try {
        const response = await fetch(`/api/container/${currentExecContainer}/exec`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ command, workdir: workdir || undefined })
        });
        const data = await response.json();

        if (data.success) {
            let result = '';
            if (data.stdout) result += data.stdout;
            if (data.stderr) result += (result ? '\n--- stderr ---\n' : '') + data.stderr;
            output.textContent = result || '(no output)';
            output.className = `exec-output exit-${data.exit_code === 0 ? 'success' : 'error'}`;
        } else {
            output.textContent = `Error: ${data.error}`;
            output.className = 'exec-output exit-error';
        }
    } catch (error) {
        output.textContent = `Error: ${error.message}`;
        output.className = 'exec-output exit-error';
    }
}

// =============================================================================
// Inspect Container
// =============================================================================

let currentInspectData = null;

async function openInspect(containerId, containerName) {
    document.getElementById('inspectTitle').textContent = `🔍 ${containerName}`;
    document.getElementById('inspectTabContent').innerHTML = '<p>Loading...</p>';
    document.getElementById('inspectModal').style.display = 'flex';

    try {
        const response = await fetch(`/api/container/${containerId}`);
        const data = await response.json();

        if (data.success) {
            currentInspectData = data.container;
            showInspectTab('env');
        } else {
            document.getElementById('inspectTabContent').innerHTML = `<p class="error">Error: ${data.error}</p>`;
        }
    } catch (error) {
        document.getElementById('inspectTabContent').innerHTML = `<p class="error">Error: ${error.message}</p>`;
    }
}

function closeInspect(e) {
    if (e && e.target && e.target.id !== 'inspectModal') return;
    document.getElementById('inspectModal').style.display = 'none';
    currentInspectData = null;
}

function showInspectTab(tab, button = null) {
    const buttons = Array.from(document.querySelectorAll('.inspect-tabs .tab-btn'));
    buttons.forEach(btn => btn.classList.remove('active'));
    const tabOrder = ['env', 'mounts', 'networks', 'labels'];
    const activeButton = button || buttons[tabOrder.indexOf(tab)];
    if (activeButton) activeButton.classList.add('active');

    const content = document.getElementById('inspectTabContent');
    if (!currentInspectData) return;

    let html = '';
    switch (tab) {
        case 'env':
            const envVars = currentInspectData.env_vars || {};
            html = '<table class="inspect-table"><thead><tr><th>Variable</th><th>Value</th></tr></thead><tbody>';
            for (const [k, v] of Object.entries(envVars)) {
                html += `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`;
            }
            html += '</tbody></table>';
            break;
        case 'mounts':
            const mounts = currentInspectData.mounts || [];
            html = '<table class="inspect-table"><thead><tr><th>Type</th><th>Source</th><th>Destination</th><th>Mode</th></tr></thead><tbody>';
            for (const m of mounts) {
                html += `<tr><td>${m.type}</td><td>${escapeHtml(m.source || '')}</td><td>${escapeHtml(m.destination || '')}</td><td>${m.rw ? 'rw' : 'ro'}</td></tr>`;
            }
            html += '</tbody></table>';
            break;
        case 'networks':
            const networks = currentInspectData.networks || [];
            html = '<ul class="inspect-list">';
            for (const n of networks) {
                html += `<li>🌐 ${escapeHtml(n)}</li>`;
            }
            html += '</ul>';
            break;
        case 'labels':
            const labels = currentInspectData.labels || {};
            html = '<table class="inspect-table"><thead><tr><th>Label</th><th>Value</th></tr></thead><tbody>';
            for (const [k, v] of Object.entries(labels)) {
                html += `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`;
            }
            html += '</tbody></table>';
            break;
    }
    content.innerHTML = html || '<p>No data</p>';
}

// =============================================================================
// Vulnerability Scanning
// =============================================================================

let vulnScanInProgress = false;

async function scanAllVulnerabilities() {
    if (vulnScanInProgress) {
        showToast('info', 'Scan already in progress...');
        return;
    }

    const btn = document.getElementById('scanVulnBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Scanning...';
    btn.disabled = true;
    vulnScanInProgress = true;

    showToast('info', 'Starting vulnerability scan for all container images...');

    try {
        const response = await fetch('/api/vulnerabilities/scan-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({})
        });
        const data = await response.json();

        if (data.success) {
            const summary = data.total_summary || {};
            showToast('success', `Scan complete! ${data.images_scanned} images scanned. ` +
                `${summary.critical || 0} Critical, ${summary.high || 0} High vulnerabilities found.`);

            // Reload to show updated vulnerability badges
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast('error', data.error || 'Scan failed');
        }
    } catch (error) {
        console.error('Error scanning vulnerabilities:', error);
        showToast('error', 'Failed to scan vulnerabilities');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
        vulnScanInProgress = false;
    }
}

// =============================================================================
// Vulnerability Details Modal
// =============================================================================

let currentVulnData = [];
let currentVulnContext = null;

async function showVulnerabilities(imageRef, containerName) {
    const modal = document.getElementById('vulnModal');
    const title = document.getElementById('vulnModalTitle');
    const summaryBar = document.getElementById('vulnSummaryBar');
    const tableBody = document.getElementById('vulnTableBody');

    title.textContent = `🛡️ Security Issues: ${containerName}`;
    summaryBar.innerHTML = '<div class="loading">Loading vulnerability data...</div>';
    tableBody.innerHTML = '';
    modal.style.display = 'flex';

    const candidates = document.querySelectorAll('.container-card[data-image-full], tr[data-image-full]');
    const source = Array.from(candidates).find(item =>
        item.dataset.imageFull === imageRef && item.dataset.name === String(containerName).toLowerCase()
    );
    currentVulnContext = source ? {
        containerId: source.dataset.id,
        containerName,
        image: imageRef,
        projectId: source.dataset.projectId,
        projectName: source.dataset.projectName,
        service: source.dataset.composeService,
        canUpdate: source.dataset.canUpdate === 'true'
    } : null;

    try {
        const response = await fetch(`/api/vulnerabilities/details/${encodeURIComponent(imageRef)}`);
        const data = await response.json();

        if (!data.success) {
            summaryBar.innerHTML = `<div class="error-msg">${data.error || 'Failed to load data'}</div>`;
            return;
        }

        currentVulnData = data.vulnerabilities || [];
        const summary = data.summary || {};
        const fixable = currentVulnData.filter(item => item.fixed_version).length;
        let remediation = '<span class="text-muted">This workload has no automated update path.</span>';
        if (currentVulnContext?.projectId) {
            if (currentVulnContext.canUpdate) {
                remediation = `<button class="btn btn-success btn-sm" onclick="updateCurrentVulnerableService()">⬆️ Pull, redeploy & rescan</button>
                    <button class="btn btn-secondary btn-sm" onclick="openCurrentVulnerabilityProject()">Open Compose project</button>`;
            } else {
                remediation = `<span class="text-muted">This service must be running before an in-place update.</span>
                    <button class="btn btn-secondary btn-sm" onclick="openCurrentVulnerabilityProject()">Open Compose project</button>`;
            }
        } else if (document.querySelector('.dashboard')?.dataset.endpointKind === 'agent') {
            remediation = '<span class="text-muted">Safe remote updates require an adopted Compose project.</span>';
        }

        // Render summary bar
        summaryBar.innerHTML = `
            <div class="vuln-stat stat-critical">🔴 Critical: ${summary.critical || 0}</div>
            <div class="vuln-stat stat-high">🟠 High: ${summary.high || 0}</div>
            <div class="vuln-stat stat-medium">🟡 Medium: ${summary.medium || 0}</div>
            <div class="vuln-stat stat-low">🟢 Low: ${summary.low || 0}</div>
            <div style="flex: 1;"></div>
            <div class="vuln-stat" style="background: #E2E8F0; color: #475569;">
                📦 Image: ${escapeHtml(data.image || imageRef)}
            </div>
            <div class="vuln-stat" style="background: #E2E8F0; color: #475569;">
                🕐 Scanned: ${data.scanned_at ? new Date(data.scanned_at).toLocaleString() : 'N/A'}
            </div>
            <div class="vuln-stat" style="background: #E2E8F0; color: #475569;">🔧 Fix published: ${fixable}</div>
            <div class="vuln-remediation-actions">${remediation}</div>
        `;

        // Render table
        filterVulnTable();

    } catch (error) {
        console.error('Error loading vulnerabilities:', error);
        summaryBar.innerHTML = '<div class="error-msg">Failed to load vulnerability data</div>';
    }
}

function filterVulnTable() {
    const showCritical = document.getElementById('vulnFilterCritical')?.checked ?? true;
    const showHigh = document.getElementById('vulnFilterHigh')?.checked ?? true;
    const showMedium = document.getElementById('vulnFilterMedium')?.checked ?? false;
    const showLow = document.getElementById('vulnFilterLow')?.checked ?? false;
    const searchTerm = (document.getElementById('vulnSearch')?.value || '').toLowerCase();

    const filtered = currentVulnData.filter(vuln => {
        const severity = (vuln.severity || '').toUpperCase();
        const matchesSeverity =
            (severity === 'CRITICAL' && showCritical) ||
            (severity === 'HIGH' && showHigh) ||
            (severity === 'MEDIUM' && showMedium) ||
            (severity === 'LOW' && showLow);

        if (!matchesSeverity) return false;

        if (searchTerm) {
            const searchable = `${vuln.id} ${vuln.package} ${vuln.title} ${vuln.description}`.toLowerCase();
            if (!searchable.includes(searchTerm)) return false;
        }

        return true;
    });

    const tableBody = document.getElementById('vulnTableBody');
    const emptyMsg = document.getElementById('vulnEmpty');

    if (filtered.length === 0) {
        tableBody.innerHTML = '';
        emptyMsg.style.display = 'block';
        return;
    }

    emptyMsg.style.display = 'none';

    // Sort by severity
    const severityOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
    filtered.sort((a, b) => {
        const aOrder = severityOrder[a.severity?.toUpperCase()] ?? 5;
        const bOrder = severityOrder[b.severity?.toUpperCase()] ?? 5;
        return aOrder - bOrder;
    });

    tableBody.innerHTML = filtered.map(vuln => {
        const severity = (vuln.severity || 'UNKNOWN').toUpperCase();
        const cveLink = vuln.id?.startsWith('CVE-')
            ? `<a href="https://nvd.nist.gov/vuln/detail/${vuln.id}" target="_blank" rel="noopener">${vuln.id}</a>`
            : escapeHtml(vuln.id || 'N/A');
        const fixedVersion = vuln.fixed_version
            ? `<span class="fixed-version">${escapeHtml(vuln.fixed_version)}</span>`
            : '<span class="no-fix">No fix</span>';

        return `
            <tr>
                <td class="severity-cell severity-${severity}">${severity}</td>
                <td class="cve-id">${cveLink}</td>
                <td class="pkg-name">${escapeHtml(vuln.package || 'N/A')}</td>
                <td class="version-cell">${escapeHtml(vuln.version || 'N/A')}</td>
                <td class="version-cell">${fixedVersion}</td>
                <td class="desc-cell" title="${escapeHtml(vuln.title || vuln.description || '')}">${escapeHtml(vuln.title || vuln.description || 'N/A')}</td>
            </tr>
        `;
    }).join('');
}

function closeVulnModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('vulnModal').style.display = 'none';
    currentVulnData = [];
    currentVulnContext = null;
}

function openCurrentVulnerabilityProject() {
    const context = currentVulnContext;
    if (!context?.projectId) return;
    const endpointId = document.querySelector('.dashboard')?.dataset.endpointId;
    location.href = `/projects?endpoint_id=${encodeURIComponent(endpointId)}&project_id=${encodeURIComponent(context.projectId)}`;
}

async function updateCurrentVulnerableService() {
    const context = currentVulnContext;
    if (!context?.canUpdate || !context.projectId || !context.service) return;
    if (!confirm(`Remediate ${context.containerName}?\n\nDockDash will pull the current image tag, redeploy only ${context.service}, verify health, and rescan it. If the tag has no newer fixed image, findings may remain and you may need to change the tag in Compose.`)) return;
    document.getElementById('vulnModal').style.display = 'none';
    showToast('info', `${context.containerName}: update and security refresh queued…`, 7000);
    try {
        const job = await queueComposeAction(context.projectId, 'update', [context.service]);
        showComposeCompletion(job, `${context.containerName}: remediation workflow`);
        setTimeout(() => location.reload(), 900);
    } catch (error) {
        showToast('error', `${context.containerName}: ${error.message}`, 12000);
    }
}

// =============================================================================
// Container Filtering
// =============================================================================

function saveFilterState() {
    const state = {
        hasUpdate: document.getElementById('filterHasUpdate')?.checked || false,
        hasVuln: document.getElementById('filterHasVuln')?.checked || false,
        filterCritical: document.getElementById('filterCritical')?.checked ?? true,
        filterHigh: document.getElementById('filterHigh')?.checked ?? true,
        filterMedium: document.getElementById('filterMedium')?.checked ?? false,
        filterLow: document.getElementById('filterLow')?.checked ?? false
    };
    sessionStorage.setItem('dockdash-filters', JSON.stringify(state));
}

function restoreFilterState() {
    try {
        const saved = sessionStorage.getItem('dockdash-filters');
        if (!saved) return;
        const state = JSON.parse(saved);

        const hasUpdateEl = document.getElementById('filterHasUpdate');
        const hasVulnEl = document.getElementById('filterHasVuln');
        const criticalEl = document.getElementById('filterCritical');
        const highEl = document.getElementById('filterHigh');
        const mediumEl = document.getElementById('filterMedium');
        const lowEl = document.getElementById('filterLow');

        if (hasUpdateEl && state.hasUpdate) hasUpdateEl.checked = true;
        if (hasVulnEl && state.hasVuln) hasVulnEl.checked = true;
        if (criticalEl) criticalEl.checked = state.filterCritical ?? true;
        if (highEl) highEl.checked = state.filterHigh ?? true;
        if (mediumEl) mediumEl.checked = state.filterMedium ?? false;
        if (lowEl) lowEl.checked = state.filterLow ?? false;

        // Apply restored filters
        if (state.hasUpdate || state.hasVuln) {
            applyFilters();
        }
    } catch (e) {
        console.warn('Could not restore filter state:', e);
    }
}

function applyFilters() {
    const hasUpdateFilter = document.getElementById('filterHasUpdate')?.checked || false;
    const hasVulnFilter = document.getElementById('filterHasVuln')?.checked || false;
    const stoppedOnly = document.getElementById('filterStopped')?.checked || false;

    // Save filter state for persistence across refresh
    saveFilterState();
    const showCritical = document.getElementById('filterCritical')?.checked ?? true;
    const showHigh = document.getElementById('filterHigh')?.checked ?? true;
    const showMedium = document.getElementById('filterMedium')?.checked ?? false;
    const showLow = document.getElementById('filterLow')?.checked ?? false;

    // Show/hide severity filters when vuln filter is active
    const severityFilters = document.getElementById('severityFilters');
    if (severityFilters) {
        severityFilters.style.display = hasVulnFilter ? 'flex' : 'none';
    }

    // Show/hide clear button
    const clearBtn = document.getElementById('clearFiltersBtn');
    if (clearBtn) {
        clearBtn.style.display = (hasUpdateFilter || hasVulnFilter || stoppedOnly) ? 'inline-block' : 'none';
    }

    const cards = document.querySelectorAll('.container-card');
    const rows = document.querySelectorAll('#tableBody tr');

    let visibleCount = 0;

    cards.forEach(card => {
        let show = true;

        // Check stopped-only filter
        if (stoppedOnly) {
            const status = card.dataset.status;
            if (status === 'running') show = false;
        }

        // Check update filter
        if (hasUpdateFilter) {
            const hasUpdate = card.dataset.hasUpdate === 'true';
            if (!hasUpdate) show = false;
        }

        // Check vulnerability filter
        if (hasVulnFilter && show) {
            const critical = parseInt(card.dataset.vulnCritical || 0);
            const high = parseInt(card.dataset.vulnHigh || 0);
            const medium = parseInt(card.dataset.vulnMedium || 0);
            const low = parseInt(card.dataset.vulnLow || 0);

            const hasMatchingVuln =
                (showCritical && critical > 0) ||
                (showHigh && high > 0) ||
                (showMedium && medium > 0) ||
                (showLow && low > 0);

            if (!hasMatchingVuln) show = false;
        }

        card.style.display = show ? '' : 'none';
        if (show) visibleCount++;
    });

    // Apply same logic to table rows
    rows.forEach(row => {
        let show = true;

        if (stoppedOnly) {
            const status = row.dataset.status;
            if (status === 'running') show = false;
        }

        if (hasUpdateFilter) {
            const hasUpdate = row.dataset.hasUpdate === 'true';
            if (!hasUpdate) show = false;
        }

        if (hasVulnFilter && show) {
            const critical = parseInt(row.dataset.vulnCritical || 0);
            const high = parseInt(row.dataset.vulnHigh || 0);
            const medium = parseInt(row.dataset.vulnMedium || 0);
            const low = parseInt(row.dataset.vulnLow || 0);

            const hasMatchingVuln =
                (showCritical && critical > 0) ||
                (showHigh && high > 0) ||
                (showMedium && medium > 0) ||
                (showLow && low > 0);

            if (!hasMatchingVuln) show = false;
        }

        row.style.display = show ? '' : 'none';
    });

    // Update count
    document.getElementById('totalFiltered').textContent = visibleCount;

    // Show/hide no results message
    const noResults = document.getElementById('noResultsState');
    if (noResults) {
        noResults.style.display = visibleCount === 0 ? 'block' : 'none';
    }
}

function clearFilters() {
    document.getElementById('filterHasUpdate').checked = false;
    document.getElementById('filterHasVuln').checked = false;
    const stoppedFilter = document.getElementById('filterStopped');
    if (stoppedFilter) stoppedFilter.checked = false;
    document.getElementById('filterCritical').checked = true;
    document.getElementById('filterHigh').checked = true;
    document.getElementById('filterMedium').checked = false;
    document.getElementById('filterLow').checked = false;
    // Clear saved filter state
    sessionStorage.removeItem('dockdash-filters');
    applyFilters();
}

// Toggle functions for clickable info bar stats
function toggleUpdateFilter() {
    const checkbox = document.getElementById('filterHasUpdate');
    if (checkbox) {
        checkbox.checked = !checkbox.checked;
        applyFilters();
    }
}

function toggleVulnFilter() {
    const checkbox = document.getElementById('filterHasVuln');
    if (checkbox) {
        checkbox.checked = !checkbox.checked;
        applyFilters();
    }
}

// =============================================================================
// Compose Project Grouping
// =============================================================================

function toggleComposeGroup(project) {
    const group = document.querySelector(`.compose-group[data-project="${project}"]`);
    if (group) {
        group.classList.toggle('collapsed');
        // Save state to localStorage
        const collapsed = JSON.parse(localStorage.getItem('dockdash-collapsed-groups') || '{}');
        collapsed[project] = group.classList.contains('collapsed');
        localStorage.setItem('dockdash-collapsed-groups', JSON.stringify(collapsed));
    }
}

function restoreCollapsedGroups() {
    const collapsed = JSON.parse(localStorage.getItem('dockdash-collapsed-groups') || '{}');
    for (const [project, isCollapsed] of Object.entries(collapsed)) {
        if (isCollapsed) {
            const group = document.querySelector(`.compose-group[data-project="${project}"]`);
            if (group) group.classList.add('collapsed');
        }
    }
}

async function waitForProjectJob(jobId) {
    const endpointId = document.querySelector('.dashboard')?.dataset.endpointId;
    const deadline = Date.now() + 30 * 60 * 1000;
    while (Date.now() < deadline) {
        const response = await fetch(`/api/jobs/${jobId}?endpoint_id=${encodeURIComponent(endpointId)}`);
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Could not read deployment job');
        if (data.job.status === 'succeeded') return data.job;
        if (data.job.status === 'failed') throw new Error(data.job.error || 'Deployment failed');
        await new Promise(resolve => setTimeout(resolve, 1500));
    }
    throw new Error('Deployment is still running; check Compose Projects for its status.');
}

async function queueComposeAction(projectId, action, services = []) {
    const endpointId = document.querySelector('.dashboard')?.dataset.endpointId;
    const response = await fetch(`/api/projects/${projectId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
        body: JSON.stringify({ action, services, endpoint_id: endpointId })
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Could not queue Compose action');
    return waitForProjectJob(data.job.id);
}

function showComposeCompletion(job, label) {
    const warning = (job.output || '').includes('Warning:');
    showToast(
        warning ? 'warning' : 'success',
        warning ? `${label} deployed, but an evidence refresh warning was recorded. Review Compose Projects.` : `${label} completed`,
        warning ? 10000 : 3000
    );
}

async function runComposeProjectAction(projectId, action, projectName) {
    const descriptions = {
        start: 'Start this Compose project?',
        stop: 'Stop this Compose project?',
        restart: 'Restart this Compose project?',
        update: 'Pull current image tags, force-redeploy running services, verify health, and refresh vulnerability evidence?'
    };
    if (!projectId || !confirm(`${projectName}\n\n${descriptions[action] || `Run ${action}?`}`)) return;
    showToast('info', `${projectName}: ${action} job queued…`, 6000);
    try {
        const job = await queueComposeAction(projectId, action);
        showComposeCompletion(job, `${projectName}: ${action}`);
        setTimeout(() => location.reload(), 900);
    } catch (error) {
        showToast('error', `${projectName}: ${error.message}`, 10000);
    }
}

function getContainersByProject(project) {
    const cards = document.querySelectorAll(`.compose-group[data-project="${project}"] .container-card`);
    return Array.from(cards).map(card => ({
        id: card.dataset.id,
        name: card.dataset.name,
        status: card.dataset.status,
        projectId: card.dataset.projectId,
        projectName: card.dataset.projectName,
        service: card.dataset.composeService,
        canUpdate: card.dataset.canUpdate === 'true'
    }));
}

// =============================================================================
// Bulk Selection
// =============================================================================

function updateBulkSelection() {
    const checkboxes = document.querySelectorAll('.container-checkbox:checked');
    const count = checkboxes.length;
    const bulkBar = document.getElementById('bulkActionsBar');
    const countSpan = document.getElementById('selectedCount');

    if (count > 0) {
        bulkBar.style.display = 'flex';
        countSpan.textContent = count;
    } else {
        bulkBar.style.display = 'none';
    }

    // Update card visual selection
    document.querySelectorAll('.container-card').forEach(card => {
        const checkbox = card.querySelector('.container-checkbox');
        if (checkbox) {
            card.classList.toggle('selected', checkbox.checked);
        }
    });

    // Sync "select all" checkboxes
    const allCheckboxes = document.querySelectorAll('.container-checkbox');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const tableSelectAll = document.getElementById('tableSelectAll');
    const allChecked = allCheckboxes.length > 0 && checkboxes.length === allCheckboxes.length;

    if (selectAllCheckbox) selectAllCheckbox.checked = allChecked;
    if (tableSelectAll) tableSelectAll.checked = allChecked;
}

function toggleSelectAll() {
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const tableSelectAll = document.getElementById('tableSelectAll');
    const isChecked = selectAllCheckbox?.checked || tableSelectAll?.checked || false;

    // Sync both select all checkboxes
    if (selectAllCheckbox) selectAllCheckbox.checked = isChecked;
    if (tableSelectAll) tableSelectAll.checked = isChecked;

    // Toggle all individual checkboxes
    document.querySelectorAll('.container-checkbox').forEach(cb => {
        cb.checked = isChecked;
    });

    updateBulkSelection();
}

function clearSelection() {
    document.querySelectorAll('.container-checkbox').forEach(cb => {
        cb.checked = false;
    });
    updateBulkSelection();
}

function getSelectedContainers() {
    const selected = [];
    document.querySelectorAll('.container-checkbox:checked').forEach(cb => {
        selected.push({
            id: cb.dataset.id,
            name: cb.dataset.name,
            status: cb.dataset.status,
            projectId: cb.dataset.projectId,
            projectName: cb.dataset.projectName,
            service: cb.dataset.composeService,
            canUpdate: cb.dataset.canUpdate === 'true'
        });
    });
    return selected;
}

async function bulkStartContainers() {
    const containers = getSelectedContainers().filter(c => c.status !== 'running');

    if (containers.length === 0) {
        showToast('info', 'No stopped containers selected');
        return;
    }

    const names = containers.map(c => c.name).join(', ');
    if (!confirm(`Start ${containers.length} container(s)?\n\n${names}`)) return;

    showToast('info', `Starting ${containers.length} container(s)...`);

    let success = 0, failed = 0;
    for (const c of containers) {
        try {
            const response = await fetch(`/api/container/${c.id}/start`, { method: 'POST', headers: csrfHeaders() });
            const data = await response.json();
            if (data.success) success++;
            else failed++;
        } catch (e) { failed++; }
    }

    if (success > 0) showToast('success', `Started ${success} container(s)`);
    if (failed > 0) showToast('error', `Failed to start ${failed} container(s)`);

    setTimeout(() => location.reload(), 1000);
}

async function bulkStopContainers() {
    const containers = getSelectedContainers().filter(c => c.status === 'running');

    if (containers.length === 0) {
        showToast('info', 'No running containers selected');
        return;
    }

    const names = containers.map(c => c.name).join(', ');
    if (!confirm(`Stop ${containers.length} container(s)?\n\n${names}`)) return;

    showToast('info', `Stopping ${containers.length} container(s)...`);

    let success = 0, failed = 0;
    for (const c of containers) {
        try {
            const response = await fetch(`/api/container/${c.id}/stop`, { method: 'POST', headers: csrfHeaders() });
            const data = await response.json();
            if (data.success) success++;
            else failed++;
        } catch (e) { failed++; }
    }

    if (success > 0) showToast('success', `Stopped ${success} container(s)`);
    if (failed > 0) showToast('error', `Failed to stop ${failed} container(s)`);

    setTimeout(() => location.reload(), 1000);
}

async function bulkRestartContainers() {
    const containers = getSelectedContainers().filter(c => c.status === 'running');

    if (containers.length === 0) {
        showToast('info', 'No running containers selected');
        return;
    }

    const names = containers.map(c => c.name).join(', ');
    if (!confirm(`Restart ${containers.length} container(s)?\n\n${names}`)) return;

    showToast('info', `Restarting ${containers.length} container(s)...`);

    let success = 0, failed = 0;
    for (const c of containers) {
        try {
            const response = await fetch(`/api/container/${c.id}/restart`, { method: 'POST', headers: csrfHeaders() });
            const data = await response.json();
            if (data.success) success++;
            else failed++;
        } catch (e) { failed++; }
    }

    if (success > 0) showToast('success', `Restarted ${success} container(s)`);
    if (failed > 0) showToast('error', `Failed to restart ${failed} container(s)`);

    setTimeout(() => location.reload(), 1000);
}

async function bulkRecreateContainers() {
    const containers = getSelectedContainers();

    if (containers.length === 0) {
        showToast('info', 'No containers selected');
        return;
    }

    const names = containers.map(c => c.name).join(', ');
    if (!confirm(`Recreate ${containers.length} container(s)?\n\nThis will pull the latest images and restart:\n${names}`)) return;

    showToast('info', `Recreating ${containers.length} container(s)...`);

    let success = 0, failed = 0;
    for (const c of containers) {
        try {
            const response = await fetch(`/api/container/${c.id}/recreate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
                body: JSON.stringify({ pull_latest: true })
            });
            const data = await response.json();
            if (data.success) success++;
            else failed++;
        } catch (e) { failed++; }
    }

    if (success > 0) showToast('success', `Recreated ${success} container(s)`);
    if (failed > 0) showToast('error', `Failed to recreate ${failed} container(s)`);

    setTimeout(() => location.reload(), 1500);
}

async function bulkUpdateComposeServices() {
    const selected = getSelectedContainers();
    const eligible = selected.filter(item => item.canUpdate && item.projectId && item.service);
    const skipped = selected.length - eligible.length;
    if (eligible.length === 0) {
        showToast('warning', 'Select running services from adopted Compose projects. Standalone and stopped containers cannot be updated safely here.', 9000);
        return;
    }

    const groups = new Map();
    for (const item of eligible) {
        if (!groups.has(item.projectId)) groups.set(item.projectId, { name: item.projectName, services: [] });
        const services = groups.get(item.projectId).services;
        if (!services.includes(item.service)) services.push(item.service);
    }
    const warning = skipped ? `\n\n${skipped} ineligible selection(s) will be skipped.` : '';
    if (!confirm(`Update ${eligible.length} selected Compose service(s)?\n\nDockDash will pull their current tags, redeploy only those services, verify the project, and rescan images.${warning}`)) return;

    showToast('info', `Queued ${groups.size} Compose update job(s)…`, 6000);
    let completed = 0;
    try {
        for (const [projectId, group] of groups) {
            const job = await queueComposeAction(projectId, 'update', group.services);
            completed += 1;
            showComposeCompletion(job, `${group.name}: update`);
        }
        setTimeout(() => location.reload(), 900);
    } catch (error) {
        showToast('error', `${completed}/${groups.size} project updates completed: ${error.message}`, 12000);
    }
}

// =============================================================================
// Container Update Functions
// =============================================================================

async function updateContainer(containerId, containerName) {
    if (!confirmAction(`Update container "${containerName}"?\n\nThis will:\n• Pull the latest image\n• Stop the container\n• Recreate it with the same settings\n• Start it if it was running`)) {
        return;
    }

    showToast('info', `Updating ${containerName}... This may take a moment.`, 6000);

    try {
        const response = await fetch(`/api/container/${containerId}/recreate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...csrfHeaders()
            },
            body: JSON.stringify({ pull_latest: true })
        });

        const data = await response.json();

        if (data.success) {
            const newContainerId = data.container_id;
            let msg = data.message || `Container ${containerName} updated successfully`;
            if (data.pulled_new_image) {
                msg += ' (new image pulled)';
            }
            if (data.started) {
                msg += ' - Container is starting...';
            }
            showToast('success', msg);

            // Wait for container to be running if it was started
            if (data.started && newContainerId) {
                await waitForContainerRunning(containerName, 15000);
            }

            // Refresh the page to show new container
            setTimeout(() => location.reload(), 500);
        } else {
            showToast('error', data.error || 'Failed to update container');
        }
    } catch (error) {
        console.error('Error updating container:', error);
        showToast('error', 'Failed to update container');
    }
}

async function waitForContainerRunning(containerName, maxMs) {
    const start = Date.now();
    while ((Date.now() - start) < maxMs) {
        try {
            const resp = await fetch(`/api/containers?show_all=true`);
            const containers = await resp.json();
            const container = (containers || []).find(c => c.name === containerName);
            if (container && container.status === 'running') {
                return true;
            }
        } catch (e) {
            // ignore
        }
        await new Promise(r => setTimeout(r, 1000));
    }
    return false;
}

async function updateAllContainers() {
    // Count containers with updates
    const containersWithUpdates = [];
    document.querySelectorAll('.container-card[data-has-update="true"]').forEach(card => {
        containersWithUpdates.push({
            id: card.dataset.id,
            name: card.querySelector('.container-name')?.textContent?.replace(/\s*ⓘ\s*$/, '').trim() || card.dataset.id,
            projectId: card.dataset.projectId,
            projectName: card.dataset.projectName,
            service: card.dataset.composeService,
            canUpdate: card.dataset.canUpdate === 'true'
        });
    });

    // Also check table view
    if (containersWithUpdates.length === 0) {
        document.querySelectorAll('tr[data-has-update="true"]').forEach(row => {
            containersWithUpdates.push({
                id: row.dataset.id,
                name: row.querySelector('.cell-name strong')?.textContent?.trim() || row.dataset.id,
                projectId: row.dataset.projectId,
                projectName: row.dataset.projectName,
                service: row.dataset.composeService,
                canUpdate: row.dataset.canUpdate === 'true'
            });
        });
    }

    if (containersWithUpdates.length === 0) {
        showToast('info', 'No containers with updates available');
        return;
    }

    const names = containersWithUpdates.map(c => c.name).join('\n• ');
    if (!confirmAction(`Update ${containersWithUpdates.length} container(s)?\n\n• ${names}\n\nThis will pull latest images and recreate each container.`)) {
        return;
    }

    const btn = document.getElementById('updateAllBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span> Updating...';
    btn.disabled = true;

    showToast('info', `Updating ${containersWithUpdates.length} container(s)...`, 5000);

    try {
        const isRemote = document.querySelector('.dashboard')?.dataset.endpointKind === 'agent';
        if (isRemote) {
            const eligible = containersWithUpdates.filter(item => item.canUpdate && item.projectId && item.service);
            const groups = new Map();
            for (const item of eligible) {
                if (!groups.has(item.projectId)) groups.set(item.projectId, { name: item.projectName, services: [] });
                const services = groups.get(item.projectId).services;
                if (!services.includes(item.service)) services.push(item.service);
            }
            if (groups.size === 0) throw new Error('No updateable running Compose services were found.');
            for (const [projectId, group] of groups) {
                const job = await queueComposeAction(projectId, 'update', group.services);
                showComposeCompletion(job, `${group.name}: update`);
            }
            const skipped = containersWithUpdates.length - eligible.length;
            if (skipped) showToast('warning', `${skipped} standalone or stopped container(s) require Compose adoption or a manual review.`);
            setTimeout(() => location.reload(), 900);
            return;
        }
        const response = await fetch('/api/containers/update-all', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...csrfHeaders()
            },
            body: JSON.stringify({
                container_ids: containersWithUpdates.map(c => c.id)
            })
        });

        const data = await response.json();
        if (!response.ok || data.success === false) throw new Error(data.error || 'Update failed');

        if (data.updated > 0) {
            showToast('success', `Updated ${data.updated} container(s) - waiting for startup...`);
        }
        if (data.errors > 0) {
            showToast('warning', `${data.errors} container(s) failed to update`);
        }

        // Wait a bit for containers to start before refreshing
        await new Promise(r => setTimeout(r, 3000));

        // Refresh the page to show updated containers
        location.reload();

    } catch (error) {
        console.error('Error updating containers:', error);
        showToast('error', error.message || 'Failed to update containers');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Load stored updates on page load
document.addEventListener('DOMContentLoaded', function() {
    const allHosts = document.querySelector('.dashboard')?.dataset.allHosts === 'true';
    if (!allHosts) loadStoredUpdates();

    // Restore collapsed compose groups
    restoreCollapsedGroups();
});

// =============================================================================
// Container Detail Modal
// =============================================================================

let currentDetailContainerId = null;
let currentDetailContainerData = null;

async function openContainerDetail(containerId, containerName, containerImage, containerStatus, hasUpdate) {
    currentDetailContainerId = containerId;

    const modal = document.getElementById('containerDetailModal');
    const title = document.getElementById('containerDetailTitle');
    const content = document.getElementById('containerDetailContent');

    title.textContent = `📦 ${containerName}`;
    content.innerHTML = '<div class="loading" style="padding: 2rem; text-align: center;">Loading container details...</div>';
    modal.style.display = 'flex';

    try {
        // Fetch full container details
        const response = await fetch(`/api/container/${containerId}`);
        const data = await response.json();

        if (!data.success) {
            content.innerHTML = `<div class="no-data-msg" style="color: var(--danger-color);">Error: ${data.error || 'Failed to load container details'}</div>`;
            return;
        }

        currentDetailContainerData = data.container;
        renderContainerDetailModal(containerName, containerImage, containerStatus, hasUpdate === 'true', data.container);

    } catch (error) {
        console.error('Error loading container details:', error);
        content.innerHTML = '<div class="no-data-msg" style="color: var(--danger-color);">Failed to load container details</div>';
    }
}

function renderContainerDetailModal(name, image, status, hasUpdate, containerData) {
    const content = document.getElementById('containerDetailContent');
    const isRunning = status === 'running';
    const dashboard = document.querySelector('.dashboard');
    const isRemote = dashboard?.dataset.endpointKind === 'agent';
    const endpointId = dashboard?.dataset.endpointId;
    const management = containerData.management || {};

    // Build vulnerability summary
    let vulnHtml = '';
    const card = document.querySelector(`.container-card[data-id="${currentDetailContainerId}"]`);
    const row = document.querySelector(`tr[data-id="${currentDetailContainerId}"]`);
    const element = card || row;

    let vulnTotal = 0;
    if (element) {
        const vulnCritical = parseInt(element.dataset.vulnCritical) || 0;
        const vulnHigh = parseInt(element.dataset.vulnHigh) || 0;
        const vulnMedium = parseInt(element.dataset.vulnMedium) || 0;
        const vulnLow = parseInt(element.dataset.vulnLow) || 0;
        vulnTotal = parseInt(element.dataset.vulnTotal) || 0;

        if (vulnTotal > 0) {
            vulnHtml = `
                <div class="security-summary-card">
                    ${vulnCritical > 0 ? `<span class="security-stat critical">🔴 ${vulnCritical} Critical</span>` : ''}
                    ${vulnHigh > 0 ? `<span class="security-stat high">🟠 ${vulnHigh} High</span>` : ''}
                    ${vulnMedium > 0 ? `<span class="security-stat medium">🟡 ${vulnMedium} Medium</span>` : ''}
                    ${vulnLow > 0 ? `<span class="security-stat low">🟢 ${vulnLow} Low</span>` : ''}
                    <button class="btn btn-secondary btn-sm security-action-btn" onclick="closeContainerDetail(); showVulnerabilities('${escapeHtml(image)}', '${escapeHtml(name)}');">
                        🔍 View Details
                    </button>
                </div>
            `;
        } else if (element.dataset.vulnScanned === 'true') {
            vulnHtml = `
                <div class="security-summary-card">
                    <span class="security-stat clean">✓ No vulnerabilities found</span>
                    <button class="btn btn-secondary btn-sm security-action-btn" onclick="scanContainerFromDetail('${currentDetailContainerId}', '${escapeHtml(name)}');">
                        🔄 Rescan
                    </button>
                </div>
            `;
        } else {
            vulnHtml = `
                <div class="security-summary-card">
                    <span class="no-data-msg" style="padding: 0;">Not yet scanned</span>
                    <button class="btn btn-info btn-sm security-action-btn" onclick="scanContainerFromDetail('${currentDetailContainerId}', '${escapeHtml(name)}');">
                        🛡️ Scan Now
                    </button>
                </div>
            `;
        }
    }

    let ownershipValue = 'Standalone container';
    if (management.mode === 'compose') {
        ownershipValue = `Compose: <strong>${escapeHtml(management.project_name || '')}</strong> / ${escapeHtml(management.service || '')}`;
    } else if (management.mode === 'unadopted-compose') {
        ownershipValue = `Compose metadata found, but <strong>${escapeHtml(management.project_name || '')}</strong> is not adopted`;
    }

    let updateActionHtml = '';
    if (management.mode === 'compose') {
        if (management.can_update) {
            const label = hasUpdate ? '⬆️ Update service' : (vulnTotal > 0 ? '🛡️ Pull, redeploy & rescan' : '⬆️ Pull & redeploy service');
            updateActionHtml = `<button class="btn btn-success action-btn-primary" onclick="updateCurrentContainer()">${label}</button>`;
        } else {
            updateActionHtml = `<button class="btn btn-secondary" onclick="openCurrentContainerProject()">📦 Open owning project</button>`;
        }
    } else if (!isRemote) {
        updateActionHtml = hasUpdate
            ? `<button class="btn btn-success action-btn-primary" onclick="closeContainerDetail(); updateContainer('${currentDetailContainerId}', '${escapeHtml(name)}');">⬆️ Update to Latest</button>`
            : `<button class="btn btn-secondary" onclick="checkSingleContainerUpdate('${currentDetailContainerId}', '${escapeHtml(image)}');">🔍 Check for Updates</button>`;
    } else {
        updateActionHtml = `<button class="btn btn-secondary" onclick="location.href='/projects?endpoint_id=${encodeURIComponent(endpointId)}';">📦 Adopt into Compose</button>`;
    }

    // Build links section
    let linksHtml = '<p class="no-data-msg">No exposed ports</p>';
    const ports = containerData.ports || [];
    if (ports.length > 0) {
        linksHtml = '<div class="links-list">';
        for (const port of ports) {
            const url = port.url || `http://${window.location.hostname}:${port.host_port}`;
            linksHtml += `<a href="${url}" target="_blank" class="link-item" rel="noopener noreferrer">🔗 :${port.host_port} → :${port.container_port}</a>`;
        }
        linksHtml += '</div>';
    }

    // Build mounts info
    let mountsHtml = '';
    const mounts = containerData.mounts || [];
    if (mounts.length > 0) {
        mountsHtml = mounts.slice(0, 5).map(m => `${m.source || 'volume'} → ${m.destination}`).join('<br>');
        if (mounts.length > 5) {
            mountsHtml += `<br><span class="text-muted">... and ${mounts.length - 5} more</span>`;
        }
    } else {
        mountsHtml = '<span class="text-muted">None</span>';
    }

    // Build networks info
    let networksHtml = '';
    const networks = containerData.networks || [];
    if (networks.length > 0) {
        networksHtml = networks.join(', ');
    } else {
        networksHtml = '<span class="text-muted">None</span>';
    }

    content.innerHTML = `
        <!-- Container Info -->
        <div class="detail-section">
            <div class="detail-section-title">📋 Container Information</div>
            <div class="container-info-grid">
                <div class="info-item">
                    <span class="info-item-label">Status</span>
                    <span class="info-item-value">
                        <span class="status-badge status-${status}">${status}</span>
                        ${hasUpdate ? '<span class="update-badge" style="margin-left: 0.5rem;">⬆️ Update Available</span>' : ''}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-item-label">Image</span>
                    <span class="info-item-value mono">${escapeHtml(image)}</span>
                </div>
                <div class="info-item">
                    <span class="info-item-label">Container ID</span>
                    <span class="info-item-value mono">${currentDetailContainerId.substring(0, 12)}</span>
                </div>
                <div class="info-item">
                    <span class="info-item-label">Networks</span>
                    <span class="info-item-value">${networksHtml}</span>
                </div>
                <div class="info-item">
                    <span class="info-item-label">Ownership</span>
                    <span class="info-item-value">${ownershipValue}</span>
                </div>
            </div>
            ${management.mode === 'compose' ? `<button class="btn btn-secondary btn-sm" style="margin-top: .75rem" onclick="openCurrentContainerProject()">Open Compose project</button>` : ''}
        </div>

        <!-- Quick Actions -->
        <div class="detail-section">
            <div class="detail-section-title">⚡ Quick Actions</div>
            <div class="container-actions-grid">
                ${isRunning ? `
                    <button class="btn btn-warning" onclick="closeContainerDetail(); restartContainer('${currentDetailContainerId}', '${escapeHtml(name)}');">
                        🔄 Restart
                    </button>
                    <button class="btn btn-danger" onclick="closeContainerDetail(); stopContainer('${currentDetailContainerId}', '${escapeHtml(name)}');">
                        ⏹️ Stop
                    </button>
                ` : `
                    <button class="btn btn-success" onclick="closeContainerDetail(); startContainer('${currentDetailContainerId}', '${escapeHtml(name)}');">
                        ▶️ Start
                    </button>
                    ${management.can_remove !== false ? `<button class="btn btn-danger" onclick="closeContainerDetail(); removeContainer('${currentDetailContainerId}', '${escapeHtml(name)}');">
                        🗑️ Delete
                    </button>` : ''}
                `}
                ${!isRemote ? `<button class="btn btn-info" onclick="closeContainerDetail(); recreateContainer('${currentDetailContainerId}', '${escapeHtml(name)}');">
                    🔃 Recreate
                </button>` : ''}
                ${updateActionHtml}
            </div>
        </div>

        <!-- More Actions -->
        <div class="detail-section">
            <div class="detail-section-title">🔧 Tools</div>
            <div class="container-actions-grid">
                <button class="btn btn-secondary" onclick="closeContainerDetail(); openLogs('${currentDetailContainerId}', '${escapeHtml(name)}');">
                    📜 View Logs
                </button>
                <button class="btn btn-secondary" onclick="closeContainerDetail(); openInspect('${currentDetailContainerId}', '${escapeHtml(name)}');">
                    🔍 Inspect
                </button>
                ${isRunning && !isRemote ? `
                    <button class="btn btn-secondary" onclick="closeContainerDetail(); openExec('${currentDetailContainerId}', '${escapeHtml(name)}');">
                        💻 Execute Command
                    </button>
                ` : ''}
                ${isRunning ? `
                    <button class="btn btn-secondary" onclick="closeContainerDetail(); toggleStats('${currentDetailContainerId}');">
                        📊 Live Stats
                    </button>
                ` : ''}
            </div>
        </div>

        <!-- Security -->
        <div class="detail-section">
            <div class="detail-section-title">🛡️ Security</div>
            ${vulnHtml}
        </div>

        <!-- Links -->
        <div class="detail-section">
            <div class="detail-section-title">🔗 Exposed Ports</div>
            ${linksHtml}
        </div>

        <!-- Mounts Preview -->
        <div class="detail-section">
            <div class="detail-section-title">💾 Mounts</div>
            <div class="container-info-grid" style="grid-template-columns: 1fr;">
                <div class="info-item">
                    <span class="info-item-value mono" style="font-size: 0.8rem; line-height: 1.6;">${mountsHtml}</span>
                </div>
            </div>
        </div>
    `;
}

function openCurrentContainerProject() {
    const management = currentDetailContainerData?.management || {};
    const endpointId = document.querySelector('.dashboard')?.dataset.endpointId;
    const projectQuery = management.project_id ? `&project_id=${encodeURIComponent(management.project_id)}` : '';
    location.href = `/projects?endpoint_id=${encodeURIComponent(endpointId)}${projectQuery}`;
}

async function updateCurrentContainer() {
    const data = currentDetailContainerData;
    const management = data?.management || {};
    if (!management.can_update || !management.project_id || !management.service) {
        showToast('warning', management.update_reason || 'This container does not have a safe Compose update path.', 9000);
        return;
    }
    const name = data.name || currentDetailContainerId;
    if (!confirm(`Update ${name}?\n\nDockDash will pull the current image tag, force-redeploy only ${management.service}, verify project health, and refresh vulnerability evidence. Persistent volumes are preserved. Published fixes may require changing the image tag in the Compose project.`)) return;
    closeContainerDetail();
    showToast('info', `${name}: secure Compose update queued…`, 7000);
    try {
        const job = await queueComposeAction(management.project_id, 'update', [management.service]);
        showComposeCompletion(job, `${name}: update and verification`);
        setTimeout(() => location.reload(), 900);
    } catch (error) {
        showToast('error', `${name}: ${error.message}`, 12000);
    }
}

function closeContainerDetail(e) {
    if (e && e.target && e.target.id !== 'containerDetailModal') return;
    document.getElementById('containerDetailModal').style.display = 'none';
    currentDetailContainerId = null;
    currentDetailContainerData = null;
}

async function scanContainerFromDetail(containerId, containerName) {
    const content = document.getElementById('containerDetailContent');
    const securitySection = content.querySelector('.security-summary-card');
    if (securitySection) {
        securitySection.innerHTML = '<div class="loading">Scanning for vulnerabilities...</div>';
    }

    try {
        // Get the image from the card/row
        const card = document.querySelector(`.container-card[data-id="${containerId}"]`);
        const row = document.querySelector(`tr[data-id="${containerId}"]`);
        const element = card || row;
        const image = element?.dataset?.imageFull || element?.dataset?.image;

        if (!image) {
            showToast('error', 'Could not determine container image');
            return;
        }

        const response = await fetch(`/api/vulnerabilities/scan-container/${encodeURIComponent(containerId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ force: true })
        });
        const data = await response.json();

        if (data.success) {
            showToast('success', `Scan complete for ${containerName}`);
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast('error', data.error || 'Scan failed');
            if (securitySection) {
                securitySection.innerHTML = '<span class="no-data-msg" style="color: var(--danger-color);">Scan failed</span>';
            }
        }
    } catch (error) {
        console.error('Error scanning container:', error);
        showToast('error', 'Failed to scan container');
    }
}

async function checkSingleContainerUpdate(containerId, image) {
    showToast('info', 'Checking for updates...');

    try {
        const response = await fetch('/api/images/check-update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
            body: JSON.stringify({ image: image })
        });
        const data = await response.json();

        if (data.success) {
            if (data.has_update) {
                showToast('success', 'Update available! Refreshing...');
                setTimeout(() => location.reload(), 1000);
            } else {
                showToast('info', 'Container is already up to date');
            }
        } else {
            showToast('error', data.error || 'Failed to check for updates');
        }
    } catch (error) {
        console.error('Error checking for updates:', error);
        showToast('error', 'Failed to check for updates');
    }
}
