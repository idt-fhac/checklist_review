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

// --- Custom Node Component ---
const GenericNode = ({ id, data, isConnectable, selected, providers = [], onOpenTextEditor }) => {
    const { label, config_schema, config = {}, onConfigChange, component_id, category } = data;

    const handleChange = (key, value) => {
        if (onConfigChange) {
            onConfigChange(id, key, value);
        }
    };
    
    // Automatically disable RAG when "answer_all_together" is enabled
    useEffect(() => {
        if (component_id === 'criterion_evaluator' && config.answer_all_together === true && config.use_rag === true) {
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

    const IGNORED_CONFIG = ['collection_name', 'pipeline_id', 'paper_name', 'criteria_set_name', 'force_review'];

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

        // For criterion_evaluator, explicitly define the order to ensure RAG fields appear after use_rag
        const questionReviewerOrder = [
            'provider_id',
            'system_prompt', 
            'force_review',
            'answer_all_together',
            'use_rag',
            'rag_chunking_strategy',
            'rag_top_k'
        ];
        // For specialist, Topic first then Criteria then provider_id
        const specialistOrder = ['topic', 'criteria', 'provider_id'];
        // For document_loader, Extraction Method first then Extract Pages as Image then Force Execution
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

        if (component_id === 'criterion_evaluator') {
            applyExplicitOrder(questionReviewerOrder);
        } else if (component_id === 'specialist') {
            applyExplicitOrder(specialistOrder);
        } else if (component_id === 'document_loader') {
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
        'tool': 'TOOL'
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
const createNodeTypes = (providers, onOpenTextEditor) => ({
    custom: (props) => {
        return React.createElement(GenericNode, { ...props, providers, onOpenTextEditor });
    }
});

// Protected node component IDs that cannot be deleted
const PROTECTED_NODES = ['document_loader', 'criterion_evaluator'];

// --- Main Editor Component ---
const ProcessEditor = () => {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [componentsMeta, setComponentsMeta] = useState({});
    const [contextMenu, setContextMenu] = useState(null);
    const [providers, setProviders] = useState([]);
    const reactFlowInstance = useReactFlow();

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

    // Helper function to safely call fitView with validation
    const safeFitView = (instance, options = {}) => {
        if (!instance || !instance.fitView) return false;
        
        try {
            // Check if nodes exist and have valid positions
            const flowNodes = instance.getNodes();
            if (!flowNodes || flowNodes.length === 0) return false;
            
            // Verify nodes have valid numeric positions
            const hasValidPositions = flowNodes.some(node => {
                const pos = node.position;
                return pos && typeof pos.x === 'number' && !isNaN(pos.x) && 
                       typeof pos.y === 'number' && !isNaN(pos.y) &&
                       isFinite(pos.x) && isFinite(pos.y);
            });
            
            if (!hasValidPositions) return false;
            
            // Check if the React Flow container element exists and has dimensions
            const reactFlowElement = document.querySelector('.react-flow');
            if (reactFlowElement) {
                const rect = reactFlowElement.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) {
                    // Container not ready yet
                    return false;
                }
            }
            
            // Call fitView with default options
            instance.fitView({
                padding: 0.2,
                duration: 300,
                includeHiddenNodes: false,
                ...options
            });
            return true;
        } catch (e) {
            console.warn('fitView failed:', e);
            return false;
        }
    };

    // Auto-fit view when nodes are loaded (similar to clicking the fit view button)
    // Use a ref to track if we should auto-fit (set by setFlow when loading)
    const shouldAutoFitRef = useRef(false);
    useEffect(() => {
        if (shouldAutoFitRef.current && nodes.length > 0 && reactFlowInstance) {
            shouldAutoFitRef.current = false; // Reset flag
            // Use requestAnimationFrame to ensure nodes are rendered to DOM
            const timeoutId = setTimeout(() => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        if (!safeFitView(reactFlowInstance)) {
                            // Retry once if first attempt failed
                            setTimeout(() => {
                                safeFitView(reactFlowInstance);
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
        // 3. criterion_evaluator -> only to post-processing

        if (sourceCategory === 'pre_process') {
            return targetComponentId === 'criterion_evaluator';
        } else if (sourceCategory === 'tool') {
            return targetComponentId === 'criterion_evaluator';
        } else if (sourceComponentId === 'criterion_evaluator') {
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
        // 3. criterion_evaluator -> only to post-processing

        let isValidConnection = false;

        if (sourceCategory === 'pre_process') {
            // Pre-processing can only connect to question reviewer
            isValidConnection = targetComponentId === 'criterion_evaluator';
        } else if (sourceCategory === 'tool') {
            // Tools can only connect to question reviewer
            isValidConnection = targetComponentId === 'criterion_evaluator';
        } else if (sourceComponentId === 'criterion_evaluator') {
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
        if ((sourceCategory === 'pre_process' && targetComponentId === 'criterion_evaluator') ||
            (sourceComponentId === 'criterion_evaluator' && targetCategory === 'post_process')) {
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

    // Load Metadata
    useEffect(() => {
        fetch('/checklist_review/api/components').then(res => res.json()).then(data => {
            const map = {}; data.forEach(c => map[c.id] = c); setComponentsMeta(map);
        });
    }, []);

    // Load Providers
    useEffect(() => {
        fetch('/checklist_review/api/providers').then(res => res.json()).then(data => {
            setProviders(data);
        }).catch(err => {
            console.error('Failed to load providers:', err);
            setProviders([]);
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

        const labels = { pre_process: "Pre-Process", review: "Review", tool: "Tools", post_process: "Post-Process" };

        ['pre_process', 'review', 'tool', 'post_process'].forEach(phase => {
            if (grouped[phase].length > 0) {
                const title = document.createElement('div');
                title.className = 'tool-category';
                title.textContent = labels[phase] || phase;
                toolsContainer.appendChild(title);

                grouped[phase].forEach(c => {
                    const el = document.createElement('div');
                    el.className = 'draggable-tool';
                    el.draggable = true;
                    el.textContent = c.label || c.name;
                    el.ondragstart = (event) => {
                        event.dataTransfer.setData('application/reactflow', c.id);
                        event.dataTransfer.effectAllowed = 'move';
                    };
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
        const questionReviewerNode = nodes.find(n => n.data?.component_id === 'criterion_evaluator');

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
        const TOOL_SPACING = 180; // Equal horizontal spacing between tool nodes
        const TOOL_VERTICAL_OFFSET = 350; // Fixed distance tools are below question reviewer (from top of QR to top of tools)

        // Group nodes by category
        const questionReviewer = nodesToLayout.find(n => n.data?.component_id === 'criterion_evaluator');
        const preProcessNodes = nodesToLayout.filter(n => n.data?.category === 'pre_process' && n.data?.component_id !== 'criterion_evaluator');
        const toolNodes = nodesToLayout.filter(n => n.data?.category === 'tool');
        const postProcessNodes = nodesToLayout.filter(n => n.data?.category === 'post_process');

        // Calculate node heights (estimate based on config items)
        const estimateNodeHeight = (node) => {
            const configSchema = node.data?.config_schema;
            const controlCount = configSchema?.properties ? Object.keys(configSchema.properties).filter(key =>
                !['collection_name', 'pipeline_id', 'paper_name', 'criteria_set_name'].includes(key)
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
                n.data?.component_id !== 'criterion_evaluator';
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

    // Use the global safeFitView function

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
            clear: () => { setNodes([]); setEdges([]); }
        };
    }, [nodes, edges, setNodes, setEdges, onConfigChange, reactFlowInstance, componentsMeta]);

    const nodeTypesWithProviders = useMemo(() => createNodeTypes(providers, openTextEditor), [providers, openTextEditor]);

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
            </div>
        `;
};

// Only initialize React Flow if the container exists (Review Process Design page)
const reactFlowRoot = document.getElementById('react-flow-root');
const textEditorModalRoot = document.getElementById('text-editor-modal-root');

if (reactFlowRoot) {
    const root = createRoot(reactFlowRoot);
    root.render(html`<${ReactFlowProvider}><${ProcessEditor} /><//>`);
}

// Render text editor modal at app level (outside React Flow) - only if container exists
let modalRoot = null;
let modalState = { isOpen: false, nodeId: null, fieldKey: null, fieldLabel: null, currentValue: '' };

if (textEditorModalRoot) {
    modalRoot = createRoot(textEditorModalRoot);
}

// Global function to open text editor from nodes
window.openTextEditor = ({ nodeId, fieldKey, fieldLabel, currentValue }) => {
    if (!modalRoot) return; // Only works on Review Process Design page
    modalState = { isOpen: true, nodeId, fieldKey, fieldLabel, currentValue };
    renderModal();
};

const renderModal = () => {
    if (!modalRoot) return; // Only works on Review Process Design page
    
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

if (modalRoot) {
    renderModal();
}

// --- Application Logic ---
// Global helper function to safely call fitView with validation
window.safeFitView = function(instance, options = {}) {
    if (!instance || !instance.fitView) return false;
    
    try {
        // Check if nodes exist and have valid positions
        const flowNodes = instance.getNodes();
        if (!flowNodes || flowNodes.length === 0) return false;
        
        // Verify nodes have valid numeric positions
        const hasValidPositions = flowNodes.some(node => {
            const pos = node.position;
            return pos && typeof pos.x === 'number' && !isNaN(pos.x) && 
                   typeof pos.y === 'number' && !isNaN(pos.y) &&
                   isFinite(pos.x) && isFinite(pos.y);
        });
        
        if (!hasValidPositions) return false;
        
        // Check if the React Flow container element exists and has dimensions
        const reactFlowElement = document.querySelector('.react-flow');
        if (reactFlowElement) {
            const rect = reactFlowElement.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) {
                // Container not ready yet
                return false;
            }
        }
        
        // Call fitView with default options
        instance.fitView({
            padding: 0.2,
            duration: 300,
            includeHiddenNodes: false,
            ...options
        });
        return true;
    } catch (e) {
        console.warn('fitView failed:', e);
        return false;
    }
};

document.addEventListener('DOMContentLoaded', async () => {
    // Helper function to get file stem (name without extension)
    function Path(pathString) {
        const parts = pathString.split(/[/\\]/);
        const filename = parts[parts.length - 1];
        const lastDot = filename.lastIndexOf('.');
        return {
            stem: lastDot > 0 ? filename.substring(0, lastDot) : filename,
            name: filename
        };
    }

    // Load settings
    let appSettings = {};
    try {
        const settingsRes = await fetch('/settings/api/settings');
        if (settingsRes.ok) {
            appSettings = await settingsRes.json();
        }
    } catch (e) {
        console.warn('Could not load settings:', e);
    }

    // Canvas toggle functionality (only if elements exist - they don't on Checklist Review page)
    const bottomPanel = document.getElementById('bottomPanel');
    const canvasToggleBtn = document.getElementById('canvasToggleBtn');
    const canvasToggleIcon = document.getElementById('canvasToggleIcon');
    const canvasToggleText = document.getElementById('canvasToggleText');
    const fullscreenToggleBtn = document.getElementById('fullscreenToggleBtn');
    let canvasVisible = false; // Canvas is not on Checklist Review page
    let isFullscreen = false;

    async function setCanvasVisibility(visible) {
        // Check if bottomPanel exists
        if (!bottomPanel) {
            console.warn('bottomPanel not found, cannot toggle visibility');
            return;
        }
        console.log('setCanvasVisibility called with:', visible, 'current canvasVisible:', canvasVisible);
        canvasVisible = visible;

        // Update canvasToggleBtn if it exists (Review Process Design page)
        if (canvasToggleBtn) {
            if (visible) {
                canvasToggleIcon?.classList.add('rotated');
                canvasToggleText.textContent = 'Hide Review Process Designer';
            } else {
                canvasToggleIcon?.classList.remove('rotated');
                canvasToggleText.textContent = 'Show Review Process Designer';
            }
        }

        if (visible) {
            bottomPanel.style.display = 'flex';
            // Force reflow
            bottomPanel.offsetHeight;
            setTimeout(() => {
                bottomPanel.classList.add('visible');
            }, 10);

            // Show fullscreen button when canvas is visible
            if (fullscreenToggleBtn) {
                fullscreenToggleBtn.style.display = 'flex';
            }

            // Auto-load the selected process when canvas becomes visible
            // Wait a bit for React Flow to be ready, then load the process
            setTimeout(async () => {
                const processSelect = document.getElementById('processSelect');
                
                // Wait for React Flow instance to be available
                let retries = 0;
                while (!window.reactFlowInstance && retries < 30) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    retries++;
                }
                
                if (window.reactFlowInstance) {
                    const selectedProcess = getSelectedProcess();
                    if (selectedProcess && selectedProcess.slug) {
                        // Load the selected process
                        await loadSpecificProcess(selectedProcess.slug);
                    } else if (processList && processList.children.length > 0) {
                        // If no process is selected but processes are available, load the first/default one
                        const defaultItem = processList.querySelector('[data-process-slug="scientific_checklist"]');
                        const firstItem = processList.querySelector('.list-group-item');
                        const processToLoad = defaultItem ? defaultItem.dataset.processSlug : (firstItem ? firstItem.dataset.processSlug : null);
                        if (processToLoad) {
                            if (defaultItem) {
                                defaultItem.classList.add('active');
                                currentSelectedProcess = {
                                    name: defaultItem.dataset.processName,
                                    slug: defaultItem.dataset.processSlug
                                };
                            } else if (firstItem) {
                                firstItem.classList.add('active');
                                currentSelectedProcess = {
                                    name: firstItem.dataset.processName,
                                    slug: firstItem.dataset.processSlug
                                };
                            }
                            await loadSpecificProcess(processToLoad);
                            updateCanvasHeader();
                        }
                    }
                } else {
                    console.warn('React Flow instance not available after showing bottom panel');
                }
            }, 300); // Give React Flow time to initialize
        } else {
            // Exit fullscreen if active when hiding canvas
            if (bottomPanel.classList.contains('fullscreen')) {
                bottomPanel.classList.remove('fullscreen');
                if (fullscreenToggleBtn) {
                    const fullscreenIcon = document.getElementById('fullscreenIcon');
                    const fullscreenText = document.getElementById('fullscreenText');
                    if (fullscreenIcon) {
                        fullscreenIcon.innerHTML = '<path d="M1.5 1a.5.5 0 0 0-.5.5v4a.5.5 0 0 1-1 0v-4A1.5 1.5 0 0 1 1.5 0h4a.5.5 0 0 1 0 1zM14 1.5a.5.5 0 0 1 .5-.5h4a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0V1.707l-4.146 4.147a.5.5 0 0 1-.708-.708L17.293 1zM1.5 14a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0v-4a.5.5 0 0 1 .5-.5m13 0a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0v-4a.5.5 0 0 1 .5-.5"/>';
                    }
                    if (fullscreenText) {
                        fullscreenText.textContent = 'Full Screen';
                    }
                }
                isFullscreen = false;
            }

            bottomPanel.classList.remove('visible');
            setTimeout(() => {
                if (!canvasVisible) {
                    bottomPanel.style.display = 'none';
                }
            }, 400);

            // Hide fullscreen button when canvas is hidden
            if (fullscreenToggleBtn) {
                fullscreenToggleBtn.style.display = 'none';
            }
        }
    }

    function toggleCanvas() {
        setCanvasVisibility(!canvasVisible);
    }

    if (canvasToggleBtn) {
        canvasToggleBtn.addEventListener('click', toggleCanvas);
    }

    // View Process Modal Functionality (Full Screen)
    const viewProcessModal = document.getElementById('viewProcessModal');
    const viewProcessModalClose = document.getElementById('viewProcessModalClose');
    const viewProcessModalTitle = document.getElementById('viewProcessModalTitle');
    const viewProcessFlowRoot = document.getElementById('viewProcessFlowRoot');
    let viewProcessFlowInstance = null;

    function closeViewModal() {
        if (viewProcessModal) {
            viewProcessModal.style.display = 'none';
        }
        if (viewProcessFlowInstance) {
            viewProcessFlowInstance.unmount();
            viewProcessFlowInstance = null;
        }
        if (viewProcessFlowRoot) {
            viewProcessFlowRoot.innerHTML = '';
        }
    }

    if (viewProcessModalClose) {
        viewProcessModalClose.addEventListener('click', closeViewModal);
    }

    if (viewProcessModal) {
        viewProcessModal.addEventListener('click', (e) => {
            if (e.target === viewProcessModal) {
                closeViewModal();
            }
        });
    }

    // View Process Button (in Review Process section) - Opens full-screen modal
    const viewProcessToggleBtn = document.getElementById('viewProcessToggleBtn');
    if (viewProcessToggleBtn) {
        viewProcessToggleBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const selectedProcess = getSelectedProcess();
            if (!selectedProcess || !selectedProcess.slug) {
                console.warn('No process selected, cannot view process');
                return;
            }

            const processName = selectedProcess.slug;
            const displayName = selectedProcess.name;

            if (viewProcessModalTitle) {
                viewProcessModalTitle.textContent = `View: ${displayName}`;
            }
            if (viewProcessModal) {
                viewProcessModal.style.display = 'flex';
            }

            try {
                // Fetch process data
                const res = await fetch(`/checklist_review/api/pipelines/${processName}`);
                if (!res.ok) {
                    throw new Error('Failed to load process');
                }
                const processData = await res.json();

                // Clear previous content
                if (viewProcessFlowRoot) {
                    viewProcessFlowRoot.innerHTML = '';
                }

                // Use main editor to get properly laid-out nodes if available
                let laidOutFlow = processData;
                if (window.reactFlowInstance && window.reactFlowInstance.setFlow) {
                    // Store current state
                    const currentFlow = window.reactFlowInstance.getFlow(false);
                    
                    // Temporarily load the process to get proper layout
                    window.reactFlowInstance.setFlow(processData, true);
                    
                    // Wait for layout, then get the laid-out nodes
                    await new Promise(resolve => setTimeout(resolve, 500));
                    laidOutFlow = window.reactFlowInstance.getFlow(true); // Get with positions
                    
                    // Restore original flow
                    if (currentFlow && currentFlow.nodes) {
                        window.reactFlowInstance.setFlow(currentFlow, true);
                    }
                }

                if (!laidOutFlow.nodes || laidOutFlow.nodes.length === 0) {
                    console.warn('No nodes to display');
                    closeViewModal();
                    return;
                }

                // Create read-only view using React Flow
                const { createRoot } = await import('react-dom/client');
                const { default: ReactFlow, ReactFlowProvider, Background, Controls, MiniMap } = await import('reactflow');
                const { default: React } = await import('react');
                const { default: htm } = await import('htm');
                const html = htm.bind(React.createElement);

                // Fetch providers and components for node rendering
                const [componentsRes, providersRes] = await Promise.all([
                    fetch('/checklist_review/api/components'),
                    fetch('/checklist_review/api/providers')
                ]);
                const components = await componentsRes.json();
                const providers = await providersRes.json();

                // Create read-only node types using GenericNode
                const createReadOnlyNodeTypes = (providers) => {
                    const ReadOnlyGenericNode = (props) => {
                        // Disable all interactions
                        return React.createElement(GenericNode, {
                            ...props,
                            providers: providers,
                            onOpenTextEditor: null, // Disable text editor
                            isConnectable: false
                        });
                    };
                    return { custom: ReadOnlyGenericNode };
                };

                const ViewProcessFlow = () => {
                    const viewNodes = laidOutFlow.nodes.map(n => ({
                        ...n,
                        type: 'custom',
                        draggable: false,
                        selectable: false,
                        connectable: false
                    }));
                    const viewEdges = (laidOutFlow.edges || []).map(e => ({
                        ...e,
                        selectable: false
                    }));

                    const [nodes] = React.useState(viewNodes);
                    const [edges] = React.useState(viewEdges);
                    const reactFlowInstance = React.useRef(null);

                    React.useEffect(() => {
                        if (reactFlowInstance.current && nodes.length > 0) {
                            setTimeout(() => {
                                if (window.safeFitView) {
                                    window.safeFitView(reactFlowInstance.current, { padding: 0.2, duration: 300 });
                                }
                            }, 200);
                        }
                    }, []);

                    const nodeTypes = createReadOnlyNodeTypes(providers);

                    if (nodes.length === 0) {
                        return html`<div style=${{ 
                            width: '100%', 
                            height: '100%', 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center',
                            color: '#64748b'
                        }}>No nodes to display</div>`;
                    }

                    return html`
                        <div style=${{ 
                            width: '100%', 
                            height: '100%', 
                            minHeight: '600px', 
                            position: 'relative',
                            background: '#f8fafc'
                        }}>
                            <${ReactFlowProvider}>
                                <${ReactFlow}
                                    nodes=${nodes}
                                    edges=${edges}
                                    onInit=${(instance) => { 
                                        reactFlowInstance.current = instance;
                                        setTimeout(() => {
                                            if (window.safeFitView) {
                                                window.safeFitView(instance, { padding: 0.2, duration: 300 });
                                            }
                                        }, 200);
                                    }}
                                    nodeTypes=${nodeTypes}
                                    nodesDraggable=${false}
                                    nodesConnectable=${false}
                                    elementsSelectable=${false}
                                    panOnDrag=${true}
                                    zoomOnScroll=${true}
                                    zoomOnPinch=${true}
                                    style=${{ width: '100%', height: '100%' }}
                                >
                                    <${Background} gap=${20} size=${1} />
                                    <${Controls} />
                                    <${MiniMap} />
                                <//>
                            <//>
                        </div>
                    `;
                };

                // Ensure container has explicit dimensions
                if (viewProcessFlowRoot) {
                    viewProcessFlowRoot.style.width = '100%';
                    viewProcessFlowRoot.style.height = '100%';
                    viewProcessFlowRoot.style.minHeight = '600px';
                }

                const root = createRoot(viewProcessFlowRoot);
                root.render(html`<${ViewProcessFlow} />`);
                viewProcessFlowInstance = root;
            } catch (e) {
                console.error('Error loading process for view:', e);
                closeViewModal();
            }
        });
        
        // Update button state when process selection changes
        const updateViewButtonState = () => {
            if (viewProcessToggleBtn) {
                const selectedProcess = getSelectedProcess();
                viewProcessToggleBtn.disabled = !selectedProcess || !selectedProcess.slug;
            }
        };
        document.addEventListener('processSelected', updateViewButtonState);
        // Store function globally so it can be called after processes load
        window.updateViewButtonState = updateViewButtonState;
    } else {
        // viewProcessToggleBtn not found - this is okay if the button doesn't exist
    }

    // Fullscreen toggle functionality
    const fullscreenIcon = document.getElementById('fullscreenIcon');
    const fullscreenText = document.getElementById('fullscreenText');

    async function toggleFullscreen() {
        isFullscreen = !isFullscreen;

        if (isFullscreen) {
            // Enter fullscreen
            bottomPanel.classList.add('fullscreen');
            // Update icon to exit fullscreen icon (compress icon)
            fullscreenIcon.innerHTML = '<path d="M5.5 0a.5.5 0 0 1 .5.5v4A1.5 1.5 0 0 0 7.5 6h4a.5.5 0 0 1 0 1h-4A2.5 2.5 0 0 1 5 4.5v-4a.5.5 0 0 1 .5-.5m5 0a.5.5 0 0 1 .5.5v4a2.5 2.5 0 0 1-2.5 2.5h-4a.5.5 0 0 1 0-1h4A1.5 1.5 0 0 0 10 4.5v-4a.5.5 0 0 1 .5-.5"/><path d="M0 5.5A1.5 1.5 0 0 1 1.5 4h4a.5.5 0 0 1 0 1h-4a.5.5 0 0 0-.5.5v4a.5.5 0 0 1-1 0zm14 0A1.5 1.5 0 0 0 12.5 4h-4a.5.5 0 0 1 0-1h4A2.5 2.5 0 0 1 15 5.5v4a.5.5 0 0 1-1 0z"/>';
            fullscreenText.textContent = 'Exit Full Screen';

            // Reload and center canvas when entering fullscreen
            await reloadAndCenterCanvas();
        } else {
            // Exit fullscreen
            bottomPanel.classList.remove('fullscreen');
            // Update icon back to fullscreen icon (expand icon)
            fullscreenIcon.innerHTML = '<path d="M1.5 1a.5.5 0 0 0-.5.5v4a.5.5 0 0 1-1 0v-4A1.5 1.5 0 0 1 1.5 0h4a.5.5 0 0 1 0 1zM14 1.5a.5.5 0 0 1 .5-.5h4a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0V1.707l-4.146 4.147a.5.5 0 0 1-.708-.708L17.293 1zM1.5 14a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0v-4a.5.5 0 0 1 .5-.5m13 0a.5.5 0 0 1 .5.5v4a.5.5 0 0 1-1 0v-4a.5.5 0 0 1 .5-.5"/>';
            fullscreenText.textContent = 'Full Screen';

            // Reload and center canvas when exiting fullscreen
            await reloadAndCenterCanvas();
        }
    }

    async function reloadAndCenterCanvas() {
        // Wait for layout to settle
        await new Promise(resolve => setTimeout(resolve, 150));

        if (!window.reactFlowInstance) {
            return;
        }

        // Get current flow data
        const currentFlow = window.reactFlowInstance.getFlow(false);
        if (!currentFlow || (!currentFlow.nodes || currentFlow.nodes.length === 0)) {
            // If no flow data, try to load the current process
            const selectedProcess = getSelectedProcess();
            if (selectedProcess && selectedProcess.slug) {
                await loadSpecificProcess(selectedProcess.slug);
            }
            return;
        }

        // Reload the flow to trigger re-render and re-layout
        window.reactFlowInstance.setFlow(currentFlow, true);

        // Fit view to center everything
        setTimeout(() => {
            if (window.reactFlowInstance && window.safeFitView) {
                if (!window.safeFitView(window.reactFlowInstance)) {
                    // Retry once if first attempt failed
                    setTimeout(() => {
                        window.safeFitView(window.reactFlowInstance);
                    }, 200);
                }
            }
        }, 200);
    }

    if (fullscreenToggleBtn) {
        fullscreenToggleBtn.addEventListener('click', toggleFullscreen);
    }

    // Canvas is not on Checklist Review page, so don't initialize it
    // setCanvasVisibility(canvasVisible);

    let currentCollection = '';
    const logContent = document.getElementById('logContent');
    const logCountElement = document.getElementById('logCount');
    const clearLogBtn = document.getElementById('clearLogBtn');
    
    // Helper function to format timestamp
    const formatTime = () => {
        const now = new Date();
        return now.toLocaleTimeString('en-US', { 
            hour12: false, 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit' 
        });
    };
    
    // Helper function to update log count
    const updateLogCount = () => {
        const entries = logContent.querySelectorAll('.log-entry:not(.log-ready)').length;
        logCountElement.textContent = `${entries} ${entries === 1 ? 'entry' : 'entries'}`;
    };
    
    // Helper function to add log entry with timestamp
    const addLogEntry = (message, className = '', prefix = '') => {
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${className}`;
        
        // Separators don't need timestamps
        if (className === 'log-separator') {
            logEntry.textContent = prefix + message;
        } else {
            const timestamp = document.createElement('span');
            timestamp.className = 'log-timestamp';
            timestamp.textContent = formatTime();
            
            const messageSpan = document.createElement('span');
            messageSpan.className = 'log-message';
            messageSpan.textContent = prefix + message;
            
            logEntry.appendChild(timestamp);
            logEntry.appendChild(messageSpan);
        }
        
        logContent.appendChild(logEntry);
        logContent.scrollTop = logContent.scrollHeight;
        updateLogCount();
    };
    
    // Clear log function
    const clearLog = () => {
        logContent.innerHTML = '<div class="log-entry log-ready"><span class="log-timestamp"></span><span class="log-message">Ready.</span></div>';
        updateLogCount();
    };
    
    // Clear log button handler
    if (clearLogBtn) {
        clearLogBtn.addEventListener('click', clearLog);
    }
    
    // Initialize log count
    updateLogCount();
    
    const log = (msg) => {
        addLogEntry(msg, '', '> ');
    };

    const collectionSelect = document.getElementById('collectionSelect');
    const collectionModeToggle = document.getElementById('collectionModeToggle');
    const collectionSection = document.getElementById('collectionSection');
    const directUploadBtn = document.getElementById('directUploadBtn');
    const fromCollectionBtn = document.getElementById('fromCollectionBtn');
    let collectionMode = 'from_collection'; // 'direct_upload' or 'from_collection'

    const startProcessBtn = document.getElementById('startProcessBtn');
    const deleteAllResponsesBtn = document.getElementById('deleteAllResponsesBtn');
    const updateProcessBtn = document.getElementById('updateProcessBtn');
    const createProcessBtn = document.getElementById('createProcessBtn');
    const renameProcessBtn = document.getElementById('renameProcessBtn');
    const deleteProcessBtn = document.getElementById('deleteProcessBtn');
    window.originalProcessData = null;
    window.hasUnsavedChanges = false;
    const processList = document.getElementById('processList');
    const papersList = document.getElementById('papersList');
    
    // Global variable for selected process
    let currentSelectedProcess = null;
    const outputsContainer = document.getElementById('outputsContainer');
    const outputsTitle = document.getElementById('outputsTitle');
    const deleteResultBtn = document.getElementById('deleteResultBtn');
    /** When a result is shown, holds { collection_name, pipeline_id, criteria_set_name, paper_id } for the Outputs tab */
    let currentResultContext = null;
    // Outputs tab elements are initialized early to avoid TDZ in startup flows.
    let outputsModalSelect = null;
    let outputsModalView = null;
    let outputsModalViewTitle = null;
    let outputsModalViewContent = null;
    let outputsModalExportBtn = null;
    let outputsModalEmpty = null;
    let outputsTokenUsageWrap = null;
    let outputsTokenUsageContent = null;
    let collectionTokenUsageContent = null;
    let collectionTokenUsageScopeLabel = null;
    const checklistList = document.getElementById('checklistList');
    const paperUploadContainer = document.getElementById('paperUploadContainer');
    const paperUpload = document.getElementById('paperUpload');
    const paperDropzone = document.getElementById('paperDropzone');
    const checklistUpload = document.getElementById('checklistUpload');
    
    // Global variable for selected checklist
    let currentSelectedChecklist = null;

    // Collection Mode Toggle Handler
    async function updateCollectionMode(mode) {
        collectionMode = mode;
        collectionModeToggle.setAttribute('data-mode', mode);

        // Reset checklist selection when switching modes and select first one
        const activeItem = checklistList.querySelector('.list-group-item.active');
        if (activeItem) {
            activeItem.classList.remove('active');
        }
        // Select first checklist by default
        const firstItem = checklistList.querySelector('.list-group-item');
        if (firstItem) {
            firstItem.classList.add('active');
            firstItem.dispatchEvent(new Event('click'));
        }

        if (mode === 'from_collection') {
            directUploadBtn.classList.remove('active');
            fromCollectionBtn.classList.add('active');
            collectionSection.style.display = 'block';
            // Remove placeholder option if it exists and collections are available
            const placeholderOption = collectionSelect.querySelector('option[value=""]');
            if (placeholderOption && collectionSelect.options.length > 1) {
                placeholderOption.remove();
            }
            // Select first collection by default
            if (!collectionSelect.value || collectionSelect.value === '') {
                if (collectionSelect.options.length > 0) {
                    collectionSelect.value = collectionSelect.options[0].value;
                }
            }
            currentCollection = collectionSelect.value;
        } else {
            directUploadBtn.classList.add('active');
            fromCollectionBtn.classList.remove('active');
            collectionSection.style.display = 'none';
            // Set to Temporary for direct upload mode
            currentCollection = 'Temporary';
        }

        if (currentCollection) {
            await initCollection();
        }
    }

    directUploadBtn.addEventListener('click', () => {
        if (collectionMode !== 'direct_upload') {
            updateCollectionMode('direct_upload');
        }
    });

    fromCollectionBtn.addEventListener('click', () => {
        if (collectionMode !== 'from_collection') {
            updateCollectionMode('from_collection');
        }
    });

    // Collection Select Handler
    collectionSelect.addEventListener('change', async () => {
        // Stop any existing polling
        stopStatusPolling();
        updateButtonState(false);
        currentTaskId = null;

        currentCollection = collectionSelect.value;
        if (currentCollection) {
            await initCollection();
            // Check for running review after collection is initialized
            setTimeout(() => {
                checkRunningReview();
            }, 500);
        }
    });

    // Init - read initial mode from HTML and initialize accordingly
    const initialMode = collectionModeToggle.getAttribute('data-mode') || 'from_collection';
    collectionMode = initialMode;
    
    // Initialize collection mode (this will set up the UI and collection selection)
    await updateCollectionMode(initialMode);
    
    // Initialize button states after collection loads
    setTimeout(() => {
        updateButtonStates();
        // Update view button state after processes are loaded
        if (window.updateViewButtonState) {
            window.updateViewButtonState();
        }
    }, 500);

    // Show Rename Modal
    function showRenameModal(title, currentName, isCreate = false) {
        return new Promise((resolve) => {
            const buttonText = isCreate ? 'Save' : 'Rename';
            const labelText = isCreate ? 'Process Name:' : 'New Name:';
            const overlay = document.createElement('div');
            overlay.className = 'delete-modal-overlay';
            overlay.style.animation = 'fadeIn 0.2s ease-out';
            overlay.innerHTML = `
                    <div class="delete-modal" style="max-width: 500px;">
                        <div class="delete-modal-header">
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                                <path d="M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.5.5 0 0 1-.175-.032l-.179.178a.5.5 0 0 0 .11.172l2 2a.5.5 0 0 0 .708 0l.13-.13z"/>
                            </svg>
                            <h5>${title}</h5>
                        </div>
                        <div class="delete-modal-body">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #0f172a;">${labelText}</label>
                            <input type="text" id="renameInput" class="form-control" value="${currentName}" style="width: 100%; padding: 0.75rem; border-radius: 6px; border: 2px solid #e2e8f0; font-size: 0.9rem;">
                        </div>
                        <div class="delete-modal-footer">
                            <button class="delete-modal-btn delete-modal-btn-cancel" id="renameModalCancel">Cancel</button>
                            <button class="delete-modal-btn" id="renameModalConfirm" style="background: #2563eb; color: white;">${buttonText}</button>
                        </div>
                    </div>
                `;

            document.body.appendChild(overlay);

            const input = overlay.querySelector('#renameInput');
            // Focus and select after a short delay to avoid autofocus conflicts
            setTimeout(() => {
                input.focus();
                input.select();
            }, 100);

            let isClosing = false;
            const closeModal = (confirmed, value = null) => {
                if (isClosing) return;
                isClosing = true;
                overlay.style.animation = 'fadeIn 0.2s ease-out reverse';
                setTimeout(() => {
                    if (document.body.contains(overlay)) {
                        document.body.removeChild(overlay);
                    }
                    resolve(confirmed ? value : null);
                }, 200);
            };

            const handleConfirm = () => {
                const newName = input.value.trim();
                if (isCreate) {
                    // For creating, just need a non-empty name
                    if (newName) {
                        closeModal(true, newName);
                    }
                } else {
                    // For renaming, need a different name
                    if (newName && newName !== currentName) {
                        closeModal(true, newName);
                    }
                }
            };

            overlay.querySelector('#renameModalCancel').addEventListener('click', () => closeModal(false));
            overlay.querySelector('#renameModalConfirm').addEventListener('click', handleConfirm);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    handleConfirm();
                }
            });

            // Close on overlay click
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    closeModal(false);
                }
            });

            // Close on Escape key
            const escapeHandler = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', escapeHandler);
                    closeModal(false);
                }
            };
            document.addEventListener('keydown', escapeHandler);
        });
    }

    // Show Delete Confirmation Modal
    function showDeleteConfirmModal(title, itemName, itemType = 'item') {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'delete-modal-overlay';
            overlay.style.animation = 'fadeIn 0.2s ease-out';
            overlay.innerHTML = `
                    <div class="delete-modal" style="max-width: 500px;">
                        <div class="delete-modal-header">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16">
                                <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
                            </svg>
                            <h5>${title}</h5>
                        </div>
                        <div class="delete-modal-body">
                            <p>Are you sure you want to delete the ${itemType} <strong>"${itemName}"</strong>?</p>
                            <p style="color: #6c757d; font-size: 0.9rem; margin-top: 1rem;">This action cannot be undone.</p>
                        </div>
                        <div class="delete-modal-footer">
                            <button class="delete-modal-btn delete-modal-btn-cancel" id="deleteConfirmCancel">Cancel</button>
                            <button class="delete-modal-btn delete-modal-btn-delete" id="deleteConfirmConfirm">Delete</button>
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
                    if (document.body.contains(overlay)) {
                        document.body.removeChild(overlay);
                    }
                    resolve(confirmed);
                }, 200);
            };

            overlay.querySelector('#deleteConfirmCancel').addEventListener('click', () => closeModal(false));
            overlay.querySelector('#deleteConfirmConfirm').addEventListener('click', () => closeModal(true));

            // Close on overlay click
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    closeModal(false);
                }
            });

            // Close on Escape key
            const escapeHandler = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', escapeHandler);
                    closeModal(false);
                }
            };
            document.addEventListener('keydown', escapeHandler);
        });
    }

    function showDeleteAllResponsesModal(resultCount, collectionName, processName, checklistName) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'delete-modal-overlay';
            overlay.style.animation = 'fadeIn 0.2s ease-out';
            overlay.innerHTML = `
                    <div class="delete-modal" style="max-width: 560px;">
                        <div class="delete-modal-header">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16">
                                <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
                            </svg>
                            <h5>Delete All Responses</h5>
                        </div>
                        <div class="delete-modal-body">
                            <p>This will permanently delete <strong>${Number(resultCount || 0).toLocaleString()} response(s)</strong> for:</p>
                            <ul style="margin: 0.75rem 0 0; padding-left: 1.25rem; color: #475569; font-size: 0.95rem; line-height: 1.6;">
                                <li><strong>Collection:</strong> ${escapeHtml(collectionName)}</li>
                                <li><strong>Process:</strong> ${escapeHtml(processName)}</li>
                                <li><strong>Checklist:</strong> ${escapeHtml(checklistName)}</li>
                            </ul>
                            <p style="color: #6c757d; font-size: 0.9rem; margin-top: 1rem;">This action cannot be undone.</p>
                        </div>
                        <div class="delete-modal-footer">
                            <button class="delete-modal-btn delete-modal-btn-cancel" id="deleteAllResponsesCancel">Cancel</button>
                            <button class="delete-modal-btn delete-modal-btn-delete" id="deleteAllResponsesConfirm">Delete All</button>
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
                    if (document.body.contains(overlay)) {
                        document.body.removeChild(overlay);
                    }
                    resolve(confirmed);
                }, 200);
            };

            overlay.querySelector('#deleteAllResponsesCancel').addEventListener('click', () => closeModal(false));
            overlay.querySelector('#deleteAllResponsesConfirm').addEventListener('click', () => closeModal(true));

            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    closeModal(false);
                }
            });

            const escapeHandler = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', escapeHandler);
                    closeModal(false);
                }
            };
            document.addEventListener('keydown', escapeHandler);
        });
    }

    async function initCollection() {
        if (!currentCollection) return;

        // Reset change tracking when collection changes
        window.originalProcessData = null;
        window.hasUnsavedChanges = false;
        updateButtonStates();

        // Show/hide paper upload box based on collection
        if (currentCollection === 'Temporary') {
            paperUploadContainer.style.display = 'block';
        } else {
            paperUploadContainer.style.display = 'none';
        }

        // Clear outputs when collection changes
        outputsContainer.innerHTML = '<div class="text-muted text-center p-4">Select a paper to view review outputs.</div>';
        outputsTitle.textContent = 'Checklist Review Outputs';
        deleteResultBtn.style.display = 'none';
        currentResultContext = null;
        clearOutputsTabState();

        await loadChecklists();
        await loadProcesses();
        await loadPapersList();
        updateCanvasHeader();
        // Update view button state after processes are loaded
        if (window.updateViewButtonState) {
            window.updateViewButtonState();
        }
    }

    async function loadProcesses(preserveSelection = false) {
        processList.innerHTML = '';
        const currentValue = preserveSelection && currentSelectedProcess ? currentSelectedProcess.slug : null;
        
        try {
            const res = await fetch(`/checklist_review/api/pipelines`);
            const data = await res.json();
            
            if (data.length === 0) {
                processList.innerHTML = '<div class="text-center p-3 text-muted small">No processes found.</div>';
                return;
            }
            
            let preservedProcess = null;
            
            data.forEach((p) => {
                const displayName = p.name || (p.data && p.data.name) || p.slug || 'Unknown';
                const slugValue = p.slug || p.name;
                
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                listItem.dataset.processName = displayName;
                listItem.dataset.processSlug = slugValue;
                
                // Process name
                const nameDiv = document.createElement('div');
                nameDiv.className = 'text-truncate';
                nameDiv.style.maxWidth = '70%';
                nameDiv.textContent = displayName;
                
                // View button
                const viewBtn = document.createElement('button');
                viewBtn.className = 'btn btn-sm btn-outline-primary process-view-btn';
                viewBtn.style.cssText = 'padding: 0.25rem 0.5rem; min-width: 32px; border-radius: 6px;';
                viewBtn.title = 'View Process';
                viewBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8M1.173 8a13 13 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5s3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8q-.086.13-.195.288c-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5s-3.879-1.168-5.168-2.457A13 13 0 0 1 1.172 8z"/>
                        <path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0"/>
                    </svg>
                `;
                
                // Click handler for selection
                listItem.addEventListener('click', async (e) => {
                    // Don't trigger selection if clicking the view button
                    if (e.target.closest('.process-view-btn')) {
                        return;
                    }
                    
                    // Remove active class from all items
                    processList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    
                    // Add active class to clicked item
                    listItem.classList.add('active');
                    currentSelectedProcess = {
                        name: displayName,
                        slug: slugValue
                    };
                    
                    // Load the selected process
                    await loadSpecificProcess(slugValue);
                    loadPapersList(); // Reload papers to update result badges
                    updateButtonStates();
                    updateCanvasHeader();
                    if (window.updateViewButtonState) {
                        window.updateViewButtonState();
                    }
                    
                    // Trigger change event for compatibility
                    const changeEvent = new Event('processSelected');
                    changeEvent.process = currentSelectedProcess;
                    document.dispatchEvent(changeEvent);
                });
                
                // View button click handler
                viewBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await viewProcess(slugValue);
                });
                
                listItem.appendChild(nameDiv);
                listItem.appendChild(viewBtn);
                processList.appendChild(listItem);
                
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
            } else if (data.length > 0 && !preserveSelection) {
                // Select first process if no preserved selection
                const firstItem = processList.querySelector('.list-group-item');
                if (firstItem) {
                    firstItem.classList.add('active');
                    currentSelectedProcess = {
                        name: firstItem.dataset.processName,
                        slug: firstItem.dataset.processSlug
                    };
                    // Load process (only loads into React Flow if available)
                    await loadSpecificProcess(firstItem.dataset.processSlug);
                    updateCanvasHeader();
                    if (window.updateViewButtonState) {
                        window.updateViewButtonState();
                    }
                }
            }
            // Always update canvas header after loading processes
            updateCanvasHeader();
            // Update view button state after processes are loaded
            if (window.updateViewButtonState) {
                window.updateViewButtonState();
            }
        } catch (e) { 
            console.error('Error loading processes:', e);
        }
    }
    
    // Helper function to get currently selected process
    function getSelectedProcess() {
        const activeItem = processList.querySelector('.list-group-item.active');
        if (activeItem) {
            return {
                name: activeItem.dataset.processName,
                slug: activeItem.dataset.processSlug
            };
        }
        return currentSelectedProcess;
    }
    
    // Helper function to view a process
    async function viewProcess(processSlug) {
        const viewProcessModal = document.getElementById('viewProcessModal');
        const viewProcessModalTitle = document.getElementById('viewProcessModalTitle');
        const viewProcessFlowRoot = document.getElementById('viewProcessFlowRoot');
        
        if (!viewProcessModal || !viewProcessFlowRoot) {
            console.warn('View process modal not found');
            return;
        }
        
        const item = processList.querySelector(`[data-process-slug="${processSlug}"]`);
        const displayName = item ? item.dataset.processName : processSlug;
        
        if (viewProcessModalTitle) {
            viewProcessModalTitle.textContent = `View: ${displayName}`;
        }
        if (viewProcessModal) {
            viewProcessModal.style.display = 'flex';
        }
        
        try {
            // Fetch process data
            const res = await fetch(`/checklist_review/api/pipelines/${processSlug}`);
            if (!res.ok) {
                throw new Error('Failed to load process');
            }
            const processData = await res.json();
            
            // Clear previous content
            if (viewProcessFlowRoot) {
                viewProcessFlowRoot.innerHTML = '';
            }
            
            // Use main editor to get properly laid-out nodes if available
            let laidOutFlow = processData;
            if (window.reactFlowInstance && window.reactFlowInstance.setFlow) {
                // Store current state
                const currentFlow = window.reactFlowInstance.getFlow(false);
                
                // Temporarily load the process to get proper layout
                window.reactFlowInstance.setFlow(processData, true);
                
                // Wait for layout, then get the laid-out nodes
                await new Promise(resolve => setTimeout(resolve, 500));
                laidOutFlow = window.reactFlowInstance.getFlow(true); // Get with positions
                
                // Restore original flow
                if (currentFlow && currentFlow.nodes) {
                    window.reactFlowInstance.setFlow(currentFlow, true);
                }
            }
            
            if (!laidOutFlow.nodes || laidOutFlow.nodes.length === 0) {
                console.warn('No nodes to display');
                if (viewProcessModal) {
                    viewProcessModal.style.display = 'none';
                }
                return;
            }
            
            // Create read-only view using React Flow (same as viewProcessToggleBtn handler)
            const { createRoot } = await import('react-dom/client');
            const { default: ReactFlow, ReactFlowProvider, Background, Controls, MiniMap, useReactFlow } = await import('reactflow');
            const { default: React } = await import('react');
            const { default: htm } = await import('htm');
            const html = htm.bind(React.createElement);
            
            // Fetch providers and components for node rendering
            const [componentsRes, providersRes] = await Promise.all([
                fetch('/checklist_review/api/components'),
                fetch('/checklist_review/api/providers')
            ]);
            const components = await componentsRes.json();
            const providers = await providersRes.json();
            
            // Create read-only node types using GenericNode
            const createReadOnlyNodeTypes = (providers) => {
                const ReadOnlyGenericNode = (props) => {
                    // Disable all interactions
                    return React.createElement(GenericNode, {
                        ...props,
                        providers: providers,
                        onOpenTextEditor: null, // Disable text editor
                        isConnectable: false
                    });
                };
                return { custom: ReadOnlyGenericNode };
            };
            
            // Inner component that uses useReactFlow hook to access the instance
            const FlowContent = ({ nodes, edges, nodeTypes }) => {
                const { fitView } = useReactFlow();
                const hasFittedRef = React.useRef(false);
                
                // Function to attempt fitView with retries
                const attemptFitView = React.useCallback(() => {
                    if (hasFittedRef.current) return;
                    
                    const tryFit = (retries = 0) => {
                        if (retries > 10) return; // Max 10 retries
                        
                        // Check if modal is visible
                        const modal = document.getElementById('viewProcessModal');
                        if (!modal || modal.style.display === 'none') {
                            setTimeout(() => tryFit(retries + 1), 100);
                            return;
                        }
                        
                        // Check if React Flow container has dimensions
                        const reactFlowElement = document.querySelector('#viewProcessFlowRoot .react-flow');
                        if (reactFlowElement) {
                            const rect = reactFlowElement.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) {
                                setTimeout(() => tryFit(retries + 1), 100);
                                return;
                            }
                        }
                        
                        // Try to fit view
                        try {
                            fitView({
                                padding: 0.2,
                                duration: 300,
                                includeHiddenNodes: false
                            });
                            hasFittedRef.current = true;
                        } catch (e) {
                            if (retries < 10) {
                                setTimeout(() => tryFit(retries + 1), 100);
                            }
                        }
                    };
                    
                    // Use requestAnimationFrame to ensure DOM is ready
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => {
                            tryFit();
                        });
                    });
                }, [fitView]);
                
                React.useEffect(() => {
                    if (nodes.length > 0) {
                        // Wait a bit for the modal to be fully visible
                        const timeoutId = setTimeout(() => {
                            attemptFitView();
                        }, 100);
                        return () => clearTimeout(timeoutId);
                    }
                }, [nodes.length, attemptFitView]);
                
                return html`
                    <${ReactFlow}
                        nodes=${nodes}
                        edges=${edges}
                        nodeTypes=${nodeTypes}
                        nodesDraggable=${false}
                        nodesConnectable=${false}
                        elementsSelectable=${false}
                        panOnDrag=${true}
                        zoomOnScroll=${true}
                        zoomOnPinch=${true}
                        style=${{ width: '100%', height: '100%' }}
                    >
                        <${Background} gap=${20} size=${1} />
                        <${Controls} />
                        <${MiniMap} />
                    <//>
                `;
            };
            
            const ViewProcessFlow = () => {
                const viewNodes = laidOutFlow.nodes.map(n => ({
                    ...n,
                    type: 'custom',
                    draggable: false,
                    selectable: false,
                    connectable: false
                }));
                const viewEdges = (laidOutFlow.edges || []).map(e => ({
                    ...e,
                    selectable: false
                }));
                
                const [nodes] = React.useState(viewNodes);
                const [edges] = React.useState(viewEdges);
                const nodeTypes = createReadOnlyNodeTypes(providers);
                
                if (nodes.length === 0) {
                    return html`<div style=${{ 
                        width: '100%', 
                        height: '100%', 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center',
                        color: '#64748b'
                    }}>No nodes to display</div>`;
                }
                
                return html`
                    <div style=${{ 
                        width: '100%', 
                        height: '100%', 
                        minHeight: '600px', 
                        position: 'relative',
                        background: '#f8fafc'
                    }}>
                        <${ReactFlowProvider}>
                            <${FlowContent} nodes=${nodes} edges=${edges} nodeTypes=${nodeTypes} />
                        <//>
                    </div>
                `;
            };
            
            // Ensure container has explicit dimensions
            if (viewProcessFlowRoot) {
                viewProcessFlowRoot.style.width = '100%';
                viewProcessFlowRoot.style.height = '100%';
                viewProcessFlowRoot.style.minHeight = '600px';
            }
            
            const root = createRoot(viewProcessFlowRoot);
            root.render(html`<${ViewProcessFlow} />`);
        } catch (e) {
            console.error('Error loading process for view:', e);
            if (viewProcessModal) {
                viewProcessModal.style.display = 'none';
            }
        }
    }

    // Listen for process selection changes
    document.addEventListener('processSelected', async (e) => {
        if (e.process && e.process.slug) {
            await loadSpecificProcess(e.process.slug);
            loadPapersList(); // Reload papers to update result badges
            updateButtonStates();
            updateCanvasHeader();
            if (window.updateViewButtonState) {
                window.updateViewButtonState();
            }
        }
    });

    // Listen for checklist selection changes
    document.addEventListener('checklistSelected', async (e) => {
        if (e.checklist && e.checklist.name) {
            loadPapersList(); // Reload papers to update result badges for the new checklist
            // Clear the outputs container if a different checklist is selected
            if (outputsContainer) {
                outputsContainer.innerHTML = '';
                outputsTitle.textContent = 'Review Outputs';
                if (deleteResultBtn) deleteResultBtn.style.display = 'none';
                currentResultContext = null;
                clearOutputsTabState();
            }
        }
    });

    async function loadSpecificProcess(name) {
        // On Checklist Review page, React Flow doesn't exist - that's normal
        // Only load into React Flow if it's available (Review Process Design page)
        if (!window.reactFlowInstance) {
            // React Flow not available - this is normal on Checklist Review page
            // Just update the canvas header if it exists and return
            updateCanvasHeader();
            return;
        }
        
        // Wait for reactFlowInstance to be available (for Review Process Design page)
        let retries = 0;
        while (!window.reactFlowInstance && retries < 10) {
            await new Promise(resolve => setTimeout(resolve, 100));
            retries++;
        }
        if (!window.reactFlowInstance) {
            // React Flow still not available - this is normal on Checklist Review page
            updateCanvasHeader();
            return;
        }
        
        try {
            const res = await fetch(`/checklist_review/api/pipelines/${name}`);
            if (res.ok) {
                const data = await res.json();
                if (data && (data.nodes || data.edges)) {
                    window.reactFlowInstance.setFlow(data, true); // Skip tracking, we'll set it manually
                    // Update canvas header immediately
                    updateCanvasHeader();
                    // Store original data for change tracking after a delay to ensure flow is set
                    setTimeout(() => {
                        if (window.reactFlowInstance) {
                            const currentFlow = window.reactFlowInstance.getFlow(false); // Exclude positions
                            window.originalProcessData = JSON.stringify(currentFlow);
                            window.hasUnsavedChanges = false;
                            updateButtonStates();
                        }
                    }, 500);
                } else {
                    console.warn('Process data has no nodes or edges:', data);
                }
            }
        } catch (e) { console.error('Error loading process:', e); }
    }

    function updateCanvasHeader() {
        // Canvas header only exists on Review Process Design page, not Checklist Review
        const canvasProcessName = document.getElementById('canvasProcessName');
        if (!canvasProcessName) return;

        const selectedProcess = getSelectedProcess();
        if (selectedProcess && selectedProcess.name) {
            const processName = selectedProcess.name;
            canvasProcessName.textContent = processName || 'No process selected';
        } else {
            canvasProcessName.textContent = 'No process selected';
        }
    }

    function updateButtonStates() {
        const selectedProcess = getSelectedProcess();
        const currentProcess = selectedProcess ? selectedProcess.slug : null;
        const isDefault = true; // Pipelines are config-managed (config/pipelines/*.yaml)

        // Disable Update if default process or no changes (only if button exists)
        if (updateProcessBtn) {
            updateProcessBtn.disabled = isDefault || !window.hasUnsavedChanges || !currentProcess;
        }

        // Disable Rename/Delete if default process or no process selected (only if buttons exist)
        if (renameProcessBtn) {
            renameProcessBtn.disabled = isDefault || !currentProcess;
        }
        if (deleteProcessBtn) {
            deleteProcessBtn.disabled = isDefault || !currentProcess;
        }

        // Update canvas header (if it exists)
        updateCanvasHeader();
    }

    // Expose functions to global scope for React component
    window.updateButtonStates = updateButtonStates;
    window.checkForChanges = () => {
        if (!window.reactFlowInstance || !window.originalProcessData) {
            window.hasUnsavedChanges = false;
            updateButtonStates();
            return;
        }

        const currentData = window.reactFlowInstance.getFlow(false); // Exclude positions for comparison
        const currentDataStr = JSON.stringify(currentData);
        window.hasUnsavedChanges = currentDataStr !== window.originalProcessData;
        updateButtonStates();
    };

    // Review process state
    let currentTaskId = null;
    let statusPollInterval = null;
    let isReviewRunning = false;
    let lastLogIndex = 0; // Track last displayed log message index

    // Update button state
    function updateButtonState(running) {
        isReviewRunning = running;
        const btn = startProcessBtn;
        const btnText = document.getElementById('startProcessBtnText');
        const btnIcon = document.getElementById('startProcessIcon');
        const btnSpinner = document.getElementById('startProcessSpinner');

        if (running) {
            btn.classList.remove('btn-success');
            btn.classList.add('btn-danger');
            btn.style.background = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
            btn.style.boxShadow = '0 2px 8px rgba(239, 68, 68, 0.3)';
            btnText.textContent = 'Ongoing Review...';
            // Show spinner, hide icon
            if (btnIcon) btnIcon.classList.add('d-none');
            if (btnSpinner) btnSpinner.classList.remove('d-none');
            btn.disabled = false;
        } else {
            btn.classList.remove('btn-danger');
            btn.classList.add('btn-success');
            btn.style.background = 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)';
            btn.style.boxShadow = '0 2px 8px rgba(22, 163, 74, 0.3)';
            btnText.textContent = 'Start Review';
            // Hide spinner, show icon
            if (btnIcon) btnIcon.classList.remove('d-none');
            if (btnSpinner) btnSpinner.classList.add('d-none');
            btn.disabled = false;
        }
    }

    // Stop status polling
    function stopStatusPolling() {
        if (statusPollInterval) {
            clearInterval(statusPollInterval);
            statusPollInterval = null;
        }
    }

    // Start status polling
    function startStatusPolling(taskId) {
        if (!taskId) {
            return false;
        }

        currentTaskId = taskId;
        stopStatusPolling();
        lastLogIndex = 0;

        // Poll immediately first time
        pollStatus(taskId).catch(() => { });

        // Then poll every 2 seconds
        try {
            statusPollInterval = setInterval(() => {
                if (currentTaskId === taskId) {
                    pollStatus(taskId).catch(() => { });
                } else {
                    stopStatusPolling();
                }
            }, 2000);

            if (!statusPollInterval) {
                return false;
            }

            return true;
        } catch (err) {
            return false;
        }
    }

    async function pollStatus(taskId) {
        try {
            if (!taskId) {
                return;
            }
            const url = `/checklist_review/api/review-status/${taskId}`;

            let res;
            try {
                const controller = new AbortController();
                // Use a longer timeout so status polls don't fail while the review is busy (e.g. github_checker LLM calls)
                const timeoutId = setTimeout(() => controller.abort(), 60000);
                res = await fetch(url, {
                    signal: controller.signal,
                    cache: 'no-cache',
                    headers: {
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache'
                    }
                });
                clearTimeout(timeoutId);
            } catch (fetchError) {
                if (fetchError.name === 'AbortError') {
                    log('Warning: Status request timed out. The review may still be running.');
                }
                return;
            }

            if (!res.ok) {
                if (res.status === 404) {
                    log("Review process not found. It may have been stopped or completed.");
                    stopStatusPolling();
                    updateButtonState(false);
                    currentTaskId = null;
                }
                return;
            }

            let data;
            try {
                data = await res.json();
            } catch (parseError) {
                return;
            }

            if (!data) {
                return;
            }

            const status = data.status;

            // Display new log messages
            if (data.log_messages && Array.isArray(data.log_messages)) {
                const newMessages = data.log_messages.slice(lastLogIndex);
                newMessages.forEach(msg => {
                    const level = msg.level || 'info';
                    let message = msg.message || '';

                    // Format message based on level
                    let prefix = '';
                    let className = '';

                    if (message.startsWith('=')) {
                        // Separator line
                        prefix = '';
                        className = 'log-separator';
                    } else if (level === 'success') {
                        prefix = '✓ ';
                        className = 'log-success';
                    } else if (level === 'error' || level === 'warning') {
                        prefix = level === 'error' ? '✗ ' : '⚠ ';
                        className = `log-${level}`;
                    } else if (message.toLowerCase().includes('processing paper')) {
                        prefix = '📄 ';
                        className = 'log-paper-header';
                    } else if (message.toLowerCase().includes('loading paper')) {
                        prefix = '📥 ';
                    } else if (message.toLowerCase().includes('loading checklist')) {
                        prefix = '📋 ';
                    } else if (message.toLowerCase().includes('answering question') || message.toLowerCase().includes('reviewing question')) {
                        prefix = '❓ ';
                    } else if (message.toLowerCase().includes('question answered')) {
                        prefix = '✓ ';
                        className = 'log-success';
                    } else if (message.toLowerCase().includes('post processing')) {
                        prefix = '📝 ';
                    } else if (message.toLowerCase().includes('completed processing')) {
                        prefix = '✓ ';
                        className = 'log-success';
                    } else {
                        prefix = '> ';
                    }

                    addLogEntry(message, className, prefix);
                });

                lastLogIndex = data.log_messages.length;
                logContent.scrollTop = logContent.scrollHeight;
            }

            if (status === 'completed' || status === 'failed' || status === 'stopped') {
                // Only process completion once; multiple in-flight responses may all have status=completed
                if (currentTaskId !== null) {
                    stopStatusPolling();
                    updateButtonState(false);
                    currentTaskId = null;
                    // Do not reset lastLogIndex here; in-flight responses would then re-append all messages

                    if (status === 'completed') {
                        log(`\nAll reviews finished. Processed ${data.current}/${data.total} papers.`);
                        await loadPapersList();
                    } else if (status === 'stopped') {
                        log(`\nReview process stopped. Processed ${data.current}/${data.total} papers.`);
                    } else if (status === 'failed') {
                        log(`\nReview process failed: ${data.error || 'Unknown error'}`);
                    }
                }
            }
        } catch (e) {
            // Silently continue polling on error
        }
    }

    // Fallback: Start polling by collection name if task ID polling fails
    function startStatusPollingByCollection(collectionName) {
        if (!collectionName) {
            return;
        }

        stopStatusPolling();
        lastLogIndex = 0;

        setTimeout(() => {
            pollStatusByCollection(collectionName).catch(() => { });
        }, 100);

        statusPollInterval = setInterval(() => {
            pollStatusByCollection(collectionName).catch(() => { });
        }, 2000);
    }

    async function pollStatusByCollection(collectionName) {
        try {
            const res = await fetch(`/checklist_review/api/review-status?collection_name=${collectionName}`);

            if (!res.ok) {
                if (res.status === 404 || res.status === 400) {
                    const data = await res.json().catch(() => ({}));
                    if (data.status === 'not_running') {
                        stopStatusPolling();
                        updateButtonState(false);
                        currentTaskId = null;
                    }
                }
                return;
            }

            const data = await res.json();
            if (!data || data.status === 'not_running') {
                stopStatusPolling();
                updateButtonState(false);
                currentTaskId = null;
                return;
            }

            if (data.task_id && data.task_id !== currentTaskId) {
                currentTaskId = data.task_id;
                startStatusPolling(data.task_id);
                return;
            }

            const status = data.status;

            // Display new log messages (same logic as pollStatus)
            if (data.log_messages && Array.isArray(data.log_messages)) {
                const newMessages = data.log_messages.slice(lastLogIndex);
                newMessages.forEach(msg => {
                    const level = msg.level || 'info';
                    let message = msg.message || '';

                    let prefix = '';
                    let className = '';

                    if (message.startsWith('=')) {
                        prefix = '';
                        className = 'log-separator';
                    } else if (level === 'success') {
                        prefix = '✓ ';
                        className = 'log-success';
                    } else if (level === 'error' || level === 'warning') {
                        prefix = level === 'error' ? '✗ ' : '⚠ ';
                        className = `log-${level}`;
                    } else {
                        prefix = '> ';
                    }

                    addLogEntry(message, className, prefix);
                });

                lastLogIndex = data.log_messages.length;
                logContent.scrollTop = logContent.scrollHeight;
            }

            if (status === 'completed' || status === 'failed' || status === 'stopped') {
                if (currentTaskId !== null) {
                    stopStatusPolling();
                    updateButtonState(false);
                    currentTaskId = null;

                    if (status === 'completed') {
                        log(`\nAll reviews finished. Processed ${data.current}/${data.total} papers.`);
                        await loadPapersList();
                    } else if (status === 'stopped') {
                        log(`\nReview process stopped. Processed ${data.current}/${data.total} papers.`);
                    } else if (status === 'failed') {
                        log(`\nReview process failed: ${data.error || 'Unknown error'}`);
                    }
                }
            }
        } catch (e) {
            // Silently continue on error
        }
    }

    // Check for running review on page load
    async function checkRunningReview() {
        if (!currentCollection) return;

        try {
            const res = await fetch(`/checklist_review/api/review-status?collection_name=${currentCollection}`);
            if (res.ok) {
                const data = await res.json();
                if (data.status && data.status !== 'not_running') {
                    currentTaskId = data.task_id;
                    updateButtonState(true);
                    if (data.task_id) {
                        startStatusPolling(data.task_id);
                    } else {
                        startStatusPollingByCollection(currentCollection);
                    }
                    log(`Resuming review process... (${data.current}/${data.total})`);
                }
            }
        } catch (e) {
            console.error('Error checking running review:', e);
        }
    }

    // Show navigation warning modal
    function showNavigationWarningModal(targetUrl = null, isRefresh = false) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'delete-modal-overlay';
            overlay.style.animation = 'fadeIn 0.2s ease-out';
            overlay.style.zIndex = '10000';

            const actionText = isRefresh ? 'refresh this page' : 'navigate away';

            overlay.innerHTML = `
                    <div class="delete-modal" style="max-width: 550px;">
                        <div class="delete-modal-header" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-bottom: 2px solid #f59e0b;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="#f59e0b" viewBox="0 0 16 16" style="margin-right: 0.75rem;">
                                <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
                            </svg>
                            <h5 style="color: #92400e; margin: 0;">Review Process Running</h5>
                        </div>
                        <div class="delete-modal-body" style="padding: 1.5rem;">
                            <div style="display: flex; align-items: start; gap: 1rem; margin-bottom: 1rem;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="#f59e0b" viewBox="0 0 16 16" style="flex-shrink: 0; opacity: 0.8;">
                                    <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
                                </svg>
                                <div style="flex: 1;">
                                    <p style="font-size: 1rem; color: #0f172a; margin: 0 0 0.75rem 0; font-weight: 500;">
                                        A review process is currently running in the background.
                                    </p>
                                    <p style="font-size: 0.9rem; color: #64748b; margin: 0 0 1rem 0; line-height: 1.5;">
                                        If you ${actionText}, the review process will be stopped and any incomplete reviews will be lost.
                                    </p>
                                    <div style="background: #fef3c7; border-left: 3px solid #f59e0b; padding: 0.75rem; border-radius: 4px; margin-top: 1rem;">
                                        <p style="font-size: 0.875rem; color: #92400e; margin: 0; font-weight: 500;">
                                            Are you sure you want to ${actionText}?
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="delete-modal-footer" style="border-top: 1px solid #e2e8f0; padding: 1rem 1.5rem;">
                            <button class="delete-modal-btn delete-modal-btn-cancel" id="navWarningCancel" style="flex: 1;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 0.5rem;">
                                    <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
                                </svg>
                                Cancel
                            </button>
                            <button class="delete-modal-btn" id="navWarningConfirm" style="flex: 1; background: #ef4444; color: white; border-color: #ef4444;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 0.5rem;">
                                    <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
                                </svg>
                                ${isRefresh ? 'Refresh Anyway' : 'Leave Page'}
                            </button>
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
                    if (document.body.contains(overlay)) {
                        document.body.removeChild(overlay);
                    }
                    resolve(confirmed);
                }, 200);
            };

            const handleConfirm = async () => {
                closeModal(true);

                // Stop the review process
                await stopReviewProcess();

                // Small delay to ensure stop request is sent
                await new Promise(resolve => setTimeout(resolve, 100));

                if (targetUrl) {
                    window.location.href = targetUrl;
                } else if (isRefresh) {
                    window.location.reload();
                }
            };

            overlay.querySelector('#navWarningCancel').addEventListener('click', () => closeModal(false));
            overlay.querySelector('#navWarningConfirm').addEventListener('click', handleConfirm);

            // Close on overlay click (but don't allow closing by clicking outside)
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    // Don't close on overlay click - require explicit action
                }
            });

            // Close on Escape key
            const escapeHandler = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', escapeHandler);
                    closeModal(false);
                }
            };
            document.addEventListener('keydown', escapeHandler);
        });
    }

    // Navigation warning
    function setupNavigationWarning() {
        let isModalOpen = false;

        // Intercept navigation within the app
        document.addEventListener('click', async (e) => {
            if (!isReviewRunning || isModalOpen) return;

            const link = e.target.closest('a');
            if (link && link.href && !link.href.startsWith('#')) {
                const href = link.getAttribute('href');
                if (href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                    e.preventDefault();
                    e.stopPropagation();
                    isModalOpen = true;
                    const confirmed = await showNavigationWarningModal(href, false);
                    isModalOpen = false;
                    // If confirmed, navigation will happen in the modal handler
                }
            }
        });

        // Intercept keyboard shortcuts for refresh (before beforeunload)
        window.addEventListener('keydown', async (e) => {
            if (!isReviewRunning || isModalOpen) return;

            // Check for refresh shortcuts: F5, Ctrl+R, Ctrl+Shift+R
            const isRefresh = e.key === 'F5' ||
                (e.ctrlKey && e.key === 'r') ||
                (e.ctrlKey && e.shiftKey && e.key === 'R');

            if (isRefresh) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                isModalOpen = true;
                const confirmed = await showNavigationWarningModal(null, true);
                isModalOpen = false;
                // If confirmed, refresh will happen in the modal handler
            }
        }, true); // Use capture phase to intercept early

        // Handle beforeunload as fallback (for browser refresh button, address bar navigation, etc.)
        // Note: We can't show async modals in beforeunload, so we use the browser's native dialog
        // But we intercept keyboard shortcuts and link clicks above to show our custom modal
        window.addEventListener('beforeunload', (e) => {
            if (isReviewRunning && !isModalOpen) {
                // Stop the process when user leaves (use sendBeacon for reliable delivery)
                if (currentTaskId) {
                    const stopUrl = `/checklist_review/api/stop-review/${currentTaskId}`;
                    navigator.sendBeacon(stopUrl);
                } else if (currentCollection) {
                    const stopUrl = `/checklist_review/api/stop-review?collection_name=${currentCollection}`;
                    navigator.sendBeacon(stopUrl);
                }

                // Show browser's native confirmation (fallback for cases we can't intercept)
                e.preventDefault();
                e.returnValue = ''; // Modern browsers show a generic message
                return e.returnValue;
            }
        });
    }

    // Stop review process
    async function stopReviewProcess() {
        if (!currentTaskId) {
            try {
                const res = await fetch(`/checklist_review/api/review-status?collection_name=${currentCollection}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.task_id) {
                        currentTaskId = data.task_id;
                    }
                }
            } catch (e) {
                // Silently continue
            }
        }

        if (currentTaskId) {
            try {
                const res = await fetch(`/checklist_review/api/stop-review/${currentTaskId}`, {
                    method: 'POST'
                });
                const responseData = await res.json();

                if (res.ok) {
                    log('Review process stopped by user.');
                    stopStatusPolling();
                    updateButtonState(false);
                    currentTaskId = null;
                    return true;
                } else {
                    log(`✗ ${responseData.error || 'An error occurred while stopping the review. Please try again.'}`);
                }
            } catch (e) {
                log(`✗ An error occurred while stopping the review. Please try again.`);
            }
        } else {
            try {
                const res = await fetch(`/checklist_review/api/stop-review?collection_name=${currentCollection}`, {
                    method: 'POST'
                });
                const responseData = await res.json();

                if (res.ok) {
                    log('Review process stopped by user.');
                    stopStatusPolling();
                    updateButtonState(false);
                    currentTaskId = null;
                    return true;
                } else {
                    log(`✗ ${responseData.error || 'An error occurred while stopping the review. Please try again.'}`);
                }
            } catch (e) {
                log(`✗ An error occurred while stopping the review. Please try again.`);
            }
        }
        return false;
    }

    // Run/Stop Review
    startProcessBtn.addEventListener('click', async () => {
        if (isReviewRunning) {
            await stopReviewProcess();
            return;
        }

        // Clear execution log first
        clearLog();
        lastLogIndex = 0;

        if (!currentCollection) {
            log("✗ Please select a collection first.");
            return;
        }
        const selectedProcess = getSelectedProcess();
        if (!selectedProcess || !selectedProcess.slug) {
            log("✗ Please select a process first.");
            return;
        }
        const processName = selectedProcess.slug;

        const selectedChecklist = getSelectedChecklist();
        if (!selectedChecklist || !selectedChecklist.name) {
            log("✗ Please select a checklist before starting the review.");
            return;
        }
        const checklistName = selectedChecklist.name;

        log("Starting Review...");

        // Get process data - either from React Flow (if available) or from API
        let processData = null;
        if (window.reactFlowInstance) {
            // Review Process Design page - get from React Flow
            processData = window.reactFlowInstance.getFlow(false);
        } else {
            // Checklist Review page - fetch from API
            try {
                const processRes = await fetch(`/checklist_review/api/pipelines/${processName}`);
                if (processRes.ok) {
                    processData = await processRes.json();
                } else {
                    log("✗ Failed to load process data. Please try again.");
                    return;
                }
            } catch (e) {
                log(`✗ Error loading process data: ${e.message}`);
                return;
            }
        }
        
        if (!processData) {
            log("✗ Failed to get process data. Please try again.");
            return;
        }

        try {
            startProcessBtn.disabled = true;

            const res = await fetch('/checklist_review/api/start-review', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    collection_name: currentCollection,
                    process_data: processData,
                    pipeline_id: processName,
                    criteria_set_name: checklistName
                })
            });

            if (!res.ok) {
                let errorMessage = 'An error occurred while starting the review. Please try again.';
                try {
                    const errorData = await res.json();
                    if (errorData.error) {
                        errorMessage = errorData.error;
                    }
                } catch (e) {
                    // If JSON parsing fails, try to get text
                    const errorText = await res.text();
                    try {
                        const errorData = JSON.parse(errorText);
                        if (errorData.error) {
                            errorMessage = errorData.error;
                        }
                    } catch (e2) {
                        // If all parsing fails, use default message
                    }
                }
                log(`✗ ${errorMessage}`);
                startProcessBtn.disabled = false;
                updateButtonState(false);
                return;
            }

            let data;
            try {
                data = await res.json();
            } catch (parseError) {
                log(`✗ An error occurred while starting the review. Please try again.`);
                startProcessBtn.disabled = false;
                updateButtonState(false);
                return;
            }

            if (data.error) {
                log(`✗ ${data.error}`);
                startProcessBtn.disabled = false;
                updateButtonState(false);
                return;
            }

            if (data.task_id) {
                currentTaskId = data.task_id;
                updateButtonState(true);
                startStatusPolling(data.task_id);
            } else {
                log("✗ Unable to start the review process. Please try again.");
                startProcessBtn.disabled = false;
                updateButtonState(false);
            }
        } catch (e) {
            log(`✗ An error occurred while starting the review. Please try again.`);
            startProcessBtn.disabled = false;
            updateButtonState(false);
        }
    });

    if (deleteAllResponsesBtn) {
        deleteAllResponsesBtn.addEventListener('click', async () => {
            if (isReviewRunning) {
                log('✗ Stop the running review before deleting responses.');
                return;
            }

            if (!currentCollection) {
                log('✗ Please select a collection first.');
                return;
            }

            const selectedProcess = getSelectedProcess();
            if (!selectedProcess || !selectedProcess.slug) {
                log('✗ Please select a process first.');
                return;
            }

            const selectedChecklist = getSelectedChecklist();
            if (!selectedChecklist || !selectedChecklist.name) {
                log('✗ Please select a checklist first.');
                return;
            }

            try {
                const query = new URLSearchParams({
                    collection_name: currentCollection,
                    pipeline_id: selectedProcess.slug,
                    criteria_set_name: selectedChecklist.name
                });

                const listRes = await fetch(`/checklist_review/api/results?${query.toString()}`);
                const existingResults = listRes.ok ? await listRes.json() : [];
                const resultCount = Array.isArray(existingResults) ? existingResults.length : 0;
                if (resultCount === 0) {
                    log('No responses found to delete for the current scope.');
                    return;
                }

                const confirmed = await showDeleteAllResponsesModal(
                    resultCount,
                    currentCollection,
                    selectedProcess.name,
                    selectedChecklist.name
                );
                if (!confirmed) return;

                deleteAllResponsesBtn.disabled = true;
                const deleteRes = await fetch(`/checklist_review/api/results?${query.toString()}`, { method: 'DELETE' });
                const deleteData = await deleteRes.json();
                if (!deleteRes.ok) {
                    log(`✗ ${deleteData.error || 'Failed to delete responses.'}`);
                    deleteAllResponsesBtn.disabled = false;
                    return;
                }

                const deleted = Number(deleteData.deleted_count || 0);
                const total = Number(deleteData.total_count || 0);
                log(`Deleted ${deleted}/${total} response(s).`);

                currentResultContext = null;
                outputsContainer.innerHTML = '<div class="text-muted text-center p-4">Select a paper to view review outputs.</div>';
                outputsTitle.textContent = 'Review Outputs';
                deleteResultBtn.style.display = 'none';
                clearOutputsTabState();
                await loadPapersList();
            } catch (error) {
                log('✗ Failed to delete responses. Please try again.');
            } finally {
                deleteAllResponsesBtn.disabled = false;
            }
        });
    }

    // Setup navigation warning
    setupNavigationWarning();

    // Cleanup on page unload (only if not stopping for navigation)
    window.addEventListener('beforeunload', () => {
        if (!isReviewRunning) {
            stopStatusPolling();
        }
    });

    // Check for running review on page load
    setTimeout(() => {
        checkRunningReview();
    }, 1000);

    // Load Papers List
    async function loadPapersList() {
        papersList.innerHTML = '<div class="p-2 text-muted">Loading...</div>';
        try {
            const papersRes = await fetch(`/checklist_review/api/artifacts?collection_name=${currentCollection}`);
            const papers = await papersRes.json();

            const selectedProcess = getSelectedProcess();
            const processName = selectedProcess ? selectedProcess.slug : null;
            const selectedChecklist = getSelectedChecklist();
            const checklistName = selectedChecklist ? selectedChecklist.name : null;
            let resultMap = new Map();
            if (processName && checklistName) {
                const resultsRes = await fetch(`/checklist_review/api/results?collection_name=${currentCollection}&pipeline_id=${processName}&criteria_set_name=${encodeURIComponent(checklistName)}`);
                const results = await resultsRes.json();
                resultMap = new Map(results.map(r => [r.filename, r]));
            }

            papersList.innerHTML = '';
            if (papers.length === 0) {
                papersList.innerHTML = '<div class="p-2 text-muted">No papers in collection.</div>';
                return;
            }

            papers.forEach(p => {
                const hasResult = resultMap.has(p.filename);
                const item = document.createElement('div');
                item.className = 'list-group-item d-flex justify-content-between align-items-center small px-2 py-1';

                const leftContent = document.createElement('div');
                leftContent.className = 'd-flex align-items-center gap-2';
                leftContent.style.flex = '1';
                leftContent.style.minWidth = '0';

                // Outputs button (in front of paper name)
                const outBtn = document.createElement('button');
                outBtn.className = 'btn btn-sm btn-outline-info me-2';
                outBtn.style.padding = '0.125rem 0.375rem';
                outBtn.style.fontSize = '0.7rem';
                outBtn.style.flexShrink = '0';
                outBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16"><path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1h12zM2 0a2 2 0 0 0-2 2v12.793a.5.5 0 0 0 .854.353l2.853-2.853A1 1 0 0 1 4.414 12H14a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z"/><path d="M3 3.5a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zM3 6a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9A.5.5 0 0 1 3 6zm0 2.5a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5z"/></svg>';
                outBtn.title = 'View Review Outputs';
                outBtn.onclick = (e) => {
                    e.stopPropagation();
                    loadResult(p);
                    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('reviewOutputModal'));
                    modal.show();
                };
                leftContent.appendChild(outBtn);

                const span = document.createElement('span');
                span.textContent = p.title || p.filename;
                span.style.overflow = 'hidden';
                span.style.textOverflow = 'ellipsis';
                span.style.whiteSpace = 'nowrap';
                span.style.flex = '1';
                span.style.cursor = 'pointer';
                span.onclick = () => {
                    loadResult(p);
                    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('reviewOutputModal'));
                    modal.show();
                };
                leftContent.appendChild(span);

                const actionsDiv = document.createElement('div');
                actionsDiv.className = 'd-flex gap-1';
                actionsDiv.style.flexShrink = '0';

                // Delete button
                // const deleteBtn = document.createElement('button');
                // deleteBtn.className = 'btn btn-sm btn-outline-danger';
                // deleteBtn.style.padding = '0.125rem 0.375rem';
                // deleteBtn.style.fontSize = '0.7rem';
                // deleteBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg>';
                // deleteBtn.title = 'Delete Paper';
                // deleteBtn.onclick = (e) => {
                //     e.stopPropagation();
                //     deletePaper(p);
                // };
                // actionsDiv.appendChild(deleteBtn);

                if (hasResult) {
                    const badge = document.createElement('span');
                    badge.className = 'badge bg-success rounded-pill d-flex align-items-center justify-content-center';
                    badge.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" fill="currentColor" viewBox="0 0 16 16"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425z"/></svg>';
                    badge.style.width = '18px';
                    badge.style.height = '18px';
                    badge.style.padding = '0';
                    badge.title = 'Reviewed';
                    badge.style.cursor = 'pointer';
                    badge.onclick = (e) => {
                        e.stopPropagation();
                        loadResult(p);
                        const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('reviewOutputModal'));
                        modal.show();
                    };
                    actionsDiv.appendChild(badge);
                } else {
                    const badge = document.createElement('span');
                    badge.className = 'badge bg-light text-secondary border rounded-pill d-flex align-items-center justify-content-center';
                    badge.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" fill="currentColor" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
                    badge.style.width = '18px';
                    badge.style.height = '18px';
                    badge.style.padding = '0';
                    badge.style.opacity = '0.5';
                    badge.title = 'Not reviewed yet';
                    actionsDiv.appendChild(badge);
                }

                leftContent.appendChild(actionsDiv);
                item.appendChild(leftContent);
                papersList.appendChild(item);
            });
        } catch (e) { console.error(e); }
    }

    // Delete paper
    async function deletePaper(paper) {
        const modalEl = document.getElementById('deletePaperModal');
        const modal = modalEl ? new bootstrap.Modal(modalEl) : null;
        const paperNameEl = document.getElementById('deletePaperName');
        const confirmBtn = document.getElementById('btnConfirmDeletePaper');
        
        if (!modal || !paperNameEl || !confirmBtn) return;
        
        const paperName = paper.title || paper.filename || paper.paper_id;
        paperNameEl.textContent = paperName;
        
        // Remove existing event listeners by cloning the button
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        
        newConfirmBtn.addEventListener('click', async () => {
            newConfirmBtn.disabled = true;
            newConfirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Deleting...';
            
            try {
                const paperId = paper.paper_id || paper.filename || paper.title;
                const res = await fetch(`/checklist_review/api/artifacts/${encodeURIComponent(paperId)}?collection_name=${encodeURIComponent(currentCollection)}`, {
                    method: 'DELETE'
                });
                
                if (res.ok) {
                    modal.hide();
                    await loadPapersList();
                    log(`Paper "${paperName}" deleted successfully.`);
                } else {
                    const data = await res.json().catch(() => ({}));
                    alert(data.error || 'Failed to delete paper. Please try again.');
                    newConfirmBtn.disabled = false;
                    newConfirmBtn.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="me-1">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                        Delete Paper
                    `;
                }
            } catch (e) {
                console.error('Error deleting paper:', e);
                alert('An error occurred while deleting the paper. Please try again.');
                newConfirmBtn.disabled = false;
                newConfirmBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="me-1">
                        <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                        <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                    </svg>
                    Delete Paper
                `;
            }
        });
        
        modal.show();
    }

    // View paper details in modal
    async function viewPaperDetails(paper) {
        const modalEl = document.getElementById('paperDetailsModal');
        const modal = modalEl ? new bootstrap.Modal(modalEl) : null;
        const detailContainer = document.getElementById('paperDetailsContent');
        
        if (!modal || !detailContainer) return;
        
        // Show loading state
        detailContainer.innerHTML = `
            <div class="text-center text-muted py-4">
                <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                Loading paper details...
            </div>
        `;
        
        modal.show();
        
        try {
            // Try to load metadata from source_extracted JSON
            const paperId = paper.paper_id || paper.filename || paper.title;
            const collectionName = currentCollection;
            
            // Fetch paper metadata
            const res = await fetch(`/checklist_review/api/paper-details?collection_name=${encodeURIComponent(collectionName)}&paper_id=${encodeURIComponent(paperId)}`);
            
            if (res.ok) {
                const data = await res.json();
                const authors = data.authors || [];
                const authorsText = authors.length > 0 ? authors.join(', ') : 'No authors information available.';
                
                detailContainer.innerHTML = `
                    <h5 class="fw-bold mb-3" style="color: #0f172a; line-height: 1.4;">${data.title || paper.title || 'Untitled'}</h5>
                    <div class="mb-3">
                        <span class="badge bg-light text-dark border me-2" style="font-size: 0.75rem;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16" class="me-1">
                                <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/>
                            </svg>
                            ${paperId}
                        </span>
                        <span class="text-muted small d-block mt-2">${data.filename || paper.filename || paperId}</span>
                    </div>
                    <hr style="margin: 1.5rem 0; border-color: #e2e8f0;">
                    <h6 class="small fw-semibold mb-2" style="color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Authors</h6>
                    <p class="small" style="color: #334155; line-height: 1.7;">${authorsText}</p>
                    <hr style="margin: 1.5rem 0; border-color: #e2e8f0;">
                    <h6 class="small fw-semibold mb-2" style="color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Abstract</h6>
                    <p class="small" style="color: #334155; line-height: 1.7; white-space: pre-wrap;">${data.abstract || data.summary || 'No abstract available.'}</p>
                `;
            } else {
                // Fallback to basic info if metadata not available
                detailContainer.innerHTML = `
                    <h5 class="fw-bold mb-3" style="color: #0f172a; line-height: 1.4;">${paper.title || paper.filename || 'Untitled'}</h5>
                    <div class="mb-3">
                        <span class="badge bg-light text-dark border me-2" style="font-size: 0.75rem;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16" class="me-1">
                                <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/>
                            </svg>
                            ${paper.paper_id || paper.filename}
                        </span>
                        <span class="text-muted small d-block mt-2">${paper.filename}</span>
                    </div>
                    <div class="alert alert-info" style="font-size: 0.875rem;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="me-2">
                            <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>
                            <path d="M7.002 11a1 1 0 1 1 2 0 1 1 0 0 1-2 0M7.1 4.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0z"/>
                        </svg>
                        Paper metadata is being processed. Please wait a moment and try again.
                    </div>
                `;
            }
        } catch (e) {
            console.error('Error loading paper details:', e);
            detailContainer.innerHTML = `
                <div class="alert alert-danger">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="me-2">
                        <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>
                        <path d="M5.354 4.646a.5.5 0 1 0-.708.708L7.293 8l-2.647 2.646a.5.5 0 0 0 .708.708L8 8.707l2.646 2.647a.5.5 0 0 0 .708-.708L8.707 8l2.647-2.646a.5.5 0 0 0-.708-.708L8 7.293z"/>
                    </svg>
                    Error loading paper details: ${e.message}
                </div>
            `;
        }
    }

    async function loadResult(paper) {
        const paperId = typeof paper === 'string' ? paper : (paper.filename || paper.paper_id || paper.title);
        const selectedProcess = getSelectedProcess();
        if (!selectedProcess || !selectedProcess.slug) {
            outputsContainer.innerHTML = '<div class="text-muted text-center p-4">Please select a process first.</div>';
            return;
        }
        const processName = selectedProcess.slug;
        
        const selectedChecklist = getSelectedChecklist();
        if (!selectedChecklist || !selectedChecklist.name) {
            outputsContainer.innerHTML = '<div class="text-muted text-center p-4">Please select a checklist first.</div>';
            return;
        }
        const checklistName = selectedChecklist.name;

        // Extract title from paperId (filename)
        const paperPath = Path(paperId);
        let paperTitle = paperPath.stem;
        
        // Convert to title case: handle hyphens, underscores, and spaces
        // First, replace hyphens and underscores with spaces, then capitalize
        paperTitle = paperTitle
            .replace(/[-_]/g, ' ')  // Replace hyphens and underscores with spaces
            .split(/\s+/)            // Split on whitespace
            .filter(word => word.length > 0)  // Remove empty strings
            .map(word => {
                // Capitalize first letter, lowercase the rest
                return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
            })
            .join(' ');
        
        outputsTitle.textContent = `Review Outputs: ${paperTitle}`;
        outputsContainer.innerHTML = '<div class="text-muted text-center p-4">Loading...</div>';
        
        // Reset tabs to show Responses by default
        const responsesTab = document.getElementById('responses-tab');
        if (responsesTab) {
            const tab = new bootstrap.Tab(responsesTab);
            tab.show();
        }
        
        // Reset and show loading for abstract
        const abstractContainer = document.getElementById('abstractContainer');
        if (abstractContainer) {
            abstractContainer.innerHTML = `
                <div class="abstract-panel abstract-panel-loading">
                    <div class="abstract-panel-header">
                        <div class="abstract-panel-title-wrap">
                            <span class="abstract-panel-title-placeholder"></span>
                            <span class="abstract-panel-meta-placeholder"></span>
                        </div>
                    </div>
                    <div class="abstract-panel-body">
                        <div class="abstract-panel-line abstract-panel-line-lg"></div>
                        <div class="abstract-panel-line"></div>
                        <div class="abstract-panel-line"></div>
                        <div class="abstract-panel-line abstract-panel-line-md"></div>
                        <div class="abstract-panel-line"></div>
                    </div>
                </div>
            `;
        }
        
        deleteResultBtn.style.display = 'none';
        currentResultContext = null;
        clearOutputsTabState();

        // Load abstract
        if (abstractContainer) {
            try {
                const res = await fetch(`/checklist_review/api/paper-details?collection_name=${encodeURIComponent(currentCollection)}&paper_id=${encodeURIComponent(paperId)}`);
                if (res.ok) {
                    const data = await res.json();
                    const abstractText = data.abstract || data.summary || (typeof paper === 'object' ? paper.abstract : null) || 'No abstract available.';
                    const abstractWords = String(abstractText).trim() ? String(abstractText).trim().split(/\s+/).length : 0;
                    const abstractChars = String(abstractText).length;
                    const abstractTitle = data.title || (typeof paper === 'object' ? paper.title : paperTitle);
                    abstractContainer.innerHTML = `
                        <div class="abstract-panel">
                            <div class="abstract-panel-header">
                                <div class="abstract-panel-title-wrap">
                                    <h6 class="abstract-panel-title">${escapeHtml(abstractTitle || 'Paper Abstract')}</h6>
                                    <div class="abstract-panel-meta">
                                        <span class="abstract-meta-chip">${abstractWords.toLocaleString()} words</span>
                                        <span class="abstract-meta-chip">${abstractChars.toLocaleString()} chars</span>
                                    </div>
                                </div>
                            </div>
                            <div class="abstract-panel-body">
                                <p class="abstract-panel-text">${escapeHtml(abstractText)}</p>
                            </div>
                        </div>
                    `;
                } else {
                    abstractContainer.innerHTML = `
                        <div class="abstract-panel abstract-panel-empty">
                            <div class="abstract-panel-header">
                                <div class="abstract-panel-title-wrap">
                                    <h6 class="abstract-panel-title">${escapeHtml(typeof paper === 'object' ? (paper.title || paperTitle) : paperTitle)}</h6>
                                </div>
                            </div>
                            <div class="abstract-panel-empty-message">Abstract is not available for this paper yet.</div>
                        </div>
                    `;
                }
            } catch (e) {
                abstractContainer.innerHTML = `
                    <div class="abstract-panel abstract-panel-error">
                        <div class="abstract-panel-empty-message">Could not load abstract. Please try again.</div>
                    </div>
                `;
            }
        }

        try {
            const res = await fetch(`/checklist_review/api/results?collection_name=${currentCollection}&paper_id=${encodeURIComponent(paperId)}&pipeline_id=${encodeURIComponent(processName)}&criteria_set_name=${encodeURIComponent(checklistName)}`);

            if (!res.ok) {
                // Handle 404 or other errors gracefully
                if (res.status === 404) {
                    outputsContainer.innerHTML = `
                            <div class="text-center p-5" style="color: #64748b;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" fill="currentColor" viewBox="0 0 16 16" style="opacity: 0.5; margin-bottom: 1rem;">
                                    <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/>
                                </svg>
                                <p class="mb-0" style="font-size: 0.9rem;">This paper has not been reviewed yet.</p>
                                <p class="mt-2 mb-0" style="font-size: 0.85rem; color: #94a3b8;">Select a checklist and process, then click "Start Review" to generate results.</p>
                            </div>
                        `;
                    deleteResultBtn.style.display = 'none';
                    return;
                }
                outputsContainer.innerHTML = '<div class="text-danger text-center p-4">Error loading result.</div>';
                deleteResultBtn.style.display = 'none';
                return;
            }

            const data = await res.json();

            // Check if result indicates not found (status: "not_found")
            if (data && data.status === "not_found") {
                outputsContainer.innerHTML = `
                        <div class="text-center p-5" style="color: #64748b;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" fill="currentColor" viewBox="0 0 16 16" style="opacity: 0.5; margin-bottom: 1rem;">
                                <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/>
                            </svg>
                            <p class="mb-0" style="font-size: 0.9rem;">This paper has not been reviewed yet.</p>
                            <p class="mt-2 mb-0" style="font-size: 0.85rem; color: #94a3b8;">Select a checklist and process, then click "Start Review" to generate results.</p>
                        </div>
                    `;
                deleteResultBtn.style.display = 'none';
                return;
            }

            currentResultContext = {
                collection_name: currentCollection,
                pipeline_id: processName,
                criteria_set_name: checklistName,
                paper_id: paperId
            };

            // Format as human-readable Question: Answer
            if (Array.isArray(data)) {
                outputsContainer.innerHTML = '';
                if (data.length === 0) {
                    outputsContainer.innerHTML = '<div class="text-muted text-center p-4">No answers found.</div>';
                    return;
                }

                data.forEach(item => {
                    const qaItem = document.createElement('div');
                    qaItem.className = 'question-answer-item';

                    const questionDiv = document.createElement('div');
                    questionDiv.className = 'question';
                    questionDiv.textContent = item.question_text || item.question || 'Question not available';
                    qaItem.appendChild(questionDiv);

                    const answerDiv = document.createElement('div');
                    const answer = item.answer;
                    const answerClass = answer === true || answer === 'true' || answer === 'True' ? 'true' :
                        (answer === false || answer === 'false' || answer === 'False' ? 'false' : 'na');
                    answerDiv.className = `answer ${answerClass}`;

                    // Create answer header with badge
                    const answerHeader = document.createElement('div');
                    answerHeader.className = 'answer-header';
                    
                    // Format answer badge
                    let answerText = '';
                    let badgeIcon = '';
                    if (answer === true || answer === 'true' || answer === 'True') {
                        answerText = 'Yes';
                        badgeIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 0.25rem;"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425z"/></svg>';
                    } else if (answer === false || answer === 'false' || answer === 'False') {
                        answerText = 'No';
                        badgeIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 0.25rem;"><path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8z"/></svg>';
                    } else {
                        answerText = String(answer || 'N/A');
                        badgeIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 0.25rem;"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="M5.255 5.786a.237.237 0 0 0 .241.247h.825c.138 0 .248-.113.266-.25.09-.656.54-1.134 1.342-1.134.686 0 1.314.343 1.314 1.168 0 .635-.374.927-.965 1.371-.673.489-1.206 1.06-1.168 1.987l.003.217a.25.25 0 0 0 .25.246h.811a.25.25 0 0 0 .25-.25v-.105c0-.718.273-.927 1.01-1.486.609-.463 1.244-.977 1.244-2.056 0-1.511-1.276-2.241-2.673-2.241-1.326 0-2.896.787-2.997 2.093a.237.237 0 0 0 .241.247m6.1 0a.5.5 0 0 1 .5.5v3a.5.5 0 0 1-1 0v-3a.5.5 0 0 1 .5-.5"/></svg>';
                    }
                    
                    const answerBadge = document.createElement('span');
                    answerBadge.className = 'answer-badge';
                    answerBadge.innerHTML = badgeIcon + answerText;
                    answerHeader.appendChild(answerBadge);

                    // Add supporting texts if available
                    const supportingTexts = item.supporting_texts || [];
                    const filteredTexts = supportingTexts.filter(st => st.text_crop);
                    const hasSupportingTexts = filteredTexts.length > 0;

                    // Add expand/collapse button if there are supporting texts
                    if (hasSupportingTexts) {
                        const toggleBtn = document.createElement('button');
                        toggleBtn.className = 'answer-toggle-btn';
                        toggleBtn.type = 'button';
                        toggleBtn.setAttribute('aria-label', 'Toggle supporting texts');
                        toggleBtn.innerHTML = `
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" class="toggle-icon">
                                <path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
                            </svg>
                            <span class="toggle-text">Show details</span>
                        `;
                        
                        const supportingTextsContainer = document.createElement('div');
                        supportingTextsContainer.className = 'supporting-texts-container collapsed';
                        
                        filteredTexts.forEach((st, index) => {
                            const textItem = document.createElement('div');
                            textItem.className = 'supporting-text-item';
                            
                            // Page badge
                            if (st.page_number >= 0) {
                                const pageBadge = document.createElement('span');
                                pageBadge.className = 'page-badge';
                                pageBadge.textContent = `Page ${st.page_number}`;
                                textItem.appendChild(pageBadge);
                            }
                            
                            // Text content
                            const textContent = document.createElement('div');
                            textContent.className = 'supporting-text-content';
                            const truncatedText = st.text_crop.length > 200 
                                ? st.text_crop.substring(0, 200) + '...' 
                                : st.text_crop;
                            textContent.textContent = truncatedText;
                            textItem.appendChild(textContent);
                            
                            // Explanation if available
                            if (st.short_explanation) {
                                const explanation = document.createElement('div');
                                explanation.className = 'supporting-text-explanation';
                                explanation.textContent = st.short_explanation;
                                textItem.appendChild(explanation);
                            }
                            
                            supportingTextsContainer.appendChild(textItem);
                        });
                        
                        // Toggle functionality
                        toggleBtn.addEventListener('click', () => {
                            const isCollapsed = supportingTextsContainer.classList.contains('collapsed');
                            const toggleIcon = toggleBtn.querySelector('.toggle-icon');
                            const toggleText = toggleBtn.querySelector('.toggle-text');
                            
                            if (isCollapsed) {
                                supportingTextsContainer.classList.remove('collapsed');
                                toggleIcon.style.transform = 'rotate(180deg)';
                                toggleText.textContent = 'Hide details';
                            } else {
                                supportingTextsContainer.classList.add('collapsed');
                                toggleIcon.style.transform = 'rotate(0deg)';
                                toggleText.textContent = 'Show details';
                            }
                        });
                        
                        answerHeader.appendChild(toggleBtn);
                        answerDiv.appendChild(answerHeader);
                        answerDiv.appendChild(supportingTextsContainer);
                    } else {
                        answerDiv.appendChild(answerHeader);
                    }

                    qaItem.appendChild(answerDiv);
                    outputsContainer.appendChild(qaItem);
                });
            } else {
                outputsContainer.innerHTML = '<div class="text-muted text-center p-4">Unexpected data format.</div>';
            }

            deleteResultBtn.style.display = 'block';
            loadOutputsTab();
            deleteResultBtn.onclick = async () => {
                const confirmed = await showDeleteConfirmModal('Delete Result', paperId, 'result');
                if (!confirmed) return;
                try {
                    const selectedChecklist = getSelectedChecklist();
                    const checklistName = selectedChecklist ? selectedChecklist.name : null;
                    if (!checklistName) {
                        alert('Please select a checklist first.');
                        return;
                    }
                    await fetch(`/checklist_review/api/results/${paperId}?collection_name=${currentCollection}&pipeline_id=${processName}&criteria_set_name=${encodeURIComponent(checklistName)}`, { method: 'DELETE' });
                    outputsContainer.innerHTML = '<div class="text-muted text-center p-4">Result deleted.</div>';
                    deleteResultBtn.style.display = 'none';
                    currentResultContext = null;
                    clearOutputsTabState();
                    loadPapersList();
                } catch (e) {
                    log(`Error deleting result: ${e.message}`);
                }
            };
        } catch (e) {
            outputsContainer.innerHTML = '<div class="text-danger text-center p-4">Error loading result.</div>';
            console.error(e);
        }
    }

    // --- Outputs Tab ---
    outputsModalSelect = document.getElementById('outputsModalSelect');
    outputsModalView = document.getElementById('outputsModalView');
    outputsModalViewTitle = document.getElementById('outputsModalViewTitle');
    outputsModalViewContent = document.getElementById('outputsModalViewContent');
    outputsModalExportBtn = document.getElementById('outputsModalExportBtn');
    outputsModalEmpty = document.getElementById('outputsModalEmpty');
    outputsTokenUsageWrap = document.getElementById('outputsTokenUsageWrap');
    outputsTokenUsageContent = document.getElementById('outputsTokenUsageContent');
    collectionTokenUsageContent = document.getElementById('collectionTokenUsageContent');
    collectionTokenUsageScopeLabel = document.getElementById('collectionTokenUsageScopeLabel');

    const collectionTokenUsageModalEl = document.getElementById('collectionTokenUsageModal');
    const refreshCollectionTokenUsageBtn = document.getElementById('refreshCollectionTokenUsageBtn');

    function renderTokenUsageInto(targetElement, data, emptyMessage = 'No token usage data.') {
        if (!targetElement) return;
        const totalIn = data.total_input_tokens ?? 0;
        const totalOut = data.total_output_tokens ?? 0;
        const total = data.total_tokens ?? 0;
        const byModel = data.by_model ?? {};
        const modelIds = Object.keys(byModel);
        if (total === 0 && modelIds.length === 0) {
            targetElement.innerHTML = `<span class="outputs-token-usage-placeholder">${escapeHtml(emptyMessage)}</span>`;
            return;
        }

        const fmt = (n) => Number(n || 0).toLocaleString();
        const pct = (n, d) => (d > 0 ? ((n / d) * 100) : 0);
        const palette = ['#2563eb', '#0ea5e9', '#14b8a6', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#f43f5e'];

        const models = modelIds
            .map((modelId) => {
                const m = byModel[modelId] || {};
                const input = m.input_tokens ?? 0;
                const output = m.output_tokens ?? 0;
                const totalTokens = m.total_tokens ?? (input + output);
                return { modelId, input, output, total: totalTokens };
            })
            .sort((a, b) => b.total - a.total);

        const renderPieSlices = () => {
            if (!models.length || total <= 0) {
                return '<text x="100" y="105" text-anchor="middle" fill="#94a3b8" font-size="12">No data</text>';
            }
            if (models.length === 1) {
                return `<circle class="token-pie-slice" data-model-index="0" cx="100" cy="100" r="84" fill="${palette[0]}" stroke="#ffffff" stroke-width="2"></circle>`;
            }

            let angle = -Math.PI / 2;
            const cx = 100;
            const cy = 100;
            const radius = 84;
            return models.map((m, idx) => {
                const ratio = m.total / total;
                const delta = ratio * Math.PI * 2;
                const nextAngle = angle + delta;
                const x1 = cx + radius * Math.cos(angle);
                const y1 = cy + radius * Math.sin(angle);
                const x2 = cx + radius * Math.cos(nextAngle);
                const y2 = cy + radius * Math.sin(nextAngle);
                const largeArc = ratio > 0.5 ? 1 : 0;
                const d = `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`;
                angle = nextAngle;
                return `<path class="token-pie-slice" data-model-index="${idx}" d="${d}" fill="${palette[idx % palette.length]}" stroke="#ffffff" stroke-width="2"></path>`;
            }).join('');
        };

        const inputPct = Math.round(pct(totalIn, total));
        const outputPct = Math.round(pct(totalOut, total));

        let html = '';
        html += '<div class="token-usage-grid">';
        html += '  <div class="token-usage-summary-cards">';
        html += `    <div class="token-usage-card"><div class="token-usage-card-label">Total tokens</div><div class="token-usage-card-value">${fmt(total)}</div></div>`;
        html += `    <div class="token-usage-card"><div class="token-usage-card-label">Input tokens</div><div class="token-usage-card-value">${fmt(totalIn)}</div><div class="token-usage-card-subtle">${inputPct}% of total</div></div>`;
        html += `    <div class="token-usage-card"><div class="token-usage-card-label">Output tokens</div><div class="token-usage-card-value">${fmt(totalOut)}</div><div class="token-usage-card-subtle">${outputPct}% of total</div></div>`;
        html += '  </div>';
        html += '  <div class="token-usage-io-split">';
        html += `    <div class="token-usage-io-fill token-usage-io-input" style="width:${Math.max(0, Math.min(100, inputPct))}%;"></div>`;
        html += `    <div class="token-usage-io-fill token-usage-io-output" style="width:${Math.max(0, Math.min(100, outputPct))}%;"></div>`;
        html += '  </div>';
        html += '  <div class="token-usage-io-legend">';
        html += `    <span><i class="token-usage-dot token-usage-dot-input"></i>Input ${fmt(totalIn)} (${inputPct}%)</span>`;
        html += `    <span><i class="token-usage-dot token-usage-dot-output"></i>Output ${fmt(totalOut)} (${outputPct}%)</span>`;
        html += '  </div>';
        html += '</div>';

        if (models.length > 0) {
            html += '<div class="token-usage-models-layout">';
            html += '  <div class="token-usage-pie-card">';
            html += '    <div class="token-usage-section-title">Share by model</div>';
            html += '    <div class="token-usage-pie-wrap">';
            html += '      <svg class="token-usage-pie" viewBox="0 0 200 200" role="img" aria-label="Token usage share by model">';
            html +=            renderPieSlices();
            html += '      </svg>';
            html += `      <div class="token-usage-pie-center"><div class="token-usage-pie-center-value">${fmt(total)}</div><div class="token-usage-pie-center-label">total</div></div>`;
            html += '    </div>';
            html += '  </div>';
            html += '  <div class="token-usage-model-list">';
            html += '    <div class="token-usage-section-title">Model breakdown</div>';
            models.forEach((m, idx) => {
                const modelPct = pct(m.total, total);
                const pctRounded = Math.round(modelPct * 10) / 10;
                const shortModel = m.modelId.length > 44 ? (m.modelId.slice(0, 41) + '...') : m.modelId;
                html += `<div class="token-usage-model-row" data-model-index="${idx}">`;
                html += `  <div class="token-usage-model-top"><span class="token-usage-model-name" title="${escapeHtml(m.modelId)}"><i class="token-usage-dot" style="background:${palette[idx % palette.length]}"></i>${escapeHtml(shortModel)}</span><span class="token-usage-model-total">${fmt(m.total)} <small>(${pctRounded}%)</small></span></div>`;
                const barWidth = modelPct <= 0 ? 0 : Math.max(2, Math.min(100, modelPct));
                html += `  <div class="token-usage-model-bar"><span style="width:${barWidth}%; background:${palette[idx % palette.length]}"></span></div>`;
                html += `  <div class="token-usage-model-sub">in ${fmt(m.input)} • out ${fmt(m.output)}</div>`;
                html += '</div>';
            });
            html += '  </div>';
            html += '</div>';
        }

        targetElement.innerHTML = html;

        const rows = targetElement.querySelectorAll('.token-usage-model-row');
        const slices = targetElement.querySelectorAll('.token-pie-slice');
        const setActive = (index, pinned = false) => {
            rows.forEach((row) => {
                const isActive = row.dataset.modelIndex === String(index);
                row.classList.toggle('active', isActive);
                if (!pinned) row.classList.remove('pinned');
                if (pinned && isActive) row.classList.add('pinned');
            });
            slices.forEach((slice) => {
                const isActive = slice.dataset.modelIndex === String(index);
                slice.classList.toggle('active', isActive);
                if (!pinned) slice.classList.remove('pinned');
                if (pinned && isActive) slice.classList.add('pinned');
            });
        };
        const clearActive = () => {
            rows.forEach((row) => row.classList.remove('active'));
            slices.forEach((slice) => slice.classList.remove('active'));
        };
        let pinnedIndex = null;
        const onEnter = (index) => {
            if (pinnedIndex === null) setActive(index, false);
        };
        const onLeave = () => {
            if (pinnedIndex === null) clearActive();
        };
        const onTogglePin = (index) => {
            if (pinnedIndex === index) {
                pinnedIndex = null;
                rows.forEach((row) => row.classList.remove('pinned'));
                slices.forEach((slice) => slice.classList.remove('pinned'));
                clearActive();
                return;
            }
            pinnedIndex = index;
            setActive(index, true);
        };

        rows.forEach((row) => {
            const index = row.dataset.modelIndex;
            row.addEventListener('mouseenter', () => onEnter(index));
            row.addEventListener('mouseleave', onLeave);
            row.addEventListener('click', () => onTogglePin(index));
        });
        slices.forEach((slice) => {
            const index = slice.dataset.modelIndex;
            slice.addEventListener('mouseenter', () => onEnter(index));
            slice.addEventListener('mouseleave', onLeave);
            slice.addEventListener('click', () => onTogglePin(index));
        });
    }

    function renderTokenUsage(data) {
        renderTokenUsageInto(outputsTokenUsageContent, data, 'No token usage data.');
    }

    async function loadTokenUsageInTab() {
        if (!currentResultContext || !outputsTokenUsageContent) return;
        outputsTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">Loading…</span>';
        try {
            const params = new URLSearchParams({
                collection_name: currentResultContext.collection_name,
                pipeline_id: currentResultContext.pipeline_id,
                criteria_set_name: currentResultContext.criteria_set_name,
                paper_id: currentResultContext.paper_id
            });
            const res = await fetch('/checklist_review/api/outputs/token_usage?' + params.toString());
            if (res.ok) {
                const data = await res.json();
                renderTokenUsage(data);
            } else {
                outputsTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">No token usage data for this run.</span>';
            }
        } catch (e) {
            outputsTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">Could not load token usage.</span>';
        }
    }

    async function loadCollectionTokenUsageSummary() {
        if (!collectionTokenUsageContent) return;
        collectionTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">Loading collection token usage…</span>';

        const selectedProcess = getSelectedProcess();
        if (!selectedProcess || !selectedProcess.slug) {
            collectionTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">Select a review process first.</span>';
            return;
        }

        const selectedChecklist = getSelectedChecklist();
        if (!selectedChecklist || !selectedChecklist.name) {
            collectionTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">Select a checklist first.</span>';
            return;
        }

        if (!currentCollection) {
            collectionTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">Select a collection first.</span>';
            return;
        }

        const renderScopeMeta = (reviewed = null, withTokens = null, withoutTokens = null) => {
            if (!collectionTokenUsageScopeLabel) return;
            const reviewedHtml = reviewed === null ? '' : `
                <span class="collection-token-scope-chip">
                    <span class="collection-token-scope-chip-label">Reviewed</span>
                    <span class="collection-token-scope-chip-value">${Number(reviewed || 0).toLocaleString()}</span>
                </span>
            `;
            const withTokensHtml = withTokens === null ? '' : `
                <span class="collection-token-scope-chip">
                    <span class="collection-token-scope-chip-label">With token data</span>
                    <span class="collection-token-scope-chip-value">${Number(withTokens || 0).toLocaleString()}</span>
                </span>
            `;
            const withoutTokensHtml = withoutTokens === null ? '' : `
                <span class="collection-token-scope-chip">
                    <span class="collection-token-scope-chip-label">Missing token data</span>
                    <span class="collection-token-scope-chip-value">${Number(withoutTokens || 0).toLocaleString()}</span>
                </span>
            `;

            collectionTokenUsageScopeLabel.innerHTML = `
                <div class="collection-token-scope-context">
                    <span class="collection-token-scope-item"><strong>Collection</strong> ${escapeHtml(currentCollection)}</span>
                    <span class="collection-token-scope-dot">•</span>
                    <span class="collection-token-scope-item"><strong>Process</strong> ${escapeHtml(selectedProcess.name)}</span>
                    <span class="collection-token-scope-dot">•</span>
                    <span class="collection-token-scope-item"><strong>Checklist</strong> ${escapeHtml(selectedChecklist.name)}</span>
                </div>
                <div class="collection-token-scope-chips">
                    ${reviewedHtml}
                    ${withTokensHtml}
                    ${withoutTokensHtml}
                </div>
            `;
        };

        renderScopeMeta();

        try {
            const params = new URLSearchParams({
                collection_name: currentCollection,
                pipeline_id: selectedProcess.slug,
                criteria_set_name: selectedChecklist.name
            });

            const res = await fetch('/checklist_review/api/outputs/token_usage/collection_summary?' + params.toString());
            if (!res.ok) {
                collectionTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">No token usage data for this scope.</span>';
                return;
            }

            const data = await res.json();
            renderTokenUsageInto(collectionTokenUsageContent, data, 'No token usage data for reviewed papers in this scope.');

            const reviewed = Number(data.reviewed_papers || 0);
            const withTokens = Number(data.papers_with_token_data || 0);
            const withoutTokens = Number(data.papers_missing_token_data || 0);
            renderScopeMeta(reviewed, withTokens, withoutTokens);
        } catch (error) {
            collectionTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">Could not load collection token usage.</span>';
        }
    }

    function buildOutputFileUrl(filename, download = false) {
        if (!currentResultContext) return '#';
        const params = new URLSearchParams({
            collection_name: currentResultContext.collection_name,
            pipeline_id: currentResultContext.pipeline_id,
            criteria_set_name: currentResultContext.criteria_set_name,
            paper_id: currentResultContext.paper_id,
            filename: filename
        });
        if (download) params.set('download', '1');
        return `/checklist_review/api/outputs/file?${params.toString()}`;
    }

    async function loadOutputsTab() {
        if (!currentResultContext) return;
        if (outputsModalSelect) {
            outputsModalSelect.innerHTML = '<option value="">Loading…</option>';
            outputsModalSelect.disabled = true;
        }
        if (outputsModalEmpty) outputsModalEmpty.style.display = 'none';
        if (outputsModalView) outputsModalView.style.display = 'flex';
        showOutputPlaceholder();
        loadTokenUsageInTab();
        try {
            const params = new URLSearchParams({
                collection_name: currentResultContext.collection_name,
                pipeline_id: currentResultContext.pipeline_id,
                criteria_set_name: currentResultContext.criteria_set_name,
                paper_id: currentResultContext.paper_id
            });
            const res = await fetch(`/checklist_review/api/outputs?${params.toString()}`);
            const items = await res.json();
            if (!outputsModalSelect) return;
            if (!Array.isArray(items) || items.length === 0) {
                outputsModalSelect.innerHTML = '<option value="">No outputs</option>';
                outputsModalSelect.disabled = true;
                if (outputsModalView) outputsModalView.style.display = 'none';
                if (outputsModalEmpty) outputsModalEmpty.style.display = 'block';
                return;
            }
            outputsModalSelect.innerHTML = '<option value="">Select an output…</option>';
            items.forEach((item) => {
                const opt = document.createElement('option');
                opt.value = `${item.name}\t${item.type}`;
                opt.textContent = `${item.name} (${item.type.toUpperCase()})`;
                outputsModalSelect.appendChild(opt);
            });
            outputsModalSelect.disabled = false;
            if (items.length > 0) outputsModalSelect.selectedIndex = 1;
            outputsModalSelect.dispatchEvent(new Event('change'));
        } catch (e) {
            outputsModalSelect.innerHTML = '<option value="">Failed to load outputs</option>';
            outputsModalSelect.disabled = true;
            if (outputsModalEmpty) {
                outputsModalEmpty.textContent = 'Failed to load outputs.';
                outputsModalEmpty.style.display = 'block';
            }
            if (outputsModalView) outputsModalView.style.display = 'none';
        }
    }

    function showOutputPlaceholder() {
        if (!outputsModalViewContent) return;
        outputsModalViewContent.innerHTML = '<div class="outputs-empty outputs-placeholder">Select an output file above to preview.</div>';
        if (outputsModalViewTitle) outputsModalViewTitle.textContent = '';
        if (outputsModalExportBtn) {
            outputsModalExportBtn.href = '#';
            outputsModalExportBtn.download = '';
        }
    }

    function onOutputsModalSelectChange() {
        if (!outputsModalSelect || !outputsModalViewContent) return;
        const val = outputsModalSelect.value;
        if (!val) {
            showOutputPlaceholder();
            return;
        }
        const [filename, type] = val.split('\t');
        showOutputInModal(filename, type);
    }

    function escapeHtml(s) {
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    async function showOutputInModal(filename, type) {
        if (!outputsModalViewTitle || !outputsModalViewContent || !outputsModalExportBtn) return;
        outputsModalViewTitle.textContent = filename;
        outputsModalExportBtn.href = buildOutputFileUrl(filename, true);
        outputsModalExportBtn.download = filename;
        if (type === 'pdf') {
            const url = buildOutputFileUrl(filename, false);
            outputsModalViewContent.innerHTML = `<iframe src="${escapeHtml(url)}" title="${escapeHtml(filename)}"></iframe>`;
        } else {
            outputsModalViewContent.innerHTML = '<div class="outputs-empty">Loading…</div>';
            try {
                const url = buildOutputFileUrl(filename, false);
                const res = await fetch(url);
                const text = await res.text();
                outputsModalViewContent.innerHTML = '';
                const pre = document.createElement('pre');
                pre.style.margin = '0'; pre.style.whiteSpace = 'pre-wrap'; pre.style.wordBreak = 'break-word';
                if (type === 'json') {
                    try {
                        pre.textContent = JSON.stringify(JSON.parse(text), null, 2);
                    } catch (_) {
                        pre.textContent = text;
                    }
                } else {
                    pre.textContent = text;
                }
                outputsModalViewContent.appendChild(pre);
            } catch (e) {
                outputsModalViewContent.innerHTML = '<div class="outputs-empty">Failed to load file.</div>';
            }
        }
    }

    function clearOutputsTabState() {
        if (outputsTokenUsageContent) {
            outputsTokenUsageContent.innerHTML = '<span class="outputs-token-usage-placeholder">No token usage data.</span>';
        }
        if (outputsModalSelect) {
            outputsModalSelect.innerHTML = '<option value="">Select an output…</option>';
            outputsModalSelect.disabled = true;
        }
        if (outputsModalEmpty) {
            outputsModalEmpty.textContent = 'No output files found in the outputs folder.';
            outputsModalEmpty.style.display = 'none';
        }
        if (outputsModalView) outputsModalView.style.display = 'flex';
        showOutputPlaceholder();
    }

    if (outputsModalSelect) {
        outputsModalSelect.addEventListener('change', onOutputsModalSelectChange);
    }

    if (collectionTokenUsageModalEl) {
        collectionTokenUsageModalEl.addEventListener('show.bs.modal', loadCollectionTokenUsageSummary);
    }

    if (refreshCollectionTokenUsageBtn) {
        refreshCollectionTokenUsageBtn.addEventListener('click', loadCollectionTokenUsageSummary);
    }

    // --- Save / Save As Handlers ---
    const showSaveNotification = (message, isError = false) => {
        const actionsSection = document.querySelector('.tools-sidebar .mb-3.pb-3.border-bottom');
        if (!actionsSection) return;

        // Remove any existing notification
        const existing = actionsSection.querySelector('.save-notification');
        if (existing) {
            existing.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => existing.remove(), 300);
        }

        // Create new notification
        const notification = document.createElement('div');
        notification.className = `save-notification ${isError ? 'error' : ''}`;
        notification.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                    ${isError
                ? '<path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>'
                : '<path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>'
            }
                </svg>
                <span>${message}</span>
            `;

        actionsSection.appendChild(notification);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.style.animation = 'slideOut 0.3s ease-out';
                setTimeout(() => notification.remove(), 300);
            }
        }, 3000);
    };

    const saveProcess = async (name) => {
        if (!window.reactFlowInstance) {
            showSaveNotification('Process editor not initialized', true);
            return;
        }
        const data = window.reactFlowInstance.getFlow(false); // Exclude positions when saving
        const currentSelection = currentSelectedProcess ? currentSelectedProcess.slug : null; // Store current selection

        try {
            const res = await fetch('/checklist_review/api/pipelines', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, data: data })
            });
            if (res.ok) {
                showSaveNotification(`"${name}" saved successfully`);
                // Reload processes but maintain selection
                await loadProcesses(true);
                // Ensure the saved process is selected
                const savedItem = processList.querySelector(`[data-process-name="${name}"]`);
                if (savedItem) {
                    processList.querySelectorAll('.list-group-item').forEach(item => item.classList.remove('active'));
                    savedItem.classList.add('active');
                    currentSelectedProcess = {
                        name: savedItem.dataset.processName,
                        slug: savedItem.dataset.processSlug
                    };
                }
                // Update canvas header with new name
                updateCanvasHeader();
                // Reset change tracking after save
                setTimeout(() => {
                    if (window.reactFlowInstance) {
                        const savedData = window.reactFlowInstance.getFlow(false); // Exclude positions
                        window.originalProcessData = JSON.stringify(savedData);
                        window.hasUnsavedChanges = false;
                        updateButtonStates();
                    }
                }, 100);
            } else {
                const err = await res.json();
                showSaveNotification(err.error || "Failed to save", true);
            }
        } catch (e) {
            console.error(e);
            showSaveNotification('Error saving process', true);
        }
    };
    if (updateProcessBtn) {
        updateProcessBtn.addEventListener('click', () => {
        const selectedProcess = getSelectedProcess();
        if (!selectedProcess || !selectedProcess.slug) {
            showSaveNotification('Please select a review process to update', true);
            return;
        }
        const current = selectedProcess.slug;
        if (current === 'scientific_checklist') {
            showSaveNotification('Cannot update the default process. Please create a new one.', true);
            return;
        }
        if (!window.hasUnsavedChanges) {
            showSaveNotification('No changes to save', true);
            return;
        }
        saveProcess(selectedProcess.name);
        });
    }
    if (createProcessBtn) {
        createProcessBtn.addEventListener('click', async () => {
        const selectedProcess = getSelectedProcess();
        const currentName = selectedProcess ? selectedProcess.slug : 'scientific_checklist';
        let defaultName;
        if (currentName === 'scientific_checklist') {
            // Find the next available "My Review Process N" name
            const processItems = Array.from(processList.querySelectorAll('.list-group-item'));
            const existingNames = new Set(processItems.map(item => item.dataset.processName || item.dataset.processSlug));
            let counter = 1;
            do {
                defaultName = `My Review Process ${counter}`;
                counter++;
            } while (existingNames.has(defaultName) && counter < 1000);
        } else {
            defaultName = currentName + '_copy';
        }
        const name = await showRenameModal("Create New Review Process", defaultName, true);
        if (name && name.trim()) {
            saveProcess(name.trim());
        } else if (name !== null) {
            showSaveNotification('Process name cannot be empty', true);
        }
        });
    }

    const showDeleteModal = (processName) => {
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
                    if (document.body.contains(overlay)) {
                        document.body.removeChild(overlay);
                    }
                    resolve(confirmed);
                }, 200);
            };

            overlay.querySelector('#deleteModalCancel').addEventListener('click', () => closeModal(false));
            overlay.querySelector('#deleteModalConfirm').addEventListener('click', () => closeModal(true));

            // Close on overlay click (outside modal)
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    closeModal(false);
                }
            });

            // Close on Escape key
            const escapeHandler = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', escapeHandler);
                    closeModal(false);
                }
            };
            document.addEventListener('keydown', escapeHandler);
        });
    };

    if (renameProcessBtn) {
        renameProcessBtn.addEventListener('click', async () => {
            const selectedProcess = getSelectedProcess();
            if (!selectedProcess || !selectedProcess.slug) {
                showSaveNotification('Please select a process to rename', true);
                return;
            }
            const current = selectedProcess.slug; // This is the slug
            if (current === 'scientific_checklist') {
                showSaveNotification('Cannot rename the default process', true);
                return;
            }

            // Get the display name
            const currentDisplayName = selectedProcess.name;

            const newName = await showRenameModal('Rename Review Process', currentDisplayName);
            if (!newName || newName === currentDisplayName) return;

            try {
                const res = await fetch(`/checklist_review/api/pipelines/${encodeURIComponent(current)}/rename`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        new_name: newName
                    })
                });

            const data = await res.json();

            if (res.ok) {
                showSaveNotification(`Process renamed to "${newName}"`);
                // Reload processes and select the renamed one
                await loadProcesses(false);
                setTimeout(() => {
                    // Find the item by matching the display name
                    const renamedItem = processList.querySelector(`[data-process-name="${newName}"]`);
                    if (renamedItem) {
                        processList.querySelectorAll('.list-group-item').forEach(item => item.classList.remove('active'));
                        renamedItem.classList.add('active');
                        currentSelectedProcess = {
                            name: renamedItem.dataset.processName,
                            slug: renamedItem.dataset.processSlug
                        };
                        loadSpecificProcess(renamedOption.value);
                        updateCanvasHeader();
                    }
                }, 100);
            } else {
                showSaveNotification(data.error || 'Failed to rename process', true);
            }
        } catch (e) {
            showSaveNotification(`Error renaming process: ${e.message}`, true);
        }
    });

    deleteProcessBtn.addEventListener('click', async () => {
        const selectedProcess = getSelectedProcess();
        if (!selectedProcess || !selectedProcess.slug) {
            showSaveNotification('Please select a process to delete', true);
            return;
        }
        const current = selectedProcess.slug;
        if (current === 'scientific_checklist') {
            showSaveNotification('Cannot delete the default process', true);
            return;
        }

        const confirmed = await showDeleteModal(selectedProcess.name);
        if (!confirmed) {
            return;
        }

        try {
            const res = await fetch(`/checklist_review/api/pipelines/${current}`, {
                method: 'DELETE'
            });

            if (res.ok) {
                const data = await res.json();
                showSaveNotification(data.message || `"${selectedProcess.name}" deleted successfully`);

                // Clear the visualization
                if (window.reactFlowInstance && window.reactFlowInstance.clear) {
                    window.reactFlowInstance.clear();
                }

                // Reset change tracking
                window.originalProcessData = null;
                window.hasUnsavedChanges = false;

                // Reload processes and select default if available
                await loadProcesses(false);
                const defaultItem = processList.querySelector('[data-process-slug="scientific_checklist"]');
                const firstItem = processList.querySelector('.list-group-item');
                if (defaultItem) {
                    defaultItem.classList.add('active');
                    currentSelectedProcess = {
                        name: defaultItem.dataset.processName,
                        slug: defaultItem.dataset.processSlug
                    };
                    await loadSpecificProcess('scientific_checklist');
                } else if (firstItem) {
                    firstItem.classList.add('active');
                    currentSelectedProcess = {
                        name: firstItem.dataset.processName,
                        slug: firstItem.dataset.processSlug
                    };
                    await loadSpecificProcess(firstItem.dataset.processSlug);
                }
                updateButtonStates();
            } else {
                const err = await res.json();
                showSaveNotification(err.error || 'Failed to delete process', true);
            }
            } catch (e) {
                console.error(e);
                showSaveNotification('Error deleting process', true);
            }
        });
    }

    // --- Checklists Loading ---
    async function loadChecklists(selectLatest = false) {
        checklistList.innerHTML = '';
        // Checklists are now global, no collection_name needed
        try {
            const res = await fetch(`/checklist_review/api/criteria-sets`);
            const data = await res.json();
            
            if (data.length === 0) {
                checklistList.innerHTML = '<div class="text-center p-3 text-muted small">No checklists found. Create one to get started.</div>';
                return;
            }
            
            data.forEach((c, index) => {
                const listItem = document.createElement('div');
                listItem.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                listItem.dataset.checklistName = c.name;
                listItem.dataset.checklistPath = c.path;
                
                // Checklist name
                const nameDiv = document.createElement('div');
                nameDiv.className = 'text-truncate';
                nameDiv.style.maxWidth = '70%';
                nameDiv.textContent = c.name;
                
                // View button
                const viewBtn = document.createElement('button');
                viewBtn.className = 'btn btn-sm btn-outline-primary checklist-view-btn';
                viewBtn.style.cssText = 'padding: 0.25rem 0.5rem; min-width: 32px; border-radius: 6px;';
                viewBtn.title = 'View Checklist';
                viewBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8M1.173 8a13 13 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5s3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8q-.086.13-.195.288c-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5s-3.879-1.168-5.168-2.457A13 13 0 0 1 1.172 8z"/>
                        <path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0"/>
                    </svg>
                `;
                
                // Click handler for selection
                listItem.addEventListener('click', (e) => {
                    // Don't trigger selection if clicking the view button
                    if (e.target.closest('.checklist-view-btn')) {
                        return;
                    }
                    
                    // Remove active class from all items
                    checklistList.querySelectorAll('.list-group-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    
                    // Add active class to clicked item
                    listItem.classList.add('active');
                    currentSelectedChecklist = {
                        name: c.name,
                        path: c.path
                    };
                    
                    // Trigger change event for compatibility
                    const changeEvent = new Event('checklistSelected');
                    changeEvent.checklist = currentSelectedChecklist;
                    document.dispatchEvent(changeEvent);
                });
                
                // View button click handler
                viewBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await viewChecklist(c.name);
                });
                
                listItem.appendChild(nameDiv);
                listItem.appendChild(viewBtn);
                checklistList.appendChild(listItem);
            });

            // Auto-select first checklist by default
            if (data.length > 0) {
                const firstItem = checklistList.querySelector('.list-group-item');
                if (firstItem) {
                    firstItem.classList.add('active');
                    currentSelectedChecklist = {
                        name: data[0].name,
                        path: data[0].path
                    };
                    // Trigger change event
                    const changeEvent = new Event('checklistSelected');
                    changeEvent.checklist = currentSelectedChecklist;
                    document.dispatchEvent(changeEvent);
                }
            }
        } catch (e) {
            console.error('Error loading checklists:', e);
        }
    }
    
    // Helper function to get currently selected checklist
    function getSelectedChecklist() {
        const activeItem = checklistList.querySelector('.list-group-item.active');
        if (activeItem) {
            return {
                name: activeItem.dataset.checklistName,
                path: activeItem.dataset.checklistPath
            };
        }
        return currentSelectedChecklist;
    }
    
    // Helper function to show rename dialog
    function showRenameChecklistDialog(currentName, nameDisplayElement, parentModal, onRenamed) {
        const overlay = document.createElement('div');
        overlay.className = 'rename-modal-overlay';
        overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 10002; animation: fadeIn 0.2s ease-out;';
        
        overlay.innerHTML = `
            <div class="rename-modal" style="background: white; border-radius: 16px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3); max-width: 480px; width: 90%; padding: 0; animation: slideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.2);">
                <div class="rename-modal-header" style="background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; padding: 1.75rem 2rem; display: flex; align-items: center; gap: 1rem; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.2);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" fill="currentColor" viewBox="0 0 16 16" style="flex-shrink: 0; filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));">
                        <path d="M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793l2.646 2.647a.5.5 0 0 0 .708-.708L11.207 1.085zm-1.5 1.5L2.293 11.207l.062.062a.5.5 0 0 1-.227.096l-.776.277a.5.5 0 0 1-.564-.564l.277-.776a.5.5 0 0 1 .096-.227l8.5-8.5zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 4.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325"/>
                    </svg>
                    <h5 style="margin: 0; font-weight: 700; font-size: 1.35rem; letter-spacing: -0.02em;">Rename Checklist</h5>
                </div>
                <div class="rename-modal-body" style="padding: 2rem;">
                    <div class="mb-3">
                        <label class="form-label" style="font-weight: 600; color: #0f172a; margin-bottom: 0.75rem; display: block;">New Checklist Name</label>
                        <input type="text" class="form-control" id="renameChecklistInput" value="${currentName}" style="border-radius: 8px; padding: 0.75rem 1rem; font-size: 1rem; border: 2px solid #e2e8f0; transition: all 0.2s ease;">
                        <div class="form-text" style="margin-top: 0.5rem; color: #64748b; font-size: 0.875rem;">
                            Enter a new name for the checklist. Only letters, numbers, spaces, hyphens, and underscores are allowed.
                        </div>
                    </div>
                </div>
                <div class="rename-modal-footer" style="padding: 1.25rem 2rem; background: linear-gradient(to bottom, #f8f9fa 0%, #ffffff 100%); border-top: 1px solid #e9ecef; display: flex; gap: 1rem; justify-content: flex-end;">
                    <button type="button" class="rename-modal-btn rename-modal-btn-cancel" style="padding: 0.625rem 1.75rem; border-radius: 8px; font-weight: 600; font-size: 0.95rem; border: none; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); min-width: 120px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); background: #6c757d; color: white;">
                        Cancel
                    </button>
                    <button type="button" class="rename-modal-btn rename-modal-btn-rename" style="padding: 0.625rem 1.75rem; border-radius: 8px; font-weight: 600; font-size: 0.95rem; border: none; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); min-width: 120px; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3); background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white;">
                        Rename
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        
        const input = overlay.querySelector('#renameChecklistInput');
        // Use setTimeout to ensure the modal is fully rendered before focusing
        setTimeout(() => {
            input.select();
            input.focus();
        }, 100);
        
        // Cancel button
        overlay.querySelector('.rename-modal-btn-cancel').addEventListener('click', () => {
            overlay.remove();
        });
        
        // Rename button
        overlay.querySelector('.rename-modal-btn-rename').addEventListener('click', async () => {
            const newName = input.value.trim();
            
            if (!newName) {
                input.style.borderColor = '#dc3545';
                input.focus();
                return;
            }
            
            // Validate name (only alphanumeric, spaces, hyphens, underscores)
            if (!/^[a-zA-Z0-9\s\-_]+$/.test(newName)) {
                input.style.borderColor = '#dc3545';
                alert('Checklist name can only contain letters, numbers, spaces, hyphens, and underscores.');
                input.focus();
                return;
            }
            
            if (newName === currentName) {
                overlay.remove();
                return;
            }
            
            const renameBtn = overlay.querySelector('.rename-modal-btn-rename');
            renameBtn.disabled = true;
            renameBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Renaming...';
            
            try {
                const res = await fetch(`/checklist_review/api/criteria-sets/${encodeURIComponent(currentName)}/rename`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ new_name: newName })
                });
                
                const data = await res.json();
                
                if (res.ok) {
                    // Update the display name in the modal
                    nameDisplayElement.textContent = newName;
                    if (typeof onRenamed === 'function') {
                        onRenamed(newName);
                    }

                    // Close rename dialog
                    overlay.remove();
                    
                    // Reload checklists list
                    await loadChecklists();
                    
                    // Update current selection if this was the selected checklist
                    if (currentSelectedChecklist && currentSelectedChecklist.name === currentName) {
                        currentSelectedChecklist.name = newName;
                        // Refresh papers list with the new checklist name
                        loadPapersList();
                    }
                    
                    // Show success notification
                    const successMsg = document.createElement('div');
                    successMsg.className = 'alert alert-success alert-dismissible fade show';
                    successMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000; min-width: 300px;';
                    successMsg.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 8px;">
                            <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0m-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.061L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z"/>
                        </svg>
                        Checklist renamed to "${newName}" successfully
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    `;
                    document.body.appendChild(successMsg);
                    setTimeout(() => successMsg.remove(), 3000);
                } else {
                    input.style.borderColor = '#dc3545';
                    alert(data.error || 'Failed to rename checklist');
                    renameBtn.disabled = false;
                    renameBtn.innerHTML = 'Rename';
                    input.focus();
                }
            } catch (err) {
                console.error('Error renaming checklist:', err);
                alert('Error renaming checklist: ' + err.message);
                renameBtn.disabled = false;
                renameBtn.innerHTML = 'Rename';
            }
        });
        
        // Handle Enter key
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                overlay.querySelector('.rename-modal-btn-rename').click();
            } else if (e.key === 'Escape') {
                overlay.remove();
            }
        });
        
        // Close on overlay click (outside modal)
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.remove();
            }
        });
    }

    // Helper function to show delete confirmation dialog
    function showDeleteChecklistConfirmation(checklistName, parentModal) {
        const overlay = document.createElement('div');
        overlay.className = 'delete-modal-overlay';
        overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 10002; animation: fadeIn 0.2s ease-out;';
        
        overlay.innerHTML = `
            <div class="delete-modal" style="background: white; border-radius: 16px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3); max-width: 480px; width: 90%; padding: 0; animation: slideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.2);">
                <div class="delete-modal-header" style="background: linear-gradient(135deg, #dc3545 0%, #c82333 100%); color: white; padding: 1.75rem 2rem; display: flex; align-items: center; gap: 1rem; box-shadow: 0 2px 8px rgba(220, 53, 69, 0.2);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" fill="currentColor" viewBox="0 0 16 16" style="flex-shrink: 0; filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));">
                        <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>
                        <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708"/>
                    </svg>
                    <h5 style="margin: 0; font-weight: 700; font-size: 1.35rem; letter-spacing: -0.02em;">Delete Checklist</h5>
                </div>
                <div class="delete-modal-body" style="padding: 2rem;">
                    <p style="margin: 0; color: #212529; line-height: 1.7; font-size: 1rem;">
                        Are you sure you want to delete the checklist <strong style="color: #dc3545; font-weight: 600;">"${checklistName}"</strong>? This action cannot be undone.
                    </p>
                </div>
                <div class="delete-modal-footer" style="padding: 1.25rem 2rem; background: linear-gradient(to bottom, #f8f9fa 0%, #ffffff 100%); border-top: 1px solid #e9ecef; display: flex; gap: 1rem; justify-content: flex-end;">
                    <button type="button" class="delete-modal-btn delete-modal-btn-cancel" style="padding: 0.625rem 1.75rem; border-radius: 8px; font-weight: 600; font-size: 0.95rem; border: none; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); min-width: 120px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); background: #6c757d; color: white;">
                        Cancel
                    </button>
                    <button type="button" class="delete-modal-btn delete-modal-btn-delete" style="padding: 0.625rem 1.75rem; border-radius: 8px; font-weight: 600; font-size: 0.95rem; border: none; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); min-width: 120px; box-shadow: 0 2px 8px rgba(220, 53, 69, 0.3); background: linear-gradient(135deg, #dc3545 0%, #c82333 100%); color: white;">
                        Delete Checklist
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        
        // Cancel button
        overlay.querySelector('.delete-modal-btn-cancel').addEventListener('click', () => {
            overlay.remove();
        });
        
        // Delete button
        overlay.querySelector('.delete-modal-btn-delete').addEventListener('click', async () => {
            const deleteBtn = overlay.querySelector('.delete-modal-btn-delete');
            deleteBtn.disabled = true;
            deleteBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Deleting...';
            
            try {
                const res = await fetch(`/checklist_review/api/criteria-sets/${encodeURIComponent(checklistName)}`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                
                if (res.ok) {
                    // Close both modals
                    overlay.remove();
                    parentModal.remove();
                    
                    // Reload checklists
                    await loadChecklists();
                    
                    // Clear selection if deleted checklist was selected
                    if (currentSelectedChecklist && currentSelectedChecklist.name === checklistName) {
                        currentSelectedChecklist = null;
                    }
                    
                    // Show success notification
                    const successMsg = document.createElement('div');
                    successMsg.className = 'alert alert-success alert-dismissible fade show';
                    successMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000; min-width: 300px;';
                    successMsg.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 8px;">
                            <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0m-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.061L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z"/>
                        </svg>
                        Checklist "${checklistName}" deleted successfully
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    `;
                    document.body.appendChild(successMsg);
                    setTimeout(() => successMsg.remove(), 3000);
                } else {
                    alert(data.error || 'Failed to delete checklist');
                    deleteBtn.disabled = false;
                    deleteBtn.innerHTML = 'Delete Checklist';
                }
            } catch (err) {
                console.error('Error deleting checklist:', err);
                alert('Error deleting checklist: ' + err.message);
                deleteBtn.disabled = false;
                deleteBtn.innerHTML = 'Delete Checklist';
            }
        });
        
        // Close on overlay click (outside modal)
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.remove();
            }
        });
    }

    // Helper function to view a checklist
    async function viewChecklist(checklistName) {
        try {
            const res = await fetch(`/checklist_review/api/criteria-sets/${encodeURIComponent(checklistName)}/view`);
            const data = await res.json();

            if (res.ok) {
                showViewChecklistModal(data);
            } else {
                log(`Error: ${data.error || 'Failed to load checklist'}`);
            }
        } catch (e) {
            log(`Error loading checklist: ${e.message}`);
        }
    }

    // --- Upload Handlers (Paper/Checklist) with Drag-Drop ---
    const handleFileUpload = async (files, endpoint, isMultiple = false) => {
        if (!files.length) return;

        const fileArray = Array.from(files);
        
        // Check if this is a checklist upload (which uses SSE)
        const isChecklistUpload = endpoint.includes('/checklists/upload');
        const isPaperUpload = endpoint.includes('/papers/upload');
        
        if (isChecklistUpload) {
            // Handle checklist uploads with SSE progress (no collection needed)
            for (const file of fileArray) {
                await handleChecklistUploadWithProgress(file, endpoint);
            }
        } else if (isPaperUpload) {
            // Paper uploads still require a collection
            if (!currentCollection) return;
            // Handle paper uploads with SSE progress (same as collections)
            await handlePaperUploadWithProgress(fileArray, endpoint);
        } else {
            // Handle other uploads (existing behavior)
            const uploadPromises = fileArray.map(async (file) => {
                const fd = new FormData();
                fd.append('file', file);
                fd.append('collection_name', currentCollection);
                try {
                    const res = await fetch(endpoint, { method: 'POST', body: fd });
                    if (res.ok) {
                        return { success: true, filename: file.name };
                    } else {
                        return { success: false, filename: file.name, error: 'Upload failed' };
                    }
                } catch (e) {
                    return { success: false, filename: file.name, error: e.message };
                }
            });

            const results = await Promise.all(uploadPromises);
            const successCount = results.filter(r => r.success).length;

            if (successCount > 0) {
                await loadPapersList();
            }
        }
    };
    
    // Handle paper upload with SSE progress (similar to collections)
    async function handlePaperUploadWithProgress(files, endpoint) {
        const progressOverlay = document.getElementById('checklistProgressOverlay');
        const progressBar = document.getElementById('checklistProgressBar');
        const progressLabel = document.getElementById('checklistProgressLabel');
        const progressFilename = document.getElementById('checklistProgressFilename');
        
        // Show progress overlay
        if (progressOverlay) {
            progressOverlay.classList.remove('d-none');
            if (progressLabel) progressLabel.textContent = `Uploading and processing ${files.length} file${files.length > 1 ? 's' : ''}...`;
            if (progressBar) progressBar.style.width = '0%';
            if (progressFilename) progressFilename.textContent = '';
        }
        
        try {
            const fd = new FormData();
            files.forEach(file => {
                fd.append('files', file);
            });
            fd.append('collection_name', currentCollection);
            
            const res = await fetch(endpoint, { method: 'POST', body: fd });
            
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || 'Upload failed');
            }
            
            // Consume SSE stream
            await consumePaperUploadEventStream(res, progressBar, progressLabel, progressFilename);
            
            // Reload papers after successful upload
            await loadPapersList();
            
        } catch (e) {
            if (progressOverlay) progressOverlay.classList.add('d-none');
            alert('Upload error: ' + e.message);
        } finally {
            if (progressOverlay) progressOverlay.classList.add('d-none');
        }
    }
    
    // Consume SSE stream for paper upload
    async function consumePaperUploadEventStream(response, progressBar, progressLabel, progressFilename) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
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
                        if (progressBar) progressBar.style.width = '0%';
                        if (progressLabel) progressLabel.textContent = data.stage_name || 'Processing...';
                        if (progressFilename) progressFilename.textContent = '';
                    } else if (event === 'progress') {
                        // Sequential per-paper: bar = completed/total; label = Paper X/total; subtitle = message
                        const completed = data.completed != null ? data.completed : data.current;
                        const total = data.total || 1;
                        const pct = Math.round((completed / total) * 100);
                        if (progressBar) progressBar.style.width = pct + '%';
                        if (progressLabel) {
                            const paperIndex = data.paper_index != null ? data.paper_index : completed + 1;
                            progressLabel.textContent = `Loading Paper ${paperIndex}/${total}`;
                        }
                        if (progressFilename) {
                            progressFilename.textContent = data.message || data.filename || '';
                        }
                    } else if (event === 'complete') {
                        if (progressBar) progressBar.style.width = '100%';
                        if (progressLabel) progressLabel.textContent = 'Processing complete!';
                        if (progressFilename) progressFilename.textContent = `Processed ${data.processed_count || data.total_count || 0} file(s)`;
                    } else if (event === 'error') {
                        if (progressLabel) progressLabel.textContent = 'Error occurred';
                        if (progressFilename) progressFilename.textContent = data.message || 'An error occurred during processing';
                    }
                }
            }
        }
    }
    
    // Handle checklist upload with SSE progress
    async function handleChecklistUploadWithProgress(file, endpoint) {
        const progressOverlay = document.getElementById('checklistProgressOverlay');
        const progressBar = document.getElementById('checklistProgressBar');
        const progressLabel = document.getElementById('checklistProgressLabel');
        const progressFilename = document.getElementById('checklistProgressFilename');
        
        // Show progress overlay
        if (progressOverlay) {
            progressOverlay.classList.remove('d-none');
            if (progressLabel) progressLabel.textContent = 'Uploading checklist...';
            if (progressBar) progressBar.style.width = '0%';
            if (progressFilename) progressFilename.textContent = file.name;
        }
        
        try {
            const fd = new FormData();
            fd.append('file', file);
            // Checklists are now global, no collection_name needed
            
            const res = await fetch(endpoint, { method: 'POST', body: fd });
            
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || 'Upload failed');
            }
            
            // Consume SSE stream
            await consumeChecklistUploadEventStream(res, progressBar, progressLabel, progressFilename);
            
            // Reload checklists after successful upload
            await loadChecklists(true);
            
        } catch (e) {
            if (progressOverlay) progressOverlay.classList.add('d-none');
            alert('Upload error: ' + e.message);
        } finally {
            if (progressOverlay) progressOverlay.classList.add('d-none');
        }
    }
    
    // Consume SSE stream for checklist upload
    async function consumeChecklistUploadEventStream(response, progressBar, progressLabel, progressFilename) {
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
                    
                    if (event === 'stage_start') {
                        if (progressLabel) {
                            progressLabel.textContent = data.stage_name || 'Processing...';
                        }
                        if (progressBar) progressBar.style.width = '0%';
                    } else if (event === 'progress') {
                        const progress = data.progress || 0;
                        if (progressBar) progressBar.style.width = progress + '%';
                        if (progressLabel && data.message) {
                            progressLabel.textContent = data.message;
                        }
                        if (progressFilename && data.filename) {
                            progressFilename.textContent = data.filename;
                        }
                    } else if (event === 'complete') {
                        if (progressBar) progressBar.style.width = '100%';
                        if (progressLabel) {
                            const msg = data.criteria_extracted 
                                ? `Extracted ${data.criteria_extracted} criteria successfully!`
                                : data.message || 'Upload complete';
                            progressLabel.textContent = msg;
                        }
                        // Small delay to show completion
                        await new Promise(resolve => setTimeout(resolve, 500));
                    } else if (event === 'error') {
                        throw new Error(data.message || 'An error occurred during processing');
                    }
                }
            }
        }
    }

    // Paper upload handlers
    paperUpload.addEventListener('change', (e) => {
        handleFileUpload(e.target.files, '/checklist_review/api/artifacts/upload', true);
        paperUpload.value = '';
    });

    // Paper drag-drop
    paperDropzone.addEventListener('click', () => paperUpload.click());
    paperDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        paperDropzone.classList.add('drag-over');
    });
    paperDropzone.addEventListener('dragleave', () => {
        paperDropzone.classList.remove('drag-over');
    });
    paperDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        paperDropzone.classList.remove('drag-over');
        const files = Array.from(e.dataTransfer.files).filter(f => f.type === 'application/pdf');
        if (files.length > 0) {
            handleFileUpload(files, '/checklist_review/api/artifacts/upload', true);
        }
        // Don't log upload-related messages in execution log
    });

    // Checklist upload handlers
    if (checklistUpload) {
        checklistUpload.addEventListener('change', (e) => {
            handleFileUpload(e.target.files, '/checklist_review/api/criteria-sets/upload', true);
            checklistUpload.value = '';
        });
    }

    // --- Checklist View/Rename/Create Handlers ---
    const checklistActions = document.getElementById('checklistActions');
    const viewChecklistBtn = document.getElementById('viewChecklistBtn');
    const createChecklistBtn = document.getElementById('createChecklistBtn');

    // Create Checklist - clicking shows the create checklist modal
    if (createChecklistBtn) {
        createChecklistBtn.addEventListener('click', () => {
            showCreateChecklistModal();
        });
        
        // Add tooltip
        createChecklistBtn.title = 'Create new checklist';
    }

    // View Checklist Modal
    async function showViewChecklistModal(data) {
        const modal = document.createElement('div');
        modal.className = 'modal fade show';
        modal.style.display = 'block';
        modal.style.backgroundColor = 'rgba(0,0,0,0.5)';

        let questionsHtml = '';
        let isPdf = data.type === 'pdf';
        const isExtracted = data.source === 'extracted'; // Indicates this was extracted from PDF
        let originalCriteria = data.criteria ? JSON.parse(JSON.stringify(data.criteria)) : [];
        let hasChanges = false; // Declare at function scope so it's accessible to closeModal
        let checklistName = data.name;

        if (!isPdf && data.criteria && data.criteria.length > 0) {
            const headerNote = isExtracted ? '<div class="alert alert-info mb-3" style="font-size: 0.875rem; padding: 0.75rem;"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px; vertical-align: text-bottom;"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0"/></svg>This checklist was extracted from a PDF file.</div>' : '';
            questionsHtml = `
                    ${headerNote}
                    <div id="checklistQuestionsContainer" class="list-group" style="max-height: 400px; overflow-y: auto;">
                        ${data.criteria.map((q, idx) => `
                            <div class="list-group-item criterion-item" data-question-idx="${idx}" style="border-left: 4px solid #2563eb; margin-bottom: 0.5rem; border-radius: 6px; padding: 1rem;">
                                <div class="d-flex align-items-start gap-2">
                                    <span class="badge bg-primary" style="margin-top: 4px; flex-shrink: 0;">${idx + 1}</span>
                                    <div class="flex-grow-1">
                                        <textarea class="form-control criterion-description-input" data-question-id="${q.id || `q${idx+1}`}" style="min-height: 60px; resize: vertical; font-size: 0.9rem;">${(q.description || q.question || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</textarea>
                                        ${q.id ? `<div class="text-muted small mt-1">ID: ${q.id}</div>` : ''}
                                        <button type="button" class="btn btn-sm btn-outline-danger mt-2 remove-criterion-btn" style="font-size: 0.75rem;">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                                <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0z"/>
                                                <path d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4zM2.5 3h11V2h-11z"/>
                                            </svg>
                                            Remove
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-primary mt-2" id="addCriterionBtn" style="border-radius: 6px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                            <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4"/>
                        </svg>
                        Add Question
                    </button>
                `;
        } else if (!isPdf) {
            questionsHtml = `
                <div id="checklistQuestionsContainer" class="list-group" style="max-height: 400px; overflow-y: auto;">
                    <p class="text-muted">No questions found in this checklist.</p>
                </div>
                <button type="button" class="btn btn-sm btn-outline-primary mt-2" id="addCriterionBtn" style="border-radius: 6px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                        <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4"/>
                    </svg>
                    Add Question
                </button>
            `;
        }

        modal.innerHTML = `
                <div class="modal-dialog modal-lg modal-dialog-centered">
                    <div class="modal-content" style="border-radius: 12px; border: none; box-shadow: 0 10px 40px rgba(0,0,0,0.2); max-width: 800px;">
                        <div class="modal-header" style="background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; border-radius: 12px 12px 0 0; border: none;">
                            <h5 class="modal-title" style="font-weight: 600; display: flex; align-items: center; gap: 0.5rem; flex: 1;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16" style="flex-shrink: 0;">
                                    <path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1h12zM2 0a2 2 0 0 0-2 2v12.793a.5.5 0 0 0 .854.353l2.853-2.853A1 1 0 0 1 4.414 12H14a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z"/>
                                </svg>
                                <span id="checklistNameDisplay">${data.name || 'Unknown'}</span>
                                ${!isPdf ? `<button type="button" class="btn btn-sm btn-outline-light" id="renameChecklistBtn" style="padding: 0.25rem 0.5rem; margin-left: 0.5rem; border-radius: 6px; flex-shrink: 0;" title="Rename checklist">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                                        <path d="M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793l2.646 2.647a.5.5 0 0 0 .708-.708L11.207 1.085zm-1.5 1.5L2.293 11.207l.062.062a.5.5 0 0 1-.227.096l-.776.277a.5.5 0 0 1-.564-.564l.277-.776a.5.5 0 0 1 .096-.227l8.5-8.5zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 4.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325"/>
                                    </svg>
                                </button>` : ''}
                            </h5>
                            <button type="button" class="btn-close btn-close-white" id="modalCloseXBtn" style="cursor: pointer;"></button>
                        </div>
                        <div class="modal-body" style="padding: 1.5rem; height: 500px; display: flex; flex-direction: column;">
                            ${isPdf ? `
                                <div style="margin-bottom: 1rem;">
                                    <label class="form-label" style="font-weight: 600; color: #0f172a;">Select Review Process</label>
                                    <select class="form-select" id="pdfExtractProcessSelect" style="border-radius: 6px;">
                                        <option value="">Select a process...</option>
                                    </select>
                                    <p class="text-muted small mt-2">Select a review process to extract questions from this PDF checklist.</p>
                                </div>
                                <div style="margin-bottom: 1rem;">
                                    <button type="button" class="btn btn-primary" id="extractPdfBtn" disabled style="border-radius: 6px;">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                            <path d="M8.5 1.5A1.5 1.5 0 0 0 7 0H2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9.5a1.5 1.5 0 0 0-1.5-1.5h-1a.5.5 0 0 1 0-1h1A2.5 2.5 0 0 1 16 9.5v4A2.5 2.5 0 0 1 13.5 16h-11A2.5 2.5 0 0 1 0 13.5v-11A2.5 2.5 0 0 1 2.5 0h5a.5.5 0 0 1 .354.146L8.5 1.5z"/>
                                            <path d="M7 1.5v6a.5.5 0 0 0 .5.5h6a.5.5 0 0 0 .146-.354L7.146 1.146A.5.5 0 0 0 7 1.5z"/>
                                        </svg>
                                        Extract Questions
                                    </button>
                                </div>
                                <div id="pdfExtractResults" style="flex: 1; overflow-y: auto; min-height: 0;">
                                    <p class="text-muted">Select a review process and click Extract to view questions.</p>
                                </div>
                            ` : `
                                <div style="flex: 1; overflow-y: auto; min-height: 0;">
                                    ${questionsHtml}
                                </div>
                            `}
                        </div>
                        <div class="modal-footer" style="border-top: 1px solid #e2e8f0; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center;">
                            <div id="checklistChangesIndicator" style="color: #64748b; font-size: 0.875rem; display: none;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                    <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>
                                    <path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0"/>
                                </svg>
                                Unsaved changes
                            </div>
                            <div style="display: flex; gap: 0.5rem; align-items: center;">
                                ${!isPdf ? `<button type="button" class="btn btn-outline-danger" id="deleteChecklistBtn" style="border-radius: 6px;">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                        <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0z"/>
                                        <path d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4zM2.5 3h11V2h-11z"/>
                                    </svg>
                                    Delete
                                </button>` : ''}
                                <button type="button" class="btn btn-secondary" id="closeChecklistModalBtn" style="border-radius: 6px;">Close</button>
                                ${!isPdf ? `<button type="button" class="btn btn-primary" id="saveChecklistBtn" style="border-radius: 6px; display: none;">
                                    Save Changes
                                </button>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        document.body.appendChild(modal);

        // Handle editing for non-PDF checklists
        if (!isPdf) {
            const questionsContainer = modal.querySelector('#checklistQuestionsContainer');
            const addCriterionBtn = modal.querySelector('#addCriterionBtn');
            const saveBtn = modal.querySelector('#saveChecklistBtn');
            const closeBtn = modal.querySelector('#closeChecklistModalBtn');
            const changesIndicator = modal.querySelector('#checklistChangesIndicator');
            
            // Function to check for changes and update UI
            function checkForChanges() {
                const criterionInputs = questionsContainer.querySelectorAll('.criterion-description-input');
                const currentQuestions = Array.from(criterionInputs).map(input => ({
                    id: input.dataset.questionId,
                    text: input.value.trim()
                })).filter(q => q.description.length > 0);
                
                // Compare with original
                const originalTexts = originalCriteria.map(q => (q.description || q.question || '').trim()).filter(t => t.length > 0);
                const currentTexts = currentQuestions.map(q => q.description.trim());
                
                hasChanges = JSON.stringify(originalTexts) !== JSON.stringify(currentTexts) || 
                            criterionInputs.length !== originalCriteria.length;
                
                if (hasChanges) {
                    saveBtn.style.display = 'inline-block';
                    changesIndicator.style.display = 'flex';
                } else {
                    saveBtn.style.display = 'none';
                    changesIndicator.style.display = 'none';
                }
            }
            
            // Add change listeners to all textareas
            function attachChangeListeners() {
                questionsContainer.querySelectorAll('.criterion-description-input').forEach(input => {
                    input.addEventListener('input', checkForChanges);
                });
            }
            
            // Add new question
            if (addCriterionBtn) {
                addCriterionBtn.addEventListener('click', () => {
                    const questionCount = questionsContainer.querySelectorAll('.criterion-item').length;
                    const newQuestionHtml = `
                        <div class="list-group-item criterion-item" data-question-idx="${questionCount}" style="border-left: 4px solid #2563eb; margin-bottom: 0.5rem; border-radius: 6px; padding: 1rem;">
                            <div class="d-flex align-items-start gap-2">
                                <span class="badge bg-primary" style="margin-top: 4px; flex-shrink: 0;">${questionCount + 1}</span>
                                <div class="flex-grow-1">
                                    <textarea class="form-control criterion-description-input" data-question-id="q${questionCount + 1}" style="min-height: 60px; resize: vertical; font-size: 0.9rem;" placeholder="Enter question text..."></textarea>
                                    <button type="button" class="btn btn-sm btn-outline-danger mt-2 remove-criterion-btn" style="font-size: 0.75rem;">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0z"/>
                                            <path d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4zM2.5 3h11V2h-11z"/>
                                        </svg>
                                        Remove
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;
                    questionsContainer.insertAdjacentHTML('beforeend', newQuestionHtml);
                    
                    // Update badge numbers
                    questionsContainer.querySelectorAll('.criterion-item').forEach((item, idx) => {
                        item.querySelector('.badge').textContent = idx + 1;
                    });
                    
                    // Attach listeners to new input
                    const newInput = questionsContainer.querySelector('.criterion-item:last-child .criterion-description-input');
                    newInput.addEventListener('input', checkForChanges);
                    
                    // Attach remove listener
                    const removeBtn = questionsContainer.querySelector('.criterion-item:last-child .remove-criterion-btn');
                    removeBtn.addEventListener('click', function() {
                        this.closest('.criterion-item').remove();
                        // Update badge numbers
                        questionsContainer.querySelectorAll('.criterion-item').forEach((item, idx) => {
                            item.querySelector('.badge').textContent = idx + 1;
                        });
                        checkForChanges();
                    });
                    
                    checkForChanges();
                });
            }
            
            // Remove question handlers
            questionsContainer.querySelectorAll('.remove-criterion-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    this.closest('.criterion-item').remove();
                    // Update badge numbers
                    questionsContainer.querySelectorAll('.criterion-item').forEach((item, idx) => {
                        item.querySelector('.badge').textContent = idx + 1;
                    });
                    checkForChanges();
                });
            });
            
            // Save button handler
            if (saveBtn) {
                saveBtn.addEventListener('click', async () => {
                    const criterionInputs = questionsContainer.querySelectorAll('.criterion-description-input');
                    const criteria = Array.from(criterionInputs)
                        .map((input, idx) => ({
                            id: input.dataset.questionId || `req-${idx + 1}`,
                            description: input.value.trim(),
                        }))
                        .filter(c => c.description.length > 0);
                    
                    if (criteria.length === 0) {
                        alert('At least one criterion is required.');
                        return;
                    }
                    
                    saveBtn.disabled = true;
                    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';
                    
                    try {
                        const res = await fetch(`/checklist_review/api/criteria-sets/${encodeURIComponent(checklistName)}`, {
                            method: 'PUT',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ criteria })
                        });
                        
                        const data = await res.json();
                        
                        if (res.ok) {
                            originalCriteria = criteria;
                            hasChanges = false;
                            saveBtn.style.display = 'none';
                            changesIndicator.style.display = 'none';
                            
                            // Show success message
                            const successMsg = document.createElement('div');
                            successMsg.className = 'alert alert-success alert-dismissible fade show';
                            successMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000; min-width: 300px;';
                            successMsg.innerHTML = `
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 8px;">
                                    <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0m-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.061L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z"/>
                                </svg>
                                Checklist saved successfully
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            `;
                            document.body.appendChild(successMsg);
                            setTimeout(() => successMsg.remove(), 3000);
                            
                            // Reload checklists list
                            await loadChecklists();
                        } else {
                            alert(data.error || 'Failed to save checklist');
                        }
                    } catch (err) {
                        console.error('Error saving checklist:', err);
                        alert('Error saving checklist: ' + err.message);
                    } finally {
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = 'Save Changes';
                    }
                });
            }
            
            // Delete button handler
            const deleteBtn = modal.querySelector('#deleteChecklistBtn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', () => {
                    showDeleteChecklistConfirmation(checklistName, modal);
                });
            }
            
            // Rename button handler
            const renameBtn = modal.querySelector('#renameChecklistBtn');
            const nameDisplay = modal.querySelector('#checklistNameDisplay');
            if (renameBtn && nameDisplay) {
                renameBtn.addEventListener('click', () => {
                    showRenameChecklistDialog(checklistName, nameDisplay, modal, (newName) => {
                        checklistName = newName;
                    });
                });
            }
            
            // Initial attachment of change listeners
            attachChangeListeners();
        }

        // Close button handler (works for both PDF and non-PDF modals)
        const closeModal = () => {
            if (!isPdf && hasChanges) {
                if (confirm('You have unsaved changes. Are you sure you want to close without saving?')) {
                    modal.remove();
                }
            } else {
                modal.remove();
            }
        };
        
        const closeBtn = modal.querySelector('#closeChecklistModalBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', closeModal);
        }
        
        // Handle X button in header
        const closeXBtn = modal.querySelector('#modalCloseXBtn');
        if (closeXBtn) {
            closeXBtn.addEventListener('click', closeModal);
        }

        // Handle PDF extraction
        if (isPdf) {
            const processSelect = modal.querySelector('#pdfExtractProcessSelect');
            const extractBtn = modal.querySelector('#extractPdfBtn');
            const resultsDiv = modal.querySelector('#pdfExtractResults');

            // Load processes
            async function loadProcessesForExtract() {
                try {
                    const res = await fetch(`/checklist_review/api/pipelines?collection_name=${encodeURIComponent(currentCollection)}`);
                    const processes = await res.json();
                    processSelect.innerHTML = '<option value="">Select a process...</option>';
                    processes.forEach(p => {
                        const opt = document.createElement('option');
                        opt.value = p.name;
                        opt.textContent = p.name;
                        processSelect.appendChild(opt);
                    });
                } catch (e) {
                    resultsDiv.innerHTML = `<p class="text-danger">Error loading processes: ${e.message}</p>`;
                }
            }

            processSelect.addEventListener('change', () => {
                extractBtn.disabled = !processSelect.value;
            });

            extractBtn.addEventListener('click', async () => {
                if (!processSelect.value) return;

                extractBtn.disabled = true;
                extractBtn.innerHTML = `
                        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                        Extracting...
                    `;
                resultsDiv.innerHTML = '<p class="text-muted">Extracting questions from PDF...</p>';

                try {
                    const res = await fetch(`/checklist_review/api/criteria-sets/${encodeURIComponent(data.name)}/criteria`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({}),
                    });

                    const result = await res.json();

                    if (res.ok && result.criteria && result.criteria.length > 0) {
                        resultsDiv.innerHTML = `
                                <div class="mb-2">
                                    <strong>Extracted ${result.count} question(s):</strong>
                                </div>
                                <div class="list-group" style="max-height: 300px; overflow-y: auto;">
                                    ${result.criteria.map((q, idx) => `
                                        <div class="list-group-item" style="border-left: 4px solid #2563eb; margin-bottom: 0.5rem; border-radius: 6px;">
                                            <div class="d-flex align-items-start">
                                                <span class="badge bg-primary me-2" style="margin-top: 2px;">${idx + 1}</span>
                                                <div class="flex-grow-1">
                                                    <strong style="color: #0f172a;">${q.description || 'Question'}</strong>
                                                    ${q.id ? `<div class="text-muted small mt-1">ID: ${q.id}</div>` : ''}
                                                </div>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                            `;
                    } else {
                        resultsDiv.innerHTML = `<p class="text-danger">${result.error || 'Failed to extract questions from PDF'}</p>`;
                    }
                } catch (e) {
                    resultsDiv.innerHTML = `<p class="text-danger">Error: ${e.message}</p>`;
                } finally {
                    extractBtn.disabled = false;
                    extractBtn.innerHTML = `
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                <path d="M8.5 1.5A1.5 1.5 0 0 0 7 0H2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9.5a1.5 1.5 0 0 0-1.5-1.5h-1a.5.5 0 0 1 0-1h1A2.5 2.5 0 0 1 16 9.5v4A2.5 2.5 0 0 1 13.5 16h-11A2.5 2.5 0 0 1 0 13.5v-11A2.5 2.5 0 0 1 2.5 0h5a.5.5 0 0 1 .354.146L8.5 1.5z"/>
                                <path d="M7 1.5v6a.5.5 0 0 0 .5.5h6a.5.5 0 0 0 .146-.354L7.146 1.146A.5.5 0 0 0 7 1.5z"/>
                            </svg>
                            Extract Questions
                        `;
                }
            });

            await loadProcessesForExtract();
        }

        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    }

    // Create Checklist Modal
    function showCreateChecklistModal() {
        let questionCount = 1;
        const modal = document.createElement('div');
        modal.className = 'modal fade show';
        modal.style.display = 'block';
        modal.style.backgroundColor = 'rgba(0,0,0,0.5)';

        const questionsContainer = document.createElement('div');
        questionsContainer.id = 'createCriteriaSetCriteria';
        questionsContainer.style.marginTop = '1rem';

        function addQuestionInput(value = '') {
            const questionDiv = document.createElement('div');
            questionDiv.className = 'mb-2';
            questionDiv.style.display = 'flex';
            questionDiv.style.gap = '0.5rem';
            questionDiv.style.alignItems = 'center';
            questionDiv.innerHTML = `
                    <input type="text" class="form-control form-control-sm" placeholder="Enter binary question..." value="${value}" style="flex: 1; border-radius: 6px;">
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.parentElement.remove()" style="border-radius: 6px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                `;
            questionsContainer.appendChild(questionDiv);
        }

        modal.innerHTML = `
                <div class="modal-dialog modal-lg modal-dialog-centered">
                    <div class="modal-content" style="border-radius: 12px; border: none; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
                        <div class="modal-header" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border-radius: 12px 12px 0 0; border: none;">
                            <h5 class="modal-title" style="font-weight: 600;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 8px;">
                                    <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4"/>
                                </svg>
                                Create New Checklist
                            </h5>
                            <button type="button" class="btn-close btn-close-white" id="modalCloseXBtn" style="cursor: pointer;"></button>
                        </div>
                        <div class="modal-body" style="padding: 1.5rem;">
                            <div class="mb-3">
                                <label class="form-label" style="font-weight: 600; color: #0f172a;">Checklist Name</label>
                                <input type="text" class="form-control" id="createChecklistName" placeholder="Enter checklist name..." style="border-radius: 6px;">
                            </div>
                            <div>
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <label class="form-label mb-0" style="font-weight: 600; color: #0f172a;">Questions</label>
                                    <button type="button" class="btn btn-sm btn-outline-primary" onclick="addQuestionInput()" style="border-radius: 6px;">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                            <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4"/>
                                        </svg>
                                        Add Question
                                    </button>
                                </div>
                                <div id="createCriteriaSetCriteria"></div>
                                <p class="text-muted small mt-2">Add binary (yes/no) questions for your checklist.</p>
                            </div>
                        </div>
                        <div class="modal-footer" style="border-top: 1px solid #e2e8f0; padding: 1rem 1.5rem;">
                            <button type="button" class="btn btn-secondary" onclick="this.closest('.modal').remove()" style="border-radius: 6px;">Cancel</button>
                            <button type="button" class="btn btn-success" id="saveChecklistBtn" style="border-radius: 6px;">
                                Save Checklist
                            </button>
                        </div>
                    </div>
                </div>
            `;
        document.body.appendChild(modal);
        modal.querySelector('#createCriteriaSetCriteria').appendChild(questionsContainer);

        // Add initial question input
        addQuestionInput();

        // Make addQuestionInput available globally for the button
        window.addQuestionInput = () => {
            const container = document.getElementById('createCriteriaSetCriteria');
            const questionDiv = document.createElement('div');
            questionDiv.className = 'mb-2';
            questionDiv.style.display = 'flex';
            questionDiv.style.gap = '0.5rem';
            questionDiv.style.alignItems = 'center';
            questionDiv.innerHTML = `
                    <input type="text" class="form-control form-control-sm" placeholder="Enter binary question..." style="flex: 1; border-radius: 6px;">
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.parentElement.remove()" style="border-radius: 6px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                    </button>
                `;
            container.appendChild(questionDiv);
        };

        // Save button handler
        modal.querySelector('#saveChecklistBtn').addEventListener('click', async () => {
            const nameInput = modal.querySelector('#createChecklistName');
            const checklistName = nameInput.value.trim();

            if (!checklistName) {
                alert('Please enter a checklist name.');
                return;
            }

            const criterionInputs = modal.querySelectorAll('#createCriteriaSetCriteria input[type="text"]');
            const criteria = Array.from(criterionInputs)
                .map((input, idx) => ({
                    id: `req-${idx + 1}`,
                    description: input.value.trim(),
                }))
                .filter(c => c.description.length > 0);

            if (criteria.length === 0) {
                alert('Please add at least one criterion.');
                return;
            }

            try {
                const res = await fetch('/checklist_review/api/criteria-sets/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: checklistName,
                        criteria,
                    })
                });

                const data = await res.json();

                if (res.ok) {
                    log(`Criteria set "${checklistName}" created successfully with ${criteria.length} criterion(s).`);
                    modal.remove();
                    await loadChecklists();
                    // Select the newly created checklist
                    setTimeout(() => {
                        const item = checklistList.querySelector(`[data-checklist-name="${checklistName}"]`);
                        if (item) {
                            // Remove active from all items
                            checklistList.querySelectorAll('.list-group-item').forEach(i => i.classList.remove('active'));
                            // Add active to new item
                            item.classList.add('active');
                            currentSelectedChecklist = {
                                name: checklistName,
                                path: item.dataset.checklistPath
                            };
                        }
                    }, 100);
                } else {
                    alert(`Error: ${data.error || 'Failed to create checklist'}`);
                }
            } catch (e) {
                alert(`Error creating checklist: ${e.message}`);
            }
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                window.addQuestionInput = null;
                modal.remove();
            }
        });
    }

});

