import {
  Bot,
  Lightbulb,
  LoaderCircle,
  MessageCircleQuestion,
  Send,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  text: "Hi! I am your GAINT Learning Assistant. Ask me to explain the current task, give a small hint, understand an error, run the project or submit from VS Code.",
};

const quickQuestions = [
  {
    icon: MessageCircleQuestion,
    label: "Explain this task",
    question: "Explain my current task in simple steps.",
  },
  {
    icon: Lightbulb,
    label: "Give one hint",
    question: "Give me one conceptual hint to start this task.",
  },
  {
    icon: ShieldCheck,
    label: "How to submit?",
    question: "How do I test and submit this task from VS Code?",
  },
];

export default function SupportBot({ taskTitle = "Current task" }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([welcomeMessage]);
  const [loading, setLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [remaining, setRemaining] = useState(null);
  const [provider, setProvider] = useState("safe-local");
  const endRef = useRef(null);

  useEffect(() => {
    if (!open || historyLoaded) return;
    let active = true;
    api("/student/ai/chat/history")
      .then((data) => {
        if (!active) return;
        setMessages(
          data.messages.length
            ? [welcomeMessage, ...data.messages]
            : [welcomeMessage],
        );
        setRemaining(data.remaining_messages);
        setProvider(data.provider);
        setHistoryLoaded(true);
      })
      .catch((error) => {
        if (!active) return;
        setMessages([
          welcomeMessage,
          { id: "load-error", role: "assistant error", text: error.message },
        ]);
        setHistoryLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [open, historyLoaded]);

  useEffect(() => {
    setMessages([welcomeMessage]);
    setHistoryLoaded(false);
  }, [taskTitle]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const ask = async (question) => {
    const cleaned = question.trim();
    if (!cleaned || loading || remaining === 0) return;
    const optimistic = {
      id: `pending-${Date.now()}`,
      role: "user",
      text: cleaned,
    };
    setMessages((items) => [...items, optimistic]);
    setInput("");
    setLoading(true);
    try {
      const result = await api("/student/ai/chat", {
        method: "POST",
        body: JSON.stringify({ message: cleaned }),
      });
      setMessages((items) => [...items, result.message]);
      setRemaining(result.remaining_messages);
      setProvider(result.provider);
    } catch (error) {
      setMessages((items) => [
        ...items,
        {
          id: `error-${Date.now()}`,
          role: "assistant error",
          text: error.message,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const send = (event) => {
    event.preventDefault();
    ask(input);
  };

  const clearHistory = async () => {
    if (!window.confirm("Clear the chat for this task?")) return;
    setLoading(true);
    try {
      await api("/student/ai/chat/history", { method: "DELETE" });
      setMessages([welcomeMessage]);
      setHistoryLoaded(false);
    } catch (error) {
      setMessages((items) => [
        ...items,
        {
          id: `clear-error-${Date.now()}`,
          role: "assistant error",
          text: error.message,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        className={`bot-toggle ${open ? "active" : ""}`}
        onClick={() => setOpen(!open)}
        aria-label="Open GAINT Learning Assistant"
      >
        <Bot />
        <span>Ask GAINT AI</span>
      </button>
      {open && (
        <section className="bot-panel" aria-label="GAINT Learning Assistant">
          <header className="bot-header">
            <div className="bot-brand">
              <span className="bot-avatar">
                <Bot size={20} />
              </span>
              <div>
                <strong>GAINT Learning Assistant</strong>
                <small>
                  <i className={provider === "openai" ? "live" : ""} />{" "}
                  {provider === "openai" ? "Live AI" : "Safe local assistant"}
                </small>
              </div>
            </div>
            <div className="bot-header-actions">
              <button
                onClick={clearHistory}
                disabled={loading}
                title="Clear current-task chat"
              >
                <Trash2 size={17} />
              </button>
              <button onClick={() => setOpen(false)} title="Close assistant">
                <X size={19} />
              </button>
            </div>
          </header>
          <div className="bot-task-context">
            <span>Helping with</span>
            <strong>{taskTitle}</strong>
            <small>Hints only — no full answers or hidden tests</small>
          </div>
          <div className="bot-messages" aria-live="polite">
            {messages.map((message) => (
              <div key={message.id} className={`bot-message ${message.role}`}>
                {message.role.startsWith("assistant") && (
                  <span>
                    <Bot size={15} />
                  </span>
                )}
                <p>{message.text}</p>
              </div>
            ))}
            {loading && (
              <div className="bot-message assistant typing">
                <span>
                  <Bot size={15} />
                </span>
                <p>
                  <LoaderCircle size={17} className="spin-icon" /> Thinking…
                </p>
              </div>
            )}
            <div ref={endRef} />
          </div>
          {messages.length <= 1 && (
            <div className="bot-quick-actions">
              {quickQuestions.map(({ icon: Icon, label, question }) => (
                <button
                  key={label}
                  onClick={() => ask(question)}
                  disabled={loading}
                >
                  <Icon size={14} /> {label}
                </button>
              ))}
            </div>
          )}
          <form className="bot-compose" onSubmit={send}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  ask(input);
                }
              }}
              maxLength={500}
              rows={2}
              placeholder="Ask about the task or paste an error…"
              disabled={loading || remaining === 0}
            />
            <button
              type="submit"
              disabled={loading || !input.trim() || remaining === 0}
              aria-label="Send message"
            >
              <Send size={18} />
            </button>
          </form>
          <footer>
            <span>
              {remaining === null
                ? "Loading limit…"
                : `${remaining} messages remaining`}
            </span>
            <span>Judge0 controls pass/fail</span>
          </footer>
        </section>
      )}
    </>
  );
}
