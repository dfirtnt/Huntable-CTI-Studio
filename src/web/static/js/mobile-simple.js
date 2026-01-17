/**
 * Simple Mobile Enhancement for Existing Annotation System
 * 
 * Adds mobile-friendly features to the working SimpleTextManager
 */

document.addEventListener('DOMContentLoaded', function() {
    // Wait for SimpleTextManager to be initialized
    setTimeout(() => {
        if (window.simpleTextManager) {
            console.log('📱 Adding mobile enhancements to existing annotation system');
            addMobileEnhancements();
        }
    }, 1000);
});

function addMobileEnhancements() {
    const contentElement = document.getElementById('article-content');
    if (!contentElement) return;
    
    // Add mobile-specific CSS
    if (!document.getElementById('mobile-enhancement-styles')) {
        const styles = document.createElement('style');
        styles.id = 'mobile-enhancement-styles';
        styles.textContent = `
            @media (max-width: 768px) {
                /* Make annotation modal mobile-friendly */
                .fixed.inset-0 {
                    padding: 1rem;
                }
                
                .bg-white.rounded-lg.shadow-xl {
                    max-width: 95vw;
                    max-height: 90vh;
                    overflow-y: auto;
                }
                
                /* Make expand buttons touch-friendly */
                .expand-controls button {
                    min-height: 44px;
                    font-size: 16px;
                    padding: 8px 12px;
                }
                
                /* Make classification buttons larger */
                .bg-green-600, .bg-red-600 {
                    min-height: 48px;
                    font-size: 18px;
                    font-weight: 600;
                }
            }
        `;
        document.head.appendChild(styles);
    }
    
    console.log('✅ Mobile enhancements added to existing system');
}
