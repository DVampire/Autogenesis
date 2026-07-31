---
name: theme_factory_skill
description: "Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifact that has been creating, or can generate a new theme on-the-fly."
version: "1.0.0"
type: worker
license: "Complete terms in LICENSE.txt"
category: design
requirements: [cpu]
metadata: {}
---
# Theme Factory Skill

This skill provides a curated collection of professional font and color themes themes, each with carefully selected color palettes and font pairings. Once a theme is chosen, it can be applied to any artifact.

## Purpose

To apply consistent, professional styling to presentation slide decks, use this skill. Each theme includes:
- A cohesive color palette with hex codes
- Complementary font pairings for headers and body text
- A distinct visual identity suitable for different contexts and audiences

## Usage Instructions

To apply styling to a slide deck, report, doc, or other artifact:

1. **Choose a theme**: If the task names a theme or states a mood/audience, pick the matching one from the list below; otherwise select the theme whose palette and typography best fit the artifact's subject and audience. `resources/theme-showcase.pdf` shows all themes visually — read it if you need to compare. (If a human is in the loop and the choice is unclear, show the showcase and ask.)
2. **Read the theme spec**: Load the chosen theme's file from `resources/themes/`.
3. **Apply the theme**: Apply its colors and fonts consistently across the whole artifact, keeping contrast and readability sound.

## Themes Available

The following 10 themes are available, each showcased in `resources/theme-showcase.pdf`:

1. **Ocean Depths** - Professional and calming maritime theme
2. **Sunset Boulevard** - Warm and vibrant sunset colors
3. **Forest Canopy** - Natural and grounded earth tones
4. **Modern Minimalist** - Clean and contemporary grayscale
5. **Golden Hour** - Rich and warm autumnal palette
6. **Arctic Frost** - Cool and crisp winter-inspired theme
7. **Desert Rose** - Soft and sophisticated dusty tones
8. **Tech Innovation** - Bold and modern tech aesthetic
9. **Botanical Garden** - Fresh and organic garden colors
10. **Midnight Galaxy** - Dramatic and cosmic deep tones

## Theme Details

Each theme is defined in the `resources/themes/` directory with complete specifications including:
- Cohesive color palette with hex codes
- Complementary font pairings for headers and body text
- Distinct visual identity suitable for different contexts and audiences

## Application Process

After a preferred theme is selected:
1. Read the corresponding theme file from the `resources/themes/` directory
2. Apply the specified colors and fonts consistently throughout the deck
3. Ensure proper contrast and readability
4. Maintain the theme's visual identity across all slides

## Create your Own Theme
To handle cases where none of the existing themes fit an artifact, create a custom theme. Based on the task's inputs, generate a new theme spec (palette + font pairing) in the same format as the ones in `resources/themes/`, and give it a descriptive name. Write it out, then apply it as described above. (If a human is in the loop, show the generated theme for review before applying.)
