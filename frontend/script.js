/**
 * ====================================================================
 * CLOUD-BASED FILE STORAGE AND SHARING SYSTEM - CLIENT SCRIPT
 * Vanilla JavaScript managing Authentication, Drag-and-Drop Upload,
 * Progress Bar, File Explorer, Sharing Modal, and Toast Feedback.
 * ====================================================================
 */

// Determine API base URL dynamically
const API_BASE_URL = (window.location.port === "5000" || window.location.port === "8000")
  ? window.location.origin
  : "http://127.0.0.1:5000";

// ====================================================================
// AUTHENTICATION & SESSION MANAGEMENT
// ====================================================================

const Auth = {
  TOKEN_KEY: "cloud_storage_auth_token",
  USER_KEY: "cloud_storage_user_profile",

  setSession(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  getUser() {
    try {
      const userStr = localStorage.getItem(this.USER_KEY);
      return userStr ? JSON.parse(userStr) : null;
    } catch (e) {
      return null;
    }
  },

  isAuthenticated() {
    return !!this.getToken();
  },

  clearSession() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },

  logout() {
    fetch(`${API_BASE_URL}/logout`, { method: "POST" }).catch(() => {});
    this.clearSession();
    window.location.href = "login.html";
  },

  requireAuth() {
    if (!this.isAuthenticated()) {
      window.location.href = "login.html";
    }
  },

  redirectIfAuthenticated() {
    if (this.isAuthenticated()) {
      window.location.href = "dashboard.html";
    }
  }
};

// ====================================================================
// TOAST NOTIFICATION SYSTEM
// ====================================================================

function showToast(message, type = "info", duration = 3800) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const icons = {
    success: "✓",
    error: "✕",
    warning: "⚠",
    info: "ℹ"
  };

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span style="font-weight: bold; font-size: 1.1rem;">${icons[type] || "•"}</span>
    <span style="flex: 1;">${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "fadeOut 0.35s forwards";
    setTimeout(() => toast.remove(), 350);
  }, duration);
}

// ====================================================================
// HELPER UTILITIES
// ====================================================================

function formatBytes(bytes, decimals = 2) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

function formatDate(isoString) {
  if (!isoString) return "Just now";
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch (e) {
    return isoString;
  }
}

function getCategoryIconInfo(category) {
  const cat = (category || "").toLowerCase();
  switch (cat) {
    case "pdf":
      return { icon: "📄", className: "icon-pdf", label: "PDF" };
    case "image":
      return { icon: "🖼️", className: "icon-img", label: "Image" };
    case "document":
      return { icon: "📝", className: "icon-doc", label: "Document" };
    case "archive":
      return { icon: "📦", className: "icon-zip", label: "Archive" };
    case "video":
      return { icon: "🎬", className: "icon-doc", label: "Video" };
    case "audio":
      return { icon: "🎵", className: "icon-img", label: "Audio" };
    default:
      return { icon: "📁", className: "icon-doc", label: "File" };
  }
}

// ====================================================================
// AUTHENTICATION PAGES (SIGNUP & LOGIN)
// ====================================================================

