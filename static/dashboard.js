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
        
        // Use pre-calculated seconds from server (more accurate)
        if (data.next_check_seconds !== undefined && data.next_check_seconds > 0) {
            nextCheckSeconds = data.next_check_seconds;
            console.log('Timer refreshed from server: next check in', nextCheckSeconds, 'seconds');
        }
        
        if (data.next_heartbeat_seconds !== undefined && data.next_heartbeat_seconds > 0) {
            nextHeartbeatSeconds = data.next_heartbeat_seconds;
            console.log('Timer refreshed from server: next heartbeat in', nextHeartbeatSeconds, 'seconds');
        }
        
        // Update stats while we're at it
        if (data.config) {
            const checksElement = document.getElementById('total-checks');
            const sentElement = document.getElementById('emails-sent');
            
            if (checksElement) checksElement.textContent = data.config.total_checks;
            if (sentElement) sentElement.textContent = data.config.emails_sent;
        }
    } catch (e) {
        console.log('Failed to refresh timers from server:', e);
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

// ===== SETTINGS MODAL =====
function openSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.add('show');
}

function closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.remove('show');
}

async function saveSettings() {
    const heartbeatEnabled = document.getElementById('settings-heartbeat')?.checked ?? true;
    const dailySummaryEnabled = document.getElementById('settings-daily-summary')?.checked ?? true;
    const trackerEnabled = document.getElementById('settings-tracker')?.checked ?? true;
    
    // Get password first
    const password = prompt('Enter admin password to save settings:');
    if (!password) {
        showToast('Settings not saved - password required', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                password: password,
                heartbeat_enabled: heartbeatEnabled,
                daily_summary_enabled: dailySummaryEnabled,
                tracker_enabled: trackerEnabled
            })
        });
        
        const result = await response.json();
        
        if (response.status === 401) {
            showToast('Invalid password', 'error');
            return;
        }
        
        if (response.status === 429) {
            showToast('Too many requests. Please wait.', 'warning');
            return;
        }
        
        if (result.success) {
            showToast('Settings saved successfully!', 'success');
            closeSettingsModal();
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast(result.message || 'Failed to save settings', 'error');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showToast('Network error', 'error');
    }
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
    // Immediately refresh timers from server on page load
    refreshTimersFromServer();
    
    // Start timer updates
    setInterval(updateTimers, 1000);
    updateTimers();
    
    // Refresh timers from server every 15 seconds to stay in sync
    setInterval(refreshTimersFromServer, 15000);
    
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
        // Use short time format (HH:MM:SS AM/PM)
        const time = log.time_short || log.time || '--:--:--';
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

// ===== STATISTICS CHART =====
var statsChart = null;
var currentChartView = 'daily';

function initStatsChart() {
    console.log('[DEBUG] Initializing stats chart...');
    const ctx = document.getElementById('statsChart');
    if (!ctx) {
        console.log('[DEBUG] Chart canvas not found');
        return;
    }
    
    statsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Checks',
                    data: [],
                    backgroundColor: 'rgba(99, 102, 241, 0.7)',
                    borderColor: 'rgba(99, 102, 241, 1)',
                    borderWidth: 1
                },
                {
                    label: 'New Events',
                    data: [],
                    backgroundColor: 'rgba(34, 197, 94, 0.7)',
                    borderColor: 'rgba(34, 197, 94, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Emails Sent',
                    data: [],
                    backgroundColor: 'rgba(245, 158, 11, 0.7)',
                    borderColor: 'rgba(245, 158, 11, 1)',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#8888a0',
                        usePointStyle: true,
                        padding: 20
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(42, 42, 58, 0.5)' },
                    ticks: { color: '#8888a0' }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(42, 42, 58, 0.5)' },
                    ticks: { color: '#8888a0', stepSize: 1 }
                }
            }
        }
    });
    
    loadChartData('daily');
}

async function loadChartData(view) {
    console.log('[DEBUG] Loading chart data for view:', view);
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        if (view === 'daily') {
            statsChart.data.labels = data.daily.labels;
            statsChart.data.datasets[0].data = data.daily.checks;
            statsChart.data.datasets[1].data = data.daily.new_events;
            statsChart.data.datasets[2].data = data.daily.emails_sent;
        } else {
            statsChart.data.labels = data.hourly.labels;
            statsChart.data.datasets[0].data = data.hourly.checks;
            statsChart.data.datasets[1].data = data.hourly.new_events;
            statsChart.data.datasets[2].data = []; // No emails in hourly view
        }
        
        statsChart.update();
        console.log('[DEBUG] Chart updated successfully');
    } catch (e) {
        console.error('[DEBUG] Failed to load chart data:', e);
    }
}

