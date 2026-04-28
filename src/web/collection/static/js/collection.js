document.addEventListener('DOMContentLoaded', () => {
  // Get configuration from global object set by template
  const config = window.collectionConfig || {};
  if (!config) {
    console.error('collectionConfig not found. Make sure the config script runs before this file.');
    return;
  }
  
  let currentCollection = config.currentCollection || '';
  let currentPaperCount = config.currentPaperCount || 0;
  let selectedExportPapers = new Map();
  let collectionIndexUrl = config.collectionIndexUrl || '/collection/';
  
  // Pre-load selected papers if available
  // Also get list of current papers to filter out deleted ones
  const currentPapers = config.currentPapers || [];
  const validPaperIds = new Set();
  const validFilenames = new Set();
  currentPapers.forEach(paper => {
    if (paper.paper_id) validPaperIds.add(paper.paper_id);
    if (paper.arxiv_id) validPaperIds.add(paper.arxiv_id);
    if (paper.filename) validFilenames.add(paper.filename);
  });
  
  if (config.preSelected && Array.isArray(config.preSelected)) {
    config.preSelected.forEach(p => {
      if (p) {
        // Only add if the paper still exists in the collection
        const paperId = p.paper_id || p.arxiv_id;
        const filename = p.filename;
        if (paperId && validPaperIds.has(paperId) || filename && validFilenames.has(filename)) {
          selectedExportPapers.set(paperId || filename, p);
        }
      }
    });
    // Update the export count badge immediately
    const badge = document.getElementById('exportCountBadge');
    if (badge) badge.innerText = selectedExportPapers.size;
  }

  // --- 1. Collection Management ---
  const createCollectionModalEl = document.getElementById('createCollectionModal');
  const createCollectionModal = createCollectionModalEl ? new bootstrap.Modal(createCollectionModalEl) : null;

  document.getElementById('btnCreateCollection')?.addEventListener('click', () => {
    const input = document.getElementById('createCollectionInput');
    input.value = '';
    
    // Calculate default name
    const existingNames = Array.from(document.querySelectorAll('.list-group-item .text-truncate')).map(el => el.textContent.trim());
    let idx = 1;
    while (existingNames.includes(`new_collection_${idx}`)) {
        idx++;
    }
    input.placeholder = `new_collection_${idx}`;
    
    createCollectionModal.show();
  });

  document.getElementById('btnConfirmCreateCollection')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnConfirmCreateCollection');
    const nameInput = document.getElementById('createCollectionInput').value.trim();
    
    btn.disabled = true;
    try {
        const res = await fetch('/collection/api/collection/create', { 
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(nameInput ? { name: nameInput } : {})
        });
        const data = await res.json();
        if (res.ok) {
            window.location.href = `${collectionIndexUrl}?collection=${data.name}`;
        } else {
            alert(data.error);
        }
    } catch(e) {
        alert('Failed to create collection');
    } finally {
        btn.disabled = false;
    }
  });

  const renameModalEl = document.getElementById('renameModal');
  const renameModal = renameModalEl ? new bootstrap.Modal(renameModalEl) : null;
  
  document.getElementById('btnRenameCollection')?.addEventListener('click', () => {
      document.getElementById('renameInput').value = currentCollection;
      renameModal.show();
  });
  
  document.getElementById('btnConfirmRename')?.addEventListener('click', async () => {
      const newName = document.getElementById('renameInput').value.trim();
      if (!newName || newName === currentCollection) return;
      
      const btn = document.getElementById('btnConfirmRename');
      btn.disabled = true;
      
      try {
          const res = await fetch(`/collection/api/collection/${encodeURIComponent(currentCollection)}/rename`, {
              method: 'PUT',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({ new_name: newName })
          });
          const d = await res.json();
          if (res.ok) {
              window.location.href = `${collectionIndexUrl}?collection=${encodeURIComponent(newName)}`;
          } else {
              alert(d.error);
              btn.disabled = false;
          }
      } catch(e) {
          alert('Rename failed');
          btn.disabled = false;
      }
  });

  // Delete Collection Modal
  const deleteModalEl = document.getElementById('deleteModal');
  const deleteModal = deleteModalEl ? new bootstrap.Modal(deleteModalEl) : null;
  let collectionToDelete = null;

  document.getElementById('btnDeleteCollection')?.addEventListener('click', (e) => {
      const name = e.currentTarget.dataset.name;
      collectionToDelete = name;
      document.getElementById('deleteCollectionName').textContent = `"${name}"`;
      if (deleteModal) deleteModal.show();
  });

  document.getElementById('btnConfirmDelete')?.addEventListener('click', async () => {
      if (!collectionToDelete) return;
      
      const btn = document.getElementById('btnConfirmDelete');
      btn.disabled = true;
      btn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Deleting...
      `;
      
      try {
          const res = await fetch(`/collection/api/collection/${encodeURIComponent(collectionToDelete)}`, { method: 'DELETE' });
          if (res.ok) {
              if (deleteModal) deleteModal.hide();
              window.location.href = collectionIndexUrl;
          } else {
              const d = await res.json();
              alert(d.error || 'Delete failed');
              btn.disabled = false;
              btn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="me-1">
                  <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                  <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                </svg>
                Delete Collection
              `;
          }
      } catch (err) {
          alert('Delete failed');
          btn.disabled = false;
          btn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="me-1">
              <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
              <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
            </svg>
            Delete Collection
          `;
      }
  });

  // Delete All Papers Modal
  const deleteAllPapersModalEl = document.getElementById('deleteAllPapersModal');
  const deleteAllPapersModal = deleteAllPapersModalEl ? new bootstrap.Modal(deleteAllPapersModalEl) : null;
  let collectionToDeleteAllPapers = null;
  
  document.getElementById('btnDeleteAllPapers')?.addEventListener('click', (e) => {
      const collectionName = e.currentTarget.dataset.name;
      const paperCount = currentPaperCount || 0;
      
      if (paperCount === 0) {
          alert('No papers to delete.');
          return;
      }
      
      collectionToDeleteAllPapers = collectionName;
      document.getElementById('deleteAllPapersCount').textContent = paperCount;
      if (deleteAllPapersModal) deleteAllPapersModal.show();
  });
  
  document.getElementById('btnConfirmDeleteAllPapers')?.addEventListener('click', async () => {
      if (!collectionToDeleteAllPapers) return;
      
      const btn = document.getElementById('btnConfirmDeleteAllPapers');
      const originalHTML = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Deleting...
      `;
      
      try {
          const res = await fetch(`/collection/api/collection/${encodeURIComponent(collectionToDeleteAllPapers)}/papers`, { method: 'DELETE' });
          const data = await res.json();
          
          if (res.ok) {
              // Clear selected papers map
              selectedExportPapers.clear();
              
              if (deleteAllPapersModal) deleteAllPapersModal.hide();
              
              // Reload page to show updated state
              window.location.reload();
          } else {
              alert(data.error || 'Failed to delete papers');
              btn.disabled = false;
              btn.innerHTML = originalHTML;
          }
      } catch (err) {
          alert('Error deleting papers: ' + err.message);
          btn.disabled = false;
          btn.innerHTML = originalHTML;
      }
  });
  
  // Auto-scan and Add Papers logic
  async function performScan(forceReload = false) {
      if (!currentCollection) return;
      
      try {
        const res = await fetch(`/collection/api/collection/${encodeURIComponent(currentCollection)}/scan`, { method: 'POST' });
        if (!res.ok) {
             console.error("Scan failed to start");
             return;
        }
        document.getElementById('progressOverlay').classList.remove('d-none');
        await consumeEventStream(res, forceReload);
      } catch(e) {
          console.error(e);
          document.getElementById('progressOverlay').classList.add('d-none');
      }
  }

  // Trigger scan on load if collection is active
  if (currentCollection) {
      // Small delay to allow page render
      setTimeout(() => performScan(false), 500);
  }

  // File Upload with Drag & Drop
  const fileInput = document.getElementById('fileInput');
  const pdfDropzone = document.getElementById('pdfDropzone');
  const btnBrowseFiles = document.getElementById('btnBrowseFiles');
  const uploadProgress = document.getElementById('uploadProgress');
  const uploadStatus = document.getElementById('uploadStatus');
  const progressBar = uploadProgress?.querySelector('.progress-bar');

  async function handleFileUpload(files) {
      if (!files || files.length === 0) return;
      
      // Filter only PDF files
      const pdfFiles = Array.from(files).filter(file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
      
      if (pdfFiles.length === 0) {
          alert('Please select PDF files only.');
          return;
      }

      if (pdfFiles.length !== files.length) {
          alert(`Only ${pdfFiles.length} of ${files.length} files are PDFs. Uploading PDFs only.`);
      }
      
      const formData = new FormData();
      pdfFiles.forEach(file => {
          formData.append('files', file);
      });
      
      // Show progress overlay (reuse the same one used for scanning)
      const progressOverlay = document.getElementById('progressOverlay');
      const progressBarEl = document.getElementById('progressBar');
      const progressLabel = document.getElementById('progressLabel');
      const progressFilename = document.getElementById('progressFilename');
      
      if (progressOverlay) {
          progressOverlay.classList.remove('d-none');
          if (progressLabel) progressLabel.textContent = `Uploading and processing ${pdfFiles.length} file${pdfFiles.length > 1 ? 's' : ''}...`;
          if (progressBarEl) progressBarEl.style.width = '0%';
          if (progressFilename) progressFilename.textContent = '';
      }
      
      try {
          const res = await fetch(`/collection/api/collection/${encodeURIComponent(currentCollection)}/upload`, {
              method: 'POST',
              body: formData
          });
          
          if (!res.ok) {
              const data = await res.json();
              throw new Error(data.error || 'Upload failed');
          }
          
          // Consume SSE stream
          await consumeUploadEventStream(res);
          
      } catch(e) {
          if (progressOverlay) progressOverlay.classList.add('d-none');
          alert('Upload error: ' + e.message);
      } finally {
          if (fileInput) fileInput.value = ''; // clear
      }
  }

  // Helper for SSE from upload
  async function consumeUploadEventStream(response) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      
      const progressOverlay = document.getElementById('progressOverlay');
      const progressBarEl = document.getElementById('progressBar');
      const progressLabel = document.getElementById('progressLabel');
      const progressFilename = document.getElementById('progressFilename');
      
      let currentStage = '';
      let currentTotal = 0;
      
      while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop();
          
          for (const line of lines) {
              const match = line.match(/event: (.*)\ndata: (.*)/s);
              if (match) {
                  const event = match[1];
                  const data = JSON.parse(match[2]);
                  
                  if (event === 'stage_start') {
                      currentStage = data.stage;
                      currentTotal = data.total;
                      if (progressBarEl) progressBarEl.style.width = '0%';
                      if (progressLabel) progressLabel.textContent = data.stage_name || 'Processing...';
                      if (progressFilename) progressFilename.textContent = '';
                  } else if (event === 'progress') {
                      // Sequential per-paper: bar = completed/total; label = Paper X/total; subtitle = message
                      const completed = data.completed != null ? data.completed : data.current;
                      const total = data.total || 1;
                      const pct = Math.round((completed / total) * 100);
                      if (progressBarEl) progressBarEl.style.width = pct + '%';
                      if (progressLabel) {
                          const paperIndex = data.paper_index != null ? data.paper_index : completed + 1;
                          progressLabel.textContent = `Loading Paper ${paperIndex}/${total}`;
                      }
                      if (progressFilename) {
                          progressFilename.textContent = data.message || data.filename || '';
                      }
                  } else if (event === 'complete') {
                      if (progressOverlay) progressOverlay.classList.add('d-none');
                      
                      // Reload page to show new papers
                      window.location.href = `${collectionIndexUrl}?collection=${data.collection}`;
                  } else if (event === 'error') {
                      if (progressOverlay) progressOverlay.classList.add('d-none');
                      alert(data.message || 'An error occurred during processing');
                  }
              }
          }
      }
  }

  // Handle upload button - directly open file picker
  const btnToggleUpload = document.getElementById('btnToggleUpload');
  if (btnToggleUpload && fileInput) {
      btnToggleUpload.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          fileInput.click();
      });
  }

  // Browse buttons in dropzone
  const btnBrowseFiles2 = document.getElementById('btnBrowseFiles2');
  if (btnBrowseFiles2 && fileInput) {
      btnBrowseFiles2.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          fileInput.click();
      });
  }

  // File input change
  if (fileInput) {
      fileInput.addEventListener('change', async (e) => {
          await handleFileUpload(e.target.files);
      });
  }

  // Drag and Drop
  if (pdfDropzone) {
      // Prevent default drag behaviors
      ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
          pdfDropzone.addEventListener(eventName, preventDefaults, false);
          document.body.addEventListener(eventName, preventDefaults, false);
      });

      function preventDefaults(e) {
          e.preventDefault();
          e.stopPropagation();
      }

      // Highlight drop zone when item is dragged over it
      ['dragenter', 'dragover'].forEach(eventName => {
          pdfDropzone.addEventListener(eventName, () => {
              pdfDropzone.classList.add('drag-over');
          }, false);
      });

      ['dragleave', 'drop'].forEach(eventName => {
          pdfDropzone.addEventListener(eventName, () => {
              pdfDropzone.classList.remove('drag-over');
          }, false);
      });

      // Handle dropped files
      pdfDropzone.addEventListener('drop', async (e) => {
          const dt = e.dataTransfer;
          const files = dt.files;
          await handleFileUpload(files);
      }, false);

      // Also allow click to browse
      pdfDropzone.addEventListener('click', () => {
          if (fileInput) fileInput.click();
      });
  }


  // --- 2. Paper Management ---
  // Update selected papers count badge
  function updateSelectedPapersCount() {
    const count = selectedExportPapers.size;
    const badge = document.getElementById('selectedPapersCount');
    if (badge) {
      badge.textContent = count;
    }
  }
  
  // Initialize selected papers from pre-selected list
  function initializeSelectedPapers() {
    if (config.preSelected && Array.isArray(config.preSelected)) {
      config.preSelected.forEach(p => {
        if (p) {
          const paperId = p.paper_id || p.arxiv_id;
          const filename = p.filename;
          if (paperId && validPaperIds.has(paperId) || filename && validFilenames.has(filename)) {
            selectedExportPapers.set(paperId || filename, p);
            // Update UI
            const paperItem = document.querySelector(`[data-paper-id="${paperId || filename}"]`);
            if (paperItem) {
              paperItem.classList.add('selected');
              const selectBtn = paperItem.querySelector('.paper-item-select-btn');
              if (selectBtn) {
                selectBtn.setAttribute('data-selected', 'true');
              }
            }
          }
        }
      });
    }
    updateSelectedPapersCount();
  }
  
  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // View paper details in modal
  window.viewPaperDetails = function(e, paperId) {
    e.stopPropagation();
    const paperItem = document.querySelector(`[data-paper-id="${paperId}"]`);
    if (!paperItem) return;
    
    const paperStr = paperItem.dataset.paper;
    try {
      const paper = JSON.parse(paperStr);
      const authors = Array.isArray(paper.authors) ? paper.authors : [];
      const authorsText = authors.length > 0
        ? authors.map(author => escapeHtml(author)).join(', ')
        : 'No authors information available.';
      const rawAbstract = String(paper.abstract || paper.summary || 'No abstract available.');
      const abstractWordCount = rawAbstract.trim().split(/\s+/).filter(Boolean).length;
      const safeTitle = escapeHtml(paper.title || 'Untitled');
      const safePaperId = escapeHtml(paper.paper_id || 'unknown-id');
      const safeFilename = escapeHtml(paper.filename || 'Unknown file');
      
      const detailContainer = document.getElementById('paperDetailsContent');
      detailContainer.innerHTML = `
        <article class="paper-details-card">
          <header class="paper-details-top">
            <h5 class="fw-bold paper-details-title">${safeTitle}</h5>
            <div class="paper-meta-row">
              <span class="paper-pill">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                  <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/>
                </svg>
                ${safePaperId}
              </span>
              <span class="paper-pill paper-pill-muted">PDF file</span>
            </div>
            <p class="paper-filename">${safeFilename}</p>
          </header>
          <section class="paper-section">
            <h6 class="paper-section-heading">Authors</h6>
            <p class="paper-authors-text">${authorsText}</p>
          </section>
          <section class="paper-section">
            <div class="paper-section-header">
              <h6 class="paper-section-heading mb-0">Abstract</h6>
              <div class="paper-section-actions">
                <span class="paper-abstract-stats">${abstractWordCount} words</span>
                <button type="button" class="btn btn-sm btn-outline-secondary paper-copy-abstract-btn" id="copyAbstractBtn">Copy</button>
              </div>
            </div>
            <p class="paper-abstract-text">${escapeHtml(rawAbstract)}</p>
          </section>
        </article>
      `;

      const copyAbstractBtn = document.getElementById('copyAbstractBtn');
      if (copyAbstractBtn) {
        copyAbstractBtn.addEventListener('click', async () => {
          const initialLabel = copyAbstractBtn.textContent;
          try {
            await navigator.clipboard.writeText(rawAbstract);
            copyAbstractBtn.textContent = 'Copied';
          } catch (err) {
            copyAbstractBtn.textContent = 'Failed';
          }
          setTimeout(() => {
            copyAbstractBtn.textContent = initialLabel;
          }, 1400);
        });
      }
      
      const modal = new bootstrap.Modal(document.getElementById('paperDetailsModal'));
      modal.show();
    } catch(e) { 
      console.error(e);
      alert('Error loading paper details');
    }
  };
  
  // Toggle paper selection
  window.togglePaperSelection = function(e, paperId) {
    e.stopPropagation();
    const paperItem = document.querySelector(`[data-paper-id="${paperId}"]`);
    if (!paperItem) return;
    
    const paperStr = paperItem.dataset.paper;
    try {
      const paper = JSON.parse(paperStr);
      const key = paper.paper_id || paper.filename;
      const isSelected = selectedExportPapers.has(key);
      
      if (isSelected) {
        selectedExportPapers.delete(key);
        paperItem.classList.remove('selected');
        const selectBtn = paperItem.querySelector('.paper-item-select-btn');
        if (selectBtn) {
          selectBtn.setAttribute('data-selected', 'false');
        }
      } else {
        selectedExportPapers.set(key, paper);
        paperItem.classList.add('selected');
        const selectBtn = paperItem.querySelector('.paper-item-select-btn');
        if (selectBtn) {
          selectBtn.setAttribute('data-selected', 'true');
        }
      }
      
      // Update visualization if it exists
      if (typeof drawPlot === 'function') {
        drawPlot();
      }
      
      // Save selection immediately
      saveSelection();
      
      // Update count badge
      updateSelectedPapersCount();
    } catch(e) {
      console.error(e);
    }
  };
  
  // Save selection to backend
  async function saveSelection() {
    const files = Array.from(selectedExportPapers.values());
    try {
      await fetch('/collection/api/export-selection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          collection_name: currentCollection,
          files: files 
        })
      });
    } catch(e) {
      console.error('Failed to save selection:', e);
    }
  }
  
  // Select All Papers
  const selectAllModal = document.getElementById('selectAllModal') ? new bootstrap.Modal(document.getElementById('selectAllModal')) : null;
  let pendingSelectAllAction = null;
  
  document.getElementById('btnSelectAll')?.addEventListener('click', () => {
    const paperItems = document.querySelectorAll('.paper-item[data-paper-id]');
    const count = paperItems.length;
    
    if (count === 0) {
      alert('No papers to select.');
      return;
    }
    
    document.getElementById('selectAllModalTitle').textContent = 'Select All Papers';
    document.getElementById('selectAllModalMessage').textContent = `Are you sure you want to select all ${count} paper(s)?`;
    pendingSelectAllAction = 'select';
    if (selectAllModal) selectAllModal.show();
  });
  
  // Deselect All Papers
  document.getElementById('btnDeselectAll')?.addEventListener('click', () => {
    const selectedCount = selectedExportPapers.size;
    
    if (selectedCount === 0) {
      alert('No papers are currently selected.');
      return;
    }
    
    document.getElementById('selectAllModalTitle').textContent = 'Deselect All Papers';
    document.getElementById('selectAllModalMessage').textContent = `Are you sure you want to deselect all ${selectedCount} selected paper(s)?`;
    pendingSelectAllAction = 'deselect';
    if (selectAllModal) selectAllModal.show();
  });
  
  // Confirm Select All/Deselect All
  document.getElementById('btnConfirmSelectAll')?.addEventListener('click', () => {
    if (pendingSelectAllAction === 'select') {
      const paperItems = document.querySelectorAll('.paper-item[data-paper-id]');
      paperItems.forEach(item => {
        const paperId = item.dataset.paperId;
        const paperStr = item.dataset.paper;
        try {
          const paper = JSON.parse(paperStr);
          const key = paper.paper_id || paper.filename;
          if (!selectedExportPapers.has(key)) {
            selectedExportPapers.set(key, paper);
            item.classList.add('selected');
            const selectBtn = item.querySelector('.paper-item-select-btn');
            if (selectBtn) {
              selectBtn.setAttribute('data-selected', 'true');
            }
          }
        } catch(e) {
          console.error(e);
        }
      });
    } else if (pendingSelectAllAction === 'deselect') {
      selectedExportPapers.clear();
      document.querySelectorAll('.paper-item').forEach(item => {
        item.classList.remove('selected');
        const selectBtn = item.querySelector('.paper-item-select-btn');
        if (selectBtn) {
          selectBtn.setAttribute('data-selected', 'false');
        }
      });
    }
    
    // Update visualization if it exists
    if (typeof drawPlot === 'function') {
      drawPlot();
    }
    
    // Save selection
    saveSelection();
    
    // Update count badge
    updateSelectedPapersCount();
    
    if (selectAllModal) selectAllModal.hide();
    pendingSelectAllAction = null;
  });
  
  // Initialize selected papers on load (after DOM is ready)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initializeSelectedPapers();
      // Initialize Bootstrap tooltips
      const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
      tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
      });
    });
  } else {
    initializeSelectedPapers();
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl);
    });
  }

  // Delete Paper Modal
  const deletePaperModalEl = document.getElementById('deletePaperModal');
  const deletePaperModal = deletePaperModalEl ? new bootstrap.Modal(deletePaperModalEl) : null;
  let paperToDelete = null;
  
  window.removePaper = function(e, paperId) {
      e.stopPropagation();
      paperToDelete = paperId;
      
      // Get paper details for display
      const paperItem = document.querySelector(`[data-paper-id="${paperId}"]`);
      if (paperItem) {
          try {
              const paperStr = paperItem.dataset.paper;
              const paper = JSON.parse(paperStr);
              const paperName = paper.title || paper.filename || paperId;
              document.getElementById('deletePaperName').textContent = `"${paperName}"`;
          } catch(e) {
              document.getElementById('deletePaperName').textContent = `"${paperId}"`;
          }
      } else {
          document.getElementById('deletePaperName').textContent = `"${paperId}"`;
      }
      
      if (deletePaperModal) deletePaperModal.show();
  };
  
  document.getElementById('btnConfirmDeletePaper')?.addEventListener('click', async () => {
      if (!paperToDelete) return;
      
      const btn = document.getElementById('btnConfirmDeletePaper');
      const originalHTML = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Deleting...
      `;
      
      try {
          const res = await fetch(`/collection/api/collection/${encodeURIComponent(currentCollection)}/paper/${encodeURIComponent(paperToDelete)}`, { method: 'DELETE' });
          if (res.ok) {
              // Remove from selected papers map if present
              selectedExportPapers.delete(paperToDelete);
              // Also try to remove by title or filename
              for (const [key, value] of selectedExportPapers.entries()) {
                  if (value.paper_id === paperToDelete || value.filename === paperToDelete) {
                      selectedExportPapers.delete(key);
                      break;
                  }
              }
              
              // Save updated selection
              saveSelection();
              
              if (deletePaperModal) deletePaperModal.hide();
              
              window.location.reload();
          } else {
              const data = await res.json();
              alert(data.error || 'Failed to remove paper');
              btn.disabled = false;
              btn.innerHTML = originalHTML;
          }
      } catch(err) {
          alert('Error removing paper: ' + err.message);
          btn.disabled = false;
          btn.innerHTML = originalHTML;
      }
  });

  // --- 3. Visualization & Export ---
  if (config.vizPayload && config.vizPayload.data && config.vizPayload.data.length > 0) {
    const vizPayload = config.vizPayload;
    const plotDiv = document.getElementById('embeddingPlot');
    const vizModal = document.getElementById('vizModal');
    const getModalPlotDiv = () => document.getElementById('modalEmbeddingPlot');
    
    function buildPlotData() {
        const plotData = JSON.parse(JSON.stringify(vizPayload.data || []));
        const trace = plotData[0];
        if (!trace || !trace.x || !Array.isArray(trace.x)) return null;

        const count = trace.x.length;
        const opacity = [];
        const customdata = trace.customdata || [];
        const hasSelection = selectedExportPapers.size > 0;

        for (let i = 0; i < count; i++) {
            const d = customdata[i] || {};
            const key = d.paper_id || d.title;
            let op;
            if (!hasSelection) {
                op = 0.85;
            } else {
                const isSelected = selectedExportPapers.has(key);
                op = isSelected ? 1.0 : 0.3;
            }
            opacity.push(op);
        }

        trace.marker = trace.marker || {};
        trace.marker.opacity = opacity;
        trace.selectedpoints = null;
        return plotData;
    }

    function buildCleanLayout() {
        const cleanLayout = JSON.parse(JSON.stringify(vizPayload.layout));
        cleanLayout.selection = null;
        cleanLayout.autosize = true;
        if (cleanLayout.width) delete cleanLayout.width;
        if (cleanLayout.height) delete cleanLayout.height;
        return cleanLayout;
    }

    function renderPlot(targetDiv) {
        if (!targetDiv || !vizPayload || !vizPayload.data || !vizPayload.data[0]) return;

        const plotData = buildPlotData();
        if (!plotData) return;
        const cleanLayout = buildCleanLayout();

        Plotly.newPlot(targetDiv, plotData, cleanLayout, {responsive: true}).then(() => {
            // Ensure selection is cleared after plot is created
            Plotly.relayout(targetDiv, {'selection': null});

            // Set cursor to pointer on scatter points
            const scatterPaths = targetDiv.querySelectorAll('.scatterlayer path, .scatterlayer .points path, .scatterlayer g.trace path');
            scatterPaths.forEach(path => {
                path.style.cursor = 'pointer';
            });

            attachPlotEvents(targetDiv);
        });
    }

    // Reusable function to draw/redraw all visible embedding plots
    function drawPlot() {
        renderPlot(plotDiv);
        if (vizModal && vizModal.classList.contains('show')) {
            renderPlot(getModalPlotDiv());
        }
    }

    function attachPlotEvents(targetDiv) {
        if (!targetDiv) return;

        // Remove old if any (though newPlot usually clears them, good to be safe)
        targetDiv.removeAllListeners && targetDiv.removeAllListeners('plotly_selected');
        targetDiv.removeAllListeners && targetDiv.removeAllListeners('plotly_click');
        targetDiv.removeAllListeners && targetDiv.removeAllListeners('plotly_hover');
        targetDiv.removeAllListeners && targetDiv.removeAllListeners('plotly_unhover');

        targetDiv.on('plotly_selected', (eventData) => {
            const points = eventData ? eventData.points : [];
            handleSelection(points, false);

            // Immediately clear the selection region using multiple methods
            // 1. Clear selectedpoints via restyle
            Plotly.restyle(targetDiv, {'selectedpoints': [null]}, 0);

            // 2. Clear selection via relayout
            Plotly.relayout(targetDiv, {'selection': null});

            // 3. Clear the selection layer DOM element directly
            setTimeout(() => {
                const selectionLayer = targetDiv.querySelector('.selectionlayer');
                if (selectionLayer) {
                    selectionLayer.innerHTML = '';
                }
                // Also try to find and clear any selection-related SVG elements
                const selectionRects = targetDiv.querySelectorAll('.select-outline, .select-outline-1, .select-outline-2');
                selectionRects.forEach(el => el.remove());

                // Redraw to show updated selection state
                drawPlot();
            }, 10);
        });

        targetDiv.on('plotly_click', (eventData) => {
            handleSelection(eventData ? eventData.points : [], true);
            drawPlot();
        });

        targetDiv.on('plotly_hover', () => {
            // Set cursor on the plot container and SVG
            targetDiv.style.cursor = 'pointer';
            const svg = targetDiv.querySelector('svg');
            if (svg) {
                svg.style.cursor = 'pointer';
            }
            // Also set on all scatter paths
            const scatterPaths = targetDiv.querySelectorAll('.scatterlayer path');
            scatterPaths.forEach(path => {
                path.style.cursor = 'pointer';
            });
        });
        targetDiv.on('plotly_unhover', () => {
            // Reset cursor when not hovering
            targetDiv.style.cursor = '';
            const svg = targetDiv.querySelector('svg');
            if (svg) {
                svg.style.cursor = '';
            }
        });
    }

    function handleSelection(points, toggle = false) {
        if (points && points.length > 0) {
            points.forEach(p => {
                const data = p.customdata || {};
                const key = data.paper_id || data.title;
                if (!key) return;
                
                if (toggle) {
                   if (selectedExportPapers.has(key)) selectedExportPapers.delete(key);
                   else selectedExportPapers.set(key, data);
                } else {
                   if (selectedExportPapers.has(key)) selectedExportPapers.delete(key);
                   else selectedExportPapers.set(key, data);
                }
                
                // Update UI for clicked papers
                const paperItem = document.querySelector(`[data-paper-id="${key}"]`);
                if (paperItem) {
                    const isSelected = selectedExportPapers.has(key);
                    if (isSelected) {
                        paperItem.classList.add('selected');
                        const selectBtn = paperItem.querySelector('.paper-item-select-btn');
                        if (selectBtn) {
                            selectBtn.setAttribute('data-selected', 'true');
                        }
                    } else {
                        paperItem.classList.remove('selected');
                        const selectBtn = paperItem.querySelector('.paper-item-select-btn');
                        if (selectBtn) {
                            selectBtn.setAttribute('data-selected', 'false');
                        }
                    }
                }
            });
        }
        
        // Save selection immediately
        saveSelection();
        
        // Update count badge
        updateSelectedPapersCount();
    }
    
    // Removed renderExportList - no longer needed since we removed the Selected Papers panel
    
    // Initial draw
    if (plotDiv && vizPayload) {
        drawPlot();
    }

    // Modal expand visualization
    if (vizModal) {
        vizModal.addEventListener('shown.bs.modal', function () {
            const modalPlotDiv = getModalPlotDiv();
            if (modalPlotDiv) {
                renderPlot(modalPlotDiv);
            }
        });
        
        // Clean up when modal closes to save memory
        vizModal.addEventListener('hidden.bs.modal', function () {
            const modalPlotDiv = getModalPlotDiv();
            if (modalPlotDiv) {
                Plotly.purge(modalPlotDiv);
            }
        });
    }
  }

  // Helper for SSE
  async function consumeEventStream(response, forceReload) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      
      while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop();
          
          for (const line of lines) {
              const match = line.match(/event: (.*)\ndata: (.*)/s);
              if (match) {
                  const event = match[1];
                  const data = JSON.parse(match[2]);
                  
                  if (event === 'progress') {
                      const pct = Math.round((data.current / data.total) * 100);
                      document.getElementById('progressBar').style.width = pct + '%';
                      document.getElementById('progressLabel').innerText = `Processing ${data.current}/${data.total}`;
                      document.getElementById('progressFilename').innerText = data.filename;
                  } else if (event === 'complete') {
                      document.getElementById('progressOverlay').classList.add('d-none');
                      
                      if (forceReload || data.paper_count !== currentPaperCount) {
                          window.location.href = `${collectionIndexUrl}?collection=${data.collection}`;
                      }
                  } else if (event === 'error') {
                      alert(data.message);
                      document.getElementById('progressOverlay').classList.add('d-none');
                  }
              }
          }
      }
  }
});