function initAuthPages() {
  // 1. Password Visibility Toggle
  document.querySelectorAll(".password-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = btn.parentElement.querySelector("input");
      if (input.type === "password") {
        input.type = "text";
        btn.textContent = "👁️";
      } else {
        input.type = "password";
        btn.textContent = "🔒";
      }
    });
  });

  // 2. Password Strength Meter on Signup Page
  const signupPasswordInput = document.getElementById("signup-password");
  const strengthBar = document.getElementById("strength-bar");

  if (signupPasswordInput && strengthBar) {
    signupPasswordInput.addEventListener("input", (e) => {
      const val = e.target.value;
      strengthBar.className = "strength-bar";

      if (val.length === 0) {
        strengthBar.style.width = "0%";
      } else if (val.length < 6) {
        strengthBar.classList.add("strength-weak");
      } else if (val.length >= 6 && /[A-Z]/.test(val) && /[0-9]/.test(val)) {
        strengthBar.classList.add("strength-strong");
      } else {
        strengthBar.classList.add("strength-medium");
      }
    });
  }

  // 3. Signup Form Handler
  const signupForm = document.getElementById("signup-form");
  if (signupForm) {
    Auth.redirectIfAuthenticated();

    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const alertBox = document.getElementById("auth-alert");
      const submitBtn = document.getElementById("signup-submit-btn");

      const name = document.getElementById("signup-name").value.trim();
      const email = document.getElementById("signup-email").value.trim();
      const password = document.getElementById("signup-password").value;
      const confirmPassword = document.getElementById("signup-confirm-password").value;

      if (!name || !email || !password) {
        showAuthAlert("Please fill in all required fields.", "danger");
        return;
      }

      if (password.length < 6) {
        showAuthAlert("Password must be at least 6 characters.", "danger");
        return;
      }

      if (password !== confirmPassword) {
        showAuthAlert("Passwords do not match.", "danger");
        return;
      }

      try {
        setButtonLoading(submitBtn, true, "Creating Account...");
        hideAuthAlert();

        const response = await fetch(`${API_BASE_URL}/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, email, password })
        });

        const data = await response.json();

        if (response.ok && data.success) {
          Auth.setSession(data.token, data.user);
          showToast("Account created successfully! Redirecting...", "success");
          setTimeout(() => {
            window.location.href = "dashboard.html";
          }, 1200);
        } else {
          showAuthAlert(data.error || "Signup failed. Please try again.", "danger");
        }
      } catch (err) {
        showAuthAlert("Unable to connect to the server. Please check if backend is running.", "danger");
      } finally {
        setButtonLoading(submitBtn, false, "Create Account");
      }
    });
  }

  // 4. Login Form Handler
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    Auth.redirectIfAuthenticated();

    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById("login-submit-btn");

      const email = document.getElementById("login-email").value.trim();
      const password = document.getElementById("login-password").value;

      if (!email || !password) {
        showAuthAlert("Please enter both email and password.", "danger");
        return;
      }

      try {
        setButtonLoading(submitBtn, true, "Signing In...");
        hideAuthAlert();

        const response = await fetch(`${API_BASE_URL}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok && data.success) {
          Auth.setSession(data.token, data.user);
          showToast("Logged in successfully! Redirecting...", "success");
          setTimeout(() => {
            window.location.href = "dashboard.html";
          }, 1000);
        } else {
          showAuthAlert(data.error || "Invalid email or password.", "danger");
        }
      } catch (err) {
        showAuthAlert("Unable to connect to backend server. Make sure Python Flask server is running.", "danger");
      } finally {
        setButtonLoading(submitBtn, false, "Sign In");
      }
    });
  }

  function showAuthAlert(msg, type = "danger") {
    const alertBox = document.getElementById("auth-alert");
    if (alertBox) {
      alertBox.textContent = msg;
      alertBox.className = `alert alert-${type}`;
      alertBox.style.display = "flex";
    }
  }

  function hideAuthAlert() {
    const alertBox = document.getElementById("auth-alert");
    if (alertBox) alertBox.style.display = "none";
  }

  function setButtonLoading(btn, isLoading, text) {
    if (!btn) return;
    btn.disabled = isLoading;
    btn.textContent = text;
    btn.style.opacity = isLoading ? "0.75" : "1";
  }
}

// ====================================================================
// DASHBOARD LOGIC & FILE MANAGEMENT
// ====================================================================

