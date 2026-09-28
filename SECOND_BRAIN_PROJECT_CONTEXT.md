# SECOND BRAIN --- COMPLETE PROJECT CONTEXT

## 1. Purpose

This document gives Claude the working context for the SecondBrain
project.

Use this together with: - the complete SecondBrain project files/ZIP -
six Stitch UI reference images - any current UI screenshots

Do not blindly trust this document. Verify it against the actual source
code. If this document and the repository disagree, trust the repository
and tell me about the discrepancy.

------------------------------------------------------------------------

## 2. Product Overview

**SecondBrain** is an AI-powered personal knowledge and study platform.

The core idea is to give a user a personal "second brain" where they
can: - save learning materials - upload documents - search saved
knowledge - ask questions about saved material - receive AI-assisted
answers - see source documents behind answers - browse saved documents
through a Library - eventually organize knowledge into subjects/folders
and support additional content sources

The product should feel like a real, polished SaaS product rather than a
generic student dashboard or generic ChatGPT clone.

------------------------------------------------------------------------

## 3. Product Philosophy

The core experience is:

1.  Save knowledge.
2.  Ask questions about it.
3.  Understand faster.
4.  Return to saved knowledge through the Library.

The product should communicate: - personal knowledge - intelligence -
focus - simplicity - trust - organization - premium SaaS quality

Avoid unnecessary complexity.

------------------------------------------------------------------------

## 4. Technology Stack

### Frontend

-   React
-   Vite
-   TypeScript
-   Tailwind CSS v4
-   react-router-dom

### Backend

-   Python
-   FastAPI

### AI / Knowledge Pipeline

The backend includes functionality related to: - document processing -
text extraction - embeddings - vector search - cosine similarity -
database chunks - RAG - AI generation - OpenRouter-based AI generation

Known backend service areas: - `services/ai` - `services/docx` -
`services/graph` - `services/ocr` - `services/pdf` - `services/ppt` -
`services/rag` - `services/youtube`

Inspect the actual repository rather than assuming these are exhaustive.

------------------------------------------------------------------------

## 5. Project Structure

Approximate structure:

``` text
SecondBrain/
├── backend/
└── frontend/
```

Known frontend concepts/components include: - `AppLayout.tsx` -
`Sidebar.tsx` - `HeroSection.tsx` - `HomePage.tsx` - `LibraryPage.tsx` -
`ChatPage.tsx` - reusable UI components - `frontend/src/api/client.ts` -
`frontend/src/types/index.ts` - `frontend/src/styles/design-tokens.css`

Inspect the repository for the complete structure.

------------------------------------------------------------------------

## 6. Confirmed Backend API Contract

Do not invent API endpoints.

### PDF Upload

`POST /api/v1/upload/pdf`

Current confirmed behavior: - accepts PDF uploads - maximum file size is
20 MB - uploaded files use UUID-based filenames - files are saved under
`uploads/` - PDF text extraction uses PyMuPDF - PDF service includes
`app.services.pdf.pdf_service.PDFService.extract_text` - response
includes a `text_preview`

Do not replace this with a fictional upload API.

### Search / RAG

`GET /api/v1/search?query=...`

This is the existing search/RAG functionality used by the frontend.

Do not invent a separate chat endpoint just to make the UI look more
complete.

### Documents

`GET /api/v1/documents`

This returns real document data.

The Library must use this real backend data.

Do not create fake documents just to make the Library look populated.

------------------------------------------------------------------------

## 7. Current Frontend/API Integration

The frontend has an API client at:

`frontend/src/api/client.ts`

Known integrations: - PDF upload through `/api/v1/upload/pdf` -
documents through `/api/v1/documents` - search through
`/api/v1/search?query=...`

The Library uses real `getDocuments()` functionality.

The Chat uses the existing search functionality and the search response,
including `result.top_matches`.

Source cards use real source information such as `source.document`.

Preserve these integrations.

------------------------------------------------------------------------

## 8. PDF Upload Requirements

PDF is the primary confirmed working ingestion flow.

The UI should: - open a real file picker - accept PDFs - enforce the 20
MB limit - call `/api/v1/upload/pdf` - show uploading/loading state -
show success state - show error state - prevent duplicate interaction
while uploading - refresh the Library/recent documents after successful
upload where appropriate

The UI may visually mention: - PDF - DOCX - PPT - TXT

because they represent the broader product direction.

However, only PDF uploading is currently confirmed functional.

Do not pretend unsupported formats work and do not invent endpoints.

------------------------------------------------------------------------

## 9. YouTube Status

YouTube ingestion is not currently confirmed as a working end-to-end
frontend/backend flow.

Present it as: - Add a YouTube video - Paste a YouTube link - Coming
Soon

Do not create fake processing or a fake endpoint.

------------------------------------------------------------------------

## 10. Home Page Direction

The Home page should be AI-first.

Primary hero:

> Your second brain.
>
> Always with you.

Supporting copy:

> Ask questions. Understand faster. Learn from everything you've saved.

Primary AI input:

> What do you want to understand?

It must connect to the existing search/RAG functionality.

