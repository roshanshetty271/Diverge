import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";

interface Props { children: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-void flex flex-col items-center justify-center px-6 text-center">
          <p className="font-display text-lg text-ivory-dim italic">&ldquo;The cycle is broken.&rdquo;</p>
          <p className="text-ivory text-sm mt-4">Something unexpected happened.</p>
          <p className="text-ivory-faint text-xs mt-1 max-w-sm">{this.state.error?.message || "An unknown error occurred."}</p>
          <button onClick={() => { this.setState({ hasError: false, error: null }); window.location.href = "/"; }}
            className="mt-6 px-6 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-all duration-200 hover:shadow-[0_0_16px_rgba(212,168,67,0.1)]">
            Go home
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