const Dashboard = {
  allFiles: [],
  filteredFiles: [],
  currentCategory: "all",
  currentSort: "date-desc",
  currentView: localStorage.getItem("dashboard_view_mode") || "grid",
  activeFileIdForAction: null,

  init() {
    Auth.requireAuth();

    // Setup User Details
    const user = Auth.getUser();
    if (user) {
      const nameEl = document.getElementById("user-display-name");
      const emailEl = document.getElementById("user-display-email");
      if (nameEl) nameEl.textContent = user.name || "User";
      if (emailEl) emailEl.textContent = user.email || "";
    }

    // Attach Event Handlers
    this.setupLogout();
    this.setupUploadZone();
    this.setupFiltersAndSearch();
    this.setupViewToggle();
    this.setupModals();

    // Check shared parameter in URL
    const urlParams = new URLSearchParams(window.location.search);
    const sharedId = urlParams.get("shared");
    if (sharedId) {
      this.openSharedFileModal(sharedId);
    }

    // Load User Files
    this.fetchFiles();
  },

  setupLogout() {
    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", (e) => {
        e.preventDefault();
        Auth.logout();
      });
    }
  },

  async fetchFiles() {
    try {
      const token = Auth.getToken();
      const response = await fetch(`${API_BASE_URL}/files`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.status === 401) {
        Auth.logout();
        return;
      }

      const data = await response.json();
      if (data.success) {
        this.allFiles = data.files || [];
        this.updateStorageOverview(data.stats);
        this.applyFilters();
      } else {
        showToast(data.error || "Failed to load files.", "error");
      }
    } catch (err) {
      showToast("Error communicating with cloud storage backend.", "error");
    }
  },

  updateStorageOverview(stats) {
    if (!stats) return;

    // Total Storage Used
    const amountEl = document.getElementById("storage-amount");
    if (amountEl) amountEl.textContent = stats.total_formatted || "0 B";

    // Storage progress bar (assuming 100 MB standard free tier display)
    const maxCapacity = 100 * 1024 * 1024; // 100 MB
    const percentage = Math.min(100, Math.round((stats.total_bytes / maxCapacity) * 100));
    const fillEl = document.getElementById("storage-progress-fill");
    if (fillEl) fillEl.style.width = `${Math.max(2, percentage)}%`;

    const countEl = document.getElementById("storage-file-count");
    if (countEl) countEl.textContent = `${stats.total_files || 0} Files`;

    // Category breakdown counts
    const cats = stats.categories || {};
    const pdfCount = document.getElementById("count-pdf");
    const imgCount = document.getElementById("count-image");
    const docCount = document.getElementById("count-doc");
    const zipCount = document.getElementById("count-zip");

    if (pdfCount) pdfCount.textContent = cats.pdf || 0;
    if (imgCount) imgCount.textContent = cats.image || 0;
    if (docCount) docCount.textContent = cats.document || 0;
    if (zipCount) zipCount.textContent = cats.archive || 0;
  },

  setupUploadZone() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const uploadBtn = document.getElementById("trigger-upload-btn");

    if (!dropZone || !fileInput) return;

    if (uploadBtn) {
      uploadBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fileInput.click();
      });
    }

    dropZone.addEventListener("click", () => fileInput.click());

    // Drag & Drop Listeners
    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add("drag-over");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove("drag-over");
      });
    });

    dropZone.addEventListener("drop", (e) => {
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        this.uploadSingleFile(files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        this.uploadSingleFile(files[0]);
      }
      fileInput.value = ""; // Reset for re-selection
    });
  },

  uploadSingleFile(file) {
    const maxMb = 50;
    if (file.size > maxMb * 1024 * 1024) {
      showToast(`File exceeds ${maxMb}MB maximum limit.`, "error");
      return;
    }

    const progressContainer = document.getElementById("upload-progress-container");
    const filenameEl = document.getElementById("progress-filename");
    const percentEl = document.getElementById("progress-percent");
    const barFillEl = document.getElementById("upload-bar-fill");

    if (progressContainer) progressContainer.style.display = "block";
    if (filenameEl) filenameEl.textContent = `Uploading "${file.name}"...`;
    if (percentEl) percentEl.textContent = "0%";
    if (barFillEl) barFillEl.style.width = "0%";

    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/upload`, true);
    xhr.setRequestHeader("Authorization", `Bearer ${Auth.getToken()}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percentComplete = Math.round((e.loaded / e.total) * 100);
        if (percentEl) percentEl.textContent = `${percentComplete}%`;
        if (barFillEl) barFillEl.style.width = `${percentComplete}%`;
      }
    };

    xhr.onload = () => {
      if (progressContainer) {
        setTimeout(() => {
          progressContainer.style.display = "none";
        }, 1500);
      }

      if (xhr.status === 201 || xhr.status === 200) {
        try {
          const res = JSON.parse(xhr.responseText);
          showToast(res.message || "File uploaded successfully!", "success");
          this.fetchFiles();
        } catch (e) {
          showToast("File uploaded successfully!", "success");
          this.fetchFiles();
        }
      } else {
        try {
          const res = JSON.parse(xhr.responseText);
          showToast(res.error || "Upload failed.", "error");
        } catch (e) {
          showToast("Upload failed. Server returned error.", "error");
        }
      }
    };

    xhr.onerror = () => {
      if (progressContainer) progressContainer.style.display = "none";
      showToast("Network error occurred during upload.", "error");
    };

    xhr.send(formData);
  },

  setupFiltersAndSearch() {
    const searchInput = document.getElementById("file-search-input");
    const sortSelect = document.getElementById("file-sort-select");
    const categoryChips = document.querySelectorAll(".category-chip");

    if (searchInput) {
      searchInput.addEventListener("input", () => this.applyFilters());
    }

    if (sortSelect) {
      sortSelect.addEventListener("change", (e) => {
        this.currentSort = e.target.value;
        this.applyFilters();
      });
    }

    categoryChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        categoryChips.forEach((c) => c.classList.remove("active"));
        const cat = chip.getAttribute("data-category");
        if (this.currentCategory === cat) {
          this.currentCategory = "all";
        } else {
          this.currentCategory = cat;
          chip.classList.add("active");
        }
        this.applyFilters();
      });
    });
  },

  setupViewToggle() {
    const gridBtn = document.getElementById("view-grid-btn");
    const tableBtn = document.getElementById("view-table-btn");

    if (gridBtn && tableBtn) {
      gridBtn.addEventListener("click", () => {
        this.currentView = "grid";
        localStorage.setItem("dashboard_view_mode", "grid");
        gridBtn.classList.add("active");
        tableBtn.classList.remove("active");
        this.renderFiles();
      });

      tableBtn.addEventListener("click", () => {
        this.currentView = "table";
        localStorage.setItem("dashboard_view_mode", "table");
        tableBtn.classList.add("active");
        gridBtn.classList.remove("active");
        this.renderFiles();
      });

      // Apply initial state
      if (this.currentView === "table") {
        tableBtn.classList.add("active");
        gridBtn.classList.remove("active");
      }
    }
  },

  applyFilters() {
    const searchInput = document.getElementById("file-search-input");
    const query = (searchInput ? searchInput.value : "").trim().toLowerCase();

    // Filter by search query & category
    this.filteredFiles = this.allFiles.filter((file) => {
      const nameMatches = !query || (file.file_name && file.file_name.toLowerCase().includes(query));
      const categoryMatches = this.currentCategory === "all" || file.category === this.currentCategory;
      return nameMatches && categoryMatches;
    });

    // Sort files
    this.filteredFiles.sort((a, b) => {
      if (this.currentSort === "date-desc") {
        return new Date(b.upload_date) - new Date(a.upload_date);
      } else if (this.currentSort === "date-asc") {
        return new Date(a.upload_date) - new Date(b.upload_date);
      } else if (this.currentSort === "name-asc") {
        return (a.file_name || "").localeCompare(b.file_name || "");
      } else if (this.currentSort === "name-desc") {
        return (b.file_name || "").localeCompare(a.file_name || "");
      } else if (this.currentSort === "size-desc") {
        return (b.file_size || 0) - (a.file_size || 0);
      } else if (this.currentSort === "size-asc") {
        return (a.file_size || 0) - (b.file_size || 0);
      }
      return 0;
    });

    this.renderFiles();
  },

  renderFiles() {
    const gridContainer = document.getElementById("files-grid-container");
    const tableContainer = document.getElementById("files-table-wrapper");
    const tableBody = document.getElementById("files-table-body");
    const emptyState = document.getElementById("empty-state");

    if (!gridContainer || !tableContainer) return;

    if (this.filteredFiles.length === 0) {
      gridContainer.style.display = "none";
      tableContainer.style.display = "none";
      if (emptyState) emptyState.style.display = "block";
      return;
    }

    if (emptyState) emptyState.style.display = "none";

    if (this.currentView === "grid") {
      gridContainer.style.display = "grid";
      tableContainer.style.display = "none";
      this.renderGridView(gridContainer);
    } else {
      gridContainer.style.display = "none";
      tableContainer.style.display = "block";
      this.renderTableView(tableBody);
    }
  },

  renderGridView(container) {
    container.innerHTML = this.filteredFiles
      .map((file) => {
        const iconInfo = getCategoryIconInfo(file.category);
        const formattedDate = formatDate(file.upload_date);

        return `
        <div class="file-card" data-id="${file.file_id}">
          <div class="file-card-top">
            <div class="file-card-icon ${iconInfo.className}">
              ${iconInfo.icon}
            </div>
            ${file.is_public ? `<span class="file-badge-public">Shared</span>` : ""}
          </div>
          
          <div class="file-card-name" title="${file.file_name}">
            ${file.file_name}
          </div>
          
          <div class="file-card-meta">
            <span>${file.file_size_formatted || formatBytes(file.file_size)}</span>
            <span>${formattedDate}</span>
          </div>
          
          <div class="file-card-actions">
            <button class="btn btn-outline btn-sm" onclick="Dashboard.downloadFile('${file.file_id}', '${file.file_name}')" title="Download">
              ⬇️ Download
            </button>
            <button class="btn btn-outline btn-sm" onclick="Dashboard.openShareModal('${file.file_id}', '${file.file_name}')" title="Share">
              🔗 Share
            </button>
            <button class="btn btn-icon btn-sm" onclick="Dashboard.confirmDelete('${file.file_id}', '${file.file_name}')" title="Delete">
              🗑️
            </button>
          </div>
        </div>
      `;
      })
      .join("");
  },

  renderTableView(tbody) {
    if (!tbody) return;
    tbody.innerHTML = this.filteredFiles
      .map((file) => {
        const iconInfo = getCategoryIconInfo(file.category);
        const formattedDate = formatDate(file.upload_date);

        return `
        <tr data-id="${file.file_id}">
          <td>
            <div class="table-file-cell">
              <div class="file-icon-box ${iconInfo.className}">
                ${iconInfo.icon}
              </div>
              <div>
                <div class="table-file-name" title="${file.file_name}">${file.file_name}</div>
                ${file.is_public ? `<span class="file-badge-public">Shared</span>` : ""}
              </div>
            </div>
          </td>
          <td>${iconInfo.label}</td>
          <td>${file.file_size_formatted || formatBytes(file.file_size)}</td>
          <td>${formattedDate}</td>
          <td>
            <div class="table-actions">
              <button class="btn btn-outline btn-sm" onclick="Dashboard.downloadFile('${file.file_id}', '${file.file_name}')">
                ⬇️ Download
              </button>
              <button class="btn btn-outline btn-sm" onclick="Dashboard.openShareModal('${file.file_id}', '${file.file_name}')">
                🔗 Share
              </button>
              <button class="btn btn-icon btn-sm" onclick="Dashboard.confirmDelete('${file.file_id}', '${file.file_name}')">
                🗑️
              </button>
            </div>
          </td>
        </tr>
      `;
      })
      .join("");
  },

  downloadFile(fileId, fileName) {
    const token = Auth.getToken();
    const downloadUrl = `${API_BASE_URL}/download/${fileId}?token=${encodeURIComponent(token)}`;

    // Create temporary link element for clean download trigger
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.setAttribute("download", fileName || "download");
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast(`Starting download for "${fileName}"...`, "info");
  },

  async openShareModal(fileId, fileName) {
    const modal = document.getElementById("share-modal");
    const linkInput = document.getElementById("share-link-input");
    const filenameEl = document.getElementById("share-modal-filename");

    if (!modal) return;

    if (filenameEl) filenameEl.textContent = fileName;
    if (linkInput) linkInput.value = "Generating share link...";

    modal.classList.add("active");

    try {
      const token = Auth.getToken();
      const res = await fetch(`${API_BASE_URL}/share/${fileId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();

      if (res.ok && data.success) {
        if (linkInput) linkInput.value = data.shared_link;
        this.fetchFiles(); // Refresh shared indicator
      } else {
        if (linkInput) linkInput.value = "Failed to generate link.";
        showToast(data.error || "Error sharing file.", "error");
      }
    } catch (e) {
      if (linkInput) linkInput.value = "Error connecting to server.";
    }
  },

  confirmDelete(fileId, fileName) {
    this.activeFileIdForAction = fileId;
    const modal = document.getElementById("delete-modal");
    const filenameEl = document.getElementById("delete-modal-filename");

    if (filenameEl) filenameEl.textContent = `"${fileName}"`;
    if (modal) modal.classList.add("active");
  },

  async executeDelete() {
    if (!this.activeFileIdForAction) return;

    const fileId = this.activeFileIdForAction;
    const modal = document.getElementById("delete-modal");
    if (modal) modal.classList.remove("active");

    try {
      const token = Auth.getToken();
      const res = await fetch(`${API_BASE_URL}/delete/${fileId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();

      if (res.ok && data.success) {
        showToast("File deleted permanently.", "success");
        this.fetchFiles();
      } else {
        showToast(data.error || "Failed to delete file.", "error");
      }
    } catch (e) {
      showToast("Error connecting to server.", "error");
    } finally {
      this.activeFileIdForAction = null;
    }
  },

  setupModals() {
    // Copy Share Link Button
    const copyBtn = document.getElementById("copy-share-btn");
    const linkInput = document.getElementById("share-link-input");

    if (copyBtn && linkInput) {
      copyBtn.addEventListener("click", () => {
        linkInput.select();
        navigator.clipboard.writeText(linkInput.value).then(() => {
          showToast("Link copied to clipboard! 🎉", "success");
          copyBtn.textContent = "Copied!";
          setTimeout(() => {
            copyBtn.textContent = "Copy Link";
          }, 2000);
        });
      });
    }

    // Confirm Delete Button
    const confirmDeleteBtn = document.getElementById("confirm-delete-btn");
    if (confirmDeleteBtn) {
      confirmDeleteBtn.addEventListener("click", () => this.executeDelete());
    }

    // Close Modals on close button or backdrop click
    document.querySelectorAll(".modal-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
          overlay.classList.remove("active");
        }
      });

      overlay.querySelectorAll(".modal-close-btn, .btn-cancel").forEach((btn) => {
        btn.addEventListener("click", () => overlay.classList.remove("active"));
      });
    });
  }
};

// ====================================================================
// INITIALIZATION ENTRYPOINT
// ====================================================================

document.addEventListener("DOMContentLoaded", () => {
  initAuthPages();

  // If on Dashboard page
  if (document.getElementById("dashboard-root")) {
    Dashboard.init();
  }
});