The user should be able to: - type a question - press Enter - click
submit - see loading - receive results - see source information where
available

This should feel like the central purpose of SecondBrain.

------------------------------------------------------------------------

## 11. Add to Your SecondBrain

Below the main AI interaction:

**Add to your SecondBrain**

Desktop: two clean side-by-side options.

### Upload Files

Visually show: - PDF - DOCX - PPT - TXT

Show: - Maximum file size: 20 MB

Only PDF needs to actually upload, using `/api/v1/upload/pdf`.

Include polished: - file picker - validation - uploading state - success
state - error state - disabled state while uploading

### YouTube

Show: - Add a YouTube video - Paste a YouTube link - Coming Soon

Clearly disabled until real backend support exists.

------------------------------------------------------------------------

## 12. Library Concept

Use: - Library - History - Saved knowledge - Recent documents

Do NOT use: - Knowledge Base - Knowledge Hub

The Library is the user's organized collection of saved learning
material.

Use real data from:

`GET /api/v1/documents`

Do not create fake documents.

Subject/folder organization may eventually be introduced, but do not
pretend backend folder functionality exists if it does not.

------------------------------------------------------------------------

## 13. Current Library UI Problem

The current large three-card folder-style design is not desired.

Do not recreate those cards with different colors or labels.

The Library should feel like a professional document/knowledge
management interface.

Possible direction: - compact document rows/cards - file type
indicators - document names - real metadata only - search/filter
controls - loading/empty/error states - polished hover states -
restrained hierarchy

Use the Stitch references for the final visual composition.

------------------------------------------------------------------------

## 14. AI Chat

AI Chat should be a polished knowledge interaction interface using:

`GET /api/v1/search?query=...`

Do not invent a separate chat backend.

Support: - user questions - AI/search answers - source documents -
loading state - empty state - error state - working input - Enter to
submit - Shift+Enter for newline - disabled submit while processing

Use actual returned source information. Do not invent citations or
documents.

------------------------------------------------------------------------

## 15. Visual Design Direction

Six Stitch screenshots are provided separately.

They are visual references, not designs to copy literally.

Use them to understand: - layout - spacing - proportions - hierarchy -
typography - sidebar structure - component treatment - interaction
patterns - density - visual polish

Desired visual language: - dark charcoal / near-black - off-white
primary text - muted gray secondary text - restrained purple/indigo
accents - subtle thin borders - small-to-moderate corner radius - clean
typography - strong hierarchy - premium SaaS appearance - deliberate
spacing - useful density - minimal visual noise

Avoid: - huge gradients - excessive glow - excessive glassmorphism -
excessive rounded containers - excessive shadows - giant empty areas -
fake statistics - unnecessary dashboards - unnecessary animations -
emojis as design elements - generic student-dashboard appearance -
generic ChatGPT-clone appearance

------------------------------------------------------------------------

## 16. Sidebar

Professional narrow sidebar:

**Brand** - SecondBrain

**Navigation** - Home - Library - AI Chat

**Bottom** - Settings

It should: - have clear active state - have hover/focus states - be
visually balanced - not consume excessive width - work responsively -
integrate naturally with main content

------------------------------------------------------------------------

## 17. Home Layout

The Home page must use the desktop viewport intelligently.

The current problem is excessive unused black space.

Do not solve this by moving existing elements a few pixels.

The composition should have: - strong hero - primary AI interaction -
ingestion section - compact recent-library area - coherent vertical
rhythm

The page should feel intentional from top to bottom.

------------------------------------------------------------------------

## 18. Responsive Design

Desktop is an important target.

Desktop: - narrow sidebar - main content uses available width
intelligently - ingestion cards can sit side-by-side

Smaller screens: - sidebar adapts/collapses appropriately - cards
stack - inputs remain usable - no horizontal overflow

------------------------------------------------------------------------

## 19. Interaction Quality

The product must not look like a static mockup.

Interactive elements should have appropriate: - hover - active - focus -
disabled - loading - success - error states

Important interactions:

### Navigation

Home / Library / AI Chat must work.

### Home AI Search

-   type question
-   Enter submit
-   button submit
-   loading
-   results
-   sources

### PDF Upload

-   file picker
-   validation
-   uploading
-   success/error
-   Library refresh

### Library

-   load real documents
-   loading
-   empty
-   error
-   frontend search/filter where appropriate

### Chat

-   input
-   Enter submit
-   Shift+Enter newline
-   loading
-   results
-   sources
-   errors

------------------------------------------------------------------------

## 20. Empty States

Empty states should be intentional and premium.

Avoid a plain sentence such as:

`No documents found. Upload your first document above.`

inside a generic border.

Instead: - explain the next action - remain compact - match the product
visual language - do not introduce fake data

------------------------------------------------------------------------

## 21. Loading and Error States

Backend-dependent areas must handle: - loading - error - empty - success

Especially: - document loading - PDF upload - AI/search - Library

User-facing errors should be understandable. Do not expose raw stack
traces.

------------------------------------------------------------------------

## 22. Implementation Rules

