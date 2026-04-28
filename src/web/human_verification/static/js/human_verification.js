// Safely initialize data with fallbacks
const INITIAL_DATA = window.HUMAN_VERIFICATION_DATA || [];
const SELECTED_COLLECTION = window.SELECTED_COLLECTION || '';
const SELECTED_PROCESS = window.SELECTED_PROCESS || '';
const SELECTED_CHECKLIST = window.SELECTED_CHECKLIST || '';
const SELECTED_PAPER = window.SELECTED_PAPER || '';

// Store selected values
let currentSelectedCollection = null;
let currentSelectedProcess = null;
let currentSelectedChecklist = null;
let currentSelectedPaper = null;
let hasUserSelectionInteraction = false;

// Initial Load Logic
document.addEventListener('DOMContentLoaded', async () => {
    const collectionList = document.getElementById('collectionList');
    const processList = document.getElementById('processList');
    const checklistList = document.getElementById('checklistList');
    const paperList = document.getElementById('paperList');
    const collectionColumn = document.getElementById('collectionColumn');
    const processColumn = document.getElementById('processColumn');
    const checklistColumn = document.getElementById('checklistColumn');
    const paperColumn = document.getElementById('paperColumn');
    const collectionSelectHidden = document.getElementById('collectionSelectHidden');
    const processSelectHidden = document.getElementById('processSelectHidden');
    const checklistSelectHidden = document.getElementById('checklistSelectHidden');
    const paperSelect = document.getElementById('paperSelect');
    const loadBtn = document.getElementById('loadBtn');
    const groundTruthVerifyBtn = document.getElementById('groundTruthVerifyBtn');
    const groundTruthFileInput = document.getElementById('groundTruthFileInput');

    // Helper function to reset subsequent selections
    function resetSubsequentSelections(resetFrom) {
        if (resetFrom === 'collection') {
            // Reset checklist, process, and paper
            currentSelectedChecklist = null;
            currentSelectedProcess = null;
            currentSelectedPaper = null;
            checklistSelectHidden.value = '';
            processSelectHidden.value = '';
            paperSelect.value = '';

            checklistList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a collection first...</div>';
            processList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a checklist first...</div>';
            paperList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a process first...</div>';

            checklistColumn.style.display = 'none';
            processColumn.style.display = 'none';
            paperColumn.style.display = 'none';

            loadBtn.disabled = true;
            if (groundTruthVerifyBtn) groundTruthVerifyBtn.disabled = true;
            updateLoadButtonState();
        } else if (resetFrom === 'checklist') {
            // Reset process and paper
            currentSelectedProcess = null;
            currentSelectedPaper = null;
            processSelectHidden.value = '';
            paperSelect.value = '';

            processList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a checklist first...</div>';
            paperList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a process first...</div>';

            processColumn.style.display = 'none';
            paperColumn.style.display = 'none';

            loadBtn.disabled = true;
            if (groundTruthVerifyBtn) groundTruthVerifyBtn.disabled = true;
            updateLoadButtonState();
        } else if (resetFrom === 'process') {
            // Reset paper
            currentSelectedPaper = null;
            paperSelect.value = '';

            paperList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a process first...</div>';
            paperColumn.style.display = 'none';

            loadBtn.disabled = true;
            if (groundTruthVerifyBtn) groundTruthVerifyBtn.disabled = true;
            updateLoadButtonState();
        }
    }

    function updateGroundTruthButtonState() {
        if (groundTruthVerifyBtn) {
            groundTruthVerifyBtn.disabled = !(currentSelectedCollection && currentSelectedProcess && currentSelectedChecklist);
        }
    }

    function selectionMatchesDisplayed() {
        if (INITIAL_DATA.length === 0 || !SELECTED_COLLECTION) return false;
        const col = (currentSelectedCollection && (currentSelectedCollection.slug || currentSelectedCollection.name)) === SELECTED_COLLECTION;
        const proc = (currentSelectedProcess && (currentSelectedProcess.slug || currentSelectedProcess.name)) === SELECTED_PROCESS;
        const check = (currentSelectedChecklist && currentSelectedChecklist.name) === SELECTED_CHECKLIST;
        const paper = (currentSelectedPaper && currentSelectedPaper.paper_id) === SELECTED_PAPER;
        return col && proc && check && paper;
    }

    function updateLoadButtonState() {
        const labelEl = document.getElementById('loadBtnLabel');
        const isStopMode = selectionMatchesDisplayed();
        if (labelEl) labelEl.textContent = isStopMode ? 'Stop Manual Verification' : 'Start Manual Verification';
        if (loadBtn) {
            if (isStopMode) loadBtn.classList.add('load-btn-stop');
            else loadBtn.classList.remove('load-btn-stop');
        }
    }

    // Load Collections
    async function loadCollections() {
        collectionList.innerHTML = '<div class="text-center p-4" style="color: #64748b;"><div class="spinner-border spinner-border-sm me-2"></div>Loading...</div>';
        try {
            const res = await fetch('/human_verification/api/collections');
            const collections = await res.json();
            
            collectionList.innerHTML = '';
            if (collections.length === 0) {
                collectionList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">No collections found.</div>';
                return;
            }
            
            collections.forEach(c => {
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action';
                listItem.dataset.collectionSlug = c.slug || c.name;
                listItem.dataset.collectionName = c.name;
                
                // Add collection icon
                const icon = document.createElement('svg');
                icon.className = 'list-item-icon';
                icon.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                icon.setAttribute('fill', 'currentColor');
                icon.setAttribute('viewBox', '0 0 16 16');
                icon.innerHTML = '<path d="M13 0H6a2 2 0 0 0-2 2 2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2 2 2 0 0 0 2-2V2a2 2 0 0 0-2-2m0 13V4a2 2 0 0 0-2-2H5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1M3 4a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>';
                
                const textSpan = document.createElement('span');
                textSpan.className = 'list-item-text';
                textSpan.textContent = c.name;
                
                listItem.appendChild(icon);
                listItem.appendChild(textSpan);
                
                listItem.addEventListener('click', () => {
                    hasUserSelectionInteraction = true;
                    // Check if this is a different collection than currently selected
                    const wasDifferentCollection = currentSelectedCollection && 
                        currentSelectedCollection.slug !== (c.slug || c.name);
                    
                    // Remove active class from all items
                    collectionList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedCollection = {
                        slug: c.slug || c.name,
                        name: c.name
                    };
                    collectionSelectHidden.value = currentSelectedCollection.slug;
                    
                    // If collection changed, reset subsequent selections
                    if (wasDifferentCollection) {
                        resetSubsequentSelections('collection');
                    }
                    
                    // Show checklist column with animation and load checklists
                    if (checklistColumn.style.display === 'none' || !checklistColumn.style.display) {
                        checklistColumn.style.display = 'block';
                        checklistColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                    updateLoadButtonState();
                    updateGroundTruthButtonState();
                    loadChecklists();
                });
                
                // Pre-select if re-rendering
                if (!hasUserSelectionInteraction && SELECTED_COLLECTION && (c.slug === SELECTED_COLLECTION || c.name === SELECTED_COLLECTION)) {
                    listItem.classList.add('active');
                    currentSelectedCollection = {
                        slug: c.slug || c.name,
                        name: c.name
                    };
                    collectionSelectHidden.value = currentSelectedCollection.slug;
                    if (checklistColumn.style.display === 'none' || !checklistColumn.style.display) {
                        checklistColumn.style.display = 'block';
                        checklistColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                }
                
                collectionList.appendChild(listItem);
            });
            
            // If a collection was pre-selected, load checklists
            if (!hasUserSelectionInteraction && SELECTED_COLLECTION) {
                await loadChecklists();
            }
        } catch (e) {
            console.error('Error loading collections:', e);
            collectionList.innerHTML = '<div class="text-center p-4" style="color: #dc3545; font-size: 0.85rem;">Error loading collections.</div>';
        }
    }

    // Load Processes
    async function loadProcesses() {
        if (!currentSelectedCollection || !currentSelectedChecklist) return;
        
        processList.innerHTML = '<div class="text-center p-4" style="color: #64748b;"><div class="spinner-border spinner-border-sm me-2"></div>Loading...</div>';
        try {
            const res = await fetch(`/human_verification/api/processes?collection_name=${currentSelectedCollection.slug}`);
            const processes = await res.json();
            
            processList.innerHTML = '';
            if (processes.length === 0) {
                processList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">No processes found.</div>';
                return;
            }
            
            processes.forEach(p => {
                const displayName = (p.data && p.data.name) ? p.data.name : (p.name || p.slug);
                const slugValue = p.slug || p.name;
                
                // Skip default_review process - it's only for design template purposes
                if (slugValue === 'default_review' || displayName === 'Default Review Process') {
                    return;
                }
                
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action';
                listItem.dataset.processSlug = slugValue;
                listItem.dataset.processName = displayName;
                
                // Add process icon
                const icon = document.createElement('svg');
                icon.className = 'list-item-icon';
                icon.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                icon.setAttribute('fill', 'currentColor');
                icon.setAttribute('viewBox', '0 0 16 16');
                icon.innerHTML = '<path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1h12zM2 0a2 2 0 0 0-2 2v12.793a.5.5 0 0 0 .854.353l2.853-2.853A1 1 0 0 1 4.414 12H14a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z"/><path d="M5 6a1 1 0 1 1-2 0 1 1 0 0 1 2 0m4 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0m4 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0"/>';
                
                const textSpan = document.createElement('span');
                textSpan.className = 'list-item-text';
                textSpan.textContent = displayName;
                
                listItem.appendChild(icon);
                listItem.appendChild(textSpan);
                
                listItem.addEventListener('click', () => {
                    hasUserSelectionInteraction = true;
                    // Check if this is a different process than currently selected
                    const wasDifferentProcess = currentSelectedProcess && 
                        currentSelectedProcess.slug !== (p.slug || p.name);
                    
                    // Remove active class from all items
                    processList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedProcess = {
                        slug: p.slug || p.name,
                        name: displayName
                    };
                    processSelectHidden.value = currentSelectedProcess.slug;
                    
                    // If process changed, reset subsequent selections
                    if (wasDifferentProcess) {
                        resetSubsequentSelections('process');
                    }
                    
                    // Show paper column with animation and load papers
                    if (paperColumn.style.display === 'none' || !paperColumn.style.display) {
                        paperColumn.style.display = 'block';
                        paperColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                    updateLoadButtonState();
                    updateGroundTruthButtonState();
                    loadPapers();
                });
                
                // Pre-select if re-rendering
                if (!hasUserSelectionInteraction && SELECTED_PROCESS && (p.slug === SELECTED_PROCESS || p.name === SELECTED_PROCESS)) {
                    listItem.classList.add('active');
                    currentSelectedProcess = {
                        slug: p.slug || p.name,
                        name: displayName
                    };
                    processSelectHidden.value = currentSelectedProcess.slug;
                    if (paperColumn.style.display === 'none' || !paperColumn.style.display) {
                        paperColumn.style.display = 'block';
                        paperColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                }
                
                processList.appendChild(listItem);
            });
            
            // If a process was pre-selected, load papers
            if (!hasUserSelectionInteraction && SELECTED_PROCESS) {
                await loadPapers();
            }
        } catch (e) {
            console.error('Error loading processes:', e);
            processList.innerHTML = '<div class="text-center p-4" style="color: #dc3545; font-size: 0.85rem;">Error loading processes.</div>';
        }
    }

    // Load Checklists
    async function loadChecklists() {
        if (!currentSelectedCollection) return;
        
        checklistList.innerHTML = '<div class="text-center p-4" style="color: #64748b;"><div class="spinner-border spinner-border-sm me-2"></div>Loading...</div>';
        try {
            const res = await fetch('/human_verification/api/checklists');
            const checklists = await res.json();
            
            checklistList.innerHTML = '';
            if (checklists.length === 0) {
                checklistList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">No checklists found.</div>';
                return;
            }
            
            checklists.forEach(c => {
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action';
                listItem.dataset.checklistName = c.name;
                
                // Add checklist icon
                const icon = document.createElement('svg');
                icon.className = 'list-item-icon';
                icon.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                icon.setAttribute('fill', 'currentColor');
                icon.setAttribute('viewBox', '0 0 16 16');
                icon.innerHTML = '<path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1h12zM2 0a2 2 0 0 0-2 2v12.793a.5.5 0 0 0 .854.353l2.853-2.853A1 1 0 0 1 4.414 12H14a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z"/><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425z"/>';
                
                const textSpan = document.createElement('span');
                textSpan.className = 'list-item-text';
                textSpan.textContent = c.name;
                
                listItem.appendChild(icon);
                listItem.appendChild(textSpan);
                
                listItem.addEventListener('click', () => {
                    hasUserSelectionInteraction = true;
                    // Remove active class from all items
                    checklistList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedChecklist = {
                        name: c.name
                    };
                    checklistSelectHidden.value = currentSelectedChecklist.name;
                    
                    // Checklist controls downstream process/paper selections.
                    resetSubsequentSelections('checklist');
                    
                    // Show process column with animation and load processes
                    if (processColumn.style.display === 'none' || !processColumn.style.display) {
                        processColumn.style.display = 'block';
                        processColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                    updateLoadButtonState();
                    loadProcesses();
                });
                
                // Pre-select if re-rendering
                if (!hasUserSelectionInteraction && SELECTED_CHECKLIST && c.name === SELECTED_CHECKLIST) {
                    listItem.classList.add('active');
                    currentSelectedChecklist = {
                        name: c.name
                    };
                    checklistSelectHidden.value = currentSelectedChecklist.name;
                    if (processColumn.style.display === 'none' || !processColumn.style.display) {
                        processColumn.style.display = 'block';
                        processColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                }
                
                checklistList.appendChild(listItem);
            });
            
            // If a checklist was pre-selected, load processes
            if (!hasUserSelectionInteraction && SELECTED_CHECKLIST) {
                await loadProcesses();
            }
        } catch (e) {
            console.error('Error loading checklists:', e);
            checklistList.innerHTML = '<div class="text-center p-4" style="color: #dc3545; font-size: 0.85rem;">Error loading checklists.</div>';
        }
    }

    // Load Papers
    async function loadPapers() {
        if (!currentSelectedCollection || !currentSelectedProcess || !currentSelectedChecklist) return;
        
        paperList.innerHTML = '<div class="text-center p-4" style="color: #64748b;"><div class="spinner-border spinner-border-sm me-2"></div>Loading...</div>';
        try {
            const res = await fetch(`/human_verification/api/papers_with_results?collection_name=${currentSelectedCollection.slug}&process_name=${currentSelectedProcess.slug}&checklist_name=${encodeURIComponent(currentSelectedChecklist.name)}`);
            const papers = await res.json();
            
            paperList.innerHTML = '';
            if (papers.length === 0) {
                paperList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">No papers found.</div>';
                loadBtn.disabled = true;
                return;
            }
            
            papers.forEach(p => {
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action';
                
                // Add paper icon
                const icon = document.createElement('svg');
                icon.className = 'list-item-icon';
                icon.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                icon.setAttribute('fill', 'currentColor');
                icon.setAttribute('viewBox', '0 0 16 16');
                icon.innerHTML = '<path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/>';
                
                const nameSpan = document.createElement('span');
                nameSpan.className = 'list-item-text';
                nameSpan.textContent = p.filename || p.paper_id;
                
                listItem.appendChild(icon);
                listItem.appendChild(nameSpan);
                
                listItem.addEventListener('click', () => {
                    hasUserSelectionInteraction = true;
                    // Remove active class from all items
                    paperList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedPaper = {
                        paper_id: p.paper_id || p.filename,
                        filename: p.filename || p.paper_id
                    };
                    paperSelect.value = currentSelectedPaper.paper_id;
                    loadBtn.disabled = false;
                    updateLoadButtonState();
                });
                
                // Pre-select if re-rendering
                if (!hasUserSelectionInteraction && SELECTED_PAPER && (p.paper_id === SELECTED_PAPER || p.filename === SELECTED_PAPER)) {
                    listItem.classList.add('active');
                    currentSelectedPaper = {
                        paper_id: p.paper_id || p.filename,
                        filename: p.filename || p.paper_id
                    };
                    paperSelect.value = currentSelectedPaper.paper_id;
                    loadBtn.disabled = false;
                }
                
                paperList.appendChild(listItem);
            });
            updateLoadButtonState();
        } catch (e) {
            console.error('Error loading papers:', e);
            paperList.innerHTML = '<div class="text-center p-4" style="color: #dc3545; font-size: 0.85rem;">Error loading papers.</div>';
            loadBtn.disabled = true;
            updateLoadButtonState();
        }
    }

    // Initial load
    await loadCollections();
    
    // Panel Toggle Functionality
    const selectionCard = document.querySelector('.selection-card');
    const panelToggleBtn = document.getElementById('panelToggleBtn');
    const collapsedToggleBtn = document.getElementById('collapsedToggleBtn');
    const collapsedToggleContainer = document.getElementById('collapsedToggleContainer');
    
    function togglePanel() {
        if (selectionCard.classList.contains('collapsed')) {
            // Expand panel
            selectionCard.classList.remove('collapsed');
            collapsedToggleContainer.classList.remove('show');
            
            // Smooth scroll to top of panel
            setTimeout(() => {
                selectionCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);
        } else {
            // Collapse panel
            selectionCard.classList.add('collapsed');
            collapsedToggleContainer.classList.add('show');
        }
    }
    
    if (panelToggleBtn) {
        panelToggleBtn.addEventListener('click', togglePanel);
    }
    
    if (collapsedToggleBtn) {
        collapsedToggleBtn.addEventListener('click', togglePanel);
    }

    const controlForm = document.getElementById('controlForm');
    if (loadBtn && controlForm) {
        loadBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (loadBtn.disabled) return;
            if (selectionMatchesDisplayed()) {
                window.location.href = '/human_verification/';
            } else {
                // Auto-collapse selection panel before submit so review area is in view after reload
                if (selectionCard && !selectionCard.classList.contains('collapsed')) {
                    selectionCard.classList.add('collapsed');
                    if (collapsedToggleContainer) collapsedToggleContainer.classList.add('show');
                }
                controlForm.requestSubmit();
            }
        });
    }

    // Automatic Verification with Ground-Truth
    if (groundTruthVerifyBtn && groundTruthFileInput) {
        groundTruthVerifyBtn.addEventListener('click', () => groundTruthFileInput.click());
        groundTruthFileInput.addEventListener('change', async (e) => {
            const files = e.target.files;
            if (!files || files.length === 0) return;
            if (!currentSelectedCollection || !currentSelectedProcess || !currentSelectedChecklist) {
                alert('Please select collection, process, and checklist first.');
                return;
            }
            const formData = new FormData();
            formData.append('collection_name', currentSelectedCollection.slug || currentSelectedCollection.name);
            formData.append('process_name', currentSelectedProcess.slug || currentSelectedProcess.name);
            formData.append('checklist_name', currentSelectedChecklist.name);
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
            const overlay = document.getElementById('groundTruthProgressOverlay');
            const progressBar = document.getElementById('groundTruthProgressBar');
            const progressLabel = document.getElementById('groundTruthProgressLabel');
            const progressFilename = document.getElementById('groundTruthProgressFilename');
            if (overlay) overlay.classList.remove('d-none');
            if (progressBar) progressBar.style.width = '0%';
            if (progressLabel) progressLabel.textContent = `Comparing 0/${files.length}...`;
            if (progressFilename) progressFilename.textContent = '';
            try {
                const res = await fetch('/human_verification/api/ground-truth-verify', { method: 'POST', body: formData });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.error || 'Verification request failed');
                }
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const parts = buffer.split('\n\n');
                    buffer = parts.pop() || '';
                    for (const part of parts) {
                        const m = part.match(/event: (\S+)\ndata: (.*)/s);
                        if (!m) continue;
                        const [, event, dataStr] = m;
                        let data;
                        try { data = JSON.parse(dataStr); } catch (_) { continue; }
                        if (event === 'progress') {
                            const pct = data.total ? Math.round((data.current / data.total) * 100) : 0;
                            if (progressBar) progressBar.style.width = pct + '%';
                            if (progressLabel) progressLabel.textContent = `Comparing ${data.current}/${data.total}...`;
                            if (progressFilename) progressFilename.textContent = data.message || data.filename || '';
                        } else if (event === 'complete') {
                            if (progressBar) progressBar.style.width = '100%';
                            if (progressLabel) progressLabel.textContent = 'Complete';
                            const msg = `Processed: ${data.processed_count || 0}, Skipped: ${data.skipped_count || 0}, Total: ${data.total || 0}`;
                            if (progressFilename) progressFilename.textContent = msg;
                            if (data.errors && data.errors.length) {
                                progressFilename.textContent = msg + '. Errors: ' + data.errors.map(e => e.file + ': ' + e.error).join('; ');
                            }
                            setTimeout(() => {
                                if (overlay) overlay.classList.add('d-none');
                                groundTruthFileInput.value = '';
                                if (currentSelectedChecklist) loadPapers();
                            }, 1500);
                        } else if (event === 'error') {
                            if (progressLabel) progressLabel.textContent = 'Error';
                            if (progressFilename) progressFilename.textContent = data.message || 'An error occurred';
                            setTimeout(() => {
                                if (overlay) overlay.classList.add('d-none');
                                groundTruthFileInput.value = '';
                            }, 3000);
                        }
                    }
                }
            } catch (err) {
                if (progressLabel) progressLabel.textContent = 'Error';
                if (progressFilename) progressFilename.textContent = err.message || 'Request failed';
                setTimeout(() => {
                    if (overlay) overlay.classList.add('d-none');
                    groundTruthFileInput.value = '';
                }, 3000);
            }
        });
    }
    
    // Ensure dropdowns are enabled even when review_payload is present (after saving)
    setTimeout(() => {
        if (INITIAL_DATA.length > 0) {
            // Auto-collapse selection panel so the review area is in view
            if (selectionCard && !selectionCard.classList.contains('collapsed')) {
                selectionCard.classList.add('collapsed');
                if (collapsedToggleContainer) collapsedToggleContainer.classList.add('show');
            }
            // Review interface is shown, but we should still allow changing the selection
            if (SELECTED_COLLECTION) {
                const activeItem = collectionList.querySelector('.list-group-item.active');
                if (activeItem) {
                    if (checklistColumn.style.display === 'none' || !checklistColumn.style.display) {
                        checklistColumn.style.display = 'block';
                        checklistColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                    if (SELECTED_CHECKLIST) {
                        loadChecklists().then(() => {
                            if (SELECTED_PROCESS) {
                                if (processColumn.style.display === 'none' || !processColumn.style.display) {
                                    processColumn.style.display = 'block';
                                    processColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                                }
                                loadProcesses().then(() => {
                                    if (SELECTED_PAPER) {
                                        if (paperColumn.style.display === 'none' || !paperColumn.style.display) {
                                            paperColumn.style.display = 'block';
                                            paperColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                                        }
                                        loadPapers();
                                    }
                                });
                            }
                        });
                    }
                }
            }
        }
        
        // Ensure the original PDF URL is stored in the data attribute
        const frame = document.getElementById('pdfFrame');
        if (frame && !frame.getAttribute('data-original-url')) {
            // Extract base URL from current src and store it
            const currentSrc = frame.src || '';
            const baseUrl = currentSrc.split('#')[0];
            if (baseUrl) {
                frame.setAttribute('data-original-url', baseUrl);
            }
        }
    }, 100);
});

// Review Logic
if (INITIAL_DATA.length > 0) {
    let currentIndex = 0;
    const entries = INITIAL_DATA;
    
    // DOM Elements
    const qText = document.getElementById('qText');
    const qAnswerBadge = document.getElementById('qAnswerBadge');
    const evidenceContainer = document.getElementById('evidenceContainer');
    const progressLabel = document.getElementById('progressLabel');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const hiddenInputs = document.getElementById('hiddenInputs');
    
    // Verification Controls
    const vCorrect = document.getElementById('v_correct');
    const vIncorrect = document.getElementById('v_incorrect');
    const vComment = document.getElementById('verifyComment');
    const radios = document.querySelectorAll('.verify-radio');

    // State for verification (persisted in JS memory before save)
    // Initialize from server data
    const verificationState = {};
    entries.forEach(entry => {
        verificationState[entry.question_id] = {
            status: entry.human_is_correct === true ? 'correct' : (entry.human_is_correct === false ? 'incorrect' : null),
            comment: entry.human_comment || ''
        };
    });

    function renderQuestion(index) {
        const entry = entries[index];
        qText.textContent = entry.question_text;
        
        // Automated Answer
        if (entry.automated_answer === true) {
            qAnswerBadge.textContent = "YES";
            qAnswerBadge.className = "badge rounded-pill bg-success";
        } else if (entry.automated_answer === false) {
            qAnswerBadge.textContent = "NO";
            qAnswerBadge.className = "badge rounded-pill bg-danger";
        } else {
            qAnswerBadge.textContent = "N/A";
            qAnswerBadge.className = "badge rounded-pill bg-secondary";
        }

        // Supporting Texts
        evidenceContainer.innerHTML = '';
        const supportingTexts = entry.supporting_texts || [];
        if (Array.isArray(supportingTexts) && supportingTexts.length > 0) {
            supportingTexts.forEach((st, stIndex) => {
                const div = document.createElement('div');
                div.className = 'evidence-item';
                
                let pageHtml = '';
                if (st.page_number && st.page_number !== -1) {
                    pageHtml = `<span class="page-badge" onclick="jumpToPage(${st.page_number})">Page ${st.page_number}</span>`;
                } else {
                    pageHtml = `<span class="badge bg-light text-dark border mb-2">Analysis</span>`;
                }
                
                // Get highlight text (use highlight_text if available, otherwise text_crop)
                const highlightText = st.highlight_text || st.text_crop || '';
                const pageNumber = st.page_number && st.page_number !== -1 ? st.page_number : null;
                
                // Escape HTML for safe display
                const safeTextCrop = (st.text_crop || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const safeExplanation = (st.short_explanation || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                
                let explanationHtml = '';
                if (safeExplanation) {
                    explanationHtml = `<div class="supporting-text-explanation" style="margin-top: 0.5rem; padding: 0.5rem; background-color: #f8f9fa; border-left: 3px solid #0d6efd; font-size: 0.875rem; color: #495057;"><strong>Explanation:</strong> ${safeExplanation}</div>`;
                }
                
                div.innerHTML = `
                    ${pageHtml}
                    <div class="evidence-box" 
                         data-page="${pageNumber || ''}" 
                         data-text="${(highlightText || '').replace(/"/g, '&quot;')}"
                         data-evidence-index="${stIndex}">
                        ${safeTextCrop}
                    </div>
                    ${explanationHtml}
                `;
                
                // Add click event listener instead of inline onclick
                const evidenceBox = div.querySelector('.evidence-box');
                if (evidenceBox && pageNumber) {
                    evidenceBox.addEventListener('click', function() {
                        const text = this.getAttribute('data-text') || '';
                        highlightEvidence(pageNumber, text);
                    });
                }
                
                evidenceContainer.appendChild(div);
            });
        } else {
            evidenceContainer.innerHTML = `
                <div class="text-center py-4">
                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="#cbd5e1" viewBox="0 0 16 16" class="mb-2">
                        <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/>
                    </svg>
                    <p class="text-muted small mb-0">No supporting text provided for this question.</p>
                </div>
            `;
        }

        // Update Controls
        progressLabel.textContent = `Question ${index + 1} of ${entries.length}`;
        prevBtn.disabled = index === 0;
        nextBtn.disabled = index === entries.length - 1;

        // Load saved verification state for this question
        const state = verificationState[entry.question_id];
        vCorrect.checked = state.status === 'correct';
        vIncorrect.checked = state.status === 'incorrect';
        // Clear checks if null
        if (!state.status) {
            vCorrect.checked = false;
            vIncorrect.checked = false;
        }
        vComment.value = state.comment;
    }

    // Save state when moving away
    function saveCurrentState() {
        const entry = entries[currentIndex];
        let status = null;
        if (vCorrect.checked) status = 'correct';
        if (vIncorrect.checked) status = 'incorrect';
        
        verificationState[entry.question_id] = {
            status: status,
            comment: vComment.value
        };
        
        updateHiddenInputs();
    }

    function updateHiddenInputs() {
        hiddenInputs.innerHTML = '';
        Object.keys(verificationState).forEach(qId => {
            const state = verificationState[qId];
            if (state.status) {
                const inputStatus = document.createElement('input');
                inputStatus.type = 'hidden';
                inputStatus.name = `verify_status::${qId}`;
                inputStatus.value = state.status;
                hiddenInputs.appendChild(inputStatus);
            }
            
            if (state.comment) {
                const inputComment = document.createElement('input');
                inputComment.type = 'hidden';
                inputComment.name = `verify_comment::${qId}`;
                inputComment.value = state.comment;
                hiddenInputs.appendChild(inputComment);
            }
        });
    }

    // Navigation Handlers
    prevBtn.addEventListener('click', () => {
        saveCurrentState();
        if (currentIndex > 0) {
            currentIndex--;
            renderQuestion(currentIndex);
        }
    });

    nextBtn.addEventListener('click', () => {
        saveCurrentState();
        if (currentIndex < entries.length - 1) {
            currentIndex++;
            renderQuestion(currentIndex);
        }
    });
    
    // Input Handlers (to save state immediately on interaction if needed, or just on nav)
    // Better to update state on interaction so submission works without navigation
    radios.forEach(r => r.addEventListener('change', saveCurrentState));
    vComment.addEventListener('input', saveCurrentState);

    // Initial Render
    renderQuestion(0);
    updateHiddenInputs(); // Initialize hidden inputs with loaded data
}

// Global Jump Function
window.jumpToPage = function(page) {
    const frame = document.getElementById('pdfFrame');
    if (!frame) return;
    
    // Get the original URL from the data attribute (set in HTML template)
    let originalPdfUrl = frame.getAttribute('data-original-url');
    
    // Fallback: extract from current src if data attribute is not available
    if (!originalPdfUrl) {
        const currentSrc = frame.src || '';
        originalPdfUrl = currentSrc.split('#')[0];
        // Store it for future use
        frame.setAttribute('data-original-url', originalPdfUrl);
    }
    
    // Construct the new URL with page number
    const newUrl = `${originalPdfUrl}#page=${page}&view=FitH`;
    
    // Update the iframe src to navigate to the page
    // Note: Setting src will cause a reload, but using the original URL ensures consistency
    frame.src = newUrl;
}

// PDF.js variables (for future enhancement - currently using iframe)
let pdfDoc = null;
let pdfViewer = {
    currentPageNumber: 1,
    scale: 1.5
};
const pdfCanvas = document.getElementById('pdfCanvas');
const pdfViewerContainer = document.getElementById('pdfViewerContainer');
const pdfFrame = document.getElementById('pdfFrame');

// Highlight evidence function - simplified version using iframe
window.highlightEvidence = function(pageNumber, highlightText) {
    if (!pageNumber || !highlightText) {
        console.warn('Missing page number or highlight text');
        return;
    }

    // Jump to the page - the iframe will handle the display
    jumpToPage(pageNumber);
    
    // Note: Direct text highlighting in iframe PDFs is limited due to browser security
    // The page jump is the best we can do with the native PDF viewer
    // Users can use the browser's find function (Ctrl/Cmd+F) to search for the text
};
