import os
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
import ollama
import google.generativeai as genai
from sentence_transformers import SentenceTransformer

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
# Models
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
CHAT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b-instruct-q4_k_m")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434") 

COLLECTION_NAME = "OCR-APPLICATION-V2" 

class RAGService:
    def __init__(self):
        try:
            self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
            
            # Initialize Sentence Transformer (Local Embeddings)
            print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
            self.encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
            print("Embedding model loaded.")

            self._ensure_collection()
            print(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
            
            # Initialize Ollama Client for Chat
            self.ollama_client = ollama.Client(host=OLLAMA_HOST)
            print(f"Connected to Ollama at {OLLAMA_HOST} using model {CHAT_MODEL}")
            
            # Initialize Gemini
            self.gemini_available = False
            # API Key provided by user
            api_key = "AIzaSyC37146oJcnxI7E9gDxTKUUbCq-Sjq_3Gw"
            if api_key:
                try:
                    genai.configure(api_key=api_key)
                    self.gemini_model = genai.GenerativeModel('gemini-pro')
                    self.gemini_available = True
                    print("Gemini API initialized successfully.")
                except Exception as e:
                    print(f"Failed to initialize Gemini: {e}")
            else:
                 print("GEMINI_API_KEY not found. Gemini integration disabled.")
            
            
        except Exception as e:
            print(f"Failed to connect to services: {e}")
            self.client = None
            self.ollama_client = None
            self.gemini_available = False

    def list_models(self) -> List[str]:
        """List available local models from Ollama."""
        try:
            if not self.ollama_client:
                 self.ollama_client = ollama.Client(host=OLLAMA_HOST)
            
            models_resp = self.ollama_client.list()
            # Handle different response structures if necessary
            # Usually returns {'models': [{'name': '...', ...}, ...]}
            model_names = [m['name'] for m in models_resp.get('models', [])]
            
            if self.gemini_available:
                model_names.append("gemini-pro")
                
            return model_names
        except Exception as e:
            print(f"Error listing models: {e}")
            return [CHAT_MODEL]  # Return default if failed

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        if not self.client:
            return

        collections = self.client.get_collections()
        exists = any(c.name == COLLECTION_NAME for c in collections.collections)

        if not exists:
            # nomadic-embed-text has 768 dimensions
            # llama2/mistral often have 4096. 
            # We'll use 768 for nomic-embed-text.
            # If using different model, this needs to match.
            # all-MiniLM-L6-v2 has 384 dimensions
            vector_size = 384 
            
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE
                )
            )
            print(f"Created collection: {COLLECTION_NAME}")

    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding using SentenceTransformer."""
        try:
            # Generate embedding
            embedding = self.encoder.encode(text)
            return embedding.tolist()
        except Exception as e:
            print(f"Error getting embedding: {e}")
            raise

    def index_document(self, doc_id: str, text: str) -> bool:
        """
        Split text into chunks and index into Qdrant.
        """
        if not self.client:
            print("Qdrant client not initialized.")
            return False

        # Simple splitting by paragraphs or fixed size
        # For simplicity, let's look for double newlines or split by char count
        chunks = self._chunk_text(text)
        
        points = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            
            try:
                vector = self._get_embedding(chunk)
                
                payload = {
                    "doc_id": doc_id,
                    "text": chunk,
                    "chunk_index": i
                }
                
                points.append(models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                ))
            except Exception as e:
                print(f"Error embedding chunk {i}: {e}")
                continue

        if points:
            try:
                self.client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points
                )
                print(f"Indexed {len(points)} chunks for document {doc_id}")
                return True
            except Exception as e:
                print(f"Error upserting to Qdrant: {e}")
                return False
        
        return False

    def chat_with_document(self, doc_id: str, query: str, model_name: Optional[str] = None) -> str:
        """
        RAG flow: Retrieve relevant chunks -> Chat with LLM.
        """
        if not self.client:
            return "Error: Database connection unavailable."

        # 1. Embed query
        try:
            query_vector = self._get_embedding(query)
        except Exception as e:
            return f"Error processing query: {str(e)}"

        # 2. Search Qdrant
        try:
            search_result = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id)
                        )
                    ]
                ),
                limit=5 
            ).points
        except Exception as e:
            return f"Error searching document: {str(e)}"

        if not search_result:
            return "I couldn't find any relevant information in the document to answer your question."

        # 3. Construct Context
        context_text = "\n\n".join([hit.payload["text"] for hit in search_result])
        
        system_prompt = (
            "You are an intelligent assistant helping a user understand a document. "
            "Use the provided context to answer the user's question accurately and concisely. "
            "If the answer is not in the context, say you don't know. "
            "Do not hallucinate. Answer ONLY in English."
            "\n\nContext:\n" + context_text
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        # 4. Generate Response
        target_model = model_name if model_name else CHAT_MODEL
        
        try:
            target_model = model_name if model_name else CHAT_MODEL
            print(f"Chatting using model: {target_model}")
            
            # Gemini Path
            if target_model.startswith("gemini"):
                if not self.gemini_available:
                     return "Error: Gemini model requested but not configured (check GEMINI_API_KEY)."

                # Construct prompt for Gemini (it works best with a direct prompt or history)
                # We can use the messages format or just concat. For RAG context, concat is often robust.
                full_prompt = (
                    f"{system_prompt}\n\n"
                    f"User Question: {query}"
                )
                
                response = self.gemini_model.generate_content(full_prompt)
                return response.text

            # Ollama Path (Default)
            if not self.ollama_client:
                 self.ollama_client = ollama.Client(host=OLLAMA_HOST)
            
            response = self.ollama_client.chat(model=target_model, messages=messages)
            return response['message']['content']
        except Exception as e:
            return f"Error generating response: {str(e)}"

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """Simple text chunker."""
        if not text:
            return []
            
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + chunk_size
            
            # If we are not at the end of text, try to find a sentence break or newline
            if end < text_len:
                # Look for last newline in the window
                last_newline = text.rfind('\n', start, end)
                if last_newline != -1 and last_newline > start + chunk_size // 2:
                    end = last_newline + 1
                else:
                    # Look for last period
                    last_period = text.rfind('. ', start, end)
                    if last_period != -1 and last_period > start + chunk_size // 2:
                        end = last_period + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap
            if start < 0: # Should not happen unless chunk_size <= overlap
                start = end
        
        return chunks

# Singleton instance
rag_service = RAGService()
