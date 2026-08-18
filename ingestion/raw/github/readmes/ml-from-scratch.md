# ML from Scratch

> Learn machine learning by building it — derivation-first, browser-native, no hand-waving.

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript)](https://typescriptlang.org)
---

<!-- Replace with a real screen recording once deployed -->
<!-- ![ML from Scratch — demo](docs/demo.gif) -->

**14 sections · 75 lessons · 168+ interactive widgets**

Every lesson starts with the math, shows you the NumPy implementation, then hands you the PyTorch shortcut — and a live widget so you can poke the idea until it breaks. No black boxes. No "trust the framework." Just derivations, code, and a gradient checker that tells you when you're wrong.

---

## Contents

- [Live Demo](#live-demo)
- [Curriculum](#curriculum)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Adding a Lesson](#adding-a-lesson)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Live Demo

→ **[ml.harshithvarma.in](https://ml.harshithvarma.in)**

![ML from Scratch — Launch Video](docs/launch.gif)

---

## Curriculum

| # | Section | Lessons | Difficulty |
|---|---------|---------|------------|
| 01 | **Math Foundations** | 6 | Easy – Medium |
| 02 | **Build a Neural Net** | 6 | Easy – Hard |
| 03 | **PyTorch** | 4 | Easy – Medium |
| 04 | **Training** | 4 | Easy – Medium |
| 05 | **CNNs & Vision** | 6 | Medium – Hard |
| 06 | **RNN & LSTM** | 5 | Medium – Hard |
| 07 | **NLP** | 4 | Easy – Hard |
| 08 | **Attention & Transformers** | 3 | Hard |
| 09 | **Build GPT** | 10 | Medium – Hard |
| 10 | **Fine-Tuning & RLHF** | 6 | Medium – Hard |
| 11 | **Mixture of Experts** | 4 | Medium – Hard |
| 12 | **Diffusion Models** | 6 | Easy – Hard |
| 13 | **Reinforcement Learning** | 6 | Medium – Hard |
| 14 | **Inference & Serving** | 5 | Medium – Hard |

Each section has a dedicated landing page at `/learn/[section]` with a visual lesson grid, difficulty breakdown, and progress tracking (stored locally).

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Framework | [Next.js 14](https://nextjs.org) App Router | SSR lesson content, static section pages, dynamic OG images |
| Language | TypeScript 5 | Full-stack type safety — lesson registry, roadmap schema, widget props |
| Styling | [Tailwind CSS 3](https://tailwindcss.com) | Terminal-dark design system with per-section accent tokens |
| Syntax highlighting | [Shiki 4](https://shiki.style) | SSR-precomputed, zero client JS for static code blocks |
| In-browser Python | [Pyodide 0.26](https://pyodide.org) | Runs NumPy in the browser — powers the gradient checker and runnable code blocks |
| 3D widgets | [React Three Fiber](https://docs.pmnd.rs/react-three-fiber) + [Drei](https://github.com/pmndrs/drei) | Visualization widgets (convolution, weight init) |
| Icons | [Lucide React](https://lucide.dev) | Consistent icon set throughout |
| Deployment | [Vercel](https://vercel.com) | Zero-config Next.js hosting |

---

## Getting Started

### Prerequisites

- Node.js ≥ 18
- npm ≥ 9

### Run locally

```bash
git clone https://github.com/YOUR_USERNAME/ml-from-scratch.git
cd ml-from-scratch
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Build for production

```bash
npm run build
npm run start
```

### Type-check

```bash
npx tsc --noEmit
```

---

## Project Structure

```
ml-from-scratch/
├── app/
│   ├── page.tsx                      # Home — 14-card section grid
│   ├── learn/
│   │   ├── [section]/
│   │   │   ├── page.tsx              # Section landing (/learn/math-foundations)
│   │   │   └── [lesson]/
│   │   │       └── page.tsx          # Lesson page (/learn/math-foundations/gradient-descent)
│   └── layout.tsx
│
├── components/
│   ├── home/
│   │   ├── Hero.tsx
│   │   └── SectionCard.tsx           # Topic card on home page
│   ├── section/
│   │   ├── SectionLanding.tsx        # Section landing page layout
│   │   └── SectionPreviewGrid.tsx    # 2-col lesson grid on section page
│   ├── lesson/
│   │   ├── LessonShell.tsx           # Sidebar + content shell
│   │   └── content/
│   │       ├── registry.ts           # Maps 'section/lesson' → Component
│   │       ├── primitives.tsx        # Prose, Callout, Bridge, Gotcha, Challenge, ...
│   │       ├── MathBlock.tsx         # Monospace math display
│   │       ├── CodeBlock.tsx         # Shiki-highlighted code, optional runnable
│   │       ├── LayeredCode.tsx       # Tabbed Pure Python / NumPy / PyTorch
│   │       ├── References.tsx        # Formatted reference list
│   │       ├── lessons/              # 75 lesson components (one file per lesson)
│   │       └── widgets/              # 168+ interactive widget components
│   └── ui/                           # Shared: DifficultyPill, StatusDot, SectionIcon, ...
│
└── lib/
    ├── roadmap.ts                    # Single source of truth — all sections/lessons
    ├── utils.ts                      # cn(), lessonHref(), sectionHref()
    └── pyodide.ts                    # Pyodide loader — shared across runnable widgets
```

### Key files

| File | Role |
|------|------|
| `lib/roadmap.ts` | Add/reorder sections and lessons here. Every page and nav element derives from this. |
| `components/lesson/content/registry.ts` | Register a new lesson component here after creating the file. |
| `components/lesson/content/primitives.tsx` | All lesson layout primitives — `Prose`, `Callout`, `Bridge`, `Gotcha`, `Challenge`, `Personify`, `KeyTerm`, `Eq`, `EqRef`. |

---

## Adding a Lesson

> Full guide in [CONTRIBUTING.md](CONTRIBUTING.md). Quick version:

**1. Add the lesson to `lib/roadmap.ts`**

```ts
// inside the correct section's `lessons: [...]` array
{
  slug: 'my-new-lesson',
  title: 'My New Lesson',
  difficulty: 'Medium',
  blurb: 'One sentence that tells someone whether they need this.',
  prerequisites: ['gradient-descent'],
  enables: ['backpropagation'],
},
```

**2. Create `components/lesson/content/lessons/my-new-lesson.tsx`**

```tsx
import { Prose, Callout, Challenge, KeyTerm } from '../primitives'
import MathBlock from '../MathBlock'

export default function MyNewLesson() {
  return (
    <div className="space-y-6">
      <Prose>
        <p>Start with the intuition. What problem does this solve?</p>
      </Prose>
      {/* ... */}
    </div>
  )
}
```

**3. Register it in `components/lesson/content/registry.ts`**

```ts
import MyNewLesson from './lessons/my-new-lesson'

// inside the REGISTRY object:
'section-slug/my-new-lesson': { Component: MyNewLesson },
```

**4. Run `npx tsc --noEmit` — zero errors, you're done.**

---

## Contributing

We welcome contributions of all sizes — fixing a typo in a derivation is as valuable as adding a full lesson.

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for:
- Lesson writing style guide (voice, structure, three-layer code pattern)
- How to build a widget (Pyodide, SVG, React Three Fiber)
- PR checklist
- Good first issues

---

## License

[MIT](LICENSE) © 2026 Nai Harshith Varma

---

## Acknowledgements

- **[Andrej Karpathy](https://karpathy.ai)** — Neural Networks: Zero to Hero. The "Backprop Ninja" lesson is a direct homage to his lecture 4 exercise.
- **[d2l.ai](https://d2l.ai)** — Dive into Deep Learning. Inspiration for numbered equations and the derivation-first pedagogy.
- **[CS231n](https://cs231n.github.io)** — Stanford's original course notes. Referenced throughout the CNN and backprop sections.
- **[Distill.pub](https://distill.pub)** — The gold standard for interactive ML writing.
- **[fast.ai](https://fast.ai)** — Proof that top-down and bottom-up both work, and that learners deserve real code.
