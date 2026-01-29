// Timer variables - initialized by inline script in HTML before this file loads
// Using var instead of let to allow hoisting and global scope assignment
var nextCheckSeconds = 0;
var nextHeartbeatSeconds = 0;
var pendingAction = null;
var pendingData = null;
var pendingSuccessMessage = null;
var pendingMaskedEmail = null;
var autoScrollEnabled = true;
var lastConsoleCount = 0;
var timerRefreshAttempts = 0;

function formatTime(seconds, showHours = false) {
    if (seconds <= 0) return showHours ? '00:00:00' : '00:00';
    
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    
    if (showHours || h > 0) {
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function updateTimers() {
    if (nextCheckSeconds > 0) nextCheckSeconds--;
    if (nextHeartbeatSeconds > 0) nextHeartbeatSeconds--;
    
    const checkElement = document.getElementById('timer-check');
    const heartbeatElement = document.getElementById('timer-heartbeat');
    
    if (checkElement) {
        checkElement.textContent = formatTime(nextCheckSeconds);
        // Visual indicator when timer is at 0 (may need refresh)
        if (nextCheckSeconds <= 0) {
            checkElement.classList.add('timer-expired');
        } else {
            checkElement.classList.remove('timer-expired');
        }
    }
    if (heartbeatElement) {
        heartbeatElement.textContent = formatTime(nextHeartbeatSeconds, true);
        if (nextHeartbeatSeconds <= 0) {
            heartbeatElement.classList.add('timer-expired');
        } else {
            heartbeatElement.classList.remove('timer-expired');
        }
    }
    
    // Auto-refresh timers if both are at 0 (server may have restarted)
    if (nextCheckSeconds <= 0 && nextHeartbeatSeconds <= 0) {
        timerRefreshAttempts++;
        if (timerRefreshAttempts >= 10 && timerRefreshAttempts % 30 === 0) {
            // Try to refresh timers every 30 seconds after initial 10 second wait
            refreshTimersFromServer();
        }
    } else {
        timerRefreshAttempts = 0;
    }
}

async function refreshTimersFromServer() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.config) {
            // Recalculate timer values from next_check and next_heartbeat
            const now = new Date();
            
            if (data.config.next_check) {
                const nextCheck = new Date(data.config.next_check);
                const checkDiff = Math.max(0, Math.floor((nextCheck - now) / 1000));
                if (checkDiff > 0) {
                    nextCheckSeconds = checkDiff;
                    console.log('Timer refreshed: next check in', checkDiff, 'seconds');
                }
            }
            
            if (data.config.next_heartbeat) {
                const nextHeartbeat = new Date(data.config.next_heartbeat);
                const heartbeatDiff = Math.max(0, Math.floor((nextHeartbeat - now) / 1000));
                if (heartbeatDiff > 0) {
                    nextHeartbeatSeconds = heartbeatDiff;
                    console.log('Timer refreshed: next heartbeat in', heartbeatDiff, 'seconds');
                }
            }
        }
    } catch (e) {
        console.log('Failed to refresh timers from server');
    }
}
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = { success: 'check-circle', error: 'x-circle', warning: 'exclamation-triangle' };
    toast.innerHTML = `
        <i class="bi bi-${icons[type]}"></i>
        <span class="toast-message">${message}</span>
    `;
    
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function openModal() {
    const modal = document.getElementById('password-modal');
    const input = document.getElementById('password-input');
    const error = document.getElementById('password-error');
    
    if (modal) modal.classList.add('show');
    if (input) {
        input.value = '';
        input.focus();
    }
    if (error) error.classList.remove('show');
}

function closeModal() {
    const modal = document.getElementById('password-modal');
    if (modal) modal.classList.remove('show');
    
    pendingAction = null;
    pendingData = null;
    pendingSuccessMessage = null;
}

function openShowEmailModal(masked) {
    pendingMaskedEmail = masked;
    
    const modal = document.getElementById('show-email-modal');
    const input = document.getElementById('show-email-password');
    const error = document.getElementById('show-email-error');
    
    if (modal) modal.classList.add('show');
    if (input) {
        input.value = '';
        input.focus();
    }
    if (error) error.classList.remove('show');
}

