# Web Frontend

Astro-based frontend for the ticket assignment system.

## Overview

Static site with interactive components for:
- Viewing ticket assignments and predictions
- Engineer profile management
- Model performance dashboards

## Structure

```
src/
├── components/        # Reusable Astro components
├── layouts/           # Page layout templates
├── pages/             # Route-based pages (index.astro, etc.)
└── styles/            # Global CSS and theme
```

**Framework:** Astro with TypeScript. Static generation with optional client-side hydration for interactive components.

## Commands

All commands are run from the root of the project, from a terminal:

| Command                   | Action                                           |
| :------------------------ | :----------------------------------------------- |
| `npm install`             | Installs dependencies                            |
| `npm run dev`             | Starts local dev server at `localhost:4321`      |
| `npm run build`           | Build your production site to `./dist/`          |
| `npm run preview`         | Preview your build locally, before deploying     |
| `npm run astro ...`       | Run CLI commands like `astro add`, `astro check` |
| `npm run astro -- --help` | Get help using the Astro CLI                     |

## Learn More

Feel free to check [Astro documentation](https://docs.astro.build) or jump into the [Discord server](https://astro.build/chat).
