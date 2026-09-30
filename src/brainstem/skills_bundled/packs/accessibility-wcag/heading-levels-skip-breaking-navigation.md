---
name: heading-levels-skip-breaking-navigation
description: Fix a page's heading structure that skips levels or uses headings out of order, breaking screen reader document navigation.
triggers: ["heading levels skip screen reader", "h1 to h3 no h2", "heading structure audit failure", "screen reader headings list confusing", "wrong heading order accessibility"]
permissions: ["READ"]
---

## Symptom
A screen reader user pulls up the page's heading list (a standard
navigation shortcut, e.g. NVDA/JAWS's "H" key or VoiceOver's rotor) to
get a quick outline of the page and jump to a section, and finds the
hierarchy doesn't make sense: an `<h1>` followed directly by `<h3>`s
with no `<h2>` in between, or heading levels that go up and down
inconsistently between sections that are visually parallel. This
doesn't affect sighted users at all if headings are styled by custom
classes rather than by their semantic level, which is exactly why it
goes unnoticed in visual QA.

## Likely causes
1. **Heading tags were chosen for their default visual size/weight
   rather than their semantic position in the outline** -- a developer
   picks `<h3>` because it "looks right" at that font size in that
   spot, independent of whether an `<h2>` exists above it in the
   document structure.
2. **A reusable component (a card, a widget, a sidebar module) hard-
   codes its internal heading level** (e.g. always renders its title as
   `<h3>`) and gets dropped into different pages/contexts where the
   surrounding heading level varies, so the same component produces a
   correct hierarchy on one page and a skipped one on another.
3. **CMS-authored content lets editors pick heading levels freely in a
   rich text field**, and editors choose based on visual appearance in
   the WYSIWYG rather than any awareness of document structure, often
   skipping straight to smaller heading sizes for "not too big" text
   that isn't actually a subheading of the item above it.
4. **A page was assembled from sections originally designed as
   independent documents** (each with its own `<h1>`/`<h2>` internally)
   and concatenated without renumbering the heading levels to nest
   correctly under the page's actual top-level heading.

## Diagnose
- Use the browser's accessibility tree inspector, or a dedicated
  heading-outline tool (e.g. the HeadingsMap browser extension, or a
  screen reader's own heading list), to list every heading on the page
  in document order along with its level -- skips are immediately
  visible as a gap in the sequence (h1, h3 with no h2).
- Run axe DevTools or Lighthouse's accessibility audit, which flags
  "Heading levels should only increase by one."
- For component-driven skips, check whether the same component (a
  card/widget) renders a different-looking heading level depending on
  what page it's embedded in, by comparing its rendered tag across two
  different pages.
- Distinguish a true structural skip from acceptable level *repetition*
  (e.g. several `<h2>`s in a row for sibling sections) -- repetition at
  the same level is fine; only jumps that increase by more than one are
  the violation.

## Fix
Decouple heading level from visual styling: choose each heading's HTML
tag based on its actual position in the document's logical outline
(each level nests one deeper than its parent section, never skipping),
and apply font size/weight via CSS classes independent of the tag, so
an `<h2>` can be styled small in one context and an `<h3>` styled large
in another without either misrepresenting the structure. For reusable
components, make the heading level a prop/parameter the parent page
sets explicitly (e.g. `<SectionTitle level={3}>`) rather than hard-
coding a tag inside the component, since the correct level genuinely
depends on where the component is used. For CMS-authored content,
constrain the rich-text editor's heading options to the levels valid at
that content's position (or provide editorial guidance and a
structure-validation step) rather than leaving full h1-h6 choice
available regardless of context.

## Pitfalls
- "Fixing" the skip by just renumbering the skipped heading to the
  correct level without checking whether its new font-size styling
  (tied to the tag rather than a class) now looks visually wrong
  reintroduces the original visual-driven-tag-choice problem in
  reverse -- decouple style from tag as part of the fix, not just the
  number.
- Flattening everything to `<h2>` to "avoid the skip problem entirely"
  removes the actual semantic nesting screen reader users rely on to
  understand which sections are subsections of others -- the fix is
  correct nesting, not eliminating levels.
- Fixing heading levels on one page without checking the shared
  component elsewhere just reintroduces the same skip on every other
  page that embeds that component at a different nesting depth.

## Verify
Generate a heading outline for the page (via a headings-map tool,
browser accessibility tree, or screen reader heading list) and confirm
every level-to-level transition increases by at most one, with a single
`<h1>` per page and each subsection nested one level deeper than its
parent.