function closeShowEmailModal() {
    const modal = document.getElementById('show-email-modal');
    if (modal) modal.classList.remove('show');
    
    pendingMaskedEmail = null;
}

function secureAction(endpoint, successMessage, data = {}) {
    pendingAction = endpoint;
    pendingData = data;
    pendingSuccessMessage = successMessage;
    openModal();
}

async function submitPassword() {
    const passwordInput = document.getElementById('password-input');
    const errorElement = document.getElementById('password-error');
    
    if (!passwordInput || !pendingAction) return;
    
    const password = passwordInput.value;
    
    if (!password) {
        if (errorElement) {
            errorElement.textContent = 'Please enter password';
            errorElement.classList.add('show');
        }
        return;
    }
    
    try {
        const response = await fetch(pendingAction, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...pendingData, password })
        });
        
        const result = await response.json();
        
        if (response.status === 401) {
            if (errorElement) {
                errorElement.textContent = 'Invalid password. Please try again.';
                errorElement.classList.add('show');
            }
            return;
        }
        
        if (response.status === 429) {
            showToast('Too many requests. Please wait.', 'warning');
            closeModal();
            return;
        }
        
        closeModal();
        
        if (result.success) {
            showToast(result.message || pendingSuccessMessage, 'success');
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast(result.message || 'Action failed', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('Network error', 'error');
        closeModal();
    }
}

function toggleFeature(feature, checkbox) {
    pendingAction = `/api/toggle/${feature}`;
    pendingData = {};
    pendingSuccessMessage = `${feature} toggled!`;
    
    checkbox.checked = !checkbox.checked;
    openModal();
}

function toggleRecipient(email) {
    secureAction(`/api/toggle-recipient/${encodeURIComponent(email)}`, 'Recipient toggled!');
}

function showFullEmail(masked) {
    openShowEmailModal(masked);
}

async function submitShowEmail() {
    const passwordInput = document.getElementById('show-email-password');
    const errorElement = document.getElementById('show-email-error');
    
    if (!passwordInput) return;
    
    const password = passwordInput.value;
    
    if (!password) {
        if (errorElement) {
            errorElement.textContent = 'Please enter password';
            errorElement.classList.add('show');
        }
        return;
    }
    
    try {
        const response = await fetch('/api/reveal-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ masked: pendingMaskedEmail, password })
        });
        
        const result = await response.json();
        
        if (response.status === 401) {
            if (errorElement) {
                errorElement.textContent = 'Invalid password. Please try again.';
                errorElement.classList.add('show');
            }
            return;
        }
        
        if (result.success) {
            alert('Email: ' + result.email);
            closeShowEmailModal();
        } else {
            if (errorElement) {
                errorElement.textContent = 'Failed to reveal email';
                errorElement.classList.add('show');
            }
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('Network error', 'error');
        closeShowEmailModal();
    }
}

// Initialize timers and polling
document.addEventListener('DOMContentLoaded', function() {
    // Start timer updates
    setInterval(updateTimers, 1000);
    updateTimers();
    
    // Periodic status polling
    setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            const checksElement = document.getElementById('total-checks');
            const sentElement = document.getElementById('emails-sent');
            
            if (checksElement && data.config) {
                checksElement.textContent = data.config.total_checks;
            }
            if (sentElement && data.config) {
                sentElement.textContent = data.config.emails_sent;
            }
        } catch (e) {
            console.log('Failed to update status');
        }
    }, 30000);
    
    // Initialize console and diagnostics polling
    updateConsoleAndDiagnostics();
    setInterval(updateConsoleAndDiagnostics, 5000);
    
    // Set auto-scroll button state
    updateAutoScrollButton();
});

// ===== SYSTEM CONSOLE FUNCTIONS =====
function toggleAutoScroll() {
    autoScrollEnabled = !autoScrollEnabled;
    updateAutoScrollButton();
}

