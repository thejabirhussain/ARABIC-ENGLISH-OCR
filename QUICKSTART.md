# 🚀 Quick Start Guide

## Prerequisites Check

```bash
# Check Python version (need 3.9+)
python3 --version

# Check Node.js version (need 18+)
node --version

# Check if Tesseract is installed
tesseract --version
tesseract --list-langs  # Should show 'ara'
```

## Quick Setup (macOS)

```bash
# Run the setup script
./setup.sh

# OR manually:

# 1. Install system dependencies
brew install tesseract tesseract-lang poppler

# 2. Setup backend
cd backend
python3 -m venv venv
source venv/bin/activate or venv\Scripts\activate #(for windows)
pip install -r requirements.txt

# 3. Setup frontend
cd ../frontend
npm install
```

## Running the App

### Terminal 1: Backend
```bash
cd backend
source venv/bin/activate
python main.py
```

### Terminal 2: Frontend
```bash
cd frontend
npm run dev
```

### Open Browser
Navigate to: **http://localhost:5173**

## Testing with cURL

```bash
# Test the API endpoint directly
curl -X POST "http://localhost:8000/process" \
  -F "file=@/path/to/your/arabic.pdf" \
  -H "Content-Type: multipart/form-data"

# Example response:
# {
#   "arabic_text": "النص العربي...",
#   "english_text": "Arabic text..."
# }
```

## Troubleshooting

### Tesseract Arabic not found
```bash
brew install tesseract-lang
tesseract --list-langs  # Verify 'ara' appears
```

### Port already in use
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

### First run - Model download
The translation model (~300MB) downloads automatically on first use. Be patient!

## Project Structure

```
SAMPLE-OCR/
├── backend/          # FastAPI server
├── frontend/         # React + Vite app
├── setup.sh          # Automated setup script
└── README.md         # Full documentation
```