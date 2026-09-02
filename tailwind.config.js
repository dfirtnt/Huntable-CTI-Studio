/**
 * Tailwind build config for Huntable CTI Studio.
 *
 * Replaces the runtime CDN script that base.html used to load. The CDN generated
 * every utility class in the browser on each page load, so nothing had to be
 * declared -- a local build only emits classes it can FIND as literal strings,
 * which makes `content` and `safelist` below load-bearing for correctness.
 *
 * Regenerate with `make css` after changing templates, static JS, or any Python
 * module that carries class strings.
 */
module.exports = {
  // Class-based dark mode. This is the sole setting the old inline
  // `tailwind.config = { darkMode: 'class' }` block in base.html carried;
  // the `dark:` variants are used throughout and the app is dark-by-default.
  darkMode: 'class',

  content: [
    './src/web/templates/**/*.html',
    './src/web/static/js/**/*.js',
    // Not a default-shaped glob, and omitting it is a silent styling break:
    // src/utils/keyword_resolution.py holds ~57 Tailwind class strings on the
    // KEYWORD_CATEGORY_METADATA entries (card/heading/badge/chip/legend/highlight),
    // which reach the DOM through render_highlighted_content and the keyword
    // panel. Several of those colours appear in no template or JS file at all,
    // so a JIT scan without this glob purges them and the keyword highlights
    // lose their backgrounds -- while every existing test still passes, because
    // the tests assert on class ATTRIBUTES in rendered HTML, not on the CSS.
    './src/**/*.py',
  ],

  safelist: [
    // Four sites assemble class names from a colour FRAGMENT, so the full class
    // name never appears literally anywhere and the scanner cannot see it:
    //   article_detail.html:7616-7617      text-${statusColor}-600, bg-${statusColor}-100
    //   sigma_similarity_test.html:302-303 text/bg-${statusColor}-{600,400,100,900}
    // Both statusColor values come from closed ternary/if chains -- article_detail
    // yields green|yellow|purple, sigma_similarity_test yields blue|green|yellow --
    // so this pattern is exhaustive rather than precautionary. Sites that
    // interpolate a COMPLETE class string (jobs.html, agent_evals.html) need no
    // safelist: the literal is present in the scanned file.
    {
      pattern: /^(text|bg)-(blue|green|yellow|purple)-(100|400|600|900)$/,
      variants: ['dark'],
    },
  ],

  theme: {
    extend: {},
  },

  // Deliberately no plugins. `prose` classes appear in ~10 templates but are
  // inert today -- no typography plugin was loaded by the CDN build and no
  // .prose rules exist in theme-variables.css. Adding @tailwindcss/typography
  // here would newly apply styling that has never been applied, changing the
  // rendering of pages this task is not meant to touch.
  plugins: [],
}
