import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import ReactFlow, {
    addEdge,
    Background,
    Controls,
    MiniMap,
    Handle,
    Position,
    useNodesState,
    useEdgesState,
    ReactFlowProvider,
    useReactFlow
} from 'reactflow';
import htm from 'htm';
import clsx from 'clsx';

const html = htm.bind(React.createElement);

// --- Text Editor Modal Component ---
const TextEditorModal = ({ isOpen, onClose, onSave, fieldName, fieldLabel, currentValue }) => {
    const [value, setValue] = useState(currentValue || '');
    const textareaRef = React.useRef(null);

    useEffect(() => {
        if (isOpen) {
            setValue(currentValue || '');
            // Focus textarea when modal opens
            setTimeout(() => {
                if (textareaRef.current) {
                    textareaRef.current.focus();
                    textareaRef.current.setSelectionRange(textareaRef.current.value.length, textareaRef.current.value.length);
                }
            }, 100);
        }
    }, [isOpen, currentValue]);

    useEffect(() => {
        if (!isOpen) return;

        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };

        document.addEventListener('keydown', handleEscape);
        return () => document.removeEventListener('keydown', handleEscape);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const handleSave = () => {
        onSave(value);
        onClose();
    };

    return html`
            <div className="text-editor-modal-overlay" onClick=${(e) => e.target.className === 'text-editor-modal-overlay' && onClose()}>
                <div className="text-editor-modal" onClick=${(e) => e.stopPropagation()}>
                    <div className="text-editor-modal-header">
                        <h5>Edit ${fieldLabel || fieldName}</h5>
                        <button className="text-editor-modal-close" onClick=${onClose}>
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                                <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8z"/>
                            </svg>
                        </button>
                    </div>
                    <div className="text-editor-modal-body">
                        <label>${fieldLabel || fieldName}</label>
                        <textarea
                            ref=${textareaRef}
                            className="text-editor-modal-textarea"
                            value=${value}
                            onChange=${(e) => setValue(e.target.value)}
                            placeholder="Enter text here..."
                        />
                    </div>
                    <div className="text-editor-modal-footer">
                        <button className="text-editor-modal-btn text-editor-modal-btn-cancel" onClick=${onClose}>
                            Cancel
                        </button>
                        <button className="text-editor-modal-btn text-editor-modal-btn-save" onClick=${handleSave}>
                            Save
                        </button>
                    </div>
                </div>
            </div>
        `;
};

// --- Import Component Modal ---
const ImportComponentModal = ({ isOpen, onClose, onSuccess }) => {
    const [file, setFile] = useState(null);
    const [dragOver, setDragOver] = useState(false);
    const [message, setMessage] = useState(null);
    const [loading, setLoading] = useState(false);
    const fileInputRef = React.useRef(null);

    const reset = useCallback(() => {
        setFile(null);
        setDragOver(false);
        setMessage(null);
        setLoading(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
    }, []);

    useEffect(() => {
        if (!isOpen) reset();
    }, [isOpen, reset]);

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f && f.name.toLowerCase().endsWith('.zip')) {
            setFile(f);
            setMessage(null);
        } else {
            setMessage('Please drop a .zip file.');
        }
    }, []);

    const handleDragOver = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragOver(true);
    }, []);

    const handleDragLeave = useCallback((e) => {
        e.preventDefault();
        setDragOver(false);
    }, []);

    const handleFileSelect = useCallback((e) => {
        const f = e.target.files && e.target.files[0];
        if (f && f.name.toLowerCase().endsWith('.zip')) {
            setFile(f);
            setMessage(null);
        } else {
            setMessage('Please select a .zip file.');
        }
    }, []);

    const handleSubmit = useCallback(async () => {
        if (!file) {
            setMessage('Please choose or drop a ZIP file.');
            return;
        }
        setLoading(true);
        setMessage(null);
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch('/review_process_design/api/components/import', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                setMessage(data.error || 'Import failed.');
                return;
            }
            setMessage(data.message || 'Component added successfully.');
            if (onSuccess) onSuccess();
            setTimeout(() => { onClose(); }, 1500);
        } catch (err) {
            setMessage('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    }, [file, onClose, onSuccess]);

    if (!isOpen) return null;

    return html`
        <div className="import-component-modal-overlay" onClick=${(e) => e.target.className === 'import-component-modal-overlay' && onClose()}>
            <div className="import-component-modal" onClick=${(e) => e.stopPropagation()}>
                <div className="import-component-modal-header">
                    <h5>Import New Component</h5>
                    <button type="button" className="import-component-modal-close" onClick=${onClose} aria-label="Close">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8z"/></svg>
                    </button>
                </div>
                <div className="import-component-modal-body">
                    <p className="import-component-modal-hint">Drag and drop a component ZIP file here, or click to choose.</p>
                    <div
                        className=${'import-component-dropzone' + (dragOver ? ' import-component-dropzone-active' : '') + (file ? ' import-component-dropzone-has-file' : '')}
                        onDrop=${handleDrop}
                        onDragOver=${handleDragOver}
                        onDragLeave=${handleDragLeave}
                        onClick=${() => fileInputRef.current && fileInputRef.current.click()}
                    >
                        <input
                            ref=${fileInputRef}
                            type="file"
                            accept=".zip"
                            onChange=${handleFileSelect}
                            style=${{ display: 'none' }}
                        />
                        ${file ? html`<span className="import-component-filename">${file.name}</span>` : html`<span>Drop .zip here or click to browse</span>`}
                    </div>
                    ${message ? html`<div className=${'import-component-message ' + (message.includes('success') || message.includes('added') ? 'import-component-message-success' : 'import-component-message-error')}>${message}</div>` : null}
                </div>
                <div className="import-component-modal-footer">
                    <button type="button" className="import-component-modal-btn import-component-modal-btn-cancel" onClick=${onClose}>Cancel</button>
                    <button type="button" className="import-component-modal-btn import-component-modal-btn-primary" onClick=${handleSubmit} disabled=${!file || loading}>
                        ${loading ? 'Importing…' : 'Import'}
                    </button>
                </div>
            </div>
        </div>
    `;
};

// --- Custom Node Component ---
const GenericNode = ({ id, data, isConnectable, selected, providers = [], embeddingProviders = [], onOpenTextEditor }) => {
    const { label, config_schema, config = {}, onConfigChange, component_id, category } = data;

    const handleChange = (key, value) => {
        if (onConfigChange) {
            onConfigChange(id, key, value);
        }
    };
    
    // Automatically disable RAG when "answer_all_together" is enabled
    useEffect(() => {
        if (component_id === 'question_reviewer' && config.answer_all_together === true && config.use_rag === true) {
            if (onConfigChange) {
                onConfigChange(id, 'use_rag', false);
            }
        }
    }, [config.answer_all_together, config.use_rag, component_id, id, onConfigChange]);

    const openTextEditor = (fieldKey, fieldLabel) => {
        if (onOpenTextEditor) {
            onOpenTextEditor({
                nodeId: id,
                fieldKey,
                fieldLabel,
                currentValue: config[fieldKey] || ''
            });
        }
    };

    const IGNORED_CONFIG = ['collection_name', 'review_process_name', 'paper_name', 'checklist_name', 'force_review'];

    // Function to evaluate ui:if conditions
    const evaluateCondition = useCallback((condition, currentConfig) => {
        if (!condition || typeof condition !== 'object') return true;

        // Check if all conditions in the object are met
        return Object.entries(condition).every(([field, expectedValue]) => {
            let actualValue = currentConfig[field];
            
            // For boolean fields, treat undefined as false
            if (actualValue === undefined && config_schema?.properties?.[field]?.type === 'boolean') {
                actualValue = false;
            }
            
            // Support "not equal" operator: { "$ne": "value" }
            if (expectedValue && typeof expectedValue === 'object' && expectedValue.$ne !== undefined) {
                return actualValue !== expectedValue.$ne;
            }
            
            return actualValue === expectedValue;
        });
    }, [config_schema]);

    // Get visible properties in order (maintains original metadata order)
    const visibleProperties = useMemo(() => {
        if (!config_schema?.properties) return [];

        // For question_reviewer, explicitly define the order to ensure RAG fields appear after use_rag
        const questionReviewerOrder = [
            'provider_id',
            'system_prompt', 
            'force_review',
            'answer_all_together',
            'use_rag',
            'rag_chunking_strategy',
            'rag_top_k',
            'rag_embedding_provider_id'
        ];
        // For specialist, Topic first then Criteria then provider_id
        const specialistOrder = ['topic', 'criteria', 'provider_id'];
        // For paper_loader, Extraction Method first then Extract Pages as Image then Force Execution
        const paperLoaderOrder = ['extraction_method', 'extract_pages_as_image', 'force_execution'];

        const result = [];
        const properties = config_schema.properties;

        const applyExplicitOrder = (order) => {
            for (const key of order) {
                if (!properties[key] || IGNORED_CONFIG.includes(key)) continue;
                const prop = properties[key];
                if (prop['ui:if'] && !evaluateCondition(prop['ui:if'], config)) continue;
                result.push([key, prop]);
            }
            for (const [key, prop] of Object.entries(properties)) {
                if (order.includes(key) || IGNORED_CONFIG.includes(key)) continue;
                if (prop['ui:if'] && !evaluateCondition(prop['ui:if'], config)) continue;
                result.push([key, prop]);
            }
        };

        if (component_id === 'question_reviewer') {
            applyExplicitOrder(questionReviewerOrder);
        } else if (component_id === 'specialist') {
            applyExplicitOrder(specialistOrder);
        } else if (component_id === 'paper_loader') {
            applyExplicitOrder(paperLoaderOrder);
        } else {
            // For other components, use Object.entries() which preserves insertion order
            for (const [key, prop] of Object.entries(properties)) {
                if (IGNORED_CONFIG.includes(key)) {
                    continue;
                }

                // Check ui:if condition
                if (prop['ui:if']) {
                    if (!evaluateCondition(prop['ui:if'], config)) {
                        continue;
                    }
                }

                result.push([key, prop]);
            }
        }
        
        return result;
    }, [config_schema, config, evaluateCondition, component_id]);

    let handles = [];
    // Configure handles based on category... same as before
    if (category === 'pre_process') {
        handles.push(html`<${Handle} type="source" position=${Position.Right} id="out" isConnectable=${isConnectable} />`);
    } else if (category === 'review') {
        handles.push(html`<${Handle} type="target" position=${Position.Left} id="in" isConnectable=${isConnectable} />`);
        handles.push(html`<${Handle} type="source" position=${Position.Right} id="out" isConnectable=${isConnectable} />`);
        handles.push(html`<${Handle} type="source" position=${Position.Bottom} id="tools" isConnectable=${isConnectable} />`);
    } else if (category === 'post_process') {
        handles.push(html`<${Handle} type="target" position=${Position.Left} id="in" isConnectable=${isConnectable} />`);
    } else if (category === 'tool') {
        handles.push(html`<${Handle} type="target" position=${Position.Top} id="in" isConnectable=${isConnectable} />`);
    } else {
        handles.push(html`<${Handle} type="target" position=${Position.Left} id="in" isConnectable=${isConnectable} />`);
        handles.push(html`<${Handle} type="source" position=${Position.Right} id="out" isConnectable=${isConnectable} />`);
    }

    // Get category icon SVG
    const getCategoryIcon = (cat) => {
        const icons = {
            'pre_process': html`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4z"/>
                </svg>`,
            'review': html`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>
                    <path d="M5.255 5.786a.237.237 0 0 0 .241.247h.825c.138 0 .248-.113.266-.25.09-.656.54-1.134 1.342-1.134.686 0 1.314.343 1.314 1.168 0 .635-.374.927-.965 1.371-.673.489-1.206 1.06-1.168 1.987l.003.217a.25.25 0 0 0 .25.246h.811a.25.25 0 0 0 .25-.25v-.105c0-.718.273-.927 1.01-1.486.609-.463 1.244-.977 1.244-2.056 0-1.511-1.276-2.241-2.673-2.241-1.267 0-2.655.59-2.75 2.286m1.557 5.763c0 .533.425.927 1.01.927.609 0 1.028-.394 1.028-.927 0-.552-.42-.94-1.029-.94-.584 0-1.009.388-1.009.94"/>
                </svg>`,
            'post_process': html`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1zM2 0a2 2 0 0 0-2 2v12.793a.5.5 0 0 0 .854.353l2.853-2.853A1 1 0 0 1 4.414 12H14a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2z"/>
                </svg>`,
            'tool': html`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/>
                </svg>`
        };
        return icons[cat] || icons['review'];
    };

    const categoryLabels = {
        'pre_process': 'PRE-PROCESS',
        'review': 'REVIEW',
        'post_process': 'POST-PROCESS',
        'tool': 'EVALUATION'
    };

    return html`
            <div className=${clsx('react-flow__node-custom', { selected })} data-category=${category || 'review'}>
                <div className="node-header">
                    <div className="node-header-label">
                        <span className="node-header-icon">${getCategoryIcon(category || 'review')}</span>
                        <span>${label}</span>
                    </div>
                    ${category ? html`<span className="node-category-badge">${categoryLabels[category] || category.toUpperCase()}</span>` : null}
                </div>
                <div className="node-body">
                    ${handles}
                    <div className="node-controls nodrag">
                        ${visibleProperties.map(([key, prop, originalIndex]) => {
        const shortLabel = prop.label || key;
        const fullDescription = prop.description || '';
        return html`
                                <div className="node-control-item" key=${key}>
                                    <div className="node-control-label-wrapper">
                                        <label title=${fullDescription}>${shortLabel}</label>
                                        ${fullDescription ? html`<div className="node-control-description">${fullDescription}</div>` : null}
                                    </div>
                                    ${prop.type === 'boolean'
                ? html`<div className="form-check"><input type="checkbox" className="form-check-input" checked=${config[key] || false} onChange=${(e) => handleChange(key, e.target.checked)} /></div>`
                : key === 'provider_id'
                    ? html`
                                                <select className="form-select" value=${config[key] || ''} onChange=${(e) => handleChange(key, e.target.value)} onKeyDown=${(e) => e.stopPropagation()}>
                                                    <option value="">Select a provider...</option>
                                                    ${providers.map(p => html`<option key=${p.id} value=${p.id}>${p.name}</option>`)}
                                                </select>`
                    : key === 'rag_embedding_provider_id'
                    ? html`
                                                <select className="form-select" value=${config[key] || ''} onChange=${(e) => handleChange(key, e.target.value)} onKeyDown=${(e) => e.stopPropagation()}>
                                                    <option value="">Select an embedding provider...</option>
                                                    ${embeddingProviders.map(p => html`<option key=${p.id} value=${p.id}>${p.name}</option>`)}
                                                </select>`
                    : prop.enum
                        ? html`
                                                <select className="form-select" value=${config[key] || prop.default || ''} onChange=${(e) => handleChange(key, e.target.value)} onKeyDown=${(e) => e.stopPropagation()}>
                                                    ${prop.enum.map(opt => html`<option key=${opt} value=${opt}>${opt}</option>`)}
                                                </select>`
                        : prop.type === 'integer'
                            ? html`
                                                <input 
                                                    type="number" 
                                                    className="form-control" 
                                                    value=${config[key] || prop.default || ''} 
                                                    min=${prop.minimum !== undefined ? prop.minimum : ''}
                                                    onChange=${(e) => handleChange(key, parseInt(e.target.value) || prop.default || 0)} 
                                                    onKeyDown=${(e) => e.stopPropagation()} 
                                                />`
                            : html`
                                                <div className="text-input-with-editor">
                                                    <input 
                                                        type="text" 
                                                        className="form-control" 
                                                        value=${config[key] || ''} 
                                                        onChange=${(e) => handleChange(key, e.target.value)} 
                                                        placeholder=${prop.default || ''} 
                                                        onKeyDown=${(e) => e.stopPropagation()} 
                                                        onClick=${(e) => {
                                // Open editor on click, but allow normal editing too
                                if (e.detail === 2) { // Double click
                                    e.preventDefault();
                                    openTextEditor(key, fullDescription || shortLabel);
                                }
                            }}
                                                    />
                                                    <button
                                                        className="text-editor-open-btn"
                                                        onClick=${(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                openTextEditor(key, fullDescription || shortLabel);
                            }}
                                                        title="Open in larger editor (or double-click the field)"
                                                    >
                                                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                                                            <path d="M15.502 1.94a.5.5 0 0 1 0 .706L14.459 3.69l-2-2L13.502.646a.5.5 0 0 1 .707 0l1.293 1.293zm-1.75 2.456-2-2L4.939 9.21a.5.5 0 0 0-.121.196l-.805 2.414a.25.25 0 0 0 .316.316l2.414-.805a.5.5 0 0 0 .196-.12l6.813-6.814z"/>
                                                            <path fill-rule="evenodd" d="M1 13.5A1.5 1.5 0 0 0 2.5 15h11a1.5 1.5 0 0 0 1.5-1.5v-11A1.5 1.5 0 0 0 13.5 1H11a.5.5 0 0 0 0 1h2.5a.5.5 0 0 1 .5.5v11a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5V3.5a.5.5 0 0 0-1 0z"/>
                                                        </svg>
                                                    </button>
                                                </div>
                                            `
            }
                                </div>
                            `;
    })}
                    </div>
                </div>
            </div>
        `;
};

// Create node types with providers and text editor callback passed to each node
const createNodeTypes = (providers, embeddingProviders, onOpenTextEditor) => ({
    custom: (props) => {
        return React.createElement(GenericNode, { ...props, providers, embeddingProviders, onOpenTextEditor });
    }
});

// Protected node component IDs that cannot be deleted
const PROTECTED_NODES = ['paper_loader', 'question_reviewer'];

// --- Main Editor Component ---
const ProcessEditor = () => {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [componentsMeta, setComponentsMeta] = useState({});
    const [componentsRefreshKey, setComponentsRefreshKey] = useState(0);
    const [showImportModal, setShowImportModal] = useState(false);
    const [contextMenu, setContextMenu] = useState(null);
    const [providers, setProviders] = useState([]);
    const [embeddingProviders, setEmbeddingProviders] = useState([]);
    const reactFlowInstance = useReactFlow();

    useEffect(() => {
        window.openImportComponentModal = () => setShowImportModal(true);
        window.refreshComponentsList = () => setComponentsRefreshKey(k => k + 1);
        return () => {
            delete window.openImportComponentModal;
            delete window.refreshComponentsList;
        };
    }, []);

    // Text editor modal handler - uses global function
    const openTextEditor = useCallback(({ nodeId, fieldKey, fieldLabel, currentValue }) => {
        if (window.openTextEditor) {
            window.openTextEditor({ nodeId, fieldKey, fieldLabel, currentValue });
        }
    }, []);

    // Store save callback globally so modal can access it
    useEffect(() => {
        window.textEditorSaveCallback = (nodeId, fieldKey, value) => {
            const node = nodes.find(n => n.id === nodeId);
            if (node && node.data.onConfigChange) {
                node.data.onConfigChange(nodeId, fieldKey, value);
            }
        };
    }, [nodes]);

    // Auto-fit view when nodes are loaded (similar to clicking the fit view button)
    // Use a ref to track if we should auto-fit (set by setFlow when loading)
    const shouldAutoFitRef = useRef(false);
    useEffect(() => {
        if (shouldAutoFitRef.current && nodes.length > 0 && reactFlowInstance && reactFlowInstance.fitView) {
            shouldAutoFitRef.current = false; // Reset flag
            // Use requestAnimationFrame to ensure nodes are rendered to DOM
            const timeoutId = setTimeout(() => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        try {
                            reactFlowInstance.fitView({
                                padding: 0.2,
                                duration: 300,
                                includeHiddenNodes: false
                            });
                        } catch (e) {
                            console.warn('Auto fitView failed:', e);
                            // Retry once
                            setTimeout(() => {
                                if (reactFlowInstance && reactFlowInstance.fitView) {
                                    reactFlowInstance.fitView({
                                        padding: 0.2,
                                        duration: 300,
                                        includeHiddenNodes: false
                                    });
                                }
                            }, 200);
                        }
                    });
                });
            }, 150);
            return () => clearTimeout(timeoutId);
        }
    }, [nodes, reactFlowInstance]);

    // --- Context Menu Component ---
    const ContextMenu = ({ x, y, nodeId, onClose, onDelete }) => {
        const node = nodes.find(n => n.id === nodeId);
        const componentId = node?.data?.component_id;
        const isProtected = PROTECTED_NODES.includes(componentId);

        useEffect(() => {
            const handleClick = () => onClose();
            const handleContextMenu = (e) => {
                e.preventDefault();
                onClose();
            };

            document.addEventListener('click', handleClick);
            document.addEventListener('contextmenu', handleContextMenu);

            return () => {
                document.removeEventListener('click', handleClick);
                document.removeEventListener('contextmenu', handleContextMenu);
            };
        }, [onClose]);

        const handleDelete = (e) => {
            e.stopPropagation();
            if (!isProtected) {
                onDelete(nodeId);
            }
            onClose();
        };

        return html`
                <div className="react-flow__context-menu" style=${{ left: `${x}px`, top: `${y}px` }} onClick=${(e) => e.stopPropagation()}>
                    <div 
                        className=${clsx('react-flow__context-menu-item', { disabled: isProtected, danger: !isProtected })}
                        onClick=${handleDelete}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 0 1 .5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                        Delete
                    </div>
                </div>
            `;
    };

    // Connection validator - checks if connection is allowed before it's created
    const isValidConnection = useCallback((connection) => {
        const sourceNode = nodes.find(n => n.id === connection.source);
        const targetNode = nodes.find(n => n.id === connection.target);

        if (!sourceNode || !targetNode) {
            return false;
        }

        const sourceCategory = sourceNode.data?.category;
        const sourceComponentId = sourceNode.data?.component_id;
        const targetCategory = targetNode.data?.category;
        const targetComponentId = targetNode.data?.component_id;

        // Connection validation rules:
        // 1. pre-processing -> only to question reviewer
        // 2. tools -> only to question reviewer
        // 3. question_reviewer -> only to post-processing

        if (sourceCategory === 'pre_process') {
            return targetComponentId === 'question_reviewer';
        } else if (sourceCategory === 'tool') {
            return targetComponentId === 'question_reviewer';
        } else if (sourceComponentId === 'question_reviewer') {
            return targetCategory === 'post_process';
        }

        return false; // All other connections are not allowed
    }, [nodes]);

    const onConnect = useCallback((params) => {
        // Validate connection rules before allowing connection
        const sourceNode = nodes.find(n => n.id === params.source);
        const targetNode = nodes.find(n => n.id === params.target);

        if (!sourceNode || !targetNode) {
            console.warn('Cannot connect: source or target node not found');
            return; // Reject connection
        }

        const sourceCategory = sourceNode.data?.category;
        const sourceComponentId = sourceNode.data?.component_id;
        const targetCategory = targetNode.data?.category;
        const targetComponentId = targetNode.data?.component_id;

        // Connection validation rules:
        // 1. pre-processing -> only to question reviewer
        // 2. tools -> only to question reviewer
        // 3. question_reviewer -> only to post-processing

        let isValidConnection = false;

        if (sourceCategory === 'pre_process') {
            // Pre-processing can only connect to question reviewer
            isValidConnection = targetComponentId === 'question_reviewer';
        } else if (sourceCategory === 'tool') {
            // Tools can only connect to question reviewer
            isValidConnection = targetComponentId === 'question_reviewer';
        } else if (sourceComponentId === 'question_reviewer') {
            // Question reviewer can only connect to post-processing
            isValidConnection = targetCategory === 'post_process';
        } else {
            // All other connections are not allowed
            isValidConnection = false;
        }

        if (!isValidConnection) {
            console.warn('Connection not allowed:', {
                source: sourceNode.data?.label || sourceNode.id,
                sourceCategory,
                target: targetNode.data?.label || targetNode.id,
                targetCategory
            });
            return; // Reject invalid connection
        }

        // Connection is valid, proceed with creating edge
        let className = '';
        // Animate edges from pre_process to review, and from review to post_process
        if ((sourceCategory === 'pre_process' && targetComponentId === 'question_reviewer') ||
            (sourceComponentId === 'question_reviewer' && targetCategory === 'post_process')) {
            className = 'animated';
        }

        const edgeWithAnimation = {
            ...params,
            className,
            type: className === 'animated' ? 'smoothstep' : undefined
        };
        setEdges((eds) => addEdge(edgeWithAnimation, eds));
        // Trigger change detection after connection
        setTimeout(() => {
            if (window.checkForChanges) window.checkForChanges();
        }, 100);
    }, [setEdges, nodes]);

    const onConfigChange = useCallback((nodeId, key, value) => {
        setNodes((nds) => nds.map((node) => {
            if (node.id === nodeId) {
                return { ...node, data: { ...node.data, config: { ...node.data.config, [key]: value } } };
            }
            return node;
        }));
        // Trigger change detection after config change
        setTimeout(() => {
            if (window.checkForChanges) window.checkForChanges();
        }, 100);
    }, [setNodes]);

    // Handle node context menu (right-click)
    const onNodeContextMenu = useCallback((event, node) => {
        event.preventDefault();
        event.stopPropagation();
        const componentId = node.data?.component_id;
        const isProtected = PROTECTED_NODES.includes(componentId);

        setContextMenu({
            x: event.clientX,
            y: event.clientY,
            nodeId: node.id,
            isProtected
        });
    }, []);

    // Handle pane context menu (right-click on empty space) - close any open menu
    const onPaneContextMenu = useCallback((event) => {
        event.preventDefault();
        if (contextMenu) {
            setContextMenu(null);
        }
    }, [contextMenu]);

    // Handle pane click - close context menu
    const onPaneClick = useCallback(() => {
        if (contextMenu) {
            setContextMenu(null);
        }
    }, [contextMenu]);


    // Handle node deletion (from keyboard or programmatic)
    const onNodesDelete = useCallback((deletedNodes) => {
        // Separate protected and deletable nodes
        const protectedNodes = deletedNodes.filter(node => {
            const componentId = node.data?.component_id;
            return PROTECTED_NODES.includes(componentId);
        });
        const nodesToDelete = deletedNodes.filter(node => {
            const componentId = node.data?.component_id;
            return !PROTECTED_NODES.includes(componentId);
        });

        // Restore protected nodes if any were deleted
        if (protectedNodes.length > 0) {
            // Re-add protected nodes to the nodes array
            setNodes((nds) => {
                const existingIds = new Set(nds.map(n => n.id));
                const toRestore = protectedNodes.filter(n => !existingIds.has(n.id));
                const restoredNodes = [...nds, ...toRestore];
                // Recalculate layout after restoring protected nodes
                const layoutedNodes = calculateAutoLayout(restoredNodes);
                return layoutedNodes;
            });
            console.log('Some nodes are protected and cannot be deleted');
        }

        // Remove only non-protected nodes and their connected edges
        if (nodesToDelete.length > 0) {
            const nodeIds = new Set(nodesToDelete.map(n => n.id));
            setNodes((nds) => {
                const remainingNodes = nds.filter(n => !nodeIds.has(n.id));
                // Recalculate layout for remaining nodes after deletion
                const layoutedNodes = calculateAutoLayout(remainingNodes);
                return layoutedNodes;
            });
            setEdges((eds) => eds.filter(e =>
                !nodeIds.has(e.source) && !nodeIds.has(e.target)
            ));

            // Trigger change detection
            setTimeout(() => {
                if (window.checkForChanges) window.checkForChanges();
            }, 100);
        } else if (protectedNodes.length > 0) {
            // Even if no nodes were deleted, trigger change detection to update UI
            setTimeout(() => {
                if (window.checkForChanges) window.checkForChanges();
            }, 100);
        }
    }, [setNodes, setEdges]);

    // Handle delete from context menu
    const handleContextMenuDelete = useCallback((nodeId) => {
        const node = nodes.find(n => n.id === nodeId);
        if (!node) return;

        const componentId = node.data?.component_id;
        if (PROTECTED_NODES.includes(componentId)) {
            return; // Should not happen, but double-check
        }

        // Delete the node and its edges
        setNodes((nds) => nds.filter(n => n.id !== nodeId));
        setEdges((eds) => eds.filter(e =>
            e.source !== nodeId && e.target !== nodeId
        ));

        // Trigger change detection
        setTimeout(() => {
            if (window.checkForChanges) window.checkForChanges();
        }, 100);
    }, [nodes, setNodes, setEdges]);

    // Load Metadata (refetch when componentsRefreshKey changes, e.g. after import)
    useEffect(() => {
        fetch('/review_process_design/api/components').then(res => res.json()).then(data => {
            const map = {}; data.forEach(c => map[c.id] = c); setComponentsMeta(map);
        });
    }, [componentsRefreshKey]);

    // Load Providers
    useEffect(() => {
        fetch('/review_process_design/api/providers').then(res => res.json()).then(data => {
            setProviders(data);
        }).catch(err => {
            console.error('Failed to load providers:', err);
            setProviders([]);
        });
        fetch('/review_process_design/api/providers?embedding_only=true').then(res => res.json()).then(data => {
            setEmbeddingProviders(data);
        }).catch(err => {
            console.error('Failed to load embedding providers:', err);
            setEmbeddingProviders([]);
        });
    }, []);

    // Filter Sidebar
    useEffect(() => {
        if (Object.keys(componentsMeta).length > 0) renderSidebar(Object.values(componentsMeta), nodes);
    }, [nodes, componentsMeta]);

    // Hydrate - Update nodes when componentsMeta becomes available
    useEffect(() => {
        if (Object.keys(componentsMeta).length === 0) return;
        setNodes((nds) => {
            let hasChanges = false;
            const newNodes = nds.map(node => {
                const compId = node.data.component_id;
                const meta = componentsMeta[compId];
                // Update if we have metadata and the node needs hydration
                if (compId && meta) {
                    const currentSchema = node.data.config_schema || {};
                    const schemaEmpty = Object.keys(currentSchema).length === 0;
                    const needsUpdate = schemaEmpty ||
                        !node.data.category ||
                        !node.data.inputs ||
                        !node.data.outputs ||
                        !node.data.label ||
                        node.data.label === compId; // Label is just the component_id
                    if (needsUpdate) {
                        hasChanges = true;
                        return {
                            ...node,
                            data: {
                                ...node.data,
                                config_schema: meta.config_schema || {},
                                category: meta.type,
                                inputs: meta.inputs || [],
                                outputs: meta.outputs || [],
                                label: meta.label || meta.name || node.data.label || compId
                            }
                        };
                    }
                }
                return node;
            });
            return hasChanges ? newNodes : nds;
        });
    }, [componentsMeta, setNodes]);

    const PROTECTED_COMPONENT_IDS = new Set(['question_reviewer', 'github_checker', 'figure_reviewer', 'specialist']);
    const isDeletable = (c) => (c.type === 'tool' || c.type === 'review') && !PROTECTED_COMPONENT_IDS.has(c.id);

    const renderSidebar = (components, currentNodes = []) => {
        const toolsContainer = document.getElementById('toolsContainer');
        if (!toolsContainer) return;

        // Clear only the tools container, not the entire sidebar
        toolsContainer.innerHTML = '';
        toolsContainer.className = ''; // Remove the loading text styling

        const usedComponentIds = new Set(currentNodes.map(n => n.data.component_id));
        const grouped = { pre_process: [], review: [], post_process: [], tool: [] };
        components.forEach(c => {
            if (usedComponentIds.has(c.id)) return;
            if (grouped[c.type]) grouped[c.type].push(c);
            else grouped.review.push(c);
        });

        const labels = { pre_process: "Pre-Process", review: "Review", tool: "Evaluation", post_process: "Post-Process" };

        const showDeleteConfirm = (componentId, componentLabel) => {
            const overlay = document.createElement('div');
            overlay.className = 'sidebar-delete-confirm-overlay';
            const box = document.createElement('div');
            box.className = 'sidebar-delete-confirm-box';
            const header = document.createElement('div');
            header.className = 'sidebar-delete-confirm-header';
            header.textContent = 'Delete component?';
            const message = document.createElement('p');
            message.className = 'sidebar-delete-confirm-message';
            const name = componentLabel || componentId;
            message.textContent = `Remove "${name}" from the list? You can add it again later by importing the ZIP.`;
            const actions = document.createElement('div');
            actions.className = 'sidebar-delete-confirm-actions';
            const cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.className = 'sidebar-delete-confirm-btn sidebar-delete-confirm-cancel';
            cancelBtn.textContent = 'Cancel';
            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'sidebar-delete-confirm-btn sidebar-delete-confirm-delete';
            deleteBtn.textContent = 'Delete';
            actions.append(cancelBtn, deleteBtn);
            box.append(header, message, actions);
            overlay.appendChild(box);
            const remove = () => {
                overlay.remove();
                document.body.style.overflow = '';
            };
            overlay.onclick = (ev) => { if (ev.target === overlay) remove(); };
            box.onclick = (ev) => ev.stopPropagation();
            cancelBtn.onclick = remove;
            deleteBtn.onclick = async () => {
                try {
                    const res = await fetch(`/review_process_design/api/components/${encodeURIComponent(componentId)}`, { method: 'DELETE' });
                    const data = await res.json().catch(() => ({}));
                    if (res.ok && window.refreshComponentsList) window.refreshComponentsList();
                    else if (!res.ok && data.error) alert(data.error);
                } catch (err) {
                    alert('Failed to delete component.');
                }
                remove();
            };
            document.body.style.overflow = 'hidden';
            document.body.appendChild(overlay);
        };

        const showToolContextMenu = (e, component) => {
            e.preventDefault();
            e.stopPropagation();
            if (!isDeletable(component)) return;
            let menu = document.getElementById('sidebar-component-context-menu');
            if (!menu) {
                menu = document.createElement('div');
                menu.id = 'sidebar-component-context-menu';
                menu.className = 'sidebar-component-context-menu';
                document.body.appendChild(menu);
                const deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.className = 'sidebar-component-context-menu-item sidebar-component-context-menu-delete';
                deleteBtn.textContent = 'Delete component';
                menu.appendChild(deleteBtn);
                deleteBtn.onclick = () => {
                    const id = menu.dataset.componentId;
                    const label = menu.dataset.componentLabel || id;
                    if (!id) return;
                    menu.style.display = 'none';
                    document.removeEventListener('click', hideMenu);
                    showDeleteConfirm(id, label);
                };
                menu.addEventListener('click', (ev) => ev.stopPropagation());
            }
            menu.dataset.componentId = component.id;
            menu.dataset.componentLabel = component.label || component.name || component.id;
            menu.style.display = 'block';
            menu.style.left = `${e.clientX}px`;
            menu.style.top = `${e.clientY}px`;
            const hideMenu = () => {
                menu.style.display = 'none';
                document.removeEventListener('click', hideMenu);
            };
            document.addEventListener('click', hideMenu);
        };

        ['pre_process', 'review', 'tool', 'post_process'].forEach(phase => {
            if (grouped[phase].length > 0) {
                const title = document.createElement('div');
                title.className = 'tool-category';
                title.textContent = labels[phase] || phase;
                toolsContainer.appendChild(title);

                grouped[phase].forEach(c => {
                    const deletable = isDeletable(c);
                    const el = document.createElement('div');
                    el.className = 'draggable-tool' + (deletable ? ' draggable-tool-deletable' : '');
                    el.draggable = true;
                    el.dataset.componentId = c.id;
                    const labelSpan = document.createElement('span');
                    labelSpan.className = 'draggable-tool-label';
                    labelSpan.textContent = c.label || c.name;
                    el.appendChild(labelSpan);
                    if (deletable) {
                        const ind = document.createElement('span');
                        ind.className = 'draggable-tool-deletable-indicator';
                        ind.title = 'Right-click to delete';
                        ind.setAttribute('aria-label', 'User-added; right-click to delete');
                        el.appendChild(ind);
                    }
                    el.ondragstart = (event) => {
                        event.dataTransfer.setData('application/reactflow', c.id);
                        event.dataTransfer.effectAllowed = 'move';
                    };
                    el.oncontextmenu = (event) => showToolContextMenu(event, c);
                    toolsContainer.appendChild(el);
                });
            }
        });
    };

    const onDragOver = useCallback((event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; }, []);
    const onDrop = useCallback((event) => {
        event.preventDefault();
        const type = event.dataTransfer.getData('application/reactflow');
        const meta = componentsMeta[type];
        if (!type || !meta) return;

        // Find Question Reviewer node for auto-connections
        const questionReviewerNode = nodes.find(n => n.data?.component_id === 'question_reviewer');

        let position;
        let newEdge = null;

        if (meta.type === 'tool' && questionReviewerNode) {
            // Find existing tools connected to Question Reviewer to avoid overlap
            const existingTools = nodes.filter(n => {
                const isTool = n.data?.category === 'tool';
                const isConnected = edges.some(e =>
                    e.source === questionReviewerNode.id &&
                    e.target === n.id &&
                    e.sourceHandle === 'tools'
                );
                return isTool && isConnected;
            });

            // Position tool below Question Reviewer (300px default distance, matching default layout)
            position = {
                x: questionReviewerNode.position.x,
                y: questionReviewerNode.position.y + 300 + (existingTools.length * 150)
            };
        } else if (meta.type === 'post_process' && questionReviewerNode) {
            // Find existing post-process components connected to Question Reviewer
            const existingPostProcess = nodes.filter(n => {
                const isPostProcess = n.data?.category === 'post_process';
                const isConnected = edges.some(e =>
                    e.source === questionReviewerNode.id &&
                    e.target === n.id &&
                    e.sourceHandle === 'out'
                );
                return isPostProcess && isConnected;
            });

            // Position post-process to the right of Question Reviewer (450px default distance, matching default layout)
            position = {
                x: questionReviewerNode.position.x + 450 + (existingPostProcess.length * 250),
                y: questionReviewerNode.position.y
            };
        } else {
            // Use drop position for other components
            position = reactFlowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY });
        }

        const newNode = {
            id: `${type}_${Date.now()}`, type: 'custom', position,
            data: {
                label: meta.label || meta.name,
                component_id: meta.id,
                category: meta.type,
                config_schema: meta.config_schema,
                config: {},
                id: `${type}_${Date.now()}`,
                onConfigChange
            },
        };
        newNode.data.id = newNode.id;

        // Auto-connect tool to Question Reviewer
        if (meta.type === 'tool' && questionReviewerNode) {
            newEdge = {
                source: questionReviewerNode.id,
                sourceHandle: 'tools',
                target: newNode.id,
                targetHandle: 'in'
            };
        }
        // Auto-connect post-process to Question Reviewer (with animation)
        else if (meta.type === 'post_process' && questionReviewerNode) {
            newEdge = {
                source: questionReviewerNode.id,
                sourceHandle: 'out',
                target: newNode.id,
                targetHandle: 'in',
                className: 'animated',
                type: 'smoothstep'
            };
        }

        setNodes((nds) => {
            const updatedNodes = nds.concat(newNode);
            // Recalculate layout for all nodes after adding new one
            const layoutedNodes = calculateAutoLayout(updatedNodes);
            return layoutedNodes;
        });
        if (newEdge) {
            setEdges((eds) => addEdge(newEdge, eds));
        }

        // Trigger change detection
        setTimeout(() => {
            if (window.checkForChanges) window.checkForChanges();
        }, 100);
    }, [componentsMeta, setNodes, setEdges, reactFlowInstance, onConfigChange, nodes, edges]
    );

    // Track changes when nodes or edges change
    useEffect(() => {
        if (window.checkForChanges && window.originalProcessData) {
            window.checkForChanges();
        }
    }, [nodes, edges]);

    // Automatic layout function - positions nodes based on their categories
    const calculateAutoLayout = (nodesToLayout) => {
        if (!nodesToLayout || nodesToLayout.length === 0) return nodesToLayout;

        // Ensure all nodes have valid positions before layout
        nodesToLayout = nodesToLayout.map(n => {
            if (!n.position || typeof n.position.x !== 'number' || typeof n.position.y !== 'number' ||
                isNaN(n.position.x) || isNaN(n.position.y)) {
                n.position = { x: 0, y: 0 };
            }
            return n;
        });

        // Constants for layout
        const NODE_WIDTH = 280; // Fixed width from CSS
        const NODE_HEIGHT_BASE = 150; // Base height estimate
        const NODE_HEIGHT_PER_CONTROL = 60; // Additional height per config item
        const HORIZONTAL_SPACING = 450; // Space between columns (pre-process, review, post-process)
        const VERTICAL_SPACING = 200; // Equal spacing between nodes in same column
        const TOOL_SPACING = 360; // Equal horizontal spacing between tool nodes (doubled to prevent overlap)
        const TOOL_VERTICAL_OFFSET = 350; // Fixed distance tools are below question reviewer (from top of QR to top of tools)

        // Group nodes by category
        const questionReviewer = nodesToLayout.find(n => n.data?.component_id === 'question_reviewer');
        const preProcessNodes = nodesToLayout.filter(n => n.data?.category === 'pre_process' && n.data?.component_id !== 'question_reviewer');
        const toolNodes = nodesToLayout.filter(n => n.data?.category === 'tool');
        const postProcessNodes = nodesToLayout.filter(n => n.data?.category === 'post_process');

        // Calculate node heights (estimate based on config items)
        const estimateNodeHeight = (node) => {
            const configSchema = node.data?.config_schema;
            const controlCount = configSchema?.properties ? Object.keys(configSchema.properties).filter(key =>
                !['collection_name', 'review_process_name', 'paper_name', 'checklist_name'].includes(key)
            ).length : 0;
            return NODE_HEIGHT_BASE + (controlCount * NODE_HEIGHT_PER_CONTROL);
        };

        // Start position (center of canvas, adjusted for layout)
        const startX = 400;
        const startY = 200;

        // Position question reviewer in the middle
        let qrHeight = 0;
        let qrCenterY = startY;
        if (questionReviewer) {
            qrHeight = estimateNodeHeight(questionReviewer);
            questionReviewer.position = {
                x: startX,
                y: startY
            };
            qrCenterY = startY + (qrHeight / 2); // Center Y of question reviewer
        }

        // Position pre-process nodes to the left, equidistant, centered on question reviewer
        if (preProcessNodes.length > 0) {
            // Calculate total height needed for all pre-process nodes with spacing
            const preProcessHeights = preProcessNodes.map(n => estimateNodeHeight(n));
            const totalPreProcessHeight = preProcessHeights.reduce((sum, h) => sum + h, 0) +
                (preProcessNodes.length - 1) * VERTICAL_SPACING;

            // Start Y position so that the middle of all pre-process nodes aligns with question reviewer center
            let preProcessStartY = qrCenterY - (totalPreProcessHeight / 2);

            preProcessNodes.forEach((node, index) => {
                const nodeHeight = estimateNodeHeight(node);
                node.position = {
                    x: startX - HORIZONTAL_SPACING,
                    y: preProcessStartY
                };
                // Move start position for next node (current height + spacing)
                preProcessStartY += nodeHeight + VERTICAL_SPACING;
            });
        }

        // Position tool nodes below question reviewer, horizontally arranged with equal spacing
        if (toolNodes.length > 0) {
            if (questionReviewer) {
                // Center tools horizontally relative to question reviewer
                const toolStartX = questionReviewer.position.x - ((toolNodes.length - 1) * TOOL_SPACING / 2);
                const toolY = questionReviewer.position.y + qrHeight + TOOL_VERTICAL_OFFSET;

                toolNodes.forEach((node, index) => {
                    node.position = {
                        x: toolStartX + (index * TOOL_SPACING),
                        y: toolY
                    };
                });
            } else {
                // Fallback if no question reviewer
                const toolStartX = startX - ((toolNodes.length - 1) * TOOL_SPACING / 2);
                toolNodes.forEach((node, index) => {
                    node.position = {
                        x: toolStartX + (index * TOOL_SPACING),
                        y: startY + TOOL_VERTICAL_OFFSET
                    };
                });
            }
        }

        // Position post-process nodes to the right, equidistant, centered on question reviewer
        if (postProcessNodes.length > 0) {
            // Calculate total height needed for all post-process nodes with spacing
            const postProcessHeights = postProcessNodes.map(n => estimateNodeHeight(n));
            const totalPostProcessHeight = postProcessHeights.reduce((sum, h) => sum + h, 0) +
                (postProcessNodes.length - 1) * VERTICAL_SPACING;

            // Start Y position so that the middle of all post-process nodes aligns with question reviewer center
            let postProcessStartY = qrCenterY - (totalPostProcessHeight / 2);

            postProcessNodes.forEach((node, index) => {
                const nodeHeight = estimateNodeHeight(node);
                node.position = {
                    x: startX + HORIZONTAL_SPACING,
                    y: postProcessStartY
                };
                // Move start position for next node (current height + spacing)
                postProcessStartY += nodeHeight + VERTICAL_SPACING;
            });
        }

        // Handle any other nodes (unknown category) - place them to the right of post-process
        const otherNodes = nodesToLayout.filter(n => {
            const cat = n.data?.category;
            return cat !== 'pre_process' && cat !== 'review' && cat !== 'tool' && cat !== 'post_process' &&
                n.data?.component_id !== 'question_reviewer';
        });

        if (otherNodes.length > 0) {
            let otherX = startX + (HORIZONTAL_SPACING * 2);
            let otherY = startY;
            otherNodes.forEach((node, index) => {
                const nodeHeight = estimateNodeHeight(node);
                node.position = {
                    x: otherX,
                    y: otherY
                };
                otherY += nodeHeight + VERTICAL_SPACING;
            });
        }

        // Center all nodes in the coordinate space
        if (nodesToLayout.length > 0) {
            // Calculate bounding box of all nodes
            let minX = Infinity, maxX = -Infinity;
            let minY = Infinity, maxY = -Infinity;

            nodesToLayout.forEach(node => {
                if (node.position) {
                    const nodeWidth = NODE_WIDTH;
                    const nodeHeight = estimateNodeHeight(node);
                    const nodeLeft = node.position.x;
                    const nodeRight = node.position.x + nodeWidth;
                    const nodeTop = node.position.y;
                    const nodeBottom = node.position.y + nodeHeight;

                    // Validate positions are numbers
                    if (typeof nodeLeft === 'number' && !isNaN(nodeLeft) &&
                        typeof nodeRight === 'number' && !isNaN(nodeRight) &&
                        typeof nodeTop === 'number' && !isNaN(nodeTop) &&
                        typeof nodeBottom === 'number' && !isNaN(nodeBottom)) {
                        minX = Math.min(minX, nodeLeft);
                        maxX = Math.max(maxX, nodeRight);
                        minY = Math.min(minY, nodeTop);
                        maxY = Math.max(maxY, nodeBottom);
                    }
                }
            });

            // Calculate center of bounding box (only if we have valid bounds)
            if (minX !== Infinity && maxX !== -Infinity && minY !== Infinity && maxY !== -Infinity) {
                const centerX = (minX + maxX) / 2;
                const centerY = (minY + maxY) / 2;

                // Only translate if center values are valid numbers
                if (!isNaN(centerX) && !isNaN(centerY)) {
                    // Translate all nodes so their center is at origin (0, 0)
                    nodesToLayout.forEach(node => {
                        if (node.position && typeof node.position.x === 'number' && typeof node.position.y === 'number') {
                            node.position.x -= centerX;
                            node.position.y -= centerY;
                        }
                    });
                }
            }
        }

        // Final validation: ensure all positions are valid numbers
        return nodesToLayout.map(node => {
            if (!node.position || typeof node.position.x !== 'number' || typeof node.position.y !== 'number' ||
                isNaN(node.position.x) || isNaN(node.position.y)) {
                // Fallback to default position if invalid
                node.position = { x: 400, y: 200 };
            }
            return node;
        });
    };

    // Expose Editor State
    useEffect(() => {
        window.reactFlowInstance = {
            getFlow: (includePositions = false) => {
                // When saving, exclude positions since they're auto-calculated on load
                if (includePositions) {
                    return { nodes, edges };
                }
                // Strip positions for saving
                const nodesWithoutPositions = nodes.map(({ position, ...node }) => node);
                return { nodes: nodesWithoutPositions, edges };
            },
            setFlow: (flow, skipTracking = false) => {
                if (!flow) {
                    console.warn('setFlow called with no flow data');
                    return;
                }
                // Logic to load nodes (same as before)
                let flowNodes = [];
                let flowEdges = [];
                const rawNodes = flow.nodes;
                if (rawNodes && !Array.isArray(rawNodes) && typeof rawNodes === 'object') {
                    // Rete legacy support logic (omitted for brevity, assume modern format or copy previous)
                    // ... (copying full logic from previous file to ensure robust loading)
                    // Note: For brevity in this edit, I am assuming the user works with saved files or I need to preserve the logic.
                    // I will try to preserve the standard flow loading logic.
                    Object.entries(rawNodes).forEach(([id, node]) => {
                        const meta = componentsMeta[node.name];
                        // If meta not found yet, we might lose data. 
                        // Fallback: use node.name as basic data
                        const inputs = meta ? meta.inputs : [];
                        const outputs = meta ? meta.outputs : [];

                        // Safely extract position - handle both array [x, y] and object {x, y} formats
                        let nodePosition = { x: 0, y: 0 };
                        if (node.position) {
                            if (Array.isArray(node.position)) {
                                nodePosition = {
                                    x: Number(node.position[0]) || 0,
                                    y: Number(node.position[1]) || 0
                                };
                            } else if (typeof node.position === 'object') {
                                nodePosition = {
                                    x: Number(node.position.x) || 0,
                                    y: Number(node.position.y) || 0
                                };
                            }
                        }

                        flowNodes.push({
                            id: id.toString(),
                            type: 'custom',
                            position: nodePosition,
                            data: {
                                label: meta ? (meta.label || meta.name) : node.name,
                                component_id: node.name,
                                category: meta ? meta.type : 'unknown',
                                inputs: inputs,
                                outputs: outputs,
                                config_schema: meta ? meta.config_schema : {},
                                config: node.data || {},
                                id: id.toString(),
                                onConfigChange
                            }
                        });

                        // Convert Edges
                        if (node.outputs) {
                            Object.entries(node.outputs).forEach(([outputKey, outputData]) => {
                                if (outputData.connections) {
                                    outputData.connections.forEach(conn => {
                                        const edge = {
                                            id: `e${id}-${outputKey}-${conn.node}-${conn.input}`,
                                            source: id.toString(),
                                            sourceHandle: outputKey === 'default' ? 'out' : outputKey, // Attempt to map legacy keys if needed, but Rete keys are usually unique
                                            target: conn.node.toString(),
                                            targetHandle: conn.input
                                        };
                                        flowEdges.push(edge);
                                    });
                                }
                            });
                        }
                    });
                    // Apply animation to edges
                    flowEdges = flowEdges.map(edge => {
                        const sourceNode = flowNodes.find(n => n.id === edge.source);
                        const targetNode = flowNodes.find(n => n.id === edge.target);

                        if (sourceNode && targetNode) {
                            const sourceCategory = sourceNode.data?.category;
                            const targetCategory = targetNode.data?.category;

                            if ((sourceCategory === 'pre_process' && targetCategory === 'review') ||
                                (sourceCategory === 'review' && targetCategory === 'post_process')) {
                                return { ...edge, className: 'animated', type: 'smoothstep' };
                            }
                        }
                        return edge;
                    });
                    // Apply automatic layout (ignore stored positions)
                    flowNodes = calculateAutoLayout(flowNodes);
                    setNodes(flowNodes);
                    setEdges(flowEdges);
                } else {
                    flowNodes = (rawNodes || []).map(n => {
                        const compId = n.data?.component_id;
                        const meta = compId ? componentsMeta[compId] : null;

                        // Safely extract position - ensure it's valid numbers
                        let nodePosition = { x: 0, y: 0 };
                        if (n.position) {
                            if (typeof n.position === 'object' && !Array.isArray(n.position)) {
                                nodePosition = {
                                    x: Number(n.position.x) || 0,
                                    y: Number(n.position.y) || 0
                                };
                            } else if (Array.isArray(n.position)) {
                                nodePosition = {
                                    x: Number(n.position[0]) || 0,
                                    y: Number(n.position[1]) || 0
                                };
                            }
                        }

                        return {
                            ...n,
                            // Use valid position or default to 0,0 - will be recalculated by layout
                            position: nodePosition,
                            data: {
                                ...n.data,
                                category: meta ? meta.type : (n.data.category || 'unknown'),
                                config_schema: meta ? meta.config_schema : (n.data.config_schema || {}),
                                onConfigChange
                            }
                        };
                    });
                    // Apply automatic layout
                    flowNodes = calculateAutoLayout(flowNodes);
                    flowEdges = (flow.edges || []).map(edge => {
                        const sourceNode = flowNodes.find(n => n.id === edge.source);
                        const targetNode = flowNodes.find(n => n.id === edge.target);

                        if (sourceNode && targetNode) {
                            const sourceCategory = sourceNode.data?.category;
                            const targetCategory = targetNode.data?.category;

                            if ((sourceCategory === 'pre_process' && targetCategory === 'review') ||
                                (sourceCategory === 'review' && targetCategory === 'post_process')) {
                                return { ...edge, className: 'animated', type: 'smoothstep' };
                            }
                        }
                        return edge;
                    });
                    setNodes(flowNodes);
                    setEdges(flowEdges);
                }

                // Ensure nodes are set even if structure is unexpected
                if (flowNodes.length === 0 && flow.nodes && Array.isArray(flow.nodes)) {
                    const fallbackNodes = flow.nodes.map(n => {
                        const compId = n.data?.component_id;
                        const meta = compId ? componentsMeta[compId] : null;

                        // Safely extract position - ensure it's valid numbers
                        let nodePosition = { x: 0, y: 0 };
                        if (n.position) {
                            if (typeof n.position === 'object' && !Array.isArray(n.position)) {
                                nodePosition = {
                                    x: Number(n.position.x) || 0,
                                    y: Number(n.position.y) || 0
                                };
                            } else if (Array.isArray(n.position)) {
                                nodePosition = {
                                    x: Number(n.position[0]) || 0,
                                    y: Number(n.position[1]) || 0
                                };
                            }
                        }

                        return {
                            ...n,
                            // Use valid position or default to 0,0 - will be recalculated by layout
                            position: nodePosition,
                            data: {
                                ...n.data,
                                category: meta ? meta.type : (n.data.category || 'unknown'),
                                config_schema: meta ? meta.config_schema : (n.data.config_schema || {}),
                                onConfigChange
                            }
                        };
                    });
                    // Apply automatic layout
                    const layoutedFallbackNodes = calculateAutoLayout(fallbackNodes);
                    const fallbackEdges = (flow.edges || []).map(edge => {
                        const sourceNode = layoutedFallbackNodes.find(n => n.id === edge.source);
                        const targetNode = layoutedFallbackNodes.find(n => n.id === edge.target);

                        if (sourceNode && targetNode) {
                            const sourceCategory = sourceNode.data?.category;
                            const targetCategory = targetNode.data?.category;

                            if ((sourceCategory === 'pre_process' && targetCategory === 'review') ||
                                (sourceCategory === 'review' && targetCategory === 'post_process')) {
                                return { ...edge, className: 'animated', type: 'smoothstep' };
                            }
                        }
                        return edge;
                    });
                    setNodes(layoutedFallbackNodes);
                    setEdges(fallbackEdges);
                }

                // Set flag to trigger auto-fit in useEffect
                shouldAutoFitRef.current = true;

                // Reset change tracking when flow is set (unless skipTracking is true)
                if (!skipTracking) {
                    setTimeout(() => {
                        window.originalProcessData = JSON.stringify(flow);
                        window.hasUnsavedChanges = false;
                        if (window.updateButtonStates) {
                            window.updateButtonStates();
                        }
                    }, 100);
                }
            },
            clear: () => { setNodes([]); setEdges([]); },
            fitView: (options = {}) => {
                if (reactFlowInstance && reactFlowInstance.fitView) {
                    return reactFlowInstance.fitView(options);
                }
            }
        };
    }, [nodes, edges, setNodes, setEdges, onConfigChange, reactFlowInstance, componentsMeta]);

    const nodeTypesWithProviders = useMemo(() => createNodeTypes(providers, embeddingProviders, openTextEditor), [providers, embeddingProviders, openTextEditor]);

    return html`
            <div style=${{ position: 'relative', width: '100%', height: '100%' }}>
                <${ReactFlow} 
                    nodes=${nodes} 
                    edges=${edges} 
                    onNodesChange=${onNodesChange} 
                    onEdgesChange=${onEdgesChange}
                    onConnect=${onConnect}
                    isValidConnection=${isValidConnection}
                    nodeTypes=${nodeTypesWithProviders} 
                    onDragOver=${onDragOver} 
                    onDrop=${onDrop}
                    onNodeContextMenu=${onNodeContextMenu}
                    onPaneContextMenu=${onPaneContextMenu}
                    onPaneClick=${onPaneClick}
                    onNodesDelete=${onNodesDelete}
                    fitView
                >
                    <${Background} />
                    <${Controls} />
                    <${MiniMap} />
                <//>
                ${contextMenu ? html`<${ContextMenu} 
                    x=${contextMenu.x} 
                    y=${contextMenu.y} 
                    nodeId=${contextMenu.nodeId}
                    onClose=${() => setContextMenu(null)}
                    onDelete=${handleContextMenuDelete}
                />` : null}
                ${showImportModal ? html`<${ImportComponentModal}
                    isOpen=${true}
                    onClose=${() => setShowImportModal(false)}
                    onSuccess=${() => setComponentsRefreshKey(k => k + 1)}
                />` : null}
            </div>
        `;
};

