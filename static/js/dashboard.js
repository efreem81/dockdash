/* =============================================================================
   DockDash - Dashboard Page JavaScript
   ============================================================================= */

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
            id: card.dataset.id
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
    
    // Initial render
    filteredContainers = [...allContainers];
    applySort();
    renderContainers();

    // Probe visible links to upgrade http -> https where appropriate
    scheduleProbeVisibleLinks();
    
    // Setup search input
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', debounce(function() {
        searchTerm = this.value.toLowerCase().trim();
        document.getElementById('searchClear').style.display = searchTerm ? 'block' : 'none';
        currentPage = 1;
        filterContainers();
        renderContainers();
    }, 200));
    
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
    
    // Show all toggle
    const showAllToggle = document.getElementById('showAllToggle');
    if (showAllToggle) {
        showAllToggle.addEventListener('change', function() {
            const showAll = this.checked;
            window.location.href = '/dashboard?show_all=' + showAll;
        });
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
            c.id.includes(searchTerm)
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
    const visibleIds = new Set(pagedContainers.map(c => c.id));
    
    // Render card view
    const cardGrid = document.getElementById('containerGrid');
    const cards = cardGrid.querySelectorAll('.container-card[data-id]');
    cards.forEach(card => {
        card.style.display = visibleIds.has(card.dataset.id) ? '' : 'none';
    });
    
    // Render table view
    const tableBody = document.getElementById('tableBody');
    if (tableBody) {
        const rows = tableBody.querySelectorAll('tr[data-id]');
        rows.forEach(row => {
            row.style.display = visibleIds.has(row.dataset.id) ? '' : 'none';
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
            const card = cardGrid.querySelector(`.container-card[data-id="${c.id}"]`);
            if (card) cardGrid.appendChild(card);
        });
    } else if (tableBody) {
        pagedContainers.forEach(c => {
            const row = tableBody.querySelector(`tr[data-id="${c.id}"]`);
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
    if (!confirm(`Are you sure you want to restart ${name}?`)) return;
    
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
    if (!confirm(`Are you sure you want to stop ${name}?`)) return;
    
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
    if (!confirm(`Are you sure you want to start ${name}?`)) return;
    
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
    if (!confirm(`Are you sure you want to remove container ${name}? This cannot be undone.`)) return;
    
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
    if (!confirm(`Recreate container ${name}? This will:\n• Pull the latest image\n• Stop and remove the current container\n• Create a new container with the same config\n• Rescan for vulnerabilities\n\nContinue?`)) return;
    
    showToast('info', `Recreating ${name}...`);
    
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
    const showAll = document.getElementById('showAllToggle')?.checked ? 'true' : 'false';
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

async function checkAllImageUpdates() {
    const btn = document.getElementById('checkUpdatesBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Checking...';
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
    
    // Update all badges in card view
    document.querySelectorAll('.container-card .update-badge').forEach(badge => {
        const image = badge.dataset.image;
        const result = results[image];
        if (result && result.has_update === true) {
            badge.style.display = 'inline-flex';
            badge.title = `Update available!\nLocal: ${result.local_digest?.substring(0, 20)}...\nRemote: ${result.remote_digest?.substring(0, 20)}...`;
            updateCount++;
        } else if (result && result.has_update === false) {
            badge.style.display = 'none';
            badge.title = 'Up to date';
        } else {
            badge.style.display = 'none';
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
    
    // Update table view badges
    document.querySelectorAll('.container-table .image-value').forEach(span => {
        const image = span.dataset.image;
        const result = results[image];
        const badge = span.querySelector('.update-badge');
        if (badge) {
            if (result && result.has_update === true) {
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
    if (updateCount > 0) {
        countContainer.style.display = 'inline';
        countValue.textContent = updateCount;
        showToast('info', `${updateCount} image update${updateCount > 1 ? 's' : ''} available`);
    } else {
        countContainer.style.display = 'none';
        showToast('success', 'All images are up to date');
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

function showInspectTab(tab) {
    document.querySelectorAll('.inspect-tabs .tab-btn').forEach(btn => btn.classList.remove('active'));
    if (event && event.target) event.target.classList.add('active');
    
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
