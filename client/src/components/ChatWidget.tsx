import { useState, useEffect, useRef } from 'react';
import './ChatWidget.css';

const WS_URL = import.meta.env.PUBLIC_WS_URL ?? 'ws://localhost:8000';

interface Message {
  text: string;
  role: 'user' | 'assistant' | 'system';
}

interface ChatWidgetProps {
  className?: string;
}

export default function ChatWidget({ className }: ChatWidgetProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isClosed, setIsClosed] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [showNotification, setShowNotification] = useState(false);
  const [showFileUploader, setShowFileUploader] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [currentTest, setCurrentTest] = useState<number>(0);
  const [currentQuestion, setCurrentQuestion] = useState<number>(0);
  const [workflowStage, setWorkflowStage] = useState('initial');

  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const MAX_MESSAGES = 50;
  const MAX_FILE_SIZE = 5 * 1024 * 1024;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const generateSessionId = () => {
    return 'eval_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  };

  const renderMessage = (text: string, role: Message['role']) => {
    setMessages(prev => [...prev, { text, role }]);

    if (role === 'assistant' && !isOpen) {
      setShowNotification(true);
    }
  };

  const detectFileRequest = (text: string) => {
    const lower = text.toLowerCase();
    return lower.includes('sube tu cv') ||
           lower.includes('subir cv') ||
           lower.includes('formato pdf') ||
           lower.includes('archivo pdf') ||
           lower.includes('sube el cv') ||
           lower.includes('envía tu cv') ||
           lower.includes('enviar cv') ||
           lower.includes('curriculum') ||
           lower.includes('hoja de vida');
  };

  const shouldShowFileUploader = (stage: string) => {
    return stage === 'awaiting_cv' || stage === 'position_selected';
  };

  const showFileUploaderFn = () => {
    setShowFileUploader(true);
  };

  const hideFileUploaderFn = () => {
    setShowFileUploader(false);
    setPendingFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const updateProgress = (test: number, question: number) => {
    if (!test || question === undefined) return;
    setCurrentTest(test);
    setCurrentQuestion(question);
  };

  const terminateConnection = () => {
    setIsConnected(false);
    setIsClosed(true);
    setInputValue('Conversación finalizada');
    hideFileUploaderFn();
    setCurrentTest(0);
    setCurrentQuestion(0);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  const connectWebSocket = () => {
    if (isClosed) {
      renderMessage('Esta conversación ha finalizado. Recarga la página para iniciar una nueva.', 'system');
      return;
    }

    if (!sessionIdRef.current) {
      sessionIdRef.current = generateSessionId();
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    setIsConnecting(true);

    const ws = new WebSocket(`${WS_URL}/api/v1/chat/ws/${sessionIdRef.current}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setIsConnecting(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsConnecting(false);
      if (isClosed) {
        setInputValue('Conversación finalizada');
      }
    };

    ws.onerror = () => {
      setIsConnected(false);
      setIsConnecting(false);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'pong') return;

        if (data.type === 'greeting') {
          if (data.data?.response) {
            renderMessage(data.data.response, 'assistant');
            const stage = data.data.workflow_stage || 'initial';
            setWorkflowStage(stage);

            if (detectFileRequest(data.data.response) || shouldShowFileUploader(stage)) {
              showFileUploaderFn();
            }
          }
          return;
        }

        if (data.type === 'message') {
          if (!data.data?.response) {
            renderMessage('Error: Sin respuesta del servidor', 'system');
            return;
          }

          renderMessage(data.data.response, 'assistant');

          const stage = data.data.workflow_stage || workflowStage;
          setWorkflowStage(stage);

          if (data.data.current_test && data.data.current_question) {
            updateProgress(data.data.current_test, data.data.current_question);
          }

          if (detectFileRequest(data.data.response) || shouldShowFileUploader(stage)) {
            showFileUploaderFn();
          } else if (showFileUploader && stage !== 'awaiting_cv') {
            hideFileUploaderFn();
          }

          if (data.data.is_complete) {
            setIsClosed(true);
            terminateConnection();
          }
          return;
        }

        if (data.type === 'cv_processed') {
          if (data.data?.response) {
            renderMessage(data.data.response, 'assistant');
            setWorkflowStage(data.data.workflow_stage || workflowStage);
          }
          hideFileUploaderFn();
          return;
        }

        if (data.type === 'close') {
          setIsClosed(true);
          if (data.data?.message) {
            renderMessage(data.data.message, 'system');
          }
          terminateConnection();
          return;
        }

        if (data.type === 'error') {
          renderMessage(data.message || 'Error del servidor', 'system');
        }

      } catch {
        renderMessage('Error procesando respuesta del servidor', 'system');
      }
    };
  };

  const transmitMessage = (message: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      renderMessage('Error: No conectado', 'system');
      return;
    }

    if (isClosed) {
      renderMessage('La conversación ha finalizado', 'system');
      return;
    }

    if (messages.length >= MAX_MESSAGES) {
      renderMessage('Límite de mensajes alcanzado', 'system');
      terminateConnection();
      return;
    }

    ws.send(JSON.stringify({ message }));
    renderMessage(message, 'user');
    setInputValue('');
  };

  const uploadCV = async (file: File) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      renderMessage('Error: No hay conexión WebSocket', 'system');
      return;
    }

    try {
      renderMessage('Procesando CV...', 'system');

      const reader = new FileReader();

      reader.onload = () => {
        const base64Content = (reader.result as string).split(',')[1];

        ws.send(JSON.stringify({
          type: 'cv_upload',
          file_content: base64Content,
          file_name: file.name
        }));
      };

      reader.onerror = () => {
        renderMessage('Error al leer el archivo', 'system');
      };

      reader.readAsDataURL(file);
    } catch (error) {
      renderMessage(`Error: ${error}`, 'system');
    }
  };

  const validateAndSetFile = (file: File | null) => {
    if (!file) return;

    if (file.type !== 'application/pdf') {
      renderMessage('Solo se aceptan archivos PDF.', 'system');
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      renderMessage('El archivo excede el máximo permitido (5MB).', 'system');
      return;
    }

    setPendingFile(file);
  };

  const handleToggle = () => {
    const willOpen = !isOpen;
    
    if (willOpen && messages.length === 0) {
      setTimeout(() => {
        renderMessage('¡Hola! 👋 Bienvenido al proceso de selección. Estoy aquí para ayudarte a encontrar tu próximo empleo. ¿Cuál es tu nombre completo?', 'assistant');
      }, 500);
    }
    
    if (isClosed) {
      if (confirm('La conversación anterior ha finalizado. ¿Deseas iniciar una nueva?')) {
        sessionIdRef.current = null;
        setIsClosed(false);
        setMessages([]);
        setInputValue('Escribe tu mensaje...');
        setCurrentTest(0);
        setCurrentQuestion(0);
        hideFileUploaderFn();
      } else {
        return;
      }
    }

    setIsOpen(!isOpen);
    setShowNotification(false);

    if (!isClosed && (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN)) {
      connectWebSocket();
    }
  };

  const handleSend = () => {
    if (inputValue.trim()) {
      transmitMessage(inputValue.trim());
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleUpload = () => {
    if (pendingFile) {
      uploadCV(pendingFile);
    }
  };

  const handleFileRemove = () => {
    setPendingFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files?.[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const questionsPerTest = 5;
  const totalQuestions = questionsPerTest * 2;
  const completed = (currentTest - 1) * questionsPerTest + (currentQuestion - 1);
  const progressPercent = currentTest > 0 ? Math.round((completed / totalQuestions) * 100) : 0;

  return (
    <div id="chatWidget" className={className}>
      <button
        id="chatToggle"
        className={`chat-toggle ${showNotification ? 'has-notification' : ''}`}
        onClick={handleToggle}
        aria-label="Abrir chat"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
        {showNotification && <span className="notification-badge">1</span>}
      </button>

      <div id="chatWindow" className={`chat-window ${isOpen ? '' : 'hidden'}`}>
        <div className="chat-header">
          <div className="header-info">
            <div className="avatar-header">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <div>
              <h3>Proceso de Selección</h3>
              <div className="chat-status">
                <span className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}></span>
                <span className="status-text">
                  {isConnecting ? 'Conectando...' : isConnected ? 'En línea' : isClosed ? 'Finalizado' : 'Desconectado'}
                </span>
              </div>
            </div>
          </div>
          <button id="chatClose" className="close-btn" onClick={() => setIsOpen(false)} aria-label="Cerrar chat">×</button>
        </div>

        {currentTest > 0 && (
          <div id="progressBar" className="progress-container">
            <div className="progress-info">
              <span id="progressLabel" className="progress-label">Test {currentTest}</span>
              <span id="progressCount" className="progress-count">{currentQuestion}/{questionsPerTest}</span>
            </div>
            <div className="progress-track">
              <div id="progressFill" className="progress-fill" style={{ width: `${progressPercent}%` }}></div>
            </div>
          </div>
        )}

        <div id="chatMessages" className="chat-messages">
          {messages.map((msg, idx) => (
            <div key={idx} className={`message-wrapper ${msg.role === 'assistant' ? 'assistant-wrapper' : msg.role === 'user' ? 'user-wrapper' : ''}`}>
              {(msg.role === 'assistant' || msg.role === 'user') && (
                <div className="message-avatar">
                  {msg.role === 'assistant' ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                      <circle cx="12" cy="7" r="4"/>
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 6v6l4 2"/>
                    </svg>
                  )}
                </div>
              )}
              <div className={`message ${msg.role}-message`}>{msg.text}</div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {showFileUploader && (
          <div id="fileUploadArea" className="file-upload-area">
            <label id="fileDropZone" className="file-drop-zone" onDragOver={handleDragOver} onDrop={handleDrop}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <span className="drop-text">Arrastra tu CV aquí o haz clic</span>
              <span className="drop-subtext">Solo PDF, máximo 5MB</span>
              <input
                type="file"
                id="fileInput"
                ref={fileInputRef}
                accept=".pdf"
                className="file-input-hidden"
                onChange={handleFileChange}
              />
            </label>
            {pendingFile && (
              <div id="filePreview" className="file-preview">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
                <span id="fileName" className="file-name">{pendingFile.name}</span>
                <button id="fileRemove" className="file-remove" onClick={handleFileRemove} aria-label="Remover archivo">×</button>
              </div>
            )}
            {pendingFile && (
              <button id="uploadButton" className="upload-button" onClick={handleUpload}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                Enviar CV
              </button>
            )}
          </div>
        )}

        <div id="chatInputArea" className={`chat-form ${showFileUploader ? 'hidden' : ''}`}>
          <input
            type="text"
            id="chatInput"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={isClosed ? 'Conversación finalizada' : 'Escribe tu mensaje...'}
            disabled={!isConnected || isClosed}
            aria-label="Mensaje de chat"
          />
          <button type="button" id="sendButton" onClick={handleSend} disabled={!isConnected || isClosed || !inputValue.trim()} aria-label="Enviar mensaje">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