const root = createRoot(document.getElementById('react-flow-root'));
root.render(html`<${ReactFlowProvider}><${ProcessEditor} /><//>`);

// Render text editor modal at app level (outside React Flow)
const modalRoot = createRoot(document.getElementById('text-editor-modal-root'));
let modalState = { isOpen: false, nodeId: null, fieldKey: null, fieldLabel: null, currentValue: '' };

// Global function to open text editor from nodes
window.openTextEditor = ({ nodeId, fieldKey, fieldLabel, currentValue }) => {
    modalState = { isOpen: true, nodeId, fieldKey, fieldLabel, currentValue };
    renderModal();
};

const renderModal = () => {
    const closeModal = () => {
        modalState = { isOpen: false, nodeId: null, fieldKey: null, fieldLabel: null, currentValue: '' };
        renderModal();
    };

    const saveModal = (value) => {
        if (modalState.nodeId && modalState.fieldKey && window.textEditorSaveCallback) {
            window.textEditorSaveCallback(modalState.nodeId, modalState.fieldKey, value);
        }
        closeModal();
    };

    modalRoot.render(html`
            <${TextEditorModal}
                isOpen=${modalState.isOpen}
                onClose=${closeModal}
                onSave=${saveModal}
                fieldName=${modalState.fieldKey}
                fieldLabel=${modalState.fieldLabel}
                currentValue=${modalState.currentValue}
            />
        `);
};

