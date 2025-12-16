# 🎯 Arabic OCR → English Translation App

A complete web application that extracts Arabic text from scanned PDFs using OCR and translates it to English. Built with FastAPI backend and React frontend.

## 📋 Features

- ✅ **Accurate Arabic OCR** using `ocrmypdf` and Tesseract with Arabic language model
- ✅ **Preserves formatting** - maintains line breaks, paragraphs, and punctuation
- ✅ **High-quality translation** using Helsinki-NLP/opus-mt-ar-en model
- ✅ **100% Open-source** - no API keys required
- ✅ **Modern UI** - clean, responsive design with TailwindCSS
- ✅ **Real-time processing** - upload PDF and get results instantly

## 🏗️ Project Structure

```
SAMPLE-OCR/
├── backend/
│   ├── main.py                 # FastAPI application
│   ├── requirements.txt        # Python dependencies
│   └── services/
│       ├── __init__.py
│       ├── ocr_service.py      # OCR extraction service
│       └── translate_service.py # Translation service
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css
│       └── components/
│           ├── UploadBox.jsx
│           └── OutputBox.jsx
└── README.md
```

## 🚀 Installation & Setup

### Prerequisites

- **Python 3.9+** (Python 3.10 or 3.11 recommended)
- **Node.js 18+** and npm
- **Tesseract OCR** with Arabic language pack
- **Poppler** (for pdf2image)
- **Ghostscript** (required by ocrmypdf)

### macOS Installation (Apple Silicon M1/M2/M3/M4)

#### 1. Install System Dependencies

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Tesseract OCR
brew install tesseract
brew install tesseract-lang

# Install Arabic language data for Tesseract
# Note: tesseract-lang may not include Arabic, so we download it manually
curl -L -o /tmp/ara.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/ara.traineddata
sudo cp /tmp/ara.traineddata /opt/homebrew/share/tessdata/ara.traineddata

# Install Poppler (required for pdf2image)
brew install poppler

# Install Ghostscript (required by ocrmypdf)
brew install ghostscript

# Install SentencePiece (required by translation model)
brew install sentencepiece

# Verify Tesseract installation
tesseract --list-langs
# Should show 'ara' in the list
```

#### 2. Setup Backend

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Note: First run will download the translation model (~300MB)
# This may take a few minutes
```

#### 3. Setup Frontend

```bash
# Navigate to frontend directory (from project root)
cd frontend

# Install Node.js dependencies
npm install
```

## 🏃 Running the Application

### Terminal 1: Start Backend Server

```bash
cd backend
source venv/bin/activate  # If using virtual environment
python main.py
```

The backend will start on `http://localhost:8000`

### Terminal 2: Start Frontend Development Server

```bash
cd frontend
npm run dev
```

The frontend will start on `http://localhost:5173`

### Access the Application

Open your browser and navigate to: **http://localhost:5173**

## 📡 API Endpoints

### POST `/process`

Upload a PDF file and get extracted Arabic text and English translation.

**Request:**
```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@path/to/your/arabic.pdf"
```

**Response:**
```json
{
  "arabic_text": "النص العربي المستخرج من PDF",
  "english_text": "Arabic text extracted from PDF"
}
```

## 🔧 Configuration

### Backend Configuration

- **Port**: Default is `8000` (can be changed in `main.py`)
- **CORS**: Configured to allow requests from `http://localhost:5173`

### Frontend Configuration

- **Port**: Default is `5173` (can be changed in `vite.config.js`)
- **API URL**: Set to `http://localhost:8000` (can be changed in `App.jsx`)

## 🐛 Troubleshooting

### Tesseract Arabic Language Not Found

```bash
# Verify Arabic language is installed
tesseract --list-langs

# If 'ara' is missing, download and install it:
curl -L -o /tmp/ara.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/ara.traineddata
sudo cp /tmp/ara.traineddata /opt/homebrew/share/tessdata/ara.traineddata

# Verify installation
tesseract --list-langs
# Should now show 'ara' in the list
```

### Poppler Not Found Error

```bash
# Install Poppler
brew install poppler

# On some systems, you may need to set the path:
export PATH="/opt/homebrew/bin:$PATH"
```

### Ghostscript Not Found Error

```bash
# Install Ghostscript (required by ocrmypdf)
brew install ghostscript

# Verify installation
gs --version

# If still not found, ensure Homebrew bin is in PATH:
export PATH="/opt/homebrew/bin:$PATH"
```

### SentencePiece Not Found Error

```bash
# Install SentencePiece via Homebrew (recommended for macOS)
brew install sentencepiece

# Then install Python package
cd backend
source venv/bin/activate
pip install sentencepiece

# Verify installation
python -c "import sentencepiece; print('SentencePiece installed')"
```

### Translation Model Download Issues

The first run will download the Helsinki-NLP model (~300MB). If it fails:

1. Check your internet connection
2. Ensure you have sufficient disk space
3. The model will be cached in `~/.cache/huggingface/`

### Memory Issues on Apple Silicon

If you encounter memory issues:

1. Ensure you're using Python 3.9+ with proper ARM64 support
2. PyTorch should automatically use MPS (Metal Performance Shaders) on Apple Silicon
3. If needed, reduce batch size in `translate_service.py`

### Port Already in Use

If port 8000 or 5173 is already in use:

```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Find and kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

## 📦 Dependencies

### Backend Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `ocrmypdf` - PDF OCR processing
- `pytesseract` - Tesseract OCR Python wrapper
- `pdf2image` - PDF to image conversion
- `PyPDF2` - PDF text extraction
- `transformers` - HuggingFace transformers for translation
- `torch` - PyTorch for model inference

### Frontend Dependencies

- `react` - UI library
- `vite` - Build tool and dev server
- `tailwindcss` - CSS framework

## 🎨 Usage

1. **Upload PDF**: Click "Choose PDF File" and select your scanned Arabic PDF
2. **Process**: Click "Extract & Translate Text"
3. **View Results**: See extracted Arabic text and English translation side by side
4. **Copy Text**: Use the "Copy" buttons to copy text to clipboard

## 📝 Notes

- **PDF Format**: The application works best with scanned PDFs (images)
- **File Size**: Large PDFs may take longer to process
- **First Run**: The translation model download happens on first use (~300MB)
- **Accuracy**: OCR accuracy depends on PDF quality and scan resolution
- **Formatting**: Line breaks and paragraphs are preserved in the output

## 🔒 License

This project uses 100% open-source libraries and models. All dependencies are open-source.

## 🤝 Contributing

Feel free to submit issues or pull requests for improvements!

## 📧 Support

For issues or questions, please check the troubleshooting section above or open an issue in the repository.

---

**Built with ❤️ using FastAPI, React, and open-source AI models**

