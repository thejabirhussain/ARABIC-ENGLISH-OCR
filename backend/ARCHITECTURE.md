# PDF Translation System Architecture

## Overview
This system is an **Advanced Financial Document Translation Pipeline** designed to convert Arabic PDFs to English while preserving complex layouts, tables, and financial formatting. It specifically addresses challenges like text overlap, fragmented Arabic tokens, and accurate table reconstruction.

## System Architecture Diagram

```mermaid
graph TD
    User([User / Frontend]) -->|Upload PDF| API[FastAPI Backend - main.py]
    
    subgraph Pipeline [Translation Pipeline]
        annot1[Orchestrator: pdf_translation_service.py]
        
        API --> annot1
        
        subgraph extraction [Extraction & Analyis]
            annot1 -->|Extract| PDFPlumber[pdfplumber]
            annot1 -->|Detect Tables| TableService[Table Detection Service]
            
            TableService -->|Heuristic Filter| DensityCheck{Density Check}
            DensityCheck -->|Avg Words/Cell > 12| TextLayout[Text Paragraph]
            DensityCheck -->|Avg Words/Cell < 12| DataTable[Financial Table]
            
            PDFPlumber -->|Extract Words| Words[Word Tokens]
            Words -->|Sort & Gap-Merge| TextBlocks[Consolidated Text Blocks]
        end
        
        subgraph translation [Translation Layer]
            direction TB
            DataTable -->|Extract CSV| TableHandler[Table Handler]
            TableHandler -->|Process| MaryumTrans[TranslationService]
            
            TextLayout -->|Treat as Text| TextBlocks
            
            TextBlocks -->|Normalize| Norm[Text Normalizer]
            Norm -->|Translation Model| Helsinki[Helsinki-NLP Model]
            
            MaryumTrans -->|Tokenize| Batch[Batch Translator]
            Batch -->|Translation Model| Helsinki
            
            Helsinki -->|Raw English| PostProcess[Post Processor]
            
            PostProcess -->|Apply Glossary| Glossary{Financial Glossary}
            Glossary -->|Correction| CleanText[Final English Text]
        end
        
        subgraph rendering [Rendering & Layout]
            annot1 -->|Layout Instructions| PyMuPDF[PyMuPDF / Fitz]
            
            PyMuPDF -->|Action 1| MegaCover[Mega Cover: White-out Table Areas]
            PyMuPDF -->|Action 2| RenderText[Render Text Blocks]
            PyMuPDF -->|Action 3| RenderTables[Render Table Cells]
            
            RenderTables -->|Fit Check| FontSize[Auto-Resize Font]
            FontSize -->|Loop| RenderTables
        end
        
        CleanText --> rendering
    end
    
    rendering -->|Output| FinalPDF[Translated PDF]
    FinalPDF --> User
```

## Core Components

### 1. **Orchestrator (`pdf_translation_service.py`)**
 The central controller that manages the document lifecycle. It iterates through pages, invokes detectors, and coordinates the translation and rendering phases. It now includes intelligent filtering to distinguish between **Data Tables** and **Multi-Column Text**.

### 2. **Table Detection & Handling (`services/tables_service/`)**
 - **Detection (`table_detection_service.py`)**: Uses a custom heuristic algorithm to find table regions based on vertical and horizontal alignment.
 - **Density Filter**: A crucial post-detection step that analyzes "Words Per Cell". 
   - *High Density (>12 words)*: Classified as a Text Layout (Paragraph) -> Sent to Text Translation.
   - *Low Density (<12 words)*: Classified as a Data Table -> Sent to Table Translation.
 - **Gap-Based Merging (`table_handler.py`)**: Solves the "Fragmented Arabic" issue by merging disjointed text tokens based on proximity before translation.

### 3. **Translation Engine**
 - **Model**: `Helsinki-NLP/opus-mt-tc-big-ar-en` (Primary) with fallback.
 - **Normalization**: Converts Arabic numerals (١٢٣) to English (123) and standardizes punctuation.
 - **Financial Glossary (`translation_service.py`)**: A post-processing layer that enforces standard financial terminology (e.g., correcting "Untraded liabilities" to "Non-current liabilities").

### 4. **Rendering Engine (In-Place)**
 - **Mega Cover**: Before rendering a table, the system draws a single white rectangle over the *entire* table area. This prevents original Arabic text from bleeding through the gaps between English rows.
 - **Auto-Resizing**: Dynamically reduces font size (down to 4pt) to ensure translated English text fits exactly within the original cell boundaries without overlapping neighbors.

## Data Flow
1.  **Upload**: User uploads a PDF.
2.  **Detection**: System scans for tables. Candidates are filtered by text density.
3.  **Extraction**: 
    -   Tables are converted to CSV-like structures.
    -   Text outside tables is grouped into blocks.
4.  **Translation**: 
    -   Text is batch-translated.
    -   Financial terms are corrected via Glossary.
5.  **Rendering**: 
    -   Original PDF page is modified in-place.
    -   Table areas are whited out ("Mega Cover").
    -   Translated text is drawn with precise alignment.
6.  **Output**: Final PDF is returned to the user.

## Future Roadmaps
-   **Structure Recognition**: Moving from heuristics to AI-based table detection (e.g., Table Transformer).
-   **Font Matching**: Attempting to match the weight and style of the original Arabic font.
-   **Vector Search**: Integrating RAG flows more deeply for "Chat with PDF" features.