renderModal();

// --- Application Logic ---
// --- Application Logic ---
document.addEventListener('DOMContentLoaded', async () => {
    // Canvas is always visible on this page
    const bottomPanel = document.getElementById('bottomPanel');
    if (bottomPanel) {
        bottomPanel.style.display = 'flex';
        bottomPanel.classList.add('visible');
    }

    // Fullscreen toggle functionality
    const fullscreenToggleBtn = document.getElementById('fullscreenToggleBtn');
    const fullscreenIcon = document.getElementById('fullscreenIcon');
    const fullscreenText = document.getElementById('fullscreenText');
    let isFullscreen = false;

    async function toggleFullscreen() {
        isFullscreen = !isFullscreen;

        if (isFullscreen) {
            bottomPanel.classList.add('fullscreen');
            fullscreenIcon.innerHTML = '<path d="M5.5 0a.5.5 0 0 1 .5.5v4A1.5 1.5 0 0 0 7.5 6h4a.5.5 0 0 1 0 1h-4A2.5 2.5 0 0 1 5 4.5v-4a.5.5 0 0 1 .5-.5m5 0a.5.5 0 0 1 .5.5v4a2.5 2.5 0 0 1-2.5 2.5h-4a.5.5 0 0 1 0-1h4A1.5 1.5 0 0 0 10 4.5v-4a.5.5 0 0 1 .5-.5"/><path d="M0 5.5A1.5 1.5 0 0 1 1.5 4h4a.5.5 0 0 1 0 1h-4a.5.5 0 0 0-.5.5v4a.5.5 0 0 1-1 0zm14 0A1.5 1.5 0 0 0 12.5 4h-4a.5.5 0 0 1 0-1h4A2.5 2.5 0 0 1 15 5.5v4a.5.5 0 0 1-1 0z"/>';
            fullscreenText.textContent = 'Exit Full Screen';
            await reloadAndCenterCanvas();
        } else {
            bottomPanel.classList.remove('fullscreen');
            fullscreenIcon.innerHTML = '<path d="M1.5 1a.5.5 0 0 0-.5.5v4a.5.5 0 0 1-1 0v-4A1.5 1.5 0 0 1 1.5 0h4a.5.5 0 0 1 0 1zM14 1.5a.5.5 0 0 1 .5-.5h4a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0V1.707l-4.146 4.147a.5.5 0 0 1-.708-.708L17.293 1zM1.5 14a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0v-4a.5.5 0 0 1 .5-.5m13 0a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0v-4a.5.5 0 0 1 .5-.5"/>';
            fullscreenText.textContent = 'Full Screen';
            await reloadAndCenterCanvas();
        }
    }

    async function reloadAndCenterCanvas() {
        await new Promise(resolve => setTimeout(resolve, 150));
        if (!window.reactFlowInstance) return;
        const currentFlow = window.reactFlowInstance.getFlow(false);
        if (!currentFlow || (!currentFlow.nodes || currentFlow.nodes.length === 0)) {
            if (currentSelectedProcess && currentSelectedProcess.slug) {
                await loadSpecificProcess(currentSelectedProcess.slug);
            }
            return;
        }
        window.reactFlowInstance.setFlow(currentFlow, true);
        setTimeout(() => {
            if (window.reactFlowInstance && window.reactFlowInstance.fitView) {
                try {
                    window.reactFlowInstance.fitView({ padding: 0.2, duration: 300, includeHiddenNodes: false });
                } catch (e) {
                    console.warn('fitView failed:', e);
                }
            }
        }, 200);
    }

    if (fullscreenToggleBtn) {
        fullscreenToggleBtn.addEventListener('click', toggleFullscreen);
    }

    // Process management
    const updateProcessBtn = document.getElementById('updateProcessBtn');
    const createProcessBtn = document.getElementById('createProcessBtn');
    const renameProcessBtn = document.getElementById('renameProcessBtn');
    const deleteProcessBtn = document.getElementById('deleteProcessBtn');
    const createReviewProcessBtn = document.getElementById('createReviewProcessBtn');
    const processListSidebar = document.getElementById('processListSidebar');
    window.originalProcessData = null;
    window.hasUnsavedChanges = false;
    
    // Store currently selected process
    let currentSelectedProcess = null;

    function showSaveNotification(message, isError = false) {
        // Simple notification - you can enhance this
        const notification = document.createElement('div');
        notification.style.cssText = `position: fixed; top: 20px; right: 20px; padding: 1rem; background: ${isError ? '#ef4444' : '#10b981'}; color: white; border-radius: 8px; z-index: 10000; box-shadow: 0 4px 12px rgba(0,0,0,0.15);`;
        notification.textContent = message;
        document.body.appendChild(notification);
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.3s';
            setTimeout(() => document.body.removeChild(notification), 300);
        }, 3000);
    }

    function showRenameModal(title, currentName, isCreate = false) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'delete-modal-overlay';
            overlay.style.animation = 'fadeIn 0.2s ease-out';
            overlay.innerHTML = `
                <div class="delete-modal" style="max-width: 500px;">
                    <div class="delete-modal-header ${isCreate ? 'create-modal-header' : 'rename-modal-header'}">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                            <path d="M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.5.5 0 0 1-.175-.032l-.179.178a.5.5 0 0 0 .11.172l2 2a.5.5 0 0 0 .708 0l.13-.13z"/>
                        </svg>
                        <h5>${title}</h5>
                    </div>
                    <div class="delete-modal-body">
                        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #0f172a;">${isCreate ? 'Process Name:' : 'New Name:'}</label>
                        <input type="text" id="renameInput" class="form-control" value="${currentName}" style="width: 100%; padding: 0.75rem; border-radius: 6px; border: 2px solid #e2e8f0; font-size: 0.9rem;">
                    </div>
                    <div class="delete-modal-footer">
                        <button class="delete-modal-btn delete-modal-btn-cancel" id="renameModalCancel">Cancel</button>
                        <button class="delete-modal-btn" id="renameModalConfirm" style="background: #2563eb; color: white;">${isCreate ? 'Save' : 'Rename'}</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
            const input = overlay.querySelector('#renameInput');
            setTimeout(() => { input.focus(); input.select(); }, 100);
            let isClosing = false;
            const closeModal = (confirmed, value = null) => {
                if (isClosing) return;
                isClosing = true;
                overlay.style.animation = 'fadeIn 0.2s ease-out reverse';
                setTimeout(() => {
                    if (document.body.contains(overlay)) document.body.removeChild(overlay);
                    resolve(confirmed ? value : null);
                }, 200);
            };
            const handleConfirm = () => {
                const newName = input.value.trim();
                if (isCreate ? newName : (newName && newName !== currentName)) {
                    closeModal(true, newName);
                }
            };
            overlay.querySelector('#renameModalCancel').addEventListener('click', () => closeModal(false));
            overlay.querySelector('#renameModalConfirm').addEventListener('click', handleConfirm);
            input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); handleConfirm(); } });
            overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(false); });
            const escapeHandler = (e) => { if (e.key === 'Escape') { document.removeEventListener('keydown', escapeHandler); closeModal(false); } };
            document.addEventListener('keydown', escapeHandler);
        });
    }

    function showDeleteModal(processName) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'delete-modal-overlay';
            overlay.innerHTML = `
                <div class="delete-modal">
                    <div class="delete-modal-header">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16">
                            <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
                        </svg>
                        <h5>Delete Review Process</h5>
                    </div>
                    <div class="delete-modal-body">
                        <p>Are you sure you want to delete the review process <strong>"${processName}"</strong>?</p>
                        <p style="color: #6c757d; font-size: 0.9rem; margin-top: 1rem;">This action cannot be undone.</p>
                    </div>
                    <div class="delete-modal-footer">
                        <button class="delete-modal-btn delete-modal-btn-cancel" id="deleteModalCancel">Cancel</button>
                        <button class="delete-modal-btn delete-modal-btn-delete" id="deleteModalConfirm">Delete Process</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
            let isClosing = false;
            const closeModal = (confirmed) => {
                if (isClosing) return;
                isClosing = true;
                overlay.style.animation = 'fadeIn 0.2s ease-out reverse';
                setTimeout(() => {
                    if (document.body.contains(overlay)) document.body.removeChild(overlay);
                    resolve(confirmed);
                }, 200);
            };
            overlay.querySelector('#deleteModalCancel').addEventListener('click', () => closeModal(false));
            overlay.querySelector('#deleteModalConfirm').addEventListener('click', () => closeModal(true));
            overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(false); });
            const escapeHandler = (e) => { if (e.key === 'Escape') { document.removeEventListener('keydown', escapeHandler); closeModal(false); } };
            document.addEventListener('keydown', escapeHandler);
        });
    }

    function updateCanvasHeader() {
        const canvasProcessName = document.getElementById('canvasProcessName');
        if (!canvasProcessName) return;
        if (currentSelectedProcess && currentSelectedProcess.name) {
            canvasProcessName.textContent = currentSelectedProcess.name;
        } else {
            canvasProcessName.textContent = 'No process selected';
        }
    }

    function updateButtonStates() {
        const currentProcess = currentSelectedProcess ? currentSelectedProcess.slug : null;
        const isDefault = currentProcess === 'default_review';
        if (updateProcessBtn) updateProcessBtn.disabled = isDefault || !window.hasUnsavedChanges || !currentProcess;
        if (renameProcessBtn) renameProcessBtn.disabled = isDefault || !currentProcess;
        if (deleteProcessBtn) deleteProcessBtn.disabled = isDefault || !currentProcess;
        updateCanvasHeader();
    }

    window.updateButtonStates = updateButtonStates;
    window.checkForChanges = () => {
        if (!window.reactFlowInstance || !window.originalProcessData) {
            window.hasUnsavedChanges = false;
            updateButtonStates();
            return;
        }
        const currentData = window.reactFlowInstance.getFlow(false);
        const currentDataStr = JSON.stringify(currentData);
        window.hasUnsavedChanges = currentDataStr !== window.originalProcessData;
        updateButtonStates();
    };

    async function loadProcesses(preserveSelection = false) {
        if (!processListSidebar) return;
        const currentValue = preserveSelection && currentSelectedProcess ? currentSelectedProcess.slug : null;
        processListSidebar.innerHTML = '<div class="text-center p-3 text-muted small">Loading processes...</div>';
        
        try {
            const res = await fetch('/review_process_design/api/processes');
            const data = await res.json();
            processListSidebar.innerHTML = '';
            
            if (data.length === 0) {
                processListSidebar.innerHTML = '<div class="text-center p-3 text-muted small">No processes found.</div>';
                return;
            }
            
            let preservedProcess = null;
            
            data.forEach(p => {
                const displayName = p.name || (p.data && p.data.name) || p.slug || 'Unknown';
                const slugValue = p.slug || p.name;
                
                // Skip default_review process - it's only for design template purposes
                if (slugValue === 'default_review' || displayName === 'Default Review Process') {
                    return;
                }
                
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action';
                listItem.dataset.processSlug = slugValue;
                listItem.dataset.processName = displayName;
                listItem.textContent = displayName;
                
                listItem.addEventListener('click', async () => {
                    // Remove active class from all items
                    processListSidebar.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    listItem.classList.add('active');
                    
                    currentSelectedProcess = {
                        name: displayName,
                        slug: slugValue
                    };
                    
                    await loadSpecificProcess(slugValue);
                    updateButtonStates();
                    updateCanvasHeader();
                });
                
                processListSidebar.appendChild(listItem);
                
                // Check for preserved selection
                if (preserveSelection && (slugValue === currentValue || displayName === currentValue)) {
                    preservedProcess = listItem;
                }
            });
            
            // Restore selection if preserving
            if (preserveSelection && preservedProcess) {
                preservedProcess.classList.add('active');
                currentSelectedProcess = {
                    name: preservedProcess.dataset.processName,
                    slug: preservedProcess.dataset.processSlug
                };
            } else if (data.length > 0 && !preserveSelection && !window.pendingProcessSelection) {
                // Select first process if no preserved selection and no pending selection
                const firstItem = processListSidebar.querySelector('.list-group-item');
                if (firstItem) {
                    firstItem.classList.add('active');
                    currentSelectedProcess = {
                        name: firstItem.dataset.processName,
                        slug: firstItem.dataset.processSlug
                    };
                    setTimeout(async () => {
                        await loadSpecificProcess(firstItem.dataset.processSlug);
                        updateCanvasHeader();
                    }, 100);
                }
            }
            updateCanvasHeader();
        } catch (e) { 
            console.error(e);
            processListSidebar.innerHTML = '<div class="text-center p-3 text-danger small">Error loading processes.</div>';
        }
    }

    async function loadSpecificProcess(name) {
        let retries = 0;
        while (!window.reactFlowInstance && retries < 10) {
            await new Promise(resolve => setTimeout(resolve, 100));
            retries++;
        }
        if (!window.reactFlowInstance) {
            console.error('ReactFlow instance not available');
            return;
        }
        try {
            const res = await fetch(`/review_process_design/api/processes/${name}`);
            if (res.ok) {
                const data = await res.json();
                if (data && (data.nodes || data.edges)) {
                    // Load the flow - this will trigger layout calculation
                    window.reactFlowInstance.setFlow(data, true);
                    updateCanvasHeader();
                    
                    // Auto-fit the view after loading the process
                    // Wait for layout calculation and node rendering
                    const attemptFitView = (retries = 0) => {
                        if (retries > 20) return; // Increased retries for larger graphs
                        
                        const reactFlowElement = document.querySelector('#react-flow-root .react-flow');
                        if (reactFlowElement) {
                            const rect = reactFlowElement.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) {
                                setTimeout(() => attemptFitView(retries + 1), 100);
                                return;
                            }
                        }
                        
                        // Check if nodes are actually rendered using getFlow
                        if (!window.reactFlowInstance) {
                            setTimeout(() => attemptFitView(retries + 1), 100);
                            return;
                        }
                        
                        const flowData = window.reactFlowInstance.getFlow(true); // Get with positions
                        const nodes = flowData ? (flowData.nodes || []) : [];
                        
                        if (nodes.length === 0) {
                            setTimeout(() => attemptFitView(retries + 1), 100);
                            return;
                        }
                        
                        // Check if nodes have valid positions
                        const hasValidPositions = nodes.some(node => {
                            const pos = node.position;
                            return pos && typeof pos.x === 'number' && !isNaN(pos.x) && 
                                   typeof pos.y === 'number' && !isNaN(pos.y) &&
                                   isFinite(pos.x) && isFinite(pos.y);
                        });
                        
                        if (!hasValidPositions) {
                            setTimeout(() => attemptFitView(retries + 1), 100);
                            return;
                        }
                        
                        if (window.reactFlowInstance && window.reactFlowInstance.fitView) {
                            try {
                                // Call fitView with options to ensure it fits properly
                                window.reactFlowInstance.fitView({
                                    padding: 0.2,
                                    duration: 300,
                                    includeHiddenNodes: false,
                                    maxZoom: 1.5,
                                    minZoom: 0.1
                                });
                            } catch (e) {
                                if (retries < 20) {
                                    setTimeout(() => attemptFitView(retries + 1), 100);
                                }
                            }
                        }
                    };
                    
                    // Use multiple requestAnimationFrame calls and longer delay to ensure layout is complete
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(() => {
                                setTimeout(() => attemptFitView(), 200);
                            });
                        });
                    });
                    
                    setTimeout(() => {
                        if (window.reactFlowInstance) {
                            const currentFlow = window.reactFlowInstance.getFlow(false);
                            window.originalProcessData = JSON.stringify(currentFlow);
                            window.hasUnsavedChanges = false;
                            updateButtonStates();
                        }
                    }, 500);
                }
            }
        } catch (e) { console.error('Error loading process:', e); }
    }

    async function saveProcess(name, isUpdate = false) {
        if (!window.reactFlowInstance) {
            showSaveNotification('Process editor not initialized', true);
            return;
        }
        const data = window.reactFlowInstance.getFlow(false);
        try {
            const res = await fetch('/review_process_design/api/processes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, data: data })
            });
            if (res.ok) {
                showSaveNotification(`"${name}" saved successfully`);
                
                if (isUpdate) {
                    // For updates, preserve the current selection and just refresh
                    const currentSlug = currentSelectedProcess ? currentSelectedProcess.slug : null;
                    await loadProcesses(true);
                    // Update the currentSelectedProcess name in case it changed
                    if (currentSelectedProcess && currentSlug) {
                        const updatedItem = processListSidebar.querySelector(`[data-process-slug="${currentSlug}"]`);
                        if (updatedItem) {
                            currentSelectedProcess.name = updatedItem.dataset.processName;
                        }
                    }
                } else {
                    // For new processes, select the newly created one
                    // Convert name to slug for matching
                    const nameSlug = name.trim().toLowerCase().replace(/\s+/g, '_');
                    // Store that we want to select a specific process
                    window.pendingProcessSelection = nameSlug;
                    // Load processes - will check for pendingProcessSelection and not auto-select first
                    await loadProcesses(false);
                    // Select the newly saved process by slug or name
                    setTimeout(() => {
                        const newProcessItem = processListSidebar.querySelector(`[data-process-slug="${nameSlug}"], [data-process-name="${name}"]`);
                        if (newProcessItem) {
                            // Remove active from all items first
                            processListSidebar.querySelectorAll('.list-group-item').forEach(item => {
                                item.classList.remove('active');
                            });
                            newProcessItem.classList.add('active');
                            currentSelectedProcess = {
                                name: newProcessItem.dataset.processName,
                                slug: newProcessItem.dataset.processSlug
                            };
                            updateCanvasHeader();
                        }
                        // Clear the pending selection flag
                        window.pendingProcessSelection = null;
                    }, 150);
                }
                
                if (window.reactFlowInstance) {
                    const savedData = window.reactFlowInstance.getFlow(false);
                    window.originalProcessData = JSON.stringify(savedData);
                    window.hasUnsavedChanges = false;
                    updateButtonStates();
                }
            } else {
                const err = await res.json();
                showSaveNotification(err.error || "Failed to save", true);
            }
        } catch (e) {
            console.error(e);
            showSaveNotification('Error saving process', true);
        }
    }

    if (updateProcessBtn) {
        updateProcessBtn.addEventListener('click', () => {
            if (!currentSelectedProcess) {
                showSaveNotification('Please select a review process to update', true);
                return;
            }
            const currentSlug = currentSelectedProcess.slug;
            const currentName = currentSelectedProcess.name;
            if (currentSlug === 'default_review') {
                showSaveNotification('Cannot update the default process. Please create a new one.', true);
                return;
            }
            if (!window.hasUnsavedChanges) {
                showSaveNotification('No changes to save', true);
                return;
            }
            // Use the actual display name, not the slug, to preserve the original name
            saveProcess(currentName, true);
        });
    }

    if (createProcessBtn) {
        createProcessBtn.addEventListener('click', async () => {
            // Get existing process names for uniqueness check
            const existingNames = new Set();
            if (processListSidebar) {
                processListSidebar.querySelectorAll('.list-group-item').forEach(item => {
                    existingNames.add(item.dataset.processName || item.textContent);
                });
            }
            
            let counter = 1;
            let defaultName;
            do {
                defaultName = `My Review Process ${counter}`;
                counter++;
            } while (existingNames.has(defaultName) && counter < 1000);
            
            const name = await showRenameModal("Create New Review Process", defaultName, true);
            if (name && name.trim()) {
                // Load default_review from active workspace process_definitions via API
                try {
                    const defaultRes = await fetch('/review_process_design/api/processes/default_review');
                    if (!defaultRes.ok) {
                        const errorData = await defaultRes.json().catch(() => ({}));
                        throw new Error(errorData.error || `Failed to load default process: ${defaultRes.status}`);
                    }
                    
                    const defaultData = await defaultRes.json();
                    if (!defaultData) {
                        throw new Error('Default process data is empty');
                    }
                    
                    // Ensure we have nodes or edges
                    if (!defaultData.nodes && !defaultData.edges) {
                        throw new Error('Default process has no nodes or edges');
                    }
                    
                    // Set the flow with default data
                    if (window.reactFlowInstance) {
                        // Update the name in the data to match the new process name
                        const processData = {
                            ...defaultData,
                            name: name.trim()
                        };
                        window.reactFlowInstance.setFlow(processData, true);
                        
                        // Wait a bit for the flow to be set and layout to be calculated
                        await new Promise(resolve => setTimeout(resolve, 300));
                        
                        // Now save it as the new process
                        await saveProcess(name.trim());
                    } else {
                        throw new Error('React Flow instance not available');
                    }
                } catch (e) {
                    console.error('Error loading default process:', e);
                    showSaveNotification(`Error loading default process template: ${e.message}`, true);
                }
            } else if (name !== null) {
                showSaveNotification('Process name cannot be empty', true);
            }
        });
    }
    
    // Create Review Process Button (in sidebar)
    if (createReviewProcessBtn) {
        createReviewProcessBtn.addEventListener('click', async () => {
            // Get existing process names for uniqueness check
            const existingNames = new Set();
            if (processListSidebar) {
                processListSidebar.querySelectorAll('.list-group-item').forEach(item => {
                    existingNames.add(item.dataset.processName || item.textContent);
                });
            }
            
            let counter = 1;
            let defaultName;
            do {
                defaultName = `My Review Process ${counter}`;
                counter++;
            } while (existingNames.has(defaultName) && counter < 1000);
            
            const name = await showRenameModal("Create New Review Process", defaultName, true);
            if (name && name.trim()) {
                // Load default_review from active workspace process_definitions via API
                try {
                    const defaultRes = await fetch('/review_process_design/api/processes/default_review');
                    if (!defaultRes.ok) {
                        const errorData = await defaultRes.json().catch(() => ({}));
                        throw new Error(errorData.error || `Failed to load default process: ${defaultRes.status}`);
                    }
                    
                    const defaultData = await defaultRes.json();
                    if (!defaultData) {
                        throw new Error('Default process data is empty');
                    }
                    
                    // Ensure we have nodes or edges
                    if (!defaultData.nodes && !defaultData.edges) {
                        throw new Error('Default process has no nodes or edges');
                    }
                    
                    // Set the flow with default data
                    if (window.reactFlowInstance) {
                        // Update the name in the data to match the new process name
                        const processData = {
                            ...defaultData,
                            name: name.trim()
                        };
                        window.reactFlowInstance.setFlow(processData, true);
                        
                        // Wait a bit for the flow to be set and layout to be calculated
                        await new Promise(resolve => setTimeout(resolve, 300));
                        
                        // Now save it as the new process
                        await saveProcess(name.trim());
                    } else {
                        throw new Error('React Flow instance not available');
                    }
                } catch (e) {
                    console.error('Error loading default process:', e);
                    showSaveNotification(`Error loading default process template: ${e.message}`, true);
                }
            } else if (name !== null) {
                showSaveNotification('Process name cannot be empty', true);
            }
        });
    }

    if (renameProcessBtn) {
        renameProcessBtn.addEventListener('click', async () => {
            const current = currentSelectedProcess ? currentSelectedProcess.slug : null;
            if (!current) {
                showSaveNotification('Please select a process to rename', true);
                return;
            }
            if (current === 'default_review') {
                showSaveNotification('Cannot rename the default process', true);
                return;
            }
            const currentDisplayName = currentSelectedProcess ? currentSelectedProcess.name : current;
            const newName = await showRenameModal('Rename Review Process', currentDisplayName);
            if (!newName || newName === currentDisplayName) return;
            try {
                const res = await fetch(`/review_process_design/api/processes/${encodeURIComponent(current)}/rename`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_name: newName })
                });
                const data = await res.json();
                if (res.ok) {
                    showSaveNotification(`Process renamed to "${newName}"`);
                    // Convert new name to slug for matching
                    const newNameSlug = newName.trim().toLowerCase().replace(/\s+/g, '_');
                    // Store that we want to select the renamed process
                    window.pendingProcessSelection = newNameSlug;
                    // Load processes - will check for pendingProcessSelection and not auto-select first
                    await loadProcesses(false);
                    // Select the renamed process by slug or name
                    setTimeout(() => {
                        const renamedItem = processListSidebar.querySelector(`[data-process-slug="${newNameSlug}"], [data-process-name="${newName}"]`);
                        if (renamedItem) {
                            // Remove active from all items first
                            processListSidebar.querySelectorAll('.list-group-item').forEach(item => {
                                item.classList.remove('active');
                            });
                            renamedItem.classList.add('active');
                            currentSelectedProcess = {
                                name: renamedItem.dataset.processName,
                                slug: renamedItem.dataset.processSlug
                            };
                            loadSpecificProcess(renamedItem.dataset.processSlug);
                            updateCanvasHeader();
                        }
                        // Clear the pending selection flag
                        window.pendingProcessSelection = null;
                    }, 150);
                } else {
                    showSaveNotification(data.error || 'Failed to rename process', true);
                }
            } catch (e) {
                showSaveNotification(`Error renaming process: ${e.message}`, true);
            }
        });
    }

    if (deleteProcessBtn) {
        deleteProcessBtn.addEventListener('click', async () => {
            const current = currentSelectedProcess ? currentSelectedProcess.slug : null;
            if (!current) {
                showSaveNotification('Please select a process to delete', true);
                return;
            }
            if (current === 'default_review') {
                showSaveNotification('Cannot delete the default process', true);
                return;
            }
            const processName = currentSelectedProcess ? currentSelectedProcess.name : current;
            const confirmed = await showDeleteModal(processName);
            if (!confirmed) return;
            try {
                const res = await fetch(`/review_process_design/api/processes/${encodeURIComponent(current)}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    showSaveNotification(`Process "${processName}" deleted successfully`);
                    currentSelectedProcess = null;
                    await loadProcesses(false);
                    // Select first process if available
                    const firstItem = processListSidebar.querySelector('.list-group-item');
                    if (firstItem) {
                        firstItem.classList.add('active');
                        currentSelectedProcess = {
                            name: firstItem.dataset.processName,
                            slug: firstItem.dataset.processSlug
                        };
                        await loadSpecificProcess(firstItem.dataset.processSlug);
                    } else if (window.reactFlowInstance) {
                        window.reactFlowInstance.clear();
                    }
                    updateCanvasHeader();
                } else {
                    const data = await res.json();
                    showSaveNotification(data.error || 'Failed to delete process', true);
                }
            } catch (e) {
                showSaveNotification(`Error deleting process: ${e.message}`, true);
            }
        });
    }

    // Load processes on page load
    await loadProcesses();
    updateButtonStates();
});