1.  Inspect the existing project before changing it.
2.  Preserve working functionality.
3.  Do not modify backend logic unless explicitly required.
4.  Do not invent API endpoints.
5.  Do not invent fake data.
6.  Reuse existing components where appropriate.
7.  Do not rewrite the entire project unnecessarily.
8.  Do not replace working API integrations without a real reason.
9.  Keep TypeScript correct.
10. Keep React architecture clean.
11. Keep routing intact.
12. Avoid unrelated refactors.
13. Avoid unnecessary dependencies.
14. Avoid fake functionality.
15. Verify changes against the actual running project.

------------------------------------------------------------------------

## 23. Current UI Problems

The current UI has gone through several iterations but is still not at
the desired quality.

Known problems: - too much unused black space - useful content
compressed into a relatively small region - weak hierarchy - upload
cards feel basic - YouTube can look partially functional/fake - Library
preview is weak - current large library cards are not desired -
interaction polish is insufficient - overall interface still feels like
an early prototype

A successful redesign must be visibly meaningful.

Changing only a few margins, font sizes, or border colors is not enough.

------------------------------------------------------------------------

## 24. What a Successful Redesign Should Improve

The improvement should be obvious in a side-by-side screenshot.

Improve: - overall composition - viewport usage - sidebar proportions -
content width - hero positioning - typography hierarchy - AI input
presentation - ingestion section - Library preview - interaction
states - spacing rhythm - responsive behavior - overall SaaS polish

------------------------------------------------------------------------

## 25. Claude's Role

Act as a senior: - product engineer - frontend engineer - UI/UX
reviewer - architecture reviewer

Do not blindly follow this document.

Process: 1. Read this document. 2. Inspect the repository. 3. Verify
architecture. 4. Verify API client. 5. Verify routes. 6. Verify
components. 7. Verify backend endpoints. 8. Compare implementation
against the Stitch references. 9. Identify discrepancies. 10. Recommend
focused improvements.

------------------------------------------------------------------------

## 26. Review-First Workflow

Before substantial implementation changes, provide:

1.  Understanding of SecondBrain.
2.  Current frontend architecture.
3.  Current backend architecture.
4.  Existing API endpoints.
5.  Current routes.
6.  Current upload flow.
7.  Current search/RAG flow.
8.  Current Library flow.
9.  What is working.
10. What is incomplete.
11. Causes of the current UI problems.
12. Prioritized implementation plan.
13. Exact files likely to change.
14. Risks.

Do not make substantial changes until explicitly authorized.

------------------------------------------------------------------------

## 27. Change Review Requirement

AI-generated changes must not be blindly accepted.

For meaningful changes, explain: - why the change is needed - affected
files - behavior changes - preserved functionality - possible risks

After implementation, review: - git diff where available - build
output - TypeScript errors - API integration - routing - UI behavior

------------------------------------------------------------------------

## 28. Verification Checklist

After frontend implementation:

Run:

``` text
npm run build
```

Confirm: - build succeeds - no TypeScript errors - routes work - Home
renders - Library renders - AI Chat renders - PDF upload calls the real
endpoint - documents load from the real endpoint - search calls the real
endpoint - YouTube remains correctly disabled/Coming Soon - no fake
documents were introduced - no fake API endpoints were introduced - no
horizontal overflow - responsive layout works

Report: - exact files changed - build result - functionality verified -
remaining issues

------------------------------------------------------------------------

## 29. Do Not Do These Things

Do NOT: - invent backend endpoints - invent fake documents - invent fake
AI responses - invent fake source citations - pretend YouTube works -
pretend unsupported formats work - add fake statistics - add a fake
dashboard - rename Library to Knowledge Base - rename Library to
Knowledge Hub - recreate the old three large folder cards - modify
backend without necessity - rewrite the entire application
unnecessarily - add huge animations - add excessive gradients - add
excessive glassmorphism - add excessive glowing effects - make unrelated
improvements

------------------------------------------------------------------------

## 30. Reference Image Rule

Six Stitch screenshots are provided separately.

Use them as visual direction.

Do not copy their exact branding, content, or layout literally.

Extract: - spacing - density - proportions - typography - hierarchy -
navigation - interaction - visual rhythm

Apply those principles specifically to SecondBrain.

------------------------------------------------------------------------

## 31. Development Workflow

The frontend is being developed incrementally.

There may be partially completed redesign work.

Do not assume old components should automatically be deleted.

Inspect first.

Prefer targeted restructuring where appropriate.

Priority: 1. Working functionality 2. Correct architecture 3. Strong
visual design 4. Interaction quality 5. Responsive behavior 6.
Maintainability

------------------------------------------------------------------------

## 32. Final Instruction

Understand the actual SecondBrain project before proposing major
changes.

Use this document as product context.

Use the actual repository as the technical source of truth.

Use the six Stitch images as visual direction.

Do not guess when the code can answer the question.

Do not invent functionality.

Do not break existing functionality for visual improvements.

Do not make changes merely for the sake of changing files.

The ultimate goal is a polished, professional, AI-first personal
knowledge product that genuinely feels like a finished SaaS application.
