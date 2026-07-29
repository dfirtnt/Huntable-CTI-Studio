/**
 * Shared front-end utilities.
 *
 * Loaded from base.html for every page, so these are attached as globals --
 * inline template scripts call them unqualified. Also exported via
 * module.exports so Node-based tests (and components/similarity-display.js
 * when required in Node) can reach the same single implementation.
 *
 * Before this file, escapeHtml was redefined in seven templates plus
 * similarity-display.js in three mutually incompatible variants. Two of them
 * (the createElement/textContent trick, and a manual replace of only & < >)
 * do not escape quote characters, yet article_detail.html, agent_evals.html,
 * workflow.html and similarity-display.js interpolate escapeHtml output
 * directly into HTML attributes -- so a value containing a double quote
 * escaped its attribute. The canonical version below escapes quotes too,
 * making it safe in both text and attribute position.
 */

(function (root, factory) {
    'use strict';

    var api = factory();

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.escapeHtml = api.escapeHtml;
        root.formatTimestamp = api.formatTimestamp;
    }
})(typeof window !== 'undefined' ? window : null, function () {
    'use strict';

    var HTML_ESCAPES = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    };

    /**
     * Escape a value for interpolation into HTML text OR an HTML attribute.
     *
     * null and undefined become the empty string; every other value is
     * stringified, so escapeHtml(0) is "0" rather than "".
     */
    function escapeHtml(value) {
        if (value === null || value === undefined) {
            return '';
        }
        return String(value).replace(/[&<>"']/g, function (char) {
            return HTML_ESCAPES[char];
        });
    }

    /**
     * Render a timestamp as a full locale string. Moved from diags.html.
     *
     * base.html also carried a formatDate() helper alongside it; that one had
     * zero callers anywhere in the templates or static JS and was deleted
     * rather than relocated here.
     */
    function formatTimestamp(ts) {
        return new Date(ts).toLocaleString();
    }

    return {
        escapeHtml: escapeHtml,
        formatTimestamp: formatTimestamp
    };
});
