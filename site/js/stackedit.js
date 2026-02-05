// StackEdit integration for MkDocs
(function() {
  'use strict';

  // Configuration
  const GITHUB_REPO = 'dfirtnt/Huntable-CTI-Studio';
  const GITHUB_BRANCH = 'main';
  const STACKEDIT_URL = 'https://stackedit.io';

  // Get current page file path
  function getCurrentFilePath() {
    // Try to get from MkDocs meta tag first
    const metaEdit = document.querySelector('meta[name="edit-uri"]');
    if (metaEdit && metaEdit.content) {
      // edit-uri format: "edit/main/docs/path/to/file.md"
      const editPath = metaEdit.content.replace(/^edit\/[^/]+\//, '');
      return editPath;
    }
    
    // Fallback: construct from current URL
    const path = window.location.pathname;
    if (path === '/' || path === '/index.html' || path === '') {
      return 'docs/index.md';
    }
    
    // Remove leading slash and .html extension, add .md
    let filePath = path.replace(/^\//, '').replace(/\.html$/, '');
    if (!filePath.endsWith('.md')) {
      filePath += '.md';
    }
    
    // Ensure it starts with docs/
    if (!filePath.startsWith('docs/')) {
      filePath = 'docs/' + filePath;
    }
    
    return filePath;
  }

  // Create StackEdit button with modal
  function createStackEditButton() {
    const filePath = getCurrentFilePath();
    const githubFileUrl = `https://github.com/${GITHUB_REPO}/blob/${GITHUB_BRANCH}/${filePath}`;
    const githubEditUrl = `https://github.com/${GITHUB_REPO}/edit/${GITHUB_BRANCH}/${filePath}`;

    // Create button element
    const button = document.createElement('button');
    button.className = 'md-source__fact md-source__fact--edit stackedit-button';
    button.title = 'Edit with StackEdit';
    button.setAttribute('aria-label', 'Edit with StackEdit');
    button.style.cssText = 'cursor: pointer; border: none; background: transparent; color: inherit;';
    
    // Add icon
    button.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" style="vertical-align: middle;">
        <path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
      </svg>
      <span class="md-source__fact-label">Edit</span>
    `;

    // Create modal
    const modal = document.createElement('div');
    modal.className = 'stackedit-modal';
    modal.style.cssText = `
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.5);
      z-index: 10000;
      align-items: center;
      justify-content: center;
    `;

    const modalContent = document.createElement('div');
    modalContent.style.cssText = `
      background: white;
      padding: 2rem;
      border-radius: 8px;
      max-width: 600px;
      margin: 1rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    `;

    modalContent.innerHTML = `
      <h2 style="margin-top: 0;">Edit with StackEdit</h2>
      <p>To edit this file with StackEdit:</p>
      <ol>
        <li>Click the button below to open StackEdit</li>
        <li>In StackEdit, click the <strong>📁</strong> icon (Synchronize)</li>
        <li>Select <strong>GitHub</strong> and authorize</li>
        <li>Navigate to: <code>${filePath}</code></li>
        <li>Edit and save - changes will sync to GitHub</li>
      </ol>
      <div style="margin-top: 1.5rem; display: flex; gap: 0.5rem;">
        <a href="${STACKEDIT_URL}" target="_blank" rel="noopener" 
           style="flex: 1; padding: 0.75rem; background: #1976d2; color: white; text-align: center; text-decoration: none; border-radius: 4px;">
          Open StackEdit
        </a>
        <a href="${githubEditUrl}" target="_blank" rel="noopener"
           style="flex: 1; padding: 0.75rem; background: #f5f5f5; color: #333; text-align: center; text-decoration: none; border-radius: 4px;">
          Edit on GitHub
        </a>
        <button class="close-modal" style="padding: 0.75rem 1.5rem; background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; cursor: pointer;">
          Close
        </button>
      </div>
      <p style="margin-top: 1rem; font-size: 0.875rem; color: #666;">
        <strong>File path:</strong> <code>${filePath}</code>
      </p>
    `;

    modal.appendChild(modalContent);
    document.body.appendChild(modal);

    // Button click handler
    button.addEventListener('click', function(e) {
      e.preventDefault();
      modal.style.display = 'flex';
    });

    // Close modal handlers
    const closeModal = function() {
      modal.style.display = 'none';
    };
    
    modal.addEventListener('click', function(e) {
      if (e.target === modal) {
        closeModal();
      }
    });
    
    modalContent.querySelector('.close-modal').addEventListener('click', closeModal);

    // Add button to page
    // Try to add to header first
    const header = document.querySelector('.md-header__inner');
    if (header) {
      let sourceFacts = header.querySelector('.md-source__facts');
      if (!sourceFacts) {
        sourceFacts = document.createElement('div');
        sourceFacts.className = 'md-source__facts';
        let source = header.querySelector('.md-source');
        if (!source) {
          source = document.createElement('div');
          source.className = 'md-source';
          header.appendChild(source);
        }
        source.appendChild(sourceFacts);
      }
      sourceFacts.appendChild(button);
    } else {
      // Fallback: add floating button
      const wrapper = document.createElement('div');
      wrapper.style.cssText = 'position: fixed; top: 1rem; right: 1rem; z-index: 999;';
      wrapper.appendChild(button);
      document.body.appendChild(wrapper);
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createStackEditButton);
  } else {
    createStackEditButton();
  }
})();
