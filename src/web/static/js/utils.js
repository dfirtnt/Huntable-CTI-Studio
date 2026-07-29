/**
 * Shared front-end utilities.
 *
 * Loaded from base.html for every page, so these are plain globals rather
 * than module exports -- inline template scripts call them unqualified.
 *
 * Before this file, escapeHtml was redefined in seven templates in three
 * mutually incompatible variants. Two of them (the createElement/textContent
 * trick, and a manual replace of only & < >) do not escape quote characters,
 * yet article_detail.html, agent_evals.html and workflow.html interpolate
 * escapeHtml output directly into HTML attributes -- so a value containing a
 * double quote escaped its attribute. The canonical version below escapes
 * quotes too, making it safe in both text and attribute position.
 */

(function (global) {
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

    global.escapeHtml = escapeHtml;
    global.formatTimestamp = formatTimestamp;
})(window);
