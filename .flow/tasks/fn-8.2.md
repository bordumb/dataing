# fn-8.2 Create custom CSS stylesheet for enterprise polish

## Description

Create custom CSS to give the documentation an enterprise polish, similar to Stripe or Auth0 docs.

### Create File

`docs/docs/stylesheets/extra.css`

### CSS Requirements

1. **Color Scheme (CSS Variables):**
   ```css
   :root {
     --md-primary-fg-color: #0A2540;      /* Deep navy */
     --md-accent-fg-color: #635BFF;       /* Electric purple */
   }
   [data-md-color-scheme="slate"] {
     --md-primary-fg-color: #635BFF;
     --md-default-bg-color: #0A1628;
   }
   ```

2. **Typography:**
   - Tighter letter-spacing on headings (-0.02em)
   - Proper line-height (1.7)
   - h2 with subtle bottom border

3. **Admonitions:**
   - Rounded corners (8px)
   - Softer colors
   - Thinner left border (4px)

4. **Code Blocks:**
   - Rounded corners (8px)
   - Slightly smaller font (0.8rem)

5. **Navigation:**
   - Smaller nav link font (0.75rem)
   - Normal-case tab labels

6. **Header:**
   - Backdrop blur effect
   - Semi-transparent background

### References

- Material CSS vars: https://squidfunk.github.io/mkdocs-material/customization/
## Acceptance
- [ ] File exists at `docs/docs/stylesheets/extra.css`
- [ ] CSS loads without errors in browser console
- [ ] Primary color is deep navy (#0A2540) in light mode
- [ ] Dark mode uses slate theme with custom background
- [ ] Admonitions have rounded corners
- [ ] Code blocks have rounded corners
- [ ] Header has backdrop blur on scroll
- [ ] Typography appears tighter/more refined than default Material
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