function switchChartView(view) {
    currentChartView = view;
    
    // Update button states
    document.getElementById('chart-daily-btn').classList.toggle('active', view === 'daily');
    document.getElementById('chart-hourly-btn').classList.toggle('active', view === 'hourly');
    
    loadChartData(view);
}

// ===== EVENT SEARCH =====
function searchEvents() {
    const query = document.getElementById('event-search').value.toLowerCase().trim();
    const events = document.querySelectorAll('#past-events-list .event-item');
    const clearBtn = document.getElementById('search-clear-btn');
    const resultsInfo = document.getElementById('search-results-info');
    
    clearBtn.style.display = query ? 'flex' : 'none';
    
    let matchCount = 0;
    events.forEach(event => {
        const title = event.dataset.title || '';
        if (title.includes(query) || !query) {
            event.style.display = 'flex';
            matchCount++;
        } else {
            event.style.display = 'none';
        }
    });
    
    if (query && events.length > 0) {
        resultsInfo.style.display = 'block';
        resultsInfo.textContent = `Found ${matchCount} event(s) matching "${query}"`;
    } else {
        resultsInfo.style.display = 'none';
    }
    
    console.log('[DEBUG] Event search:', query, '- Found:', matchCount);
}

function clearEventSearch() {
    document.getElementById('event-search').value = '';
    searchEvents();
}

// ===== THEME TOGGLE =====
function toggleTheme() {
    const isDark = document.getElementById('settings-theme').checked;
    const theme = isDark ? 'dark' : 'light';
    
    document.body.className = 'theme-' + theme;
    document.documentElement.setAttribute('data-theme', theme);
    
    // Save to server
    fetch('/api/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: theme })
    }).then(() => {
        console.log('[DEBUG] Theme saved:', theme);
    });
    
    // Update chart colors if exists
    if (statsChart) {
        const textColor = isDark ? '#8888a0' : '#5a5a70';
        const gridColor = isDark ? 'rgba(42, 42, 58, 0.5)' : 'rgba(200, 200, 210, 0.5)';
        statsChart.options.scales.x.ticks.color = textColor;
        statsChart.options.scales.y.ticks.color = textColor;
        statsChart.options.scales.x.grid.color = gridColor;
        statsChart.options.scales.y.grid.color = gridColor;
        statsChart.options.plugins.legend.labels.color = textColor;
        statsChart.update();
    }
}

// ===== BROWSER NOTIFICATIONS =====
var notificationsEnabled = false;
var lastNotificationCheck = '';

function checkNotificationPermission() {
    if (!('Notification' in window)) {
        console.log('[DEBUG] Browser does not support notifications');
        updateNotificationStatus('Not supported');
        return;
    }
    
    if (Notification.permission === 'granted') {
        notificationsEnabled = true;
        updateNotificationStatus('Enabled');
        startNotificationPolling();
    } else if (Notification.permission === 'denied') {
        updateNotificationStatus('Blocked');
    } else {
        updateNotificationStatus('Click to enable');
    }
}

function toggleNotifications() {
    const checkbox = document.getElementById('settings-notifications');
    
    if (!('Notification' in window)) {
        showToast('Browser does not support notifications', 'warning');
        checkbox.checked = false;
        return;
    }
    
    if (checkbox.checked) {
        Notification.requestPermission().then(permission => {
            if (permission === 'granted') {
                notificationsEnabled = true;
                updateNotificationStatus('Enabled');
                showToast('Notifications enabled!', 'success');
                
                // Send test notification
                new Notification('🏪 Dubai Flea Market Tracker', {
                    body: 'Notifications are now enabled! You will be alerted when new events are found.',
                    icon: '🏪'
                });
                
                startNotificationPolling();
                saveNotificationSetting(true);
            } else {
                checkbox.checked = false;
                updateNotificationStatus('Blocked');
                showToast('Notification permission denied', 'warning');
            }
        });
    } else {
        notificationsEnabled = false;
        updateNotificationStatus('Disabled');
        saveNotificationSetting(false);
    }
}

function updateNotificationStatus(status) {
    const statusEl = document.getElementById('notification-status');
    if (statusEl) statusEl.textContent = status;
}

function saveNotificationSetting(enabled) {
    fetch('/api/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notifications_enabled: enabled })
    });
}

