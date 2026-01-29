// Timer variables - these are initialized with template data in HTML
let nextCheckSeconds;
let nextHeartbeatSeconds;
let pendingAction = null;
let pendingData = null;
let pendingSuccessMessage = null;
let pendingMaskedEmail = null;

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
    
    if (checkElement) checkElement.textContent = formatTime(nextCheckSeconds);
    if (heartbeatElement) heartbeatElement.textContent = formatTime(nextHeartbeatSeconds, true);
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
});
