document.addEventListener('DOMContentLoaded', () => {
    const collectionList = document.getElementById('collectionList');
    const processList = document.getElementById('processList');
    const checklistList = document.getElementById('checklistList');
    const collectionColumn = document.getElementById('collectionColumn');
    const processColumn = document.getElementById('processColumn');
    const checklistColumn = document.getElementById('checklistColumn');
    const loadBtn = document.getElementById('loadBtn');
    
    const dashboard = document.getElementById('dashboard');
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');
    
    let automatedStackedChart = null;
    let humanChart = null;
    let lastReportData = null;
    let lastReportCollectionName = '';
    let lastReportChecklistName = '';
    
    function sanitizeFilenamePart(s) {
        if (s == null || s === '') return 'export';
        return String(s).replace(/[/\\:*?"<>|]/g, '_').replace(/\s+/g, '_').slice(0, 80);
    }
    
    // Store selected values
    let currentSelectedCollection = null;
    let currentSelectedProcess = null;
    let currentSelectedChecklist = null;
    
    // Helper function to reset subsequent selections
    function resetSubsequentSelections(resetFrom) {
        if (resetFrom === 'collection') {
            currentSelectedChecklist = null;
            currentSelectedProcess = null;
            
            // Clear and hide subsequent columns
            checklistList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a collection first...</div>';
            processList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a checklist first...</div>';
            
            checklistColumn.style.display = 'none';
            processColumn.style.display = 'none';
            
            loadBtn.disabled = true;
        } else if (resetFrom === 'checklist') {
            // Reset process
            currentSelectedProcess = null;
            
            // Clear and hide process column
            processList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">Select a checklist first...</div>';
            
            processColumn.style.display = 'none';
            
            loadBtn.disabled = true;
        }
    }
    
    // Load Collections
    async function loadCollections() {
        collectionList.innerHTML = '<div class="text-center p-4" style="color: #64748b;"><div class="spinner-border spinner-border-sm me-2"></div>Loading...</div>';
        try {
            const res = await fetch('/analysis/api/collections');
            const collections = await res.json();
            
            collectionList.innerHTML = '';
            if (collections.length === 0) {
                collectionList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">No collections found.</div>';
                return;
            }
            
            collections.forEach(c => {
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action';
                listItem.dataset.collectionSlug = c.slug;
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
                    // Check if this is a different collection than currently selected
                    const wasDifferentCollection = currentSelectedCollection && 
                        currentSelectedCollection.slug !== c.slug;
                    
                    // Remove active class from all items
                    collectionList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedCollection = {
                        slug: c.slug,
                        name: c.name
                    };
                    
                    // If collection changed, reset subsequent selections
                    if (wasDifferentCollection) {
                        resetSubsequentSelections('collection');
                    }
                    
                    // Show checklist column with animation and load checklists
                    if (checklistColumn.style.display === 'none' || !checklistColumn.style.display) {
                        checklistColumn.style.display = 'block';
                        checklistColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                    loadChecklists();
                });
                
                collectionList.appendChild(listItem);
            });
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
            const res = await fetch(`/analysis/api/processes?collection_name=${currentSelectedCollection.slug}`);
            const processes = await res.json();
            
            processList.innerHTML = '';
            if (processes.length === 0) {
                processList.innerHTML = '<div class="text-center p-4" style="color: #64748b; font-size: 0.85rem;">No processes found.</div>';
                return;
            }
            
            processes.forEach(p => {
                const displayName = (p.data && p.data.name) ? p.data.name : (p.name || p.slug);
                const slugValue = p.slug || p.name;
                
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
                    // Remove active class from all items
                    processList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedProcess = {
                        slug: p.slug || p.name,
                        name: displayName
                    };
                    
                    // Update button state
                    loadBtn.disabled = !(currentSelectedCollection && currentSelectedProcess && currentSelectedChecklist);
                });
                
                processList.appendChild(listItem);
            });
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
            const res = await fetch('/analysis/api/checklists');
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
                    // Remove active class from all items
                    checklistList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedChecklist = {
                        name: c.name
                    };
                    
                    // Checklist controls downstream process selection.
                    resetSubsequentSelections('checklist');

                    // Show process column with animation and load processes
                    if (processColumn.style.display === 'none' || !processColumn.style.display) {
                        processColumn.style.display = 'block';
                        processColumn.style.animation = 'slideInRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
                    }
                    loadProcesses();
                    loadBtn.disabled = !(currentSelectedCollection && currentSelectedProcess && currentSelectedChecklist);
                });
                
                checklistList.appendChild(listItem);
            });
            
            // Enable button if all are selected
            loadBtn.disabled = !(currentSelectedCollection && currentSelectedProcess && currentSelectedChecklist);
        } catch (e) {
            console.error('Error loading checklists:', e);
            checklistList.innerHTML = '<div class="text-center p-4" style="color: #dc3545; font-size: 0.85rem;">Error loading checklists.</div>';
        }
    }
    
    // Initial load
    loadCollections();
    
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
    
    // Load Report Button Handler
    loadBtn.addEventListener('click', async () => {
        if (!currentSelectedCollection || !currentSelectedProcess || !currentSelectedChecklist) return;
        
        emptyState.style.display = 'none';
        dashboard.style.display = 'none';
        loadingState.style.display = 'block';
        
        try {
            const res = await fetch(`/analysis/api/report?collection_name=${currentSelectedCollection.slug}&process_name=${currentSelectedProcess.slug}&checklist_name=${encodeURIComponent(currentSelectedChecklist.name)}`);
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || `Request failed (${res.status})`);
            }
            const data = await res.json();
            if (!data || !data.automated || !data.human || !Array.isArray(data.breakdown)) {
                throw new Error('Invalid report data from server');
            }
            lastReportCollectionName = sanitizeFilenamePart(currentSelectedCollection?.slug || currentSelectedCollection?.name);
            lastReportChecklistName = sanitizeFilenamePart(currentSelectedChecklist?.name);
            renderDashboard(data);
            
            loadingState.style.display = 'none';
            dashboard.style.display = 'block';
            // Auto-collapse selection panel so the report is in view
            if (selectionCard && !selectionCard.classList.contains('collapsed')) {
                selectionCard.classList.add('collapsed');
                if (collapsedToggleContainer) collapsedToggleContainer.classList.add('show');
            }
        } catch (e) {
            console.error(e);
            lastReportData = null;
            lastReportCollectionName = '';
            lastReportChecklistName = '';
            document.getElementById('exportAutomatedBtn') && (document.getElementById('exportAutomatedBtn').disabled = true);
            document.getElementById('exportHumanBtn') && (document.getElementById('exportHumanBtn').disabled = true);
            alert("Failed to load report: " + (e.message || 'Unknown error'));
            loadingState.style.display = 'none';
            emptyState.style.display = 'block';
        }
    });
    
    function downloadJson(obj, filename) {
        const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }
    
    document.getElementById('exportAutomatedBtn')?.addEventListener('click', () => {
        if (!lastReportData?.automated) return;
        const auto = lastReportData.automated;
        const dist = auto.distribution || {};
        const totalAnswers = (dist.yes || 0) + (dist.no || 0) + (dist.na || 0);
        const yesRatePct = totalAnswers > 0 ? Math.round((dist.yes || 0) / totalAnswers * 100) : 0;
        const breakdown = Array.isArray(lastReportData.breakdown) ? lastReportData.breakdown : [];
        const payload = {
            export_type: 'automated_response_analysis',
            generated_at: new Date().toISOString(),
            summary: {
                total_papers: auto.total_papers ?? 0,
                total_answers: totalAnswers,
                yes_count: dist.yes ?? 0,
                no_count: dist.no ?? 0,
                yes_rate_pct: yesRatePct
            },
            per_question: breakdown.map(b => ({
                question: b.question ?? '',
                yes_pct: b.yes_pct ?? 0,
                no_pct: b.no_pct != null ? b.no_pct : (100 - (b.yes_pct || 0)),
                yes_count: b.yes_count ?? 0,
                no_count: b.no_count ?? 0,
                total: b.total ?? 0
            }))
        };
        const filename = `${lastReportCollectionName}_${lastReportChecklistName}_automated.json`;
        downloadJson(payload, filename);
    });
    
    document.getElementById('exportHumanBtn')?.addEventListener('click', () => {
        if (!lastReportData?.human) return;
        const human = lastReportData.human;
        const agreement = human.agreement || {};
        const totalVerifications = (agreement.agreed ?? 0) + (agreement.disagreed ?? 0);
        const breakdown = Array.isArray(lastReportData.breakdown) ? lastReportData.breakdown : [];
        const payload = {
            export_type: 'human_verification_analysis',
            generated_at: new Date().toISOString(),
            summary: {
                papers_verified: human.verified_papers_count ?? 0,
                verification_coverage_pct: human.verification_coverage_pct ?? 0,
                total_verifications: totalVerifications,
                agreed_count: agreement.agreed ?? 0,
                disagreed_count: agreement.disagreed ?? 0,
                agreement_rate_pct: agreement.agreement_rate ?? 0
            },
            per_question: breakdown.map(b => ({
                question: b.question ?? '',
                verified_count: b.verified_count ?? 0,
                agreed_count: b.agreed_count ?? 0,
                disagreed_count: b.disagreed_count ?? 0,
                agreement_rate_pct: b.agreement_rate ?? 0
            }))
        };
        const filename = `${lastReportCollectionName}_${lastReportChecklistName}_verified.json`;
        downloadJson(payload, filename);
    });
    
    function renderDashboard(data) {
        lastReportData = data;
        const exportAutomatedBtn = document.getElementById('exportAutomatedBtn');
        const exportHumanBtn = document.getElementById('exportHumanBtn');
        if (exportAutomatedBtn) exportAutomatedBtn.disabled = false;
        if (exportHumanBtn) exportHumanBtn.disabled = false;
        
        // Top Stats
        const auto = data.automated;
        const human = data.human;
        
        document.getElementById('statTotalPapers').textContent = auto.total_papers;
        
        const totalAnswers = auto.distribution.yes + auto.distribution.no + auto.distribution.na;
        const yesRate = totalAnswers > 0 ? Math.round(auto.distribution.yes / totalAnswers * 100) : 0;
        document.getElementById('statYesRate').textContent = `${yesRate}%`;
        
        document.getElementById('statVerifiedCount').textContent = human.verified_papers_count;
        document.getElementById('statVerifiedPct').textContent = `${human.verification_coverage_pct}%`;
        
        document.getElementById('statAgreement').textContent = `${human.agreement.agreement_rate}%`;
        
        // ----- Automated: overall summary bar + legend -----
        const yesPctOverall = totalAnswers > 0 ? Math.round(auto.distribution.yes / totalAnswers * 100) : 0;
        const noPctOverall = totalAnswers > 0 ? Math.round(auto.distribution.no / totalAnswers * 100) : 0;
        const overallBarYes = document.getElementById('overallBarYes');
        const overallBarNo = document.getElementById('overallBarNo');
        const overallLegend = document.getElementById('overallLegend');
        if (overallBarYes) overallBarYes.style.width = yesPctOverall + '%';
        if (overallBarNo) overallBarNo.style.width = noPctOverall + '%';
        if (overallLegend) {
            overallLegend.innerHTML = `
                <span class="overall-legend-item"><span class="overall-legend-dot overall-legend-dot-yes"></span><strong>Yes</strong> ${auto.distribution.yes} (${yesPctOverall}%)</span>
                <span class="overall-legend-item"><span class="overall-legend-dot overall-legend-dot-no"></span><strong>No</strong> ${auto.distribution.no} (${noPctOverall}%)</span>
            `;
        }
        
        // ----- Automated: stacked horizontal bar (Yes vs No by question) -----
        const breakdownSorted = [...data.breakdown].sort((a, b) => (a.yes_pct || 0) - (b.yes_pct || 0));
        const questionLabels = breakdownSorted.map(b => {
            const q = b.question || '';
            return q.length > 50 ? q.slice(0, 47) + '...' : q;
        });
        const ctxStacked = document.getElementById('automatedChartStacked');
        const stackedWrap = ctxStacked && ctxStacked.closest('.panel-chart-wrap-stacked');
        if (stackedWrap) stackedWrap.style.height = Math.min(420, Math.max(220, breakdownSorted.length * 32)) + 'px';
        if (ctxStacked) {
            if (automatedStackedChart) automatedStackedChart.destroy();
            automatedStackedChart = new Chart(ctxStacked.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: questionLabels,
                    datasets: [
                        { label: 'Yes', data: breakdownSorted.map(b => b.yes_pct || 0), backgroundColor: '#198754', barThickness: 'flex', order: 2 },
                        { label: 'No', data: breakdownSorted.map(b => b.no_pct != null ? b.no_pct : (100 - (b.yes_pct || 0))), backgroundColor: '#dc3545', barThickness: 'flex', order: 1 }
                    ]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top', labels: { usePointStyle: true, padding: 12 } },
                        tooltip: {
                            callbacks: {
                                title: function(context) {
                                    const i = context[0].dataIndex;
                                    return breakdownSorted[i] ? (breakdownSorted[i].question || 'Question') : '';
                                },
                                afterBody: function(context) {
                                    const i = context[0].dataIndex;
                                    const b = breakdownSorted[i];
                                    const total = b && (b.total != null ? b.total : (b.yes_count + b.no_count));
                                    if (total == null) return '';
                                    return `Total answers: ${total}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            stacked: true,
                            max: 100,
                            ticks: { callback: v => v + '%' },
                            grid: { display: true }
                        },
                        y: {
                            stacked: true,
                            ticks: { font: { size: 11 }, maxRotation: 0, autoSkip: false }
                        }
                    }
                }
            });
        }
        
        // Automated Breakdown Table
        const autoBody = document.getElementById('automatedTableBody');
        autoBody.innerHTML = '';
        data.breakdown.forEach(item => {
            const row = `<tr>
                <td>${item.question}</td>
                <td class="text-end fw-bold">${item.yes_pct}%</td>
            </tr>`;
            autoBody.innerHTML += row;
        });
        
        // Human Chart
        const ctxHuman = document.getElementById('humanChart').getContext('2d');
        if(humanChart) humanChart.destroy();
        humanChart = new Chart(ctxHuman, {
            type: 'pie',
            data: {
                labels: ['Agreed', 'Disagreed'],
                datasets: [{
                    data: [human.agreement.agreed, human.agreement.disagreed],
                    backgroundColor: ['#ffc107', '#fd7e14'],
                    borderWidth: 0
                }]
            },
            options: {
                maintainAspectRatio: false,
                plugins: { legend: { display: false } }
            }
        });
        
        // Verification Table
        const verBody = document.getElementById('verificationTableBody');
        verBody.innerHTML = '';
        data.breakdown.forEach(item => {
            // Only show if there's verification data
            if(item.verified_count > 0) {
                const row = `<tr>
                    <td>${item.question}</td>
                    <td class="text-center">${item.verified_count}</td>
                    <td class="text-end fw-bold ${item.agreement_rate > 80 ? 'text-success' : (item.agreement_rate < 50 ? 'text-danger' : 'text-warning')}">
                        ${item.agreement_rate}%
                    </td>
                </tr>`;
                verBody.innerHTML += row;
            }
        });
    }
});
