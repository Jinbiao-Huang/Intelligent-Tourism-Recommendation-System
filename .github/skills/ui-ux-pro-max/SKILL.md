---
name: ui-ux-pro-max
description: "Auto-load this skill for UI/UX tasks: redesign, visual polish, login page, home page, dashboard, landing page, color palette, typography, interaction, animation, usability, accessibility, or requests mentioning ui-ux-pro-max. Also applies to Chinese requests like 页面设计, 美化, 改版, 登录页, 主页面, 毕设页面优化."
---

# UI UX Pro Max Skill

Use this workflow when the user asks for UI UX design or front-end visual improvements.

## Prerequisites

Check Python:

```bash
python3 --version || python --version
```

If Python is missing:

- macOS: `brew install python3`
- Ubuntu or Debian: `sudo apt update && sudo apt install python3`
- Windows: `winget install Python.Python.3.12`

## Required Workflow

### 1. Analyze request

Extract:

- Product type
- Industry
- Style keywords
- Target stack

For this repository, default stack should be `vue` unless user specifies another stack.

### 2. Generate design system first (required)

Always run this command first:

```bash
python .github/prompts/ui-ux-pro-max/scripts/search.py "<product_type industry keywords>" --design-system -p "<Project Name>"
```

Optional persistence:

```bash
python .github/prompts/ui-ux-pro-max/scripts/search.py "<query>" --design-system --persist -p "<Project Name>" --page "<page_name>"
```

### 3. Run targeted supplemental searches when needed

```bash
python .github/prompts/ui-ux-pro-max/scripts/search.py "<keyword>" --domain <domain> -n <max_results>
```

Domains: `product`, `style`, `color`, `typography`, `landing`, `chart`, `ux`, `react`, `web`, `icons`.

### 4. Run stack guidance

```bash
python .github/prompts/ui-ux-pro-max/scripts/search.py "<keyword>" --stack vue
```

Available stacks include: `html-tailwind`, `react`, `nextjs`, `vue`, `svelte`, `swiftui`, `react-native`, `flutter`, `shadcn`, `jetpack-compose`.

## Output behavior

- Synthesize recommendations into an implementable design direction.
- Keep visual system consistent: colors, typography, spacing, component states.
- Include accessibility and mobile adaptation by default.
- Prefer concrete code changes over abstract suggestions when user asks to implement.

## Notes

- Data and scripts are currently located at:
  - `.github/prompts/ui-ux-pro-max/data`
  - `.github/prompts/ui-ux-pro-max/scripts`
- This skill intentionally references those paths to avoid breaking your existing setup.
