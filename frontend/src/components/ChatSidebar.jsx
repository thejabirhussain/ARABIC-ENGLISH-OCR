import { useState, useEffect, useRef } from 'react'
import { v4 as uuidv4 } from 'uuid'
import ReactMarkdown from 'react-markdown'

function ChatSidebar({ isOpen, onClose, docId }) {
    const [messages, setMessages] = useState([
        {
            id: 'welcome',
            text: "Hello! I've analyzed your document. Ask me anything about its content.",
            isUser: false
        }
    ])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const messagesEndRef = useRef(null)

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }

    useEffect(() => {
        scrollToBottom()
    }, [messages])

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (!input.trim() || loading) return

        const userMessage = { id: uuidv4(), text: input, isUser: true }
        setMessages(prev => [...prev, userMessage])
        setInput('')
        setLoading(true)

        try {
            const response = await fetch('http://127.0.0.1:8000/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    doc_id: docId,
                    query: userMessage.text
                }),
            })

            if (!response.ok) {
                throw new Error('Failed to get answer')
            }

            const data = await response.json()

            const aiMessage = {
                id: uuidv4(),
                text: data.response,
                isUser: false
            }
            setMessages(prev => [...prev, aiMessage])
        } catch (err) {
            console.error(err)
            setMessages(prev => [...prev, {
                id: uuidv4(),
                text: "Sorry, I encountered an error while processing your request.",
                isUser: false,
                isError: true
            }])
        } finally {
            setLoading(false)
        }
    }

    return (
        <div
            className={`fixed top-0 right-0 h-full w-[400px] bg-white shadow-2xl transform transition-transform duration-300 ease-in-out z-50 flex flex-col ${isOpen ? 'translate-x-0' : 'translate-x-full'
                }`}
        >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                            <path fillRule="evenodd" d="M4.848 2.771A49.144 49.144 0 0112 2.25c2.43 0 4.817.178 7.152.52 1.978.292 3.348 2.024 3.348 3.97v6.02c0 1.946-1.37 3.678-3.348 3.97-1.94.284-3.916.455-5.922.505a.39.39 0 00-.266.112L8.78 21.53A.75.75 0 017.5 21v-3.955a48.842 48.842 0 01-2.652-.316c-1.978-.29-3.348-2.024-3.348-3.97V6.741c0-1.946 1.37-3.678 3.348-3.97z" clipRule="evenodd" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="font-semibold text-slate-800">Document Assistant</h3>
                        <p className="text-xs text-slate-500">Ask questions based on content</p>
                    </div>
                </div>
                <button
                    onClick={onClose}
                    className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded-md hover:bg-slate-100"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
                        <path fillRule="evenodd" d="M5.47 5.47a.75.75 0 011.06 0L12 10.94l5.47-5.47a.75.75 0 111.06 1.06L13.06 12l5.47 5.47a.75.75 0 11-1.06 1.06L12 13.06l-5.47 5.47a.75.75 0 01-1.06-1.06L10.94 12 5.47 6.53a.75.75 0 010-1.06z" clipRule="evenodd" />
                    </svg>
                </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50">
                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        className={`flex ${msg.isUser ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${msg.isUser
                                ? 'bg-indigo-600 text-white rounded-tr-sm font-medium'
                                : 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm shadow-sm'
                                } ${msg.isError ? 'bg-red-50 border-red-200 text-red-800' : ''}`}
                        >
                            {msg.isUser ? (
                                <p className="text-white whitespace-pre-wrap">{msg.text}</p>
                            ) : (
                                <ReactMarkdown
                                    className="prose prose-sm max-w-none prose-slate prose-p:leading-relaxed prose-pre:bg-slate-100 prose-pre:text-slate-800"
                                >
                                    {msg.text || ''}
                                </ReactMarkdown>
                            )}
                        </div>
                    </div>
                ))}
                {loading && (
                    <div className="flex justify-start">
                        <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                            <div className="flex gap-1.5">
                                <div className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                                <div className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                                <div className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-4 bg-white border-t border-slate-100">
                <form onSubmit={handleSubmit} className="relative">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Ask about your document..."
                        className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 transition-all text-sm text-slate-800 placeholder-slate-400"
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || loading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                            <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
                        </svg>
                    </button>
                </form>
            </div>
        </div>
    )
}

export default ChatSidebar