function startNotificationPolling() {
    if (!notificationsEnabled) return;
    
    lastNotificationCheck = new Date().toISOString();
    
    setInterval(async () => {
        if (!notificationsEnabled) return;
        
        try {
            const response = await fetch(`/api/notification-check?since=${encodeURIComponent(lastNotificationCheck)}`);
            const data = await response.json();
            
            if (data.count > 0) {
                console.log('[DEBUG] New events for notification:', data.count);
                
                data.new_events.forEach(event => {
                    new Notification('🆕 New Dubai Flea Market Event!', {
                        body: event.title,
                        icon: '🏪',
                        tag: 'event-' + event.id
                    });
                });
            }
            
            lastNotificationCheck = data.last_check || new Date().toISOString();
        } catch (e) {
            console.error('[DEBUG] Notification poll failed:', e);
        }
    }, 30000); // Check every 30 seconds
}

// ===== TEST SINGLE EMAIL MODAL =====
function openTestSingleEmailModal() {
    const modal = document.getElementById('test-single-email-modal');
    const password = document.getElementById('test-email-password');
    const error = document.getElementById('test-email-error');
    
    if (modal) modal.classList.add('show');
    if (password) password.value = '';
    if (error) error.classList.remove('show');
}

function closeTestSingleEmailModal() {
    const modal = document.getElementById('test-single-email-modal');
    if (modal) modal.classList.remove('show');
}

async function submitTestSingleEmail() {
    const email = document.getElementById('test-email-select').value;
    const password = document.getElementById('test-email-password').value;
    const error = document.getElementById('test-email-error');
    
    if (!password) {
        error.textContent = 'Please enter password';
        error.classList.add('show');
        return;
    }
    
    console.log('[DEBUG] Testing single email to:', email);
    
    try {
        const response = await fetch('/api/test-single-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        
        const result = await response.json();
        
        if (response.status === 401) {
            error.textContent = 'Invalid password';
            error.classList.add('show');
            return;
        }
        
        if (result.success) {
            showToast(result.message, 'success');
            closeTestSingleEmailModal();
        } else {
            error.textContent = result.message || 'Failed to send';
            error.classList.add('show');
        }
    } catch (e) {
        console.error('[DEBUG] Test email error:', e);
        showToast('Network error', 'error');
    }
}

// ===== LIVE EVENTS SEARCH =====
function searchLiveEvents() {
    const query = document.getElementById('live-event-search').value.toLowerCase().trim();
    const events = document.querySelectorAll('#live-events-list .event-card');
    const clearBtn = document.getElementById('live-search-clear-btn');
    const resultsInfo = document.getElementById('live-search-results-info');
    
    clearBtn.style.display = query ? 'flex' : 'none';
    
    let matchCount = 0;
    events.forEach(event => {
        const title = event.dataset.title || '';
        if (title.includes(query) || !query) {
            event.style.display = 'block';
            matchCount++;
        } else {
            event.style.display = 'none';
        }
    });
    
    if (query && events.length > 0) {
        resultsInfo.style.display = 'block';
        resultsInfo.textContent = `Found ${matchCount} event(s) matching "${query}"`;
    } else {
        resultsInfo.style.display = 'none';
    }
    
    console.log('[DEBUG] Live event search:', query, '- Found:', matchCount);
}

function clearLiveEventSearch() {
    document.getElementById('live-event-search').value = '';
    searchLiveEvents();
}

// ===== TEST NEW EVENT MODAL (Real Email Test) =====
function openTestNewEventModal() {
    const modal = document.getElementById('test-new-event-modal');
    const password = document.getElementById('test-new-event-password');
    const error = document.getElementById('test-new-event-error');
    
    if (modal) modal.classList.add('show');
    if (password) password.value = '';
    if (error) error.classList.remove('show');
    
    console.log('[DEBUG] Test new event modal opened');
}

function closeTestNewEventModal() {
    const modal = document.getElementById('test-new-event-modal');
    if (modal) modal.classList.remove('show');
}

async function submitTestNewEvent() {
    const password = document.getElementById('test-new-event-password').value;
    const error = document.getElementById('test-new-event-error');
    
    if (!password) {
        error.textContent = 'Please enter admin password';
        error.classList.add('show');
        return;
    }
    
    console.log('[DEBUG] Triggering test new event notification...');
    
    try {
        const response = await fetch('/api/test-new-event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        
        const result = await response.json();
        
        if (response.status === 401) {
            error.textContent = 'Invalid password';
            error.classList.add('show');
            return;
        }
        
        if (result.success) {
            showToast(result.message, 'success');
            closeTestNewEventModal();
            // Refresh page after a short delay to see the changes
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            error.textContent = result.message || 'Failed to trigger test';
            error.classList.add('show');
        }
    } catch (e) {
        console.error('[DEBUG] Test new event error:', e);
        showToast('Network error', 'error');
    }
}

