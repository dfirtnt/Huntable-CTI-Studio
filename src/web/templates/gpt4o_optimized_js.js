// Enhanced GPT4o Ranking Function with Content Filtering
async function rankWithGPT4oOptimized() {
    const articleId = {{ article.id }};
    
    // Get API key from settings
    const settings = JSON.parse(localStorage.getItem('ctiScraperSettings') || '{}');
    const apiKey = settings.openaiApiKey;
    
    if (!apiKey) {
        showNotification('Please configure your OpenAI API key in Settings first', 'error');
        return;
    }
    
    // Show optimization options dialog
    const optimizationOptions = await showOptimizationDialog();
    if (!optimizationOptions) {
        return; // User cancelled
    }
    
    // Estimate cost before proceeding
    const articleContent = `{{ article.content[:1000] }}`; // Get first 1000 chars for estimation
    const estimatedTokens = Math.ceil(articleContent.length / 4); // Rough estimate: 1 token ≈ 4 chars
    const promptTokens = 1508; // Updated prompt length (6,033 chars ≈ 1,508 tokens)
    const totalTokens = estimatedTokens + promptTokens;
    
    // GPT4o pricing: $5.00 per 1M input tokens, $15.00 per 1M output tokens
    const inputCost = (totalTokens / 1000000) * 5.00;
    const outputCost = (2000 / 1000000) * 15.00; // Assume 2000 output tokens
    const totalCost = inputCost + outputCost;
    
    // Estimate cost savings if filtering is enabled
    let costSavings = 0;
    let costMessage = `Estimated cost: $${totalCost.toFixed(4)} (${totalTokens.toLocaleString()} input tokens + ~2,000 output tokens)`;
    
    if (optimizationOptions.useFiltering) {
        // Rough estimate: 20-40% cost reduction based on analysis
        costSavings = totalCost * 0.3; // Assume 30% savings
        const optimizedCost = totalCost - costSavings;
        costMessage = `Estimated cost: $${optimizedCost.toFixed(4)} (with ${(costSavings/totalCost*100).toFixed(0)}% savings from content filtering)`;
    }
    
    const confirmed = confirm(`GPT4o Analysis Cost Estimate:\n\n${costMessage}\n\nOptimization: ${optimizationOptions.useFiltering ? 'Enabled' : 'Disabled'}\nConfidence Threshold: ${optimizationOptions.minConfidence}\n\nDo you want to proceed with the analysis?`);
    if (!confirmed) {
        return;
    }
    
    // Show loading state
    const button = event.target;
    const originalText = button.innerHTML;
    button.innerHTML = '<span class="mr-2">⏳</span>Analyzing...';
    button.disabled = true;
    
    try {
        const response = await fetch(`/api/articles/${articleId}/gpt4o-rank-optimized`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                api_key: apiKey,
                use_filtering: optimizationOptions.useFiltering,
                min_confidence: optimizationOptions.minConfidence
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            displayGPT4oRanking(data.analysis);
            
            // Show optimization results if enabled
            if (data.optimization && data.optimization.enabled) {
                const opt = data.optimization;
                showNotification(
                    `GPT4o analysis completed! Cost savings: $${opt.cost_savings.toFixed(4)} (${opt.tokens_saved.toLocaleString()} tokens saved, ${opt.chunks_removed} chunks removed)`, 
                    'success'
                );
            } else {
                showNotification('GPT4o analysis completed successfully!', 'success');
            }
        } else {
            const error = await response.json();
            showNotification(`GPT4o analysis failed: ${error.detail}`, 'error');
        }
    } catch (error) {
        console.error('GPT4o ranking error:', error);
        showNotification(`GPT4o analysis failed: ${error.message}`, 'error');
    } finally {
        // Restore button state
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

// Show optimization options dialog
async function showOptimizationDialog() {
    return new Promise((resolve) => {
        // Get AI model from settings to determine modal title
        const settings = JSON.parse(localStorage.getItem('ctiScraperSettings') || '{}');
        const aiModel = settings.aiModel || 'chatgpt';
        const modelDisplayName = aiModel === 'chatgpt' ? 'GPT-4o' : 
                                aiModel === 'anthropic' ? 'Claude' : 
                                aiModel === 'tinyllama' ? 'TinyLlama' : 'LLM';
        
        // Create modal dialog
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">${modelDisplayName} Content Filter</h3>
                
                <div class="space-y-4">
                    <div class="flex items-center">
                        <input type="checkbox" id="useFiltering" checked class="mr-3">
                        <label for="useFiltering" class="text-sm text-gray-700">
                            Enable content filtering to reduce costs
                        </label>
                    </div>
                    
                    <div id="confidenceSection" class="ml-6">
                        <label for="minConfidence" class="block text-sm text-gray-700 mb-2">
                            Confidence threshold:
                        </label>
                        <select id="minConfidence" class="w-full border border-gray-300 rounded px-3 py-2">
                            <option value="0.5">0.5 - Aggressive filtering (more cost savings)</option>
                            <option value="0.7" selected>0.7 - Balanced filtering</option>
                            <option value="0.8">0.8 - Conservative filtering (less cost savings)</option>
                        </select>
                        <p class="text-xs text-gray-500 mt-1">
                            Higher values keep more content but reduce cost savings
                        </p>
                    </div>
                    
                    <div class="bg-blue-50 p-3 rounded">
                        <h4 class="text-sm font-medium text-blue-900 mb-2">How it works:</h4>
                        <ul class="text-xs text-blue-800 space-y-1">
                            <li>• Analyzes content chunks for huntability</li>
                            <li>• Removes acknowledgments, marketing content</li>
                            <li>• Keeps technical details, commands, IOCs</li>
                            <li>• Typically saves 20-40% on costs</li>
                        </ul>
                    </div>
                </div>
                
                <div class="flex justify-end space-x-3 mt-6">
                    <button id="cancelBtn" class="px-4 py-2 text-gray-600 hover:text-gray-800">
                        Cancel
                    </button>
                    <button id="confirmBtn" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        Analyze
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close modal when clicking outside
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                document.body.removeChild(modal);
                document.removeEventListener('keydown', handleEscape);
                resolve(null);
            }
        });
        
        // Handle checkbox change
        const useFilteringCheckbox = modal.querySelector('#useFiltering');
        const confidenceSection = modal.querySelector('#confidenceSection');
        
        useFilteringCheckbox.addEventListener('change', (e) => {
            confidenceSection.style.display = e.target.checked ? 'block' : 'none';
        });
        
        // Handle button clicks
        modal.querySelector('#cancelBtn').addEventListener('click', () => {
            document.body.removeChild(modal);
            document.removeEventListener('keydown', handleEscape);
            resolve(null);
        });
        
        modal.querySelector('#confirmBtn').addEventListener('click', () => {
            const useFiltering = useFilteringCheckbox.checked;
            const minConfidence = parseFloat(modal.querySelector('#minConfidence').value);
            
            document.body.removeChild(modal);
            document.removeEventListener('keydown', handleEscape);
            resolve({
                useFiltering,
                minConfidence
            });
        });
        
        // Handle escape key
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                document.body.removeChild(modal);
                document.removeEventListener('keydown', handleEscape);
                resolve(null);
            }
        };
        document.addEventListener('keydown', handleEscape);
    });
}
