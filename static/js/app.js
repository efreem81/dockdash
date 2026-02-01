/* =============================================================================
    DockDash - JavaScript
   ============================================================================= */

// Toast notification system
function showToast(type, message) {
    // Create container if it doesn't exist
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Auto-refresh containers every 30 seconds (only on dashboard)
if (window.location.pathname === '/dashboard') {
    setInterval(() => {
        // Only refresh if user hasn't interacted recently
        if (!document.hidden) {
            // Silent refresh - could implement AJAX refresh here
            // For now, we'll let users manually refresh
        }
    }, 30000);
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Press 'R' to refresh on dashboard
    if (e.key === 'r' && !e.ctrlKey && !e.metaKey && 
        document.activeElement.tagName !== 'INPUT' &&
        document.activeElement.tagName !== 'TEXTAREA') {
        if (window.location.pathname === '/dashboard') {
            e.preventDefault();
            location.reload();
        }
    }
});

// Confirm before dangerous actions
document.querySelectorAll('[data-confirm]').forEach(element => {
    element.addEventListener('click', (e) => {
        if (!confirm(element.dataset.confirm)) {
            e.preventDefault();
        }
    });
});

// Copy URL to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('success', 'URL copied to clipboard!');
    }).catch(() => {
        showToast('error', 'Failed to copy URL');
    });
}

// Initialize tooltips (if any)
document.querySelectorAll('[title]').forEach(element => {
    // Add tooltip functionality if needed
});

// Form validation feedback
document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="loading">⏳</span> Processing...';
            
            // Re-enable after 5 seconds in case of error
            setTimeout(() => {
                submitBtn.disabled = false;
                submitBtn.innerHTML = submitBtn.dataset.originalText || 'Submit';
            }, 5000);
        }
    });
});

// Store original button text
document.querySelectorAll('button[type="submit"]').forEach(btn => {
    btn.dataset.originalText = btn.innerHTML;
});

console.log('⛵ DockDash loaded successfully!');
