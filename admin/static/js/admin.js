// admin/static/js/admin.js

// Admin panel JavaScript functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // JSON field validation
    const jsonTextareas = document.querySelectorAll('textarea[data-type="json"]');
    jsonTextareas.forEach(textarea => {
        textarea.addEventListener('blur', function() {
            validateJSON(this);
        });
    });

    // Form submission loading state
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
            }
        });
    });

    // Search functionality
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                performSearch(this.value);
            }, 500);
        });
    }
});

// JSON validation function
function validateJSON(textarea) {
    try {
        if (textarea.value.trim()) {
            JSON.parse(textarea.value);
            textarea.classList.remove('is-invalid');
            textarea.classList.add('is-valid');
            
            // Remove any existing error message
            const errorMsg = textarea.parentNode.querySelector('.json-error');
            if (errorMsg) {
                errorMsg.remove();
            }
        } else {
            textarea.classList.remove('is-invalid', 'is-valid');
        }
    } catch (e) {
        textarea.classList.remove('is-valid');
        textarea.classList.add('is-invalid');
        
        // Show error message
        let errorMsg = textarea.parentNode.querySelector('.json-error');
        if (!errorMsg) {
            errorMsg = document.createElement('div');
            errorMsg.className = 'json-error text-danger small mt-1';
            textarea.parentNode.appendChild(errorMsg);
        }
        errorMsg.textContent = 'Invalid JSON: ' + e.message;
    }
}

// Search functionality
function performSearch(query) {
    const currentUrl = new URL(window.location);
    if (query) {
        currentUrl.searchParams.set('search', query);
    } else {
        currentUrl.searchParams.delete('search');
    }
    currentUrl.searchParams.delete('page'); // Reset to first page
    window.location.href = currentUrl.toString();
}

// Confirm delete with better UX
function confirmDelete(itemName, deleteUrl) {
    if (confirm(`Are you sure you want to delete "${itemName}"? This action cannot be undone.`)) {
        // Show loading state
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center';
        loadingDiv.style.backgroundColor = 'rgba(0,0,0,0.5)';
        loadingDiv.style.zIndex = '9999';
        loadingDiv.innerHTML = '<div class="spinner-border text-light" role="status"><span class="visually-hidden">Deleting...</span></div>';
        document.body.appendChild(loadingDiv);
        
        // Create and submit form
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = deleteUrl;
        document.body.appendChild(form);
        form.submit();
    }
}

// Format timestamps
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString();
}

// Auto-resize textareas
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

// Initialize auto-resize for all textareas
document.addEventListener('DOMContentLoaded', function() {
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        textarea.addEventListener('input', function() {
            autoResizeTextarea(this);
        });
        // Initial resize
        autoResizeTextarea(textarea);
    });
});

// Copy to clipboard functionality
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        // Show success message
        const toast = document.createElement('div');
        toast.className = 'position-fixed top-0 end-0 p-3';
        toast.style.zIndex = '9999';
        toast.innerHTML = `
            <div class="toast show" role="alert">
                <div class="toast-body bg-success text-white">
                    <i class="fas fa-check me-2"></i>
                    Copied to clipboard!
                </div>
            </div>
        `;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    });
}