function updateAutoScrollButton() {
    const btn = document.getElementById('auto-scroll-btn');
    if (btn) {
        if (autoScrollEnabled) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
}

async function updateConsoleAndDiagnostics() {
    try {
        const response = await fetch('/api/console');
        const data = await response.json();
        
        // Update terminal output
        updateTerminal(data.console);
        
        // Update diagnostics
        updateDiagnostics(data.diagnostics);
        
    } catch (e) {
        console.log('Failed to update console/diagnostics');
    }
}

function updateTerminal(consoleLogs) {
    const terminal = document.getElementById('terminal-output');
    if (!terminal || !consoleLogs) return;
    
    // Only update if there are new logs
    if (consoleLogs.length === lastConsoleCount) return;
    lastConsoleCount = consoleLogs.length;
    
    // Build terminal HTML (logs are already in reverse order from server)
    const html = consoleLogs.slice(0, 50).reverse().map(log => {
        const time = log.time ? log.time.split(' ')[1] || log.time : '--:--:--';
        return `
            <div class="terminal-line ${log.type}">
                <span class="term-time">${time}</span>
                <span class="term-type ${log.type}">${log.type}</span>
                <span class="term-msg">${escapeHtml(log.msg)}</span>
            </div>
        `;
    }).join('');
    
    terminal.innerHTML = html || '<div class="terminal-line welcome"><span class="term-time">--:--:--</span><span class="term-msg">Waiting for activity...</span></div>';
    
    // Auto-scroll to bottom
    if (autoScrollEnabled) {
        terminal.scrollTop = terminal.scrollHeight;
    }
}

function updateDiagnostics(diag) {
    if (!diag) return;
    
    // Response time
    const responseTime = document.getElementById('diag-response-time');
    if (responseTime) {
        const ms = diag.last_response_time_ms || 0;
        responseTime.textContent = ms > 0 ? `${ms}ms` : '--';
        responseTime.className = 'diag-value' + (ms > 2000 ? ' warning' : ms > 5000 ? ' error' : ' good');
    }
    
    // Status code
    const statusCode = document.getElementById('diag-status-code');
    if (statusCode) {
        const code = diag.last_status_code;
        statusCode.textContent = code || '--';
        statusCode.className = 'diag-value' + (code === 200 ? ' good' : code ? ' error' : '');
    }
    
    // Response size
    const responseSize = document.getElementById('diag-response-size');
    if (responseSize) {
        const bytes = diag.last_response_size || 0;
        responseSize.textContent = bytes > 0 ? formatBytes(bytes) : '--';
    }
    
    // Events count
    const eventsCount = document.getElementById('diag-events-count');
    if (eventsCount) {
        eventsCount.textContent = diag.last_events_count !== undefined ? diag.last_events_count : '--';
    }
    
    // Total calls
    const totalCalls = document.getElementById('diag-total-calls');
    if (totalCalls) {
        totalCalls.textContent = diag.total_api_calls || 0;
    }
    
    // Failed calls
    const failedCalls = document.getElementById('diag-failed-calls');
    if (failedCalls) {
        const failed = diag.failed_api_calls || 0;
        failedCalls.textContent = failed;
        failedCalls.className = 'diag-value' + (failed > 0 ? ' error' : ' good');
    }
    
    // Avg response time
    const avgTime = document.getElementById('diag-avg-time');
    if (avgTime) {
        const avg = diag.avg_response_time_ms || 0;
        avgTime.textContent = avg > 0 ? `${avg}ms` : '--';
    }
    
    // Last error
    const lastError = document.getElementById('diag-last-error');
    if (lastError) {
        lastError.textContent = diag.last_error || 'None';
        lastError.className = 'diag-value error-text-sm' + (diag.last_error ? ' error' : '');
    }
    
    // API status badge
    const statusBadge = document.getElementById('api-status-badge');
    if (statusBadge) {
        if (diag.last_status_code === 200) {
            statusBadge.textContent = 'Connected';
            statusBadge.className = 'badge success';
        } else if (diag.last_error) {
            statusBadge.textContent = 'Error';
            statusBadge.className = 'badge error';
        } else {
            statusBadge.textContent = 'Waiting...';
            statusBadge.className = 'badge warning';
        }
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
