import React, { useState, useRef, useEffect } from 'react';

const RAGChat = () => {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I\'m your threat intelligence assistant. I can help you search through our database of cybersecurity articles using semantic search. What would you like to know about?',
      timestamp: new Date().toISOString()
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [settings, setSettings] = useState({
    maxResults: 10,  // Default to 10 chunks for better precision
    similarityThreshold: 0.3,  // Lower threshold for broader coverage
    useChunks: false,  // Disable chunk-level search until annotations have embeddings
    contextLength: 2000  // Context length per chunk
  });
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage = {
      role: 'user',
      content: inputMessage,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat/rag', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputMessage,
          conversation_history: messages,
          max_results: settings.maxResults,
          similarity_threshold: settings.similarityThreshold,
          use_chunks: settings.useChunks,
          context_length: settings.contextLength
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      const assistantMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: data.timestamp,
        relevantArticles: data.relevant_articles,
        totalResults: data.total_results
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error while processing your request. Please try again.',
        timestamp: new Date().toISOString(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  const renderMessage = (message, index) => {
    const isUser = message.role === 'user';
    const isError = message.isError;

    return (
      <div
        key={index}
        className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}
      >
        <div
          className={`max-w-3xl px-4 py-3 rounded-lg ${
            isUser
              ? 'bg-purple-600 text-white'
              : isError
              ? 'bg-red-900 text-red-200 border border-red-700'
              : 'bg-gray-800 text-gray-200 border border-gray-700'
          }`}
        >
          <div className="whitespace-pre-wrap">{message.content}</div>
          
          {message.relevantArticles && message.relevantArticles.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-600">
              <div className="text-sm font-semibold mb-2 text-gray-300">
                📚 Found {message.totalResults} relevant articles:
              </div>
              <div className="space-y-2">
                {message.relevantArticles.map((article, idx) => (
                  <div key={idx} className="text-sm bg-gray-700 p-3 rounded border border-gray-600">
                    <div className="font-medium text-purple-400">
                      {article.title}
                    </div>
                    <div className="text-gray-400 text-xs">
                      Source: {article.source_name} | Similarity: {(article.similarity * 100).toFixed(1)}%
                    </div>
                    {article.summary && (
                      <div className="text-gray-300 mt-1">
                        {article.summary.substring(0, 150)}...
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          
          <div className="text-xs opacity-70 mt-2 text-gray-400">
            {formatTimestamp(message.timestamp)}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-gray-900">
      {/* Header */}
      <div className="bg-gray-800 border-b border-gray-700 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white">🔍 Threat Intelligence Chat</h2>
            <p className="text-sm text-gray-300">
              Ask questions about cybersecurity threats, malware, and security vulnerabilities
            </p>
          </div>
          
          {/* Settings */}
          <div className="flex items-center space-x-4 text-sm">
            <div className="flex items-center space-x-2">
              <label htmlFor="maxResults" className="text-gray-300">Max Results:</label>
              <select
                id="maxResults"
                value={settings.maxResults}
                onChange={(e) => setSettings(prev => ({ ...prev, maxResults: parseInt(e.target.value) }))}
                className="border border-gray-600 bg-gray-700 text-white rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value={3}>3</option>
                <option value={5}>5</option>
                <option value={10}>10</option>
              </select>
            </div>
            
            <div className="flex items-center space-x-2">
              <label htmlFor="threshold" className="text-gray-300">Similarity:</label>
              <select
                id="threshold"
                value={settings.similarityThreshold}
                onChange={(e) => setSettings(prev => ({ ...prev, similarityThreshold: parseFloat(e.target.value) }))}
                className="border border-gray-600 bg-gray-700 text-white rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value={0.3}>30%</option>
                <option value={0.5}>50%</option>
                <option value={0.6}>60%</option>
                <option value={0.7}>70%</option>
                <option value={0.8}>80%</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-900">
        {messages.map((message, index) => renderMessage(message, index))}
        
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 text-gray-200 px-4 py-3 rounded-lg border border-gray-700">
              <div className="flex items-center space-x-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-purple-400"></div>
                <span>Searching threat intelligence database...</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-700 p-4 bg-gray-800">
        <div className="flex space-x-2">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about cybersecurity threats, malware, vulnerabilities..."
            className="flex-1 border border-gray-600 bg-gray-700 text-white rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent placeholder-gray-400"
            rows={2}
            disabled={isLoading}
          />
          <button
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || isLoading}
            className="bg-purple-600 text-white px-6 py-2 rounded-lg hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Sending...' : 'Send'}
          </button>
        </div>
        
        <div className="mt-2 text-xs text-gray-400">
          💡 Try asking: "What are the latest ransomware threats?" or "Tell me about malware detection techniques"
        </div>
      </div>
    </div>
  );
};

export default RAGChat;
