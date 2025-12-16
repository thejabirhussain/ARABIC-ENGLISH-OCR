#!/bin/bash

# Arabic OCR Translation App - Setup Script
# This script helps set up the project on macOS

echo "🚀 Setting up Arabic OCR Translation App..."
echo ""

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew is not installed. Please install it first:"
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

echo "✅ Homebrew found"
echo ""

# Install Tesseract OCR
echo "📦 Installing Tesseract OCR..."
brew install tesseract tesseract-lang

# Install Arabic language data
echo "📦 Installing Arabic language data for Tesseract..."
if [ ! -f /opt/homebrew/share/tessdata/ara.traineddata ]; then
    curl -L -o /tmp/ara.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/ara.traineddata
    if [ -w /opt/homebrew/share/tessdata ]; then
        cp /tmp/ara.traineddata /opt/homebrew/share/tessdata/ara.traineddata
    else
        echo "⚠️  Need sudo to copy Arabic language data. Please run:"
        echo "   sudo cp /tmp/ara.traineddata /opt/homebrew/share/tessdata/ara.traineddata"
        sudo cp /tmp/ara.traineddata /opt/homebrew/share/tessdata/ara.traineddata
    fi
    echo "✅ Arabic language data installed"
else
    echo "✅ Arabic language data already installed"
fi

# Install Poppler
echo "📦 Installing Poppler..."
brew install poppler

# Install Ghostscript
echo "📦 Installing Ghostscript..."
brew install ghostscript

# Install SentencePiece
echo "📦 Installing SentencePiece..."
brew install sentencepiece

echo ""
echo "✅ System dependencies installed"
echo ""

# Setup Backend
echo "🐍 Setting up Python backend..."
cd backend

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9+ first."
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Backend setup complete"
echo ""

# Setup Frontend
cd ../frontend
echo "⚛️  Setting up React frontend..."

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

# Install Node dependencies
echo "Installing Node.js dependencies..."
npm install

echo ""
echo "✅ Frontend setup complete"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Setup complete!"
echo ""
echo "To run the application:"
echo ""
echo "Terminal 1 (Backend):"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "Terminal 2 (Frontend):"
echo "  cd frontend"
echo "  npm run dev"
echo ""
echo "Then open http://localhost:5173 in your browser"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

