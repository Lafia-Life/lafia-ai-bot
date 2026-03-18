define(['core/ajax', 'core/notification', 'core/str'], function(Ajax, Notification, Str) {
    const THINKING_FRAMES = ['Thinking', 'Thinking.', 'Thinking..', 'Thinking...'];

    const state = {
        documents: [],
        activePreview: null,
    };

    const elements = {};
    const strings = {};
    let config = {};

    const STRING_DEFINITIONS = [
        {key: 'status:nodocuments', component: 'mod_chatlearning', identifier: 'nodocuments'},
        {key: 'status:searching', component: 'mod_chatlearning', identifier: 'searching'},
        {key: 'status:uploading', component: 'mod_chatlearning', identifier: 'uploading'},
        {key: 'status:syncing', component: 'mod_chatlearning', identifier: 'syncing'},
        {key: 'status:synccomplete', component: 'mod_chatlearning', identifier: 'synccomplete'},
        {key: 'status:deleting', component: 'mod_chatlearning', identifier: 'deleting'},
        {key: 'status:deleted', component: 'mod_chatlearning', identifier: 'deleted'},
        {key: 'label:delete', component: 'mod_chatlearning', identifier: 'delete'},
    ];

    function $(selector) {
        return elements.root.querySelector(selector);
    }

    function setStatus(node, message, style) {
        if (!node) {
            return;
        }
        node.textContent = message || '';
        node.style.color = style || '';
    }

    function formatMessageTime() {
        return new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    }

    function startThinkingAnimation(bubble) {
        stopThinkingAnimation(bubble);
        let frameIndex = 0;
        bubble.textContent = THINKING_FRAMES[frameIndex];
        const timer = window.setInterval(function() {
            frameIndex = (frameIndex + 1) % THINKING_FRAMES.length;
            bubble.textContent = THINKING_FRAMES[frameIndex];
        }, 450);
        bubble.dataset.thinkingTimer = String(timer);
    }

    function stopThinkingAnimation(bubble) {
        if (bubble && bubble.dataset && bubble.dataset.thinkingTimer) {
            window.clearInterval(Number(bubble.dataset.thinkingTimer));
            delete bubble.dataset.thinkingTimer;
        }
    }

    function clearPreview() {
        const dialog = elements.modalDialog;
        if (!dialog) {
            return;
        }
        if (elements.modalBackdrop) {
            elements.modalBackdrop.classList.remove("active");
        }
        dialog.classList.remove("active");
        const frame = dialog.querySelector('[data-modal-frame]');
        if (frame) {
            frame.src = '';
        }
        const download = dialog.querySelector('[data-modal-download]');
        if (download) {
            download.removeAttribute('href');
        }
        elements.root.querySelectorAll('.citation-chip.active').forEach(function(node) {
            node.classList.remove('active');
        });
        state.activePreview = null;
    }

    function showPreview(citation, trigger) {
        const dialog = elements.modalDialog;
        if (!dialog) {
            return;
        }
        const frame = dialog.querySelector('[data-modal-frame]');
        if (!frame) {
            return;
        }
        const title = dialog.querySelector('[data-modal-title]');
        const download = dialog.querySelector('[data-modal-download]');

        elements.root.querySelectorAll('.citation-chip.active').forEach(function(node) {
            node.classList.remove('active');
        });
        if (trigger) {
            trigger.classList.add('active');
        }

        const page = citation.page_start || 1;
        frame.src = config.documentBase + citation.document_id + '/inline#page=' + page;
        if (title) {
            title.textContent = citation.filename + ' · page ' + page;
        }
        if (download) {
            download.href = config.documentBase + citation.document_id + '/download';
        }

        if (elements.modalBackdrop) {
            elements.modalBackdrop.classList.add('active');
        }
        dialog.classList.add('active');
        const close = dialog.querySelector('[data-modal-close]');
        if (close) {
            close.focus();
        }

        state.activePreview = {
            documentId: citation.document_id,
            pageStart: page,
        };
    }

    function appendMessage(role, content, timestamp) {
        const message = document.createElement('div');
        message.className = 'chat-message ' + role;

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble ' + role;
        bubble.textContent = content;

        const meta = document.createElement('div');
        meta.className = 'chat-meta';
        meta.textContent = timestamp || formatMessageTime();

        message.append(bubble, meta);
        elements.chatLog.appendChild(message);
        elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
        return bubble;
    }

    function renderDocuments(documents) {
        if (!elements.documentList) {
            return;
        }
        elements.documentList.innerHTML = '';
        if (!documents.length) {
            const li = document.createElement('li');
            li.className = 'document-empty';
            li.textContent = strings.nodocuments || 'No documents indexed yet.';
            elements.documentList.appendChild(li);
            return;
        }
        documents.forEach(function(doc) {
            const li = document.createElement('li');
            const main = document.createElement('div');
            main.className = 'document-main';
            const name = document.createElement('span');
            name.className = 'document-name';
            name.textContent = doc.filename;
            const meta = document.createElement('span');
            meta.className = 'document-meta';
            if (doc.source_type === 'web' && doc.url) {
                meta.textContent = 'Web · ' + doc.url;
            } else if (doc.source_type === 'image') {
                meta.textContent = 'Image · ' + (doc.page_count || 1) + ' frames';
            } else if (doc.source_type === 'scorm') {
                meta.textContent = 'SCORM · ' + (doc.page_count || 0) + ' sections';
            } else {
                meta.textContent = 'PDF · ' + (doc.page_count || 0) + ' pages';
            }

            main.append(name, meta);
            li.append(main);

            if (config.canManage) {
                const actions = document.createElement('div');
                actions.className = 'document-actions';
                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'document-delete';
                removeBtn.textContent = strings.delete || 'Delete';
                removeBtn.title = 'Delete indexed document';
                removeBtn.addEventListener('click', function(event) {
                    event.preventDefault();
                    event.stopPropagation();
                    handleDeleteDocument(doc);
                });
                actions.appendChild(removeBtn);
                li.append(actions);
            }

            elements.documentList.appendChild(li);
        });
    }

    function scopeDocumentsForDisplay(documents) {
        const list = Array.isArray(documents) ? documents : [];
        const includeGlobal = !!config.includeGlobalDocs;
        const scope = String(config.documentScope || '').trim().toLowerCase();
        const hasScopedFilter = scope === 'currentcourse' || scope === 'enrolledcourses';

        const allowed = Array.isArray(config.allowedCourseIds)
            ? config.allowedCourseIds.map(function(id) { return String(id).trim(); }).filter(Boolean)
            : [];
        const allowedSet = new Set(allowed);

        return list.filter(function(doc) {
            var docCourseId = doc && doc.course_id !== undefined && doc.course_id !== null
                ? String(doc.course_id).trim()
                : '';

            if (!docCourseId) {
                return includeGlobal;
            }
            if (allowedSet.size > 0) {
                return allowedSet.has(docCourseId);
            }
            if (hasScopedFilter) {
                return false;
            }
            return true;
        });
    }

    function citationLabel(citation) {
        const name = citation.filename || 'Source';
        const start = citation.page_start || 1;
        const end = citation.page_end || start;
        if (citation.source_type === 'web' || citation.source_type === 'scorm') {
            return name + ' §' + start;
        }
        return name + ' p.' + start + (end > start ? '-' + end : '');
    }

    function renderInlineReferences(citations, assistantBubble) {
        const message = assistantBubble ? assistantBubble.closest('.chat-message') : null;
        if (!message) {
            return;
        }
        const existing = message.querySelector('.inline-citations');
        if (existing) {
            existing.remove();
        }

        if (!citations || !citations.length) {
            clearPreview();
            return;
        }

        const wrap = document.createElement('div');
        wrap.className = 'inline-citations';

        citations.forEach(function(citation) {
            if (citation.source_type === 'pdf' && citation.document_id && config.documentBase) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'citation-chip';
                button.textContent = citationLabel(citation);
                button.title = 'Open in viewer';
                button.addEventListener('click', function() {
                    showPreview(citation, button);
                });
                wrap.appendChild(button);
                return;
            }

            if (citation.url) {
                const link = document.createElement('a');
                link.href = citation.url;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.className = 'citation-chip link';
                link.textContent = citationLabel(citation);
                wrap.appendChild(link);
                return;
            }

            const chip = document.createElement('span');
            chip.className = 'citation-chip disabled';
            chip.textContent = citationLabel(citation);
            wrap.appendChild(chip);
        });

        message.appendChild(wrap);
        elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
    }

    function fetchDocuments() {
        if (!elements.documentList) {
            return;
        }
        Ajax.call([
            {
                methodname: 'mod_chatlearning_get_documents',
                args: {cmid: Number(config.cmid)},
            },
        ])[0]
            .then(function(docs) {
                state.documents = scopeDocumentsForDisplay(docs || []);
                renderDocuments(state.documents);
            })
            .catch(Notification.exception);
    }

    function handleDeleteDocument(document) {
        if (!document || !document.document_id) {
            return;
        }

        const label = document.filename || 'this document';
        const confirmed = window.confirm('Delete "' + label + '" from indexed documents?');
        if (!confirmed) {
            return;
        }

        setStatus(elements.documentStatus, strings.deleting || 'Deleting document...');

        Ajax.call([
            {
                methodname: 'mod_chatlearning_delete_document',
                args: {
                    cmid: Number(config.cmid),
                    document_id: String(document.document_id),
                },
            },
        ])[0]
            .then(function() {
                setStatus(elements.documentStatus, strings.deleted || 'Document deleted.');
                fetchDocuments();
            })
            .catch(function(err) {
                const message = err && err.message ? err.message : 'Delete failed';
                setStatus(elements.documentStatus, message, '#dc2626');
            });
    }

    function handleUpload(event) {
        event.preventDefault();
        const input = elements.uploadInput;
        const status = elements.uploadStatus;
        if (!input || !input.files || !input.files.length) {
            return;
        }
        const file = input.files[0];
        const formData = new FormData();
        formData.append('file', file);

        setStatus(status, strings.uploading || 'Uploading...');

        fetch(config.uploadEndpoint, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        })
            .then(function(response) {
                if (!response.ok) {
                    return response.json().then(function(payload) {
                        var message = payload && payload.error ? payload.error : response.statusText;
                        throw new Error(message || 'Upload failed');
                    });
                }
                return response.json();
            })
            .then(function(payload) {
                var uploadedName = payload && payload.document && payload.document.filename ? payload.document.filename : file.name;
                setStatus(status, 'Uploaded ' + uploadedName + '.');
                input.value = '';
                fetchDocuments();
            })
            .catch(function(err) {
                setStatus(status, err && err.message ? err.message : 'Upload failed', '#dc2626');
            });
    }

    function handleScrape(event) {
        event.preventDefault();
        const input = elements.scrapeInput;
        const status = elements.scrapeStatus;
        const url = input && input.value ? input.value.trim() : '';
        if (!url) {
            return;
        }
        setStatus(status, 'Scraping...');

        Ajax.call([
            {
                methodname: 'mod_chatlearning_scrape_url',
                args: {cmid: Number(config.cmid), url: url},
            },
        ])[0]
            .then(function(payload) {
                var scrapedName = payload && payload.document && payload.document.filename ? payload.document.filename : url;
                setStatus(status, 'Scraped ' + scrapedName + '.');
                input.value = '';
                fetchDocuments();
            })
            .catch(function(err) {
                setStatus(status, err && err.message ? err.message : 'Scrape failed', '#dc2626');
            });
    }

    function handleMoodleSync(event) {
        event.preventDefault();

        const status = elements.syncStatus;
        const includePdf = !!(elements.syncPdf && elements.syncPdf.checked);
        const includeScorm = !!(elements.syncScorm && elements.syncScorm.checked);

        if (!includePdf && !includeScorm) {
            setStatus(status, 'Select at least one source type.', '#dc2626');
            return;
        }

        setStatus(status, strings.syncing || 'Syncing Moodle files...');

        Ajax.call([
            {
                methodname: 'mod_chatlearning_sync_moodle_documents',
                args: {
                    cmid: Number(config.cmid),
                    include_pdf: includePdf ? 1 : 0,
                    include_scorm: includeScorm ? 1 : 0,
                },
            },
        ])[0]
            .then(function(payload) {
                var indexed = payload && payload.documents_indexed ? payload.documents_indexed : 0;
                var discovered = payload && payload.files_discovered ? payload.files_discovered : 0;
                var skipped = payload && payload.documents_skipped ? payload.documents_skipped : 0;
                setStatus(
                    status,
                    'Sync complete: ' + indexed + ' indexed, ' + discovered + ' discovered, ' + skipped + ' skipped.'
                );
                fetchDocuments();
            })
            .catch(function(err) {
                setStatus(status, err && err.message ? err.message : 'Moodle sync failed', '#dc2626');
            });
    }

    function handleChat(event) {
        event.preventDefault();
        const question = elements.chatInput.value.trim();
        if (!question) {
            return;
        }
        appendMessage('user', question);
        const assistantBubble = appendMessage('assistant', 'Thinking...');
        assistantBubble.dataset.placeholder = 'true';
        startThinkingAnimation(assistantBubble);
        const submitButton = elements.chatForm ? elements.chatForm.querySelector('button[type="submit"]') : null;

        elements.chatInput.value = '';
        elements.chatInput.disabled = true;
        if (submitButton) {
            submitButton.disabled = true;
        }
        setStatus(elements.chatStatus, '');

        Ajax.call([
            {
                methodname: 'mod_chatlearning_submit_question',
                args: {cmid: Number(config.cmid), question: question},
            },
        ])[0]
            .then(function(payload) {
                stopThinkingAnimation(assistantBubble);
                assistantBubble.textContent = payload && payload.answer ? payload.answer : '';
                assistantBubble.dataset.placeholder = 'false';
                renderInlineReferences(payload && payload.citations ? payload.citations : [], assistantBubble);
                elements.chatInput.disabled = false;
                if (submitButton) {
                    submitButton.disabled = false;
                }
                elements.chatInput.focus();
            })
            .catch(function(err) {
                stopThinkingAnimation(assistantBubble);
                assistantBubble.textContent = 'Request failed';
                setStatus(elements.chatStatus, err && err.message ? err.message : 'Chat failed', '#dc2626');
                elements.chatInput.disabled = false;
                if (submitButton) {
                    submitButton.disabled = false;
                }
                elements.chatInput.focus();
            });
    }

    function bindEvents() {
        if (elements.uploadForm) {
            elements.uploadForm.addEventListener('submit', handleUpload);
        }
        if (elements.scrapeForm) {
            elements.scrapeForm.addEventListener('submit', handleScrape);
        }
        if (elements.syncForm) {
            elements.syncForm.addEventListener('submit', handleMoodleSync);
        }
        if (elements.chatForm) {
            elements.chatForm.addEventListener('submit', handleChat);
        }
        if (elements.chatInput) {
            elements.chatInput.addEventListener('keydown', function(event) {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    if (elements.chatForm) {
                        elements.chatForm.requestSubmit();
                    }
                }
            });
        }
        if (elements.modalClose) {
            elements.modalClose.addEventListener('click', clearPreview);
        }
        if (elements.modalBackdrop) {
            elements.modalBackdrop.addEventListener('click', clearPreview);
        }

        window.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                clearPreview();
            }
        });
    }

    function init(userConfig) {
        config = Object.assign({}, userConfig);

        elements.root = document.querySelector('[data-component="chatlearning"]');
        if (!elements.root) {
            return;
        }

        elements.documentList = elements.root.querySelector('[data-document-list]');
        elements.documentStatus = elements.root.querySelector('[data-document-status]');
        elements.uploadForm = elements.root.querySelector('[data-upload-form]');
        elements.uploadInput = elements.root.querySelector('[data-upload-input]');
        elements.uploadStatus = elements.root.querySelector('[data-upload-status]');
        elements.scrapeForm = elements.root.querySelector('[data-scrape-form]');
        elements.scrapeInput = elements.root.querySelector('[data-scrape-input]');
        elements.scrapeStatus = elements.root.querySelector('[data-scrape-status]');
        elements.syncForm = elements.root.querySelector('[data-sync-form]');
        elements.syncPdf = elements.root.querySelector('[data-sync-pdf]');
        elements.syncScorm = elements.root.querySelector('[data-sync-scorm]');
        elements.syncStatus = elements.root.querySelector('[data-sync-status]');
        elements.chatForm = elements.root.querySelector('[data-chat-form]');
        elements.chatInput = elements.root.querySelector('[data-chat-input]');
        elements.chatLog = elements.root.querySelector('[data-chat-log]');
        elements.chatStatus = elements.root.querySelector('[data-chat-status]');
        elements.modalBackdrop = elements.root.querySelector('[data-modal-backdrop]');
        elements.modalDialog = elements.root.querySelector('[data-modal-dialog]');
        elements.modalClose = elements.root.querySelector('[data-modal-close]');

        if (!config.documentBase) {
            config.documentBase = config.apiBase ? config.apiBase.replace(/\/$/, '') + '/documents/' : '';
        }
        if (!config.uploadEndpoint) {
            config.uploadEndpoint = M.cfg.wwwroot + '/mod/chatlearning/upload.php?cmid=' + config.cmid + '&sesskey=' + encodeURIComponent(config.sesskey);
        }

        bindEvents();

        appendMessage('assistant', 'Hello! Ask me anything about the indexed course documents.');

        Str.get_strings(
            STRING_DEFINITIONS.map(function(def) {
                return {key: def.key, component: def.component};
            })
        )
            .then(function(values) {
                values.forEach(function(value, index) {
                    strings[STRING_DEFINITIONS[index].identifier] = value;
                });
            })
            .finally(fetchDocuments);
    }

    return {init: init};
});
